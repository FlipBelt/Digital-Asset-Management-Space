<script setup lang="ts">
import { X } from "lucide-vue-next";
import { onMounted, onUnmounted, ref } from "vue";

const props = defineProps<{ title: string; description?: string; wide?: boolean; trapFocus?: boolean }>();
defineEmits<{ close: [] }>();
const panel = ref<HTMLElement | null>(null);
let previousFocus: HTMLElement | null = null;
function trapTab(event: KeyboardEvent) {
  if (!props.trapFocus || event.key !== "Tab") return;
  const controls = Array.from(panel.value?.querySelectorAll<HTMLElement>(
    'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
  ) ?? []).filter(item => item.getClientRects().length);
  const first = controls[0];
  const last = controls.at(-1);
  if (!first || !last) { event.preventDefault(); panel.value?.focus(); return; }
  if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.value)) {
    event.preventDefault(); last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault(); first.focus();
  }
}
onMounted(() => {
  if (!props.trapFocus) return;
  previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  panel.value?.querySelector<HTMLElement>("button")?.focus();
});
onUnmounted(() => { if (props.trapFocus && previousFocus?.isConnected) previousFocus.focus(); });
</script>

<template>
  <div class="modal-backdrop" role="presentation" @mousedown.self="$emit('close')">
    <section ref="panel" class="modal-panel" :class="{ wide }" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1" @keydown="trapTab" @keydown.esc="props.trapFocus && $emit('close')">
      <header class="modal-header">
        <div><h2>{{ title }}</h2><p v-if="description">{{ description }}</p></div>
        <button class="icon-button" type="button" aria-label="关闭" @click="$emit('close')"><X :size="19" /></button>
      </header>
      <div class="modal-body"><slot /></div>
      <footer v-if="$slots.footer" class="modal-footer"><slot name="footer" /></footer>
    </section>
  </div>
</template>
