"""
service_call_detector.py — Automatic detection of inter-service calls
(HTTP/REST and message-queue pub/sub) from raw source text.

No LLM. Deterministic, language-agnostic regex/keyword scanning — rather than
parsing every HTTP-client/MQ-library's exact call syntax per language, this
looks for a known service's hostname appearing near an HTTP-call keyword, and
correlates message-queue publish/consume calls by their shared queue name.
Static analysis only: like the rest of this codebase's detectors, it can miss
dynamic/templated URLs and can't verify a call ever executes at runtime.
"""

import re
from dataclasses import dataclass
from typing import Dict, List

HTTP_CALL_KEYWORDS = [
    "axios", "fetch(", "requests.get", "requests.post", "requests.put", "requests.delete",
    "requests.patch", "httpx.", "resttemplate", "webclient", "http.get(", "http.post(",
    "http.newrequest", "reqwest::", "httpclient", "urlopen", "xmlhttprequest",
]

MQ_PUBLISH_KEYWORDS = [
    "channel.publish", "channel.basic_publish", "channel.sendtoqueue",
    "producer.send", "kafkaproducer.send", "basicpublish",
]
MQ_CONSUME_KEYWORDS = [
    "channel.consume", "channel.basic_consume", "consumer.subscribe",
    "kafkaconsumer.subscribe", "@rabbitlistener", "@kafkalistener",
]

_STRING_LITERAL_RE = re.compile(r"""['"`]([\w.\-]{3,64})['"`]""")

# Ignore hostname variants too short/common to be a reliable signal on their own.
_MIN_VARIANT_LEN = 4


@dataclass
class DetectedConnection:
    from_service: str
    to_service: str
    type: str  # "REST" | "MessageQueue"
    label: str
    evidence_file: str
    evidence_line: int
    confidence: float

    def to_dict(self) -> dict:
        return {
            "from": self.from_service,
            "to": self.to_service,
            "type": self.type,
            "label": self.label,
            "unresolved": False,
            "detected": True,
            "evidence": f"{self.evidence_file}:{self.evidence_line}",
            "confidence": self.confidence,
        }


def _service_hostname_variants(service_id: str) -> List[str]:
    """book_service -> [book_service, book-service, bookservice]"""
    base = service_id.strip()
    variants = {base, base.replace("_", "-"), base.replace("-", "_"), base.replace("_", "").replace("-", "")}
    return [v for v in variants if len(v) >= _MIN_VARIANT_LEN]


def detect_http_calls(services: List[dict]) -> List[DetectedConnection]:
    hostname_to_service: Dict[str, str] = {}
    for svc in services:
        for variant in _service_hostname_variants(svc["service_id"]):
            hostname_to_service[variant.lower()] = svc["service_id"]

    connections: List[DetectedConnection] = []
    seen_pairs = set()
    for svc in services:
        src_id = svc["service_id"]
        for file_info in svc.get("files", []):
            content = file_info.get("content") or ""
            path = file_info.get("path", "")
            for line_no, line in enumerate(content.split("\n"), start=1):
                lower = line.lower()
                has_http_keyword = any(kw in lower for kw in HTTP_CALL_KEYWORDS)
                has_url_scheme = "http://" in lower or "https://" in lower
                if not (has_http_keyword or has_url_scheme):
                    continue
                for hostname, target_id in hostname_to_service.items():
                    if target_id == src_id or hostname not in lower:
                        continue
                    pair_key = (src_id, target_id)
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    connections.append(DetectedConnection(
                        from_service=src_id,
                        to_service=target_id,
                        type="REST",
                        label=f"HTTP call to {target_id}",
                        evidence_file=path,
                        evidence_line=line_no,
                        confidence=0.85 if (has_http_keyword and has_url_scheme) else 0.6,
                    ))
    return connections


def _scan_mq_keywords(services: List[dict], keywords: List[str]) -> Dict[str, List[tuple]]:
    """Return {queue_name: [(service_id, file, line), ...]} for lines matching `keywords`."""
    hits: Dict[str, List[tuple]] = {}
    for svc in services:
        src_id = svc["service_id"]
        for file_info in svc.get("files", []):
            content = file_info.get("content") or ""
            path = file_info.get("path", "")
            for line_no, line in enumerate(content.split("\n"), start=1):
                lower = line.lower()
                if not any(kw in lower for kw in keywords):
                    continue
                match = _STRING_LITERAL_RE.search(line)
                if not match:
                    continue
                queue_name = match.group(1)
                hits.setdefault(queue_name, []).append((src_id, path, line_no))
    return hits


def detect_message_queue_calls(services: List[dict]) -> List[DetectedConnection]:
    publishers = _scan_mq_keywords(services, MQ_PUBLISH_KEYWORDS)
    consumers = _scan_mq_keywords(services, MQ_CONSUME_KEYWORDS)

    connections: List[DetectedConnection] = []
    seen_pairs = set()
    for queue_name, pub_entries in publishers.items():
        for pub_service, pub_file, pub_line in pub_entries:
            for cons_service, _cons_file, _cons_line in consumers.get(queue_name, []):
                if cons_service == pub_service:
                    continue
                pair_key = (pub_service, cons_service, queue_name)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                connections.append(DetectedConnection(
                    from_service=pub_service,
                    to_service=cons_service,
                    type="MessageQueue",
                    label=queue_name,
                    evidence_file=pub_file,
                    evidence_line=pub_line,
                    confidence=0.75,
                ))
    return connections


def detect_service_connections(services: List[dict]) -> List[dict]:
    """services: [{"service_id": str, "files": [{"path": str, "content": str}, ...]}, ...]

    Returns connection dicts in the same shape the (now removed) manual
    service-map.json parser produced: {"from", "to", "type", "label",
    "unresolved"} — plus additive "detected"/"evidence"/"confidence" keys.
    """
    connections = detect_http_calls(services) + detect_message_queue_calls(services)
    return [c.to_dict() for c in connections]
