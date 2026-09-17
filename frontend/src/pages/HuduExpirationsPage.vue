<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowLeft, CalendarClock, ChevronRight, RefreshCw, UserRound } from "lucide-vue-next";
import { useRouter } from "vue-router";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type HuduAssetItem } from "../lib/api";

const router = useRouter();
const items = ref<HuduAssetItem[]>([]);
const loading = ref(true);
const error = ref("");
const tab = ref<"all" | "due" | "owner">("all");
const filtered = computed(() => items.value.filter((item) => tab.value === "all" || (tab.value === "owner" ? !item.has_owner : Boolean(item.expires_at))));
function date(value: string | null) { return value ? new Date(value).toLocaleDateString("zh-CN") : "待补负责人"; }
function tone(item: HuduAssetItem) { if (!item.has_owner) return "warning"; if (item.expires_at && item.expires_at < new Date().toISOString()) return "warning"; return "success"; }
async function load() { loading.value = true; error.value = ""; try { items.value = (await api.huduExpirations()).items; } catch (reason) { error.value = reason instanceof Error ? reason.message : "加载失败"; } finally { loading.value = false; } }
onMounted(load);
</script>

<template>
  <div class="hudu-page"><div class="hudu-breadcrumb"><button class="hudu-back" type="button" @click="router.push('/hudu')"><ArrowLeft :size="16" />资产库</button><span>/ 到期与交接</span></div><header class="hudu-page-header"><div><span class="hudu-eyebrow">跟进中心</span><h1>到期与交接</h1><p>把快到期、未指定负责人的资产集中到一个清单里。</p></div><button class="secondary-button" type="button" @click="load"><RefreshCw :size="16" />刷新</button></header><div v-if="error" class="hudu-error">{{ error }}</div><section class="hudu-followup-tabs"><button :class="{ active: tab === 'all' }" type="button" @click="tab = 'all'">全部 <b>{{ items.length }}</b></button><button :class="{ active: tab === 'due' }" type="button" @click="tab = 'due'">有到期日 <b>{{ items.filter((item) => item.expires_at).length }}</b></button><button :class="{ active: tab === 'owner' }" type="button" @click="tab = 'owner'">待补负责人 <b>{{ items.filter((item) => !item.has_owner).length }}</b></button></section><section class="hudu-surface hudu-followup-list"><div v-if="loading" class="hudu-empty">正在读取跟进清单…</div><div v-else-if="!filtered.length" class="hudu-empty"><CalendarClock :size="28" /><strong>当前没有待跟进项目</strong><span>资产库状态良好，可以继续探索或新增资产。</span></div><RouterLink v-for="item in filtered" :key="item.id" :to="`/hudu/assets/${item.id}`" class="hudu-followup-row"><div class="hudu-followup-icon"><CalendarClock :size="19" /></div><div class="hudu-asset-main"><strong>{{ item.name }}</strong><span>{{ item.asset_code }} · {{ item.category_name }} · {{ item.asset_type_name }}</span><small><UserRound :size="13" />{{ item.owner_department_name || "待补负责人" }} <i>·</i> 到期 {{ date(item.expires_at) }}</small></div><StatusBadge :tone="tone(item)">{{ !item.has_owner ? "补负责人" : item.expires_at && item.expires_at < new Date().toISOString() ? "已到期" : "即将到期" }}</StatusBadge><ChevronRight :size="18" /></RouterLink></section></div>
</template>
