<script setup>
import { computed } from "vue";
import { BaseEdge, EdgeLabelRenderer } from "@vue-flow/core";

const props = defineProps({
  id: { type: String, required: true },
  sourceX: { type: Number, required: true },
  sourceY: { type: Number, required: true },
  targetX: { type: Number, required: true },
  targetY: { type: Number, required: true },
  markerEnd: { type: [String, Object], default: undefined },
  style: { type: Object, default: () => ({}) },
  label: { type: [String, Number], default: "" }
});

const LANE_PADDING = 90;
const TARGET_APPROACH_GAP = 26;

const laneY = computed(() => Math.max(props.sourceY, props.targetY) + LANE_PADDING);
const preTargetX = computed(() => props.targetX + TARGET_APPROACH_GAP);

const edgePath = computed(
  () =>
    `M ${props.sourceX},${props.sourceY} L ${props.sourceX},${laneY.value} L ${preTargetX.value},${laneY.value} L ${preTargetX.value},${props.targetY} L ${props.targetX},${props.targetY}`
);

const labelX = computed(() => (props.sourceX + preTargetX.value) / 2);
const labelY = computed(() => laneY.value - 10);
</script>

<template>
  <BaseEdge :id="id" :path="edgePath" :marker-end="markerEnd" :style="style" />

  <EdgeLabelRenderer>
    <div
      v-if="label"
      class="back-edge-label nodrag nopan"
      :style="{
        transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`
      }"
    >
      {{ label }}
    </div>
  </EdgeLabelRenderer>
</template>

<style scoped>
.back-edge-label {
  position: absolute;
  background: #ffffff;
  color: #184f43;
  border: 1px solid rgba(24, 79, 67, 0.18);
  border-radius: 6px;
  padding: 2px 6px;
  font-size: 10px;
  font-weight: 600;
  pointer-events: none;
  white-space: nowrap;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
}
</style>
