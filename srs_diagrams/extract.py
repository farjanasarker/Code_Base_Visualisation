import re, os, json

with open(r"f:\spl3\SRS.md", encoding="utf-8") as f:
    content = f.read()

# Find all mermaid blocks along with the nearest preceding heading (### or ##) as title
pattern = re.compile(r"```mermaid\n(.*?)\n```", re.DOTALL)
heading_pattern = re.compile(r"^(#{2,4})\s+(.*)$", re.MULTILINE)

headings = [(m.start(), m.group(2).strip()) for m in heading_pattern.finditer(content)]

diagrams = []
for i, m in enumerate(pattern.finditer(content)):
    start = m.start()
    code = m.group(1)
    # find nearest heading before this block
    title = None
    for pos, text in headings:
        if pos < start:
            title = text
        else:
            break
    diagrams.append({"index": i, "title": title, "code": code})

os.makedirs(r"f:\spl3\srs_diagrams", exist_ok=True)
for d in diagrams:
    fname = f"diagram_{d['index']:02d}.mmd"
    with open(os.path.join(r"f:\spl3\srs_diagrams", fname), "w", encoding="utf-8") as f:
        f.write(d["code"])

with open(r"f:\spl3\srs_diagrams\manifest.json", "w", encoding="utf-8") as f:
    json.dump(diagrams, f, indent=2)

print(f"Extracted {len(diagrams)} diagrams")
for d in diagrams:
    print(d['index'], '-', d['title'])
