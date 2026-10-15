<script setup lang="ts">
import { computed } from "vue";
import { AppWindow, ArrowRight, Bookmark, Bot, CreditCard, FileBox, Hexagon, Puzzle, Terminal, Users, Workflow } from "lucide-vue-next";
import { type Asset } from "../lib/api";
import { displayStatus } from "../lib/labels";

const props = defineProps<{ asset: Asset; typeName?: string; typeCode?: string; teamName?: string; bookmarked: boolean; busy?: boolean; returnTo?: string; aiFocus?: boolean; groupLabel?: string }>();
defineEmits<{ bookmark: [asset: Asset] }>();
const typeIcons: Record<string, typeof FileBox> = {
  ai_skill: Hexagon, ai_plugin: Puzzle, ai_agent: Bot, ai_workflow: Workflow,
  automation_script: Terminal, saas_subscription: CreditCard, internal_system: AppWindow,
};
const typeIcon = computed(() => typeIcons[props.typeCode || ""] || FileBox);
const detailLink = computed(() => ({ path: `/discover/${props.asset.id}`, query: props.returnTo ? { returnTo: props.returnTo } : {} }));
const bookmarkLabel = computed(() => `${props.bookmarked ? '取消收藏' : '收藏'}${props.asset.name}`);
</script>
<template>
  <article class="fusion-card" :class="{ 'ai-outcome-card': aiFocus }">
    <div class="fusion-card-meta">
      <div class="fusion-type">
        <span class="fusion-asset-symbol" :class="typeCode"><component :is="typeIcon" :size="22" aria-hidden="true" /></span>
        <span><strong>{{ typeName || '资产' }}</strong><small>版本 {{ asset.version }}</small></span>
      </div>
      <button class="icon-button fusion-bookmark" :class="{ saved: bookmarked }" :aria-label="bookmarkLabel" :title="bookmarkLabel" :aria-pressed="bookmarked" :disabled="busy" @click="$emit('bookmark', asset)"><Bookmark :size="19" aria-hidden="true" /></button>
    </div>
    <span v-if="aiFocus && groupLabel" class="ai-capability-label">{{ groupLabel }}</span>
    <h2><RouterLink :to="detailLink">{{ asset.name }}</RouterLink></h2>
    <span v-if="asset.review_status === 'pending_review'" class="fusion-review-state">待审核</span>
    <small v-if="aiFocus" class="ai-outcome-caption">成果说明</small>
    <p>{{ asset.description || '暂无说明，待负责人补充。' }}</p>
    <div class="fusion-card-footer">
      <span class="fusion-owner"><Users :size="14" aria-hidden="true" />{{ teamName || '归属待确认' }}</span>
      <span class="fusion-status" :class="{ 'is-draft': asset.status === 'draft' }">{{ displayStatus(asset.status) }}</span>
    </div>
    <RouterLink :to="detailLink" class="fusion-detail">{{ aiFocus ? '查看成果与用法' : '查看详情' }}<ArrowRight :size="17" aria-hidden="true" /></RouterLink>
  </article>
</template>
