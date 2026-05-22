<script setup>
import { Handle, Position } from "@vue-flow/core";

defineProps({
  data: {
    type: Object,
    default: () => ({})
  }
});
</script>

<template>
  <div
    class="fn-card"
    :class="[data.nodeType || 'function', { 'fn-root': data.isRoot }]"
    :title="data.fullLabel || data.label"
  >
    <Handle type="target" :position="Position.Top" class="fn-handle" />
    <Handle type="source" :position="Position.Bottom" class="fn-handle" />

    <div class="fn-badge">
      <span v-if="data.nodeType === 'module'">M</span>
      <span v-else-if="data.nodeType === 'rootfiles'">RF</span>
      <span v-else-if="data.nodeType === 'file'">F</span>
      <span v-else-if="data.nodeType === 'chunk'">C</span>
      <span v-else>f</span>
    </div>

    <div class="fn-body">
      <div class="fn-name">{{ data.label }}</div>
      <div class="fn-sub">{{ data.language || data.nodeType }}</div>
    </div>
  </div>
</template>

<style scoped>
/* ── Base card — matches the image style ─────────── */
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
  transition: box-shadow 140ms ease, transform 140ms ease;
  /* default = function: lavender */
  background: #eef2ff;
  border: 1.5px solid #c7d2fe;
  box-shadow: 0 1px 4px rgba(99,102,241,0.10);
}

/* type variants */
.fn-card.module {
  background: #eff6ff;
  border-color: #bfdbfe;
  box-shadow: 0 1px 4px rgba(59,130,246,0.10);
}
.fn-card.file {
  background: #fffbeb;
  border-color: #fde68a;
  box-shadow: 0 1px 4px rgba(245,158,11,0.10);
}
.fn-card.chunk {
  background: #f5f3ff;
  border-color: #ddd6fe;
  box-shadow: 0 1px 4px rgba(139,92,246,0.10);
  animation: pulse-chunk 2.8s ease-in-out infinite;
}
.fn-card.fn-root {
  background: #eef2ff;
  border-color: #a5b4fc;
  box-shadow: 0 2px 10px rgba(99,102,241,0.20);
}

@keyframes pulse-chunk {
  0%, 100% { box-shadow: 0 1px 4px rgba(139,92,246,0.10); }
  50%       { box-shadow: 0 3px 14px rgba(139,92,246,0.28); }
}

.fn-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(99,102,241,0.18);
}

/* ── Circle badge (the "f" or "M" on the left) ─── */
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
  /* default purple */
  background: #6366f1;
  color: #fff;
}
.fn-card.module  .fn-badge { background: #3b82f6; font-style: normal; font-size: 11px; }
.fn-card.file    .fn-badge { background: #f59e0b; font-style: normal; font-size: 11px; }
.fn-card.chunk   .fn-badge { background: #8b5cf6; font-style: normal; font-size: 12px; }
.fn-card.rootfiles .fn-badge { background: #22c55e; font-style: normal; font-size: 14px; }

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

/* ── Handles (invisible, just connection points) ─ */
.fn-handle {
  width: 10px;
  height: 10px;
  background: transparent;
  border: 0;
}
/* style-এ যোগ করো */
.fn-card.rootfiles {
  background: #f0fdf4;
  border-color: #86efac;
  border-style: dashed;
  box-shadow: 0 1px 4px rgba(34,197,94,0.15);
}
.fn-card.rootfiles .fn-badge {
  background: #22c55e;
  font-style: normal;
  font-size: 14px;
}
</style>
