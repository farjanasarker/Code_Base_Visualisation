<template>
  <div class="prd">
    <template v-for="([role, cls], i) in roles" :key="role">
      <div class="prd-box">
        <InfoTooltip
          :text="`The &quot;${role.replace(/_/g, ' ')}&quot; participant in the ${patternName} pattern.`"
          :icon="false"
        >
          <span class="prd-role">{{ role.replace(/_/g, ' ') }}</span>
        </InfoTooltip>
        <div class="prd-class">{{ cls }}</div>
      </div>
      <div v-if="i < roles.length - 1" class="prd-arrow">↓</div>
    </template>
  </div>
</template>

<script setup>
import { computed } from "vue";
import InfoTooltip from "./InfoTooltip.vue";

defineOptions({ name: "PatternRoleDiagram" });
const props = defineProps({
  bindings: { type: Object, required: true },
  patternName: { type: String, default: "" },
});
const roles = computed(() => Object.entries(props.bindings || {}));
</script>

<style scoped>
.prd {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  margin: 8px 0;
}
.prd-box {
  width: 100%;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 6px 10px;
  text-align: center;
}
.prd-role {
  display: block;
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: #a5b4fc;
  margin-bottom: 3px;
}
.prd-class {
  font-size: 13px;
  font-family: monospace;
  color: #e2e8f0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.prd-arrow {
  font-size: 12px;
  color: #475569;
  line-height: 1;
}
</style>
