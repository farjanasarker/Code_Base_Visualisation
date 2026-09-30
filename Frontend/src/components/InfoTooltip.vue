<template>
  <span class="info-tooltip" tabindex="0">
    <span class="info-tooltip-trigger">
      <slot>{{ icon ? 'ⓘ' : '' }}</slot>
    </span>
    <span class="info-tooltip-bubble" role="tooltip">{{ text }}</span>
  </span>
</template>

<script setup>
defineOptions({ name: "InfoTooltip" });
defineProps({
  text: { type: String, required: true },
  icon: { type: Boolean, default: true },
});
</script>

<style scoped>
.info-tooltip {
  position: relative;
  display: inline-flex;
  align-items: center;
  outline: none;
}
.info-tooltip-trigger {
  display: inline-flex;
  align-items: center;
  cursor: help;
}
.info-tooltip-bubble {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%) translateY(2px);
  width: max-content;
  max-width: 220px;
  background: #0f172a;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 10.5px;
  font-weight: 400;
  line-height: 1.45;
  text-transform: none;
  white-space: normal;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition: opacity 0.15s ease, transform 0.15s ease, visibility 0.15s;
  z-index: 50;
}
.info-tooltip:hover .info-tooltip-bubble,
.info-tooltip:focus-within .info-tooltip-bubble {
  opacity: 1;
  visibility: visible;
  transform: translateX(-50%) translateY(0);
}
@media (prefers-reduced-motion: reduce) {
  .info-tooltip-bubble {
    transition: opacity 0.12s ease;
    transform: translateX(-50%);
  }
  .info-tooltip:hover .info-tooltip-bubble,
  .info-tooltip:focus-within .info-tooltip-bubble {
    transform: translateX(-50%);
  }
}
</style>
