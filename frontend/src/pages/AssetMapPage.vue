<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { AlertTriangle, Boxes, ChevronLeft, ChevronRight, Compass, Filter, Focus, Layers3, ListTree, Moon, Network, RefreshCw, Search, Sparkles, Sun, Users, X } from "lucide-vue-next";

import AssetGraphCanvas from "../components/AssetGraphCanvas.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type AssetMapData, type AssetMapEdge, type AssetMapNode } from "../lib/api";
import { displayStatus } from "../lib/labels";

type PlatformSummary = { node: AssetMapNode; nodeIds: Set<string>; serviceCount: number; accountCount: number; systemCount: number; pendingCount: number };
type GraphMode = "architecture" | "explore";
type GraphTheme = "light" | "particle";

const overviewData = ref<AssetMapData>({ nodes: [], edges: [] }); const focusData = ref<AssetMapData>({ nodes: [], edges: [] });
const loading = ref(true); const error = ref(""); const includePeople = ref(false); const selectedId = ref(""); const activePlatformId = ref("");
const searchQuery = ref(""); const focusSearch = ref(""); const attentionOnly = ref(false); const compactServices = ref(true); const graphMode = ref<GraphMode>("architecture"); const graphTheme = ref<GraphTheme>("particle"); const trail = ref<string[]>([]);

const data = computed(() => activePlatformId.value ? focusData.value : overviewData.value);
const activePlatform = computed(() => overviewData.value.nodes.find((item) => item.id === activePlatformId.value) ?? focusData.value.nodes.find((item) => item.id === activePlatformId.value) ?? null);

function scopeNodeIds(source: AssetMapData, platformKey: string) {
  const included = new Set([platformKey]); const expandable = [platformKey];
  while (expandable.length) { const current = expandable.pop()!; source.edges.forEach((edge) => { const other = edge.source === current ? edge.target : edge.target === current ? edge.source : ""; if (!other || (other.startsWith("platform:") && other !== platformKey)) return; if (other.startsWith("entity:")) { included.add(other); return; } if (!included.has(other)) { included.add(other); expandable.push(other); } }); }
  return included;
}

const platformSummaries = computed<PlatformSummary[]>(() => overviewData.value.nodes.filter((node) => node.kind === "platform").map((node) => { const nodeIds = scopeNodeIds(overviewData.value, node.id); const scopeNodes = overviewData.value.nodes.filter((item) => nodeIds.has(item.id)); return { node, nodeIds, serviceCount: scopeNodes.filter((item) => item.kind === "resource").length, accountCount: scopeNodes.filter((item) => item.kind === "platform_account").length, systemCount: scopeNodes.filter((item) => item.kind === "system").length, pendingCount: scopeNodes.filter((item) => item.status === "pending_review" || item.label.startsWith("待")).length }; }));
const filteredPlatforms = computed(() => { const term = searchQuery.value.trim().toLowerCase(); return platformSummaries.value.filter((summary) => { const hasTerm = !term || overviewData.value.nodes.some((node) => summary.nodeIds.has(node.id) && `${node.label} ${node.subtitle ?? ""}`.toLowerCase().includes(term)); return hasTerm && (!attentionOnly.value || summary.pendingCount > 0); }); });
const overviewStats = computed(() => ({ platforms: platformSummaries.value.length, services: overviewData.value.nodes.filter((item) => item.kind === "resource").length, pending: overviewData.value.nodes.filter((item) => item.status === "pending_review" || item.label.startsWith("待")).length }));
const serviceNodeIds = computed(() => new Set(data.value.edges.filter((edge) => /购买|开通/.test(edge.relation)).map((edge) => edge.target).filter((id) => data.value.nodes.some((node) => node.id === id && node.kind === "resource"))));
const graphData = computed<AssetMapData>(() => {
  if (!activePlatformId.value || !compactServices.value || serviceNodeIds.value.size < 2) return data.value;
  const groupId = `service-group:${activePlatformId.value}`; const groupNode: AssetMapNode = { id: groupId, label: `服务实例（${serviceNodeIds.value.size} 项）`, kind: "resource", status: "active", asset_id: null, subtitle: "点击展开服务明细" };
  const nodes = data.value.nodes.filter((node) => !serviceNodeIds.value.has(node.id)).concat(groupNode); const seen = new Set<string>(); const edges: AssetMapEdge[] = [];
  data.value.edges.forEach((edge) => { const source = serviceNodeIds.value.has(edge.source) ? groupId : edge.source; const target = serviceNodeIds.value.has(edge.target) ? groupId : edge.target; if (source === target) return; const key = `${source}:${target}:${edge.relation}`; if (!seen.has(key)) { seen.add(key); edges.push({ id: `grouped:${key}`, source, target, relation: edge.relation }); } }); return { nodes, edges };
});
const selected = computed(() => graphData.value.nodes.find((item) => item.id === selectedId.value) ?? null);
const selectedRelations = computed(() => graphData.value.edges.filter((edge) => edge.source === selectedId.value || edge.target === selectedId.value));
const serviceList = computed(() => data.value.nodes.filter((node) => serviceNodeIds.value.has(node.id)));
const trailNodes = computed(() => trail.value.map((id) => graphData.value.nodes.find((node) => node.id === id)).filter((node): node is AssetMapNode => Boolean(node)));

function platformUuid(key: string) { return key.replace("platform:", ""); }
function neighborName(edge: AssetMapEdge) { const otherId = edge.source === selectedId.value ? edge.target : edge.source; return graphData.value.nodes.find((node) => node.id === otherId)?.label ?? "关联对象"; }
async function loadOverview() { loading.value = true; error.value = ""; try { overviewData.value = await api.assetMap(includePeople.value); } catch (reason) { error.value = reason instanceof Error ? reason.message : "资产地图加载失败"; } finally { loading.value = false; } }
async function openPlatform(platformKey: string) { activePlatformId.value = platformKey; selectedId.value = ""; trail.value = []; compactServices.value = true; graphMode.value = "architecture"; loading.value = true; error.value = ""; try { focusData.value = await api.assetMap(includePeople.value, platformUuid(platformKey)); } catch (reason) { error.value = reason instanceof Error ? reason.message : "平台地图加载失败"; activePlatformId.value = ""; } finally { loading.value = false; } }
function backToOverview() { activePlatformId.value = ""; selectedId.value = ""; trail.value = []; focusSearch.value = ""; }
function selectNode(node: AssetMapNode) { if (node.id.startsWith("service-group:")) { compactServices.value = false; return; } selectedId.value = node.id; graphMode.value = "explore"; if (trail.value.at(-1) !== node.id) trail.value.push(node.id); if (serviceNodeIds.value.has(node.id)) compactServices.value = false; }
function clearSelection() { selectedId.value = ""; graphMode.value = "architecture"; }
function selectRelation(edge: AssetMapEdge) {
  const targetId = edge.source === selectedId.value ? edge.target : edge.source;
  const target = graphData.value.nodes.find((node) => node.id === targetId);
  if (target) selectNode(target);
}
function selectTrail(node: AssetMapNode) { selectedId.value = node.id; trail.value = trail.value.slice(0, trail.value.indexOf(node.id) + 1); }
function searchFocusNode() { const term = focusSearch.value.trim().toLowerCase(); if (!term) return; const match = graphData.value.nodes.find((node) => `${node.label} ${node.subtitle ?? ""}`.toLowerCase().includes(term)); if (match) selectNode(match); else error.value = `当前平台中没有找到“${focusSearch.value.trim()}”`; }
async function refresh() { if (activePlatformId.value) await openPlatform(activePlatformId.value); else await loadOverview(); }

watch(includePeople, refresh); onMounted(loadOverview);
</script>

<template>
  <div class="page-stack map-page map-page-v3" :class="`theme-${graphTheme}`">
    <PageHeader eyebrow="关系视图" title="资产地图" :description="activePlatform ? `正在探索 ${activePlatform.label} 的六层资产关系。` : '先看平台全貌，再进入局部关系探索。'">
      <label class="map-people-toggle"><input v-model="includePeople" type="checkbox" /><Users :size="16" />显示负责人</label><button class="secondary-button" @click="refresh"><RefreshCw :size="16" />刷新</button>
    </PageHeader>
    <div v-if="error" class="message-panel error-message">{{ error }}<button class="icon-button" @click="error = ''"><X :size="15" /></button></div>

    <template v-if="!activePlatformId">
      <section class="map-overview-hero"><div><span class="hero-kicker">资产地图 · 平台总览</span><h2>从平台进入，而不是一次铺满所有关系。</h2><p>每张卡片代表一个平台及其注册身份、公司账号、服务资源、系统和待补充事项。</p></div><div class="map-stat-grid"><div><Layers3 :size="19" /><strong>{{ overviewStats.platforms }}</strong><span>归属平台</span></div><div><Boxes :size="19" /><strong>{{ overviewStats.services }}</strong><span>服务/资源</span></div><div class="attention"><AlertTriangle :size="19" /><strong>{{ overviewStats.pending }}</strong><span>待补充事项</span></div></div></section>
      <section class="map-overview-panel"><div class="map-overview-toolbar"><label class="map-search"><Search :size="16" /><input v-model="searchQuery" placeholder="搜索平台、账号、服务或系统" /></label><label class="map-filter-toggle"><input v-model="attentionOnly" type="checkbox" /><Filter :size="15" />仅看有待办的平台</label></div><div v-if="loading" class="map-loading compact"><Network :size="26" />正在汇总资产地图…</div><div v-else-if="filteredPlatforms.length" class="platform-map-grid"><button v-for="summary in filteredPlatforms" :key="summary.node.id" class="platform-map-card" @click="openPlatform(summary.node.id)"><div class="platform-map-card-title"><span class="platform-dot" /><div><strong>{{ summary.node.label }}</strong><small>{{ summary.node.subtitle || '服务平台' }}</small></div><ChevronRight :size="18" /></div><div class="platform-map-metrics"><span><b>{{ summary.accountCount }}</b>账号节点</span><span><b>{{ summary.serviceCount }}</b>服务/资源</span><span><b>{{ summary.systemCount }}</b>关联系统</span></div><div class="platform-map-footer" :class="{ pending: summary.pendingCount }"><AlertTriangle :size="14" />{{ summary.pendingCount ? `${summary.pendingCount} 项待补充 / 待确认` : '资产关系已具备' }}</div></button></div><div v-else-if="!loading" class="map-empty">没有符合当前筛选条件的平台。</div></section>
    </template>

    <template v-else>
      <section class="map-focus-bar"><button class="quiet-button" @click="backToOverview"><ChevronLeft :size="16" />返回平台总览</button><nav class="map-trail"><span>探索轨迹</span><button @click="graphMode = 'architecture'; clearSelection()">{{ activePlatform?.label }}</button><template v-for="node in trailNodes" :key="node.id"><ChevronRight :size="13" /><button :class="{ active: node.id === selectedId }" @click="selectTrail(node)">{{ node.label }}</button></template></nav><button v-if="selectedId" class="quiet-button" @click="clearSelection"><X :size="15" />取消聚焦</button></section>
      <section class="map-commandbar"><div class="map-mode-switch"><button :class="{ active: graphMode === 'architecture' }" @click="graphMode = 'architecture'"><ListTree :size="16" />六层星图</button><button :class="{ active: graphMode === 'explore' }" :disabled="!selectedId" @click="graphMode = 'explore'"><Compass :size="16" />关系探索</button></div><div class="map-theme-switch" aria-label="资产地图视觉主题"><span>视觉主题</span><button :class="{ active: graphTheme === 'light' }" :aria-pressed="graphTheme === 'light'" @click="graphTheme = 'light'"><Sun :size="14" />白底星图</button><button :class="{ active: graphTheme === 'particle' }" :aria-pressed="graphTheme === 'particle'" @click="graphTheme = 'particle'"><Moon :size="14" />深空粒子</button></div><form class="map-focus-search" @submit.prevent="searchFocusNode"><Search :size="16" /><input v-model="focusSearch" placeholder="查找当前平台中的对象" /><kbd>Enter</kbd></form><div class="map-command-actions"><button v-if="serviceNodeIds.size > 1" class="secondary-button" @click="compactServices = !compactServices">{{ compactServices ? `展开 ${serviceNodeIds.size} 项服务` : '折叠服务明细' }}</button><span><Focus :size="15" />悬停聚焦 · 点击锁定 · 拖动画布 · 滚轮缩放</span></div></section>
      <section class="map-shell graph-modern-shell" :class="[{ 'with-drawer': selected }, `theme-${graphTheme}`]">
        <div class="map-toolbar"><div class="map-legend"><span><i class="company" />公司</span><span><i class="platform" />平台</span><span><i class="registration_identity" />注册身份</span><span><i class="platform_account" />公司账号</span><span><i class="resource" />服务/资源</span><span><i class="system" />系统</span></div><small>{{ graphMode === 'architecture' ? '六层星图：星体自由展开，关系以直线连接' : '关系探索：悬停临时聚焦，点击后固定保留上下文' }}</small></div>
        <div v-if="loading" class="map-loading map-loading-overlay" role="status" aria-live="polite"><Network :size="26" /><span>正在加载平台关系…</span></div><AssetGraphCanvas v-else :data="graphData" :selected-id="selectedId" :mode="graphMode" :theme="graphTheme" :drawer-open="Boolean(selected)" @select="selectNode" @clear="clearSelection" />
        <aside v-if="selected" class="map-detail-panel modern-map-drawer"><button class="icon-button close-map-detail" aria-label="关闭" @click="clearSelection"><X :size="16" /></button><div class="drawer-kicker"><Sparkles :size="15" />当前聚焦对象</div><span class="map-detail-kind">{{ selected.subtitle || selected.kind }}</span><h3>{{ selected.label }}</h3><StatusBadge :tone="selected.status === 'active' ? 'success' : 'warning'">{{ displayStatus(selected.status) }}</StatusBadge><div class="map-relation-list"><strong>直接关系 · {{ selectedRelations.length }}</strong><button v-for="edge in selectedRelations" :key="edge.id" @click="selectRelation(edge)"><span>{{ edge.relation }}</span><b>{{ neighborName(edge) }}</b><ChevronRight :size="14" /></button></div><RouterLink v-if="selected.asset_id" :to="`/assets/${selected.asset_id}`" class="primary-button">查看资产详情</RouterLink></aside>
        <div v-if="selected && graphTheme === 'particle'" class="particle-statusbar"><span class="particle-status-dot" /><strong>节点：{{ selected.label }}</strong><span>直接关系：<b>{{ selectedRelations.length }}</b></span><span>类型：<b>{{ selected.subtitle || selected.kind }}</b></span><button @click="clearSelection">清场</button></div>
      </section>
      <section v-if="serviceList.length" class="map-service-list"><div><span class="hero-kicker">服务清单</span><h3>{{ compactServices ? '服务已在关系图中聚合，可从此直接定位。' : '当前平台的服务与资源' }}</h3></div><button v-for="service in serviceList" :key="service.id" @click="selectNode(service)"><span class="resource-dot" />{{ service.label }}<small>{{ service.subtitle || displayStatus(service.status) }}</small></button></section>
    </template>
  </div>
</template>
