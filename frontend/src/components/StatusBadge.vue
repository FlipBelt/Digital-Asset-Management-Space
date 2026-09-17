<script setup lang="ts">
withDefaults(
  defineProps<{
    tone?: "success" | "warning" | "neutral" | "default";
  }>(),
  { tone: "neutral" },
);
</script>

<template><span class="status-badge" :class="`tone-${tone}`"><slot /></span></template>
