<script setup lang="ts">
import { computed } from "vue";
import { AppWindow, ArrowRight, Bookmark, Bot, CreditCard, ExternalLink, FileBox, Github, Hexagon, Puzzle, Terminal, Users, Workflow } from "lucide-vue-next";
import { type Asset } from "../lib/api";
import { isPersonalSubscription, subscriptionStatus } from "../lib/personalSubscriptions";
import { displayOutcomeVersion } from "../lib/assetVersions";
import { assetCardSummary, assetLinks } from "../lib/assetLinks";

const props = defineProps<{ asset: Asset; typeName?: string; typeCode?: string; teamName?: string; bookmarked: boolean; busy?: boolean; returnTo?: string; aiFocus?: boolean; groupLabel?: string }>();
defineEmits<{ bookmark: [asset: Asset] }>();
const typeIcons: Record<string, typeof FileBox> = {
  ai_skill: Hexagon, ai_plugin: Puzzle, ai_agent: Bot, ai_workflow: Workflow,
  automation_script: Terminal, saas_subscription: CreditCard, internal_system: AppWindow,
};
const typeIcon = computed(() => typeIcons[props.typeCode || ""] || FileBox);
const detailLink = computed(() => ({ path: `/discover/${props.asset.id}`, query: props.returnTo ? { returnTo: props.returnTo } : {} }));
const bookmarkLabel = computed(() => `${props.bookmarked ? '取消收藏' : '收藏'}${props.asset.name}`);
const links = computed(() => assetLinks(props.asset));
const summary = computed(() => assetCardSummary(props.asset.description));
</script>
<template>
  <article class="fusion-card" :class="{ 'ai-outcome-card': aiFocus }">
    <div class="fusion-card-meta">
      <div class="fusion-type">
        <span class="fusion-asset-symbol" :class="typeCode"><component :is="typeIcon" :size="22" aria-hidden="true" /></span>
        <span><strong>{{ isPersonalSubscription(asset) ? '个人订阅' : typeName || '资产' }}</strong><small>{{ isPersonalSubscription(asset) ? '个人登记 · 无需审核' : displayOutcomeVersion(asset) }}</small></span>
      </div>
      <button class="icon-button fusion-bookmark" :class="{ saved: bookmarked }" :aria-label="bookmarkLabel" :title="bookmarkLabel" :aria-pressed="bookmarked" :disabled="busy" @click="$emit('bookmark', asset)"><Bookmark :size="19" aria-hidden="true" /></button>
    </div>
    <span v-if="aiFocus && groupLabel" class="ai-capability-label">{{ groupLabel }}</span>
    <h2><RouterLink :to="detailLink">{{ asset.name }}</RouterLink></h2>
    <span v-if="!asset.is_child_account && !isPersonalSubscription(asset) && asset.review_status === 'pending_review'" class="fusion-review-state">待审核</span>
    <small v-if="aiFocus" class="ai-outcome-caption">成果说明</small>
    <p class="asset-card-summary">{{ summary }}</p>
    <div class="asset-card-actions">
      <div class="fusion-card-footer">
        <span class="fusion-owner"><Users :size="14" aria-hidden="true" />{{ teamName || '归属待确认' }}</span>
        <span class="fusion-status" :class="{ 'is-draft': asset.status === 'draft' && !isPersonalSubscription(asset) }">{{ subscriptionStatus(asset) }}</span>
      </div>
      <div class="asset-card-links" :aria-label="links.length ? `${asset.name}的访问链接` : undefined" :aria-hidden="!links.length || undefined">
        <a v-for="link in links" :key="link.url" :href="link.url" target="_blank" rel="noopener noreferrer" :title="`${link.label} · ${link.url}`" :aria-label="`${asset.name} · ${link.label}（新窗口打开）`">
          <component :is="link.kind === 'repository' ? Github : ExternalLink" :size="16" aria-hidden="true" /><span>{{ link.label }}</span><ExternalLink v-if="link.kind === 'repository'" :size="13" aria-hidden="true" />
        </a>
      </div>
      <RouterLink :to="detailLink" class="fusion-detail">{{ aiFocus ? '查看成果与用法' : '查看详情' }}<ArrowRight :size="17" aria-hidden="true" /></RouterLink>
    </div>
  </article>
</template>
<style scoped>
.asset-card-summary { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:4; overflow:hidden; flex:none; }
.asset-card-actions { display:grid; gap:16px; margin-top:auto; }
.asset-card-links { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; min-height:40px; }
.asset-card-links a { display:flex; align-items:center; justify-content:center; gap:8px; min-width:0; min-height:40px; padding:8px 10px; border:1px solid var(--border); border-radius:8px; color:var(--text); font-size:13px; font-weight:550; }
.asset-card-links a:hover { border-color:var(--accent); background:var(--surface-soft); }
.asset-card-links svg { flex:none; }
.asset-card-links span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.asset-card-links a:only-child { grid-column:1 / -1; }
</style>
