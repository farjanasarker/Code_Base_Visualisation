<script setup>
import { Handle, Position } from "@vue-flow/core";
import { computed } from "vue";

const props = defineProps({
  data: {
    type: Object,
    default: () => ({})
  }
});

const riskTitle = computed(() => {
  const base = props.data.fullLabel || props.data.label || '';
  if (props.data.isDead) {
    const conf = props.data.deadConfidence === 'high'
      ? 'High confidence — private function with no detected callers.'
      : 'No detected callers in this codebase. May still be called dynamically, via reflection, polymorphism, or by external code.';
    return `${base}\n👻 Potentially Unreachable\n${conf}`;
  }
  if (props.data.nodeType === 'service-unresolved') {
    return `${base}\n⚠ Referenced in service-map.json but no matching folder was found.\nCheck for a typo in the service name.`;
  }
  return base;
});
</script>

<template>
  <div
    class="fn-card"
    :class="[
      data.nodeType || 'function',
      { 'fn-root': data.isRoot },
      data.riskLevel && data.riskLevel !== 'none' ? `risk-${data.riskLevel}` : '',
      { 'dead-code': data.isDead },
      data.smellSeverity && data.smellSeverity !== 'none' ? `smell-node-${data.smellSeverity}` : '',
    ]"
    :title="riskTitle"
  >
    <Handle type="target" :position="Position.Top" class="fn-handle" />
    <Handle type="source" :position="Position.Bottom" class="fn-handle" />

    <div class="fn-badge">
      <span v-if="data.nodeType === 'service'">S</span>
      <span v-else-if="data.nodeType === 'service-unresolved'">!</span>
      <span v-else-if="data.nodeType === 'module'">M</span>
      <span v-else-if="data.nodeType === 'rootfiles'">RF</span>
      <span v-else-if="data.nodeType === 'file'">F</span>
      <span v-else-if="data.nodeType === 'chunk'">C</span>
      <span v-else>f</span>
    </div>

    <div class="fn-body">
      <div class="fn-name">{{ data.label }}</div>
      <div v-if="data.nodeType === 'chunk'" class="fn-sub chunk-sub">
        {{ data.fnCount > 0 ? data.fnCount + ' functions' : (data.language || 'chunk') }}
      </div>
      <div v-else-if="data.nodeType === 'function' && data.className" class="fn-sub fn-class">{{ data.className }}</div>
      <div v-else-if="data.nodeType === 'service' && data.className" class="fn-sub fn-class">{{ data.className }}</div>
      <div v-else-if="data.nodeType === 'service-unresolved'" class="fn-sub">not found</div>
      <div v-else class="fn-sub">{{ data.language || data.nodeType }}</div>
    </div>

    <!-- Chunk expand hint -->
    <div v-if="data.nodeType === 'chunk'" class="chunk-expand-hint" title="Click to expand functions">▶</div>

    <!-- Risk counter badge: only on function nodes that have callers -->
    <div
      v-if="data.nodeType === 'function' && data.fanIn > 0"
      class="risk-dot"
      :class="`risk-dot-${data.riskLevel || 'none'}`"
    >{{ data.fanIn }}</div>

    <!-- Potentially unreachable ghost badge -->
    <div
      v-if="data.isDead && data.nodeType === 'function'"
      class="dead-badge"
      :class="data.deadConfidence === 'high' ? 'dead-badge-high' : 'dead-badge-medium'"
      :title="data.deadConfidence === 'high' ? 'High confidence: private, no callers' : 'Medium confidence: no detected callers'"
    >👻</div>
  </div>
</template>

<style scoped>
/* ── Base card ─────────────────────────────────────── */
.fn-card {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 10px;
  position: relative;
  overflow: visible;
  cursor: pointer;
  transition: box-shadow 140ms ease, transform 140ms ease, border-color 140ms ease;
  background: #eef2ff;
  border: 1.5px solid #c7d2fe;
  box-shadow: 0 1px 4px rgba(99,102,241,0.10);
}

/* type variants */
.fn-card.module    { background: #eff6ff; border-color: #bfdbfe; box-shadow: 0 1px 4px rgba(59,130,246,0.10); }
.fn-card.file      { background: #fffbeb; border-color: #fde68a; box-shadow: 0 1px 4px rgba(245,158,11,0.10); }
.fn-card.chunk     { background: #f5f3ff; border-color: #ddd6fe; box-shadow: 0 1px 4px rgba(139,92,246,0.10); animation: pulse-chunk 2.8s ease-in-out infinite; }
.fn-card.fn-root   { background: #eef2ff; border-color: #a5b4fc; box-shadow: 0 2px 10px rgba(99,102,241,0.20); }
.fn-card.rootfiles { background: #f0fdf4; border-color: #86efac; border-style: dashed; box-shadow: 0 1px 4px rgba(34,197,94,0.15); }
.fn-card.service   { background: #f0fdfa; border-color: #5eead4; box-shadow: 0 1px 4px rgba(20,184,166,0.15); }
.fn-card.service-unresolved { background: #fef2f2; border-color: #fca5a5; border-style: dashed; box-shadow: 0 1px 4px rgba(239,68,68,0.15); }

/* ── Risk level overrides (only for function nodes) ── */
.fn-card.function.risk-high   { border-color: #ef4444; border-width: 2px; box-shadow: 0 0 0 3px rgba(239,68,68,0.18); }
.fn-card.function.risk-medium { border-color: #f59e0b; border-width: 2px; box-shadow: 0 0 0 3px rgba(245,158,11,0.15); }
.fn-card.function.risk-low    { border-color: #22c55e; border-width: 2px; box-shadow: 0 0 0 3px rgba(34,197,94,0.12); }

@keyframes pulse-chunk {
  0%, 100% { box-shadow: 0 1px 4px rgba(139,92,246,0.10); }
  50%       { box-shadow: 0 3px 14px rgba(139,92,246,0.28); }
}

.fn-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(99,102,241,0.18);
}

/* ── Circle badge ─────────────────────────────────── */
.fn-badge {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  font-style: italic;
  background: #6366f1;
  color: #fff;
}
.fn-card.module    .fn-badge { background: #3b82f6; font-style: normal; font-size: 11px; }
.fn-card.file      .fn-badge { background: #f59e0b; font-style: normal; font-size: 11px; }
.fn-card.chunk     .fn-badge { background: #8b5cf6; font-style: normal; font-size: 12px; }
.fn-card.rootfiles .fn-badge { background: #22c55e; font-style: normal; font-size: 14px; }
.fn-card.service   .fn-badge { background: #14b8a6; font-style: normal; font-size: 11px; }
.fn-card.service-unresolved .fn-badge { background: #ef4444; font-style: normal; font-size: 14px; }

/* ── Text body ───────────────────────────────────── */
.fn-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.fn-name {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.2;
}
.fn-sub {
  font-size: 11px;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.2;
}

/* ── Chunk-specific ─────────────────────────────── */
.chunk-sub {
  color: #8b5cf6;
  font-weight: 600;
}
.fn-class {
  color: #6366f1;
  font-weight: 600;
}
.chunk-expand-hint {
  font-size: 10px;
  color: #8b5cf6;
  flex-shrink: 0;
  opacity: 0.7;
  transition: opacity 140ms, transform 140ms;
}
.fn-card.chunk:hover .chunk-expand-hint {
  opacity: 1;
  transform: translateX(2px);
}

/* ── Risk counter badge (top-right corner) ───────── */
.risk-dot {
  position: absolute;
  top: -7px;
  right: -7px;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: 9px;
  font-size: 10px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  border: 1.5px solid #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.18);
  z-index: 10;
}
.risk-dot-high   { background: #ef4444; }
.risk-dot-medium { background: #f59e0b; }
.risk-dot-low    { background: #22c55e; }
.risk-dot-none   { background: #94a3b8; }

/* ── Smell severity glow (function nodes) ────────── */
.fn-card.smell-node-critical { border-color: #7c3aed; box-shadow: 0 0 0 3px rgba(124,58,237,0.22), inset 0 0 8px rgba(124,58,237,0.08); }
.fn-card.smell-node-high     { border-color: #ef4444; box-shadow: 0 0 0 2px rgba(239,68,68,0.18); }
.fn-card.smell-node-medium   { border-color: #f59e0b; box-shadow: 0 0 0 2px rgba(245,158,11,0.15); }
.fn-card.smell-node-low      { border-color: #84cc16; box-shadow: 0 0 0 1px rgba(132,204,22,0.15); }

/* ── Dead code styling ───────────────────────────── */
.fn-card.dead-code {
  opacity: 0.55;
  border-style: dashed;
  border-color: #94a3b8;
  background: #f8fafc;
  box-shadow: none;
}
.fn-card.dead-code .fn-name {
  text-decoration: line-through;
  color: #94a3b8;
}
.fn-card.dead-code .fn-badge {
  background: #94a3b8;
}
.fn-card.dead-code:hover {
  opacity: 0.8;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.dead-badge {
  position: absolute;
  top: -7px;
  left: -7px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #64748b;
  color: #fff;
  border: 1.5px solid #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.18);
  z-index: 10;
}
.dead-badge-high   { background: #475569; }
.dead-badge-medium { background: #94a3b8; }

/* ── Handles ─────────────────────────────────────── */
.fn-handle {
  width: 10px;
  height: 10px;
  background: transparent;
  border: 0;
}
</style>
