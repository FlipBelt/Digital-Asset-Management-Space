<script setup lang="ts">
import { nextTick } from "vue";
defineProps<{ modelValue: string; label: string; idPrefix: string; tabs: { value: string; label: string; count?: number }[] }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
async function move(event: KeyboardEvent, index: number, tabs: { value: string }[]) {
  const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1
    : event.key === "ArrowRight" ? (index + 1) % tabs.length
    : event.key === "ArrowLeft" ? (index - 1 + tabs.length) % tabs.length : -1;
  if (next < 0) return;
  event.preventDefault();
  const list = (event.currentTarget as HTMLElement).parentElement;
  emit("update:modelValue", tabs[next]!.value);
  await nextTick();
  (list?.querySelectorAll<HTMLButtonElement>("[role=tab]")[next])?.focus();
}
</script>
<template>
  <div class="fusion-tabs workspace-tabs" role="tablist" :aria-label="label">
    <button v-for="(tab, index) in tabs" :id="`${idPrefix}-${tab.value}`" :key="tab.value" type="button"
      role="tab" :aria-selected="modelValue === tab.value" :aria-controls="`${idPrefix}-panel`"
      :tabindex="modelValue === tab.value ? 0 : -1" :class="{ active: modelValue === tab.value }"
      @click="emit('update:modelValue', tab.value)" @keydown="move($event, index, tabs)">
      {{ tab.label }}<span v-if="tab.count !== undefined" class="workspace-tab-count">{{ tab.count }}</span>
    </button>
  </div>
</template>
