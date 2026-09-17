<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowRight, Boxes, BriefcaseBusiness, CircleAlert, RefreshCw, Search, Server, Users } from "lucide-vue-next";

import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type ScenarioNode, type ScenarioOverview, type ScenarioSummary } from "../lib/api";

const scenarios = ref<ScenarioSummary[]>([]);
const overview = ref<ScenarioOverview | null>(null);
const selectedCode = ref("");
const keyword = ref("");
const loading = ref(true);
const error = ref("");

const filteredNodes = computed(() => {
  const term = keyword.value.trim().toLowerCase();
  if (!term) return overview.value?.nodes ?? [];
  return (overview.value?.nodes ?? []).filter((node) =>
    `${node.label} ${node.subtitle ?? ""} ${node.responsible_name ?? ""} ${node.department_name ?? ""}`.toLowerCase().includes(term),
  );
});
const platformNodes = computed(() => filteredNodes.value.filter((node) => node.kind === "platform"));
const roots = computed(() => filteredNodes.value.filter((node) => node.parent_id === `scenario:${selectedCode.value}`));

function childrenOf(parentId: string) {
  return filteredNodes.value.filter((node) => node.parent_id === parentId);
}

async function loadScenario(code = selectedCode.value) {
  if (!code) return;
  loading.value = true;
  error.value = "";
  try {
    overview.value = await api.scenario(code);
    selectedCode.value = code;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "业务场景加载失败";
  } finally {
    loading.value = false;
  }
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    scenarios.value = await api.scenarios();
    const preferred = scenarios.value.find((item) => item.code === "technology") ?? scenarios.value[0];
    if (preferred) await loadScenario(preferred.code);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "业务场景加载失败";
    loading.value = false;
  }
}

function selectScenario(code: string) {
  if (code !== selectedCode.value) void loadScenario(code);
}

function nodeTone(node: ScenarioNode) {
  return node.status === "active" || node.status === "approved" ? "success" : "warning";
}

onMounted(load);
</script>

<template>
  <div class="page-stack scenario-page">
    <PageHeader eyebrow="用户工作视图" title="业务场景工作区" description="按业务找到平台、账号、资源和负责人；资产入库与六层治理保持不变。">
      <RouterLink to="/intake" class="secondary-button"><BriefcaseBusiness :size="16" />资产入库</RouterLink>
      <RouterLink to="/assets" class="secondary-button"><Boxes :size="16" />资产底库</RouterLink>
      <button class="primary-button" @click="load"><RefreshCw :size="16" />刷新</button>
    </PageHeader>

    <div v-if="error" class="message-panel error-message">{{ error }}</div>
    <section class="scenario-notice"><CircleAlert :size="18" /><div><strong>这是业务导航，不是另一套台账。</strong><p>场景只是把已有资产按使用方式重新组织；任何新增、修改、归档仍回到资产底库留痕。</p></div></section>

    <section class="scenario-card-grid" aria-label="业务场景">
      <button v-for="item in scenarios" :key="item.code" class="scenario-card" :class="{ active: item.code === selectedCode }" @click="selectScenario(item.code)">
        <div class="scenario-card-icon"><Server :size="20" /></div>
        <div><strong>{{ item.name }}</strong><p>{{ item.description }}</p></div>
        <div class="scenario-card-counts"><span><b>{{ item.asset_count }}</b>资产</span><span><b>{{ item.platform_count }}</b>平台</span><span><b>{{ item.account_count }}</b>账号</span></div>
      </button>
      <div v-if="!scenarios.length && !loading" class="large-empty-panel"><BriefcaseBusiness :size="28" /><strong>尚未建立业务场景</strong><p>请先运行基础种子数据。</p></div>
    </section>

    <section v-if="overview" class="scenario-toolbar">
      <div><span class="hero-kicker">{{ overview.scenario.name }}</span><h2>从平台进入，逐层找到可执行资源</h2><p>{{ overview.scenario.description }}</p></div>
      <label class="map-search"><Search :size="16" /><input v-model="keyword" placeholder="搜索平台、账号、资源或负责人" /></label>
    </section>

    <section v-if="loading" class="loading-state"><RefreshCw :size="24" />正在加载业务场景…</section>
    <section v-else-if="overview" class="scenario-platform-list">
      <article v-for="platform in platformNodes" :key="platform.id" class="scenario-platform-card">
        <header><div class="scenario-platform-title"><span class="platform-dot" /><div><strong>{{ platform.label }}</strong><small>{{ platform.subtitle || "平台目录" }}</small></div></div><RouterLink v-if="platform.href" :to="platform.href" class="quiet-button">查看平台 <ArrowRight :size="14" /></RouterLink></header>
        <div class="scenario-node-grid">
          <RouterLink v-for="node in childrenOf(platform.id)" :key="node.id" :to="node.href || '/assets'" class="scenario-node-card" :class="`node-${node.kind}`">
            <div class="scenario-node-head"><span class="scenario-node-kind">{{ node.kind === "tenant" ? "企业账号" : node.kind === "account" ? "子账号" : node.kind === "service" ? "服务" : node.kind === "system" ? "系统" : "资源" }}</span><StatusBadge :tone="nodeTone(node)">{{ node.status === "active" ? "正常" : node.status }}</StatusBadge></div>
            <strong>{{ node.label }}</strong><small>{{ node.subtitle || node.metadata.asset_code || "" }}</small>
            <div v-if="node.responsible_name || node.department_name" class="scenario-node-owner"><Users :size="13" />{{ node.responsible_name || node.department_name }}</div>
            <div v-for="child in childrenOf(node.id)" :key="child.id" class="scenario-child-row"><span>{{ child.label }}</span><small>{{ child.subtitle || "子账号" }}</small></div>
          </RouterLink>
          <div v-if="!childrenOf(platform.id).length" class="scenario-empty-inline">该平台暂未关联可用资产。</div>
        </div>
      </article>
      <div v-if="!platformNodes.length" class="large-empty-panel"><Search :size="28" /><strong>没有找到匹配的场景对象</strong><p>可以清空搜索词，或回到资产底库查看未归类数据。</p><button class="secondary-button" @click="keyword = ''">清空筛选</button></div>
    </section>

    <section class="scenario-footer"><div><strong>还有 {{ overview?.unclassified_count ?? 0 }} 项资产未归入业务场景</strong><p>未归类不影响资产底库使用，后续可在治理流程中补充场景归属。</p></div><RouterLink to="/assets?view=business" class="secondary-button">去资产底库补充 <ArrowRight :size="15" /></RouterLink><RouterLink to="/services" class="primary-button"><Server :size="15" />打开 AI / API 工作台</RouterLink></section>
  </div>
</template>
