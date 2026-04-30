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
    class="function-node"
    :class="{ root: data.isRoot, module: data.nodeType === 'module', file: data.nodeType === 'file', function: data.nodeType === 'function', chunk: data.nodeType === 'chunk' }"
    :title="data.fullLabel || data.label"
  >
    <Handle type="target" :position="Position.Left" class="node-handle" />
    <Handle type="source" :position="Position.Right" class="node-handle" />

    <div class="function-node-label">
      {{ data.label }}
    </div>

    <div v-if="data.nodeType" class="function-node-kind">
      {{ data.nodeType }}
    </div>

    <div v-if="data.callCount > 0" class="function-node-count">
      {{ data.callCount }}
    </div>
  </div>
</template>

<style scoped>
.function-node {
  width: 100%;
  height: 100%;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: visible;
  color: #fff;
  background: #3f8f7a;
  border: 2px solid #2f6f61;
  box-shadow: 0 8px 18px rgba(63, 143, 122, 0.3);
  text-align: center;
}

.function-node.root {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: 3px solid #667eea;
  box-shadow: 0 10px 20px rgba(102, 126, 234, 0.35);
}

.function-node.module {
  background: linear-gradient(135deg, #1f8a70 0%, #146c94 100%);
  border: 3px solid #1f8a70;
  box-shadow: 0 10px 20px rgba(31, 138, 112, 0.28);
}

.function-node.chunk {
  background: linear-gradient(135deg, #7c3aed 0%, #5b21b6 100%);
  border: 3px solid #6d28d9;
  box-shadow: 0 12px 26px rgba(99, 102, 241, 0.18);
  transform-origin: center;
  animation: pulse 2.6s ease-in-out infinite;
}

@keyframes pulse {
  0% { box-shadow: 0 6px 14px rgba(124,58,237,0.12); transform: scale(1); }
  50% { box-shadow: 0 18px 40px rgba(124,58,237,0.18); transform: scale(1.04); }
  100% { box-shadow: 0 6px 14px rgba(124,58,237,0.12); transform: scale(1); }
}

.function-node.file {
  background: linear-gradient(135deg, #d97706 0%, #b45309 100%);
  border: 3px solid #d97706;
  box-shadow: 0 10px 20px rgba(217, 119, 6, 0.28);
}

.function-node.function {
  background: #3f8f7a;
  border: 2px solid #2f6f61;
}

.function-node-label {
  max-width: 90%;
  padding: 0 4px;
  line-height: 1.05;
  font-weight: 700;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.function-node:hover {
  transform: scale(1.06);
  transition: transform 160ms ease, box-shadow 200ms ease;
}

.function-node-count {
  position: absolute;
  right: -4px;
  bottom: -4px;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: 999px;
  background: #ffffff;
  color: #184f43;
  border: 1px solid rgba(24, 79, 67, 0.25);
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
}

.function-node-kind {
  position: absolute;
  left: 50%;
  bottom: -14px;
  transform: translateX(-50%);
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  color: #334155;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
}

.node-handle {
  width: 8px;
  height: 8px;
  background: transparent;
  border: 0;
}
</style>