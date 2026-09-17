<script setup lang="ts">
import { X } from "lucide-vue-next";

defineProps<{ title: string; description?: string; wide?: boolean }>();
defineEmits<{ close: [] }>();
</script>

<template>
  <div class="modal-backdrop" role="presentation" @mousedown.self="$emit('close')">
    <section class="modal-panel" :class="{ wide }" role="dialog" aria-modal="true" :aria-label="title">
      <header class="modal-header">
        <div><h2>{{ title }}</h2><p v-if="description">{{ description }}</p></div>
        <button class="icon-button" type="button" aria-label="关闭" @click="$emit('close')"><X :size="19" /></button>
      </header>
      <div class="modal-body"><slot /></div>
      <footer v-if="$slots.footer" class="modal-footer"><slot name="footer" /></footer>
    </section>
  </div>
</template>
