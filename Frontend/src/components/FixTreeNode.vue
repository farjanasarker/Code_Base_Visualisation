<template>
  <div class="tree-node">
    <div
      class="tree-node-row"
      :class="`tree-sev-${node.severity}`"
      @click="node.children?.length && (expanded = !expanded)"
    >
      <span class="tree-toggle" :class="{ 'tree-toggle-leaf': !node.children?.length }">
        {{ node.children?.length ? (expanded ? '▾' : '▸') : '•' }}
      </span>
      <span class="tree-node-type">{{ node.type.replace(/_/g, ' ') }}</span>
      <span class="tree-node-target">{{ node.target_name }}</span>
      <span class="tree-node-sev" :class="`sev-badge-${node.severity}`">{{ node.severity }}</span>
    </div>
    <div v-if="expanded && node.children?.length" class="tree-children">
      <FixTreeNode
        v-for="(child, i) in node.children"
        :key="`${child.smell_id}-${i}`"
        :node="child"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";

defineOptions({ name: "FixTreeNode" });
defineProps({
  node: { type: Object, required: true },
});
const expanded = ref(true);
</script>

<style scoped>
.tree-node { margin: 2px 0; }
.tree-node-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 6px;
  border-radius: 6px;
  border-left: 3px solid #475569;
  background: #1e293b;
  cursor: pointer;
  transition: background 140ms ease, transform 140ms ease;
}
.tree-node-row:hover { background: #273549; transform: translateX(1px); }
.tree-node-row:focus-visible {
  outline: 2px solid #818cf8;
  outline-offset: 1px;
}
.tree-sev-critical { border-left-color: #a855f7; background: #1a1025; }
.tree-sev-critical:hover { background: #241535; }
.tree-sev-high     { border-left-color: #ef4444; background: #1c1010; }
.tree-sev-high:hover { background: #271515; }
.tree-sev-medium   { border-left-color: #f59e0b; background: #1c1800; }
.tree-sev-medium:hover { background: #272000; }
.tree-sev-low      { border-left-color: #22c55e; background: #0f1c12; }
.tree-sev-low:hover { background: #152718; }

.tree-toggle {
  font-size: 10px;
  color: #64748b;
  width: 10px;
  flex-shrink: 0;
  text-align: center;
}
.tree-toggle-leaf { color: #334155; }

.tree-node-type {
  font-size: 11px;
  font-weight: 700;
  color: #e2e8f0;
  text-transform: capitalize;
}
.tree-node-target {
  flex: 1;
  font-size: 10px;
  color: #94a3b8;
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.tree-node-sev {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 6px;
  flex-shrink: 0;
  text-transform: uppercase;
}
.sev-badge-critical { background: #3b0764; color: #d8b4fe; }
.sev-badge-high     { background: #450a0a; color: #fca5a5; }
.sev-badge-medium   { background: #451a03; color: #fde68a; }
.sev-badge-low      { background: #052e16; color: #86efac; }

.tree-children {
  margin-left: 16px;
  padding-left: 8px;
  border-left: 1px dashed #334155;
}
@media (prefers-reduced-motion: no-preference) {
  .tree-children {
    animation: tree-children-in 160ms ease-out both;
  }
  @keyframes tree-children-in {
    from { opacity: 0; transform: translateY(-2px); }
    to   { opacity: 1; transform: translateY(0); }
  }
}
</style>
