<script setup lang="ts">
import { ArrowRight, Bookmark } from "lucide-vue-next";
import { type Asset } from "../lib/api";
import { displayStatus } from "../lib/labels";
defineProps<{ asset: Asset; typeName?: string; teamName?: string; bookmarked: boolean; busy?: boolean }>();
defineEmits<{ bookmark: [asset: Asset] }>();
</script>
<template>
  <article class="fusion-card">
    <div class="fusion-card-meta">
      <div class="fusion-type"><span class="fusion-monogram">{{ asset.name.slice(0, 1) }}</span><span><strong>{{ typeName || '资产' }}</strong><small>版本 {{ asset.version }}</small></span></div>
      <button class="icon-button fusion-bookmark" :class="{ saved: bookmarked }" :aria-label="`${bookmarked ? '取消收藏' : '收藏'}${asset.name}`" :aria-pressed="bookmarked" :disabled="busy" @click="$emit('bookmark', asset)"><Bookmark :size="19" /></button>
    </div>
    <h2><RouterLink :to="`/discover/${asset.id}`">{{ asset.name }}</RouterLink></h2>
    <p>{{ asset.description || '暂无说明，待负责人补充。' }}</p>
    <div class="fusion-card-footer"><small>{{ teamName || '归属待确认' }}</small><span class="fusion-status">{{ displayStatus(asset.status) }}</span></div>
    <RouterLink :to="`/discover/${asset.id}`" class="fusion-detail">查看详情<ArrowRight :size="18" /></RouterLink>
  </article>
</template>
