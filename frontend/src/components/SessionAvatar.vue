<script setup lang="ts">
import { computed, ref, watch } from "vue";

const props = defineProps<{ src?: string | null; name: string }>();
const failed = ref(false);
const avatar = computed(() => {
  if (!props.src || failed.value) return "";
  try {
    const url = new URL(props.src);
    return url.protocol === "https:" && !url.username && !url.password ? url.href : "";
  } catch { return ""; }
});
const initial = computed(() => Array.from(props.name.trim())[0] || "访");
watch(() => props.src, () => { failed.value = false; });
</script>

<template>
  <span class="avatar session-avatar" aria-hidden="true">
    <img v-if="avatar" :src="avatar" alt="" referrerpolicy="no-referrer" decoding="async" @error="failed = true" />
    <span v-else>{{ initial }}</span>
  </span>
</template>

<style scoped>
.session-avatar { flex: none; overflow: hidden; font-size: 12px; font-weight: 600; }
.session-avatar img { width: 100%; height: 100%; object-fit: cover; }
</style>
