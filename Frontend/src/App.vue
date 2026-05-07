<template>
  <div class="app-container">
    <GraphView />
  </div>
</template>

<script setup>
import GraphView from "./components/GraphView.vue";
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  background: #0f172a;
}

.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
</style>