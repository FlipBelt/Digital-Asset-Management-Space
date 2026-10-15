<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Building2 } from "lucide-vue-next";
import { resolvePlatformBrand } from "../lib/platformBrand";

const props = withDefaults(defineProps<{ name: string; website?: string | null; size?: number }>(), { size: 40 });
const failed = ref(false);
const brand = computed(() => resolvePlatformBrand(props.name, props.website));
const source = computed(() => failed.value ? null : brand.value?.src);
const dimensions = computed(() => {
  const size = Number.isFinite(props.size) && props.size > 0 ? props.size : 40;
  const width = brand.value?.wide && !failed.value ? size * 2.4 : size;
  return { width: `${width}px`, height: `${size}px`, minWidth: `${width}px`, minHeight: `${size}px`, maxWidth: `${width}px`, maxHeight: `${size}px`, flex: `0 0 ${width}px`, backgroundColor: "#fff" };
});
watch(() => [props.name, props.website, brand.value?.src], () => { failed.value = false; });
</script>

<template>
  <span class="platform-logo" :style="dimensions" aria-hidden="true">
    <img v-if="source" :src="source" alt="" decoding="async" @error="failed = true" />
    <Building2 v-else :size="22" />
  </span>
</template>

<style scoped>
.platform-logo { display:inline-grid; flex:none; place-items:center; box-sizing:border-box; padding:6px; border:1px solid var(--border); border-radius:8px; color:var(--muted); vertical-align:middle; }
.platform-logo img { display:block; width:100%; height:100%; min-width:0; min-height:0; object-fit:contain; }
.platform-logo > svg { width:65%; height:65%; }
</style>
