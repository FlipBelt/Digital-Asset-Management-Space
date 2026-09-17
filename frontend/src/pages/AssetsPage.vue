<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  BarChart3,
  ChevronDown,
  Download,
  FileUp,
  Filter,
  List,
  Plus,
  RefreshCw,
  Search,
} from "lucide-vue-next";

import ModalPanel from "../components/ModalPanel.vue";
import PageHeader from "../components/PageHeader.vue";
import SimpleBarChart from "../components/SimpleBarChart.vue";
import StatusBadge from "../components/StatusBadge.vue";
import {
  api,
  apiPath,
  type Asset,
  type AssetType,
  type Department,
  type ImportPreview,
  type ImportBatch,
  type ImportPlan,
  type ImportProposalObject,
  type LayerRecord,
  type LegalEntity,
} from "../lib/api";
import { displayStatus } from "../lib/labels";

const loading = ref(true);
const saving = ref(false);
const error = ref("");
const message = ref("");
const records = ref<LayerRecord[]>([]);
const total = ref(0);
const businessAssets = ref<Asset[]>([]);
const businessTypes = ref<AssetType[]>([]);
const importBatches = ref<ImportBatch[]>([]);
const sourcePlans = ref<ImportPlan[]>([]);
const types = ref<AssetType[]>([]);
const entities = ref<LegalEntity[]>([]);
const departments = ref<Department[]>([]);
const tableView = ref<"list" | "chart">("list");
const layer = ref(6);
const createOpen = ref(false);
const importOpen = ref(false);
const importPreview = ref<ImportPreview | null>(null);
const filters = reactive({ keyword: "", status: "", include_archived: false });
const form = reactive({
  name: "",
  asset_type_id: "",
  legal_entity_id: "",
  owner_department_id: "",
  status: "active",
  criticality: "normal",
  confidentiality: "internal",
  expires_at: "",
  description: "",
});
const categoryChart = ref<{ label: string; value: number }[]>([]);
const layerCounts = ref<Record<number, number>>({});
const route = useRoute();
const router = useRouter();
type DisplayMode = "business" | "governance" | "source";
function normalizeDisplayMode(value: unknown): DisplayMode {
  return value === "governance" || value === "source" ? value : "business";
}
const displayMode = ref<DisplayMode>(normalizeDisplayMode(route.query.view));
const businessFilters = reactive({ keyword: "", status: "", include_archived: false });
const layerOptions = [
  { value: 1, label: "公司主体", hint: "先看有哪些公司" },
  { value: 2, label: "注册身份", hint: "手机号、邮箱等身份" },
  { value: 3, label: "平台", hint: "服务平台目录" },
  { value: 4, label: "公司平台账号", hint: "公司在平台上的账号" },
  { value: 5, label: "人员授权", hint: "谁可使用什么" },
  { value: 6, label: "实体服务 / 资源", hint: "日常最常查看" },
];
const currentLayer = computed(
  () =>
    layerOptions.find((item) => item.value === layer.value) ?? layerOptions[5],
);
const displayModeMeta: Record<DisplayMode, { label: string; description: string }> = {
  business: { label: "业务台账", description: "按资产名称、类型、归属和状态查看日常需要管理的真实实例。" },
  governance: { label: "六层治理", description: "面向管理员查看 L1-L6 对象、关系和缺失项；不会因缺层自动补造对象。" },
  source: { label: "原始台账", description: "保留来源文件和原始记录，并查看它们与正式资产的映射及确认状态。" },
};
const currentDisplayMode = computed(() => displayModeMeta[displayMode.value]);
function ownershipLabel(value: string | null) {
  return ({ company_owned: "公司所有", personal_for_company: "个人注册、公司使用", unknown: "归属待确认" } as Record<string, string>)[value ?? ""] ?? "未填写";
}
function categoryLabel(value: string | null) {
  return ({ cloud: "云平台", ai: "大模型 / AI", saas: "SaaS / 协作", marketing: "营销 / 电商", payment: "支付", other: "其他" } as Record<string, string>)[value ?? ""] ?? value ?? "未分类";
}
function detailPath(record: LayerRecord) {
  if (record.layer === 1) return `/directory/entity/${record.id.replace("entity:", "")}`;
  if (record.layer === 3) return `/directory/platform/${record.id.replace("platform:", "")}`;
  if (record.layer === 5) return `/directory/grant/${record.id.replace("grant:", "")}`;
  if (record.asset_id) return record.layer === 4 ? `/assets/${record.asset_id}?tab=accounts` : `/assets/${record.asset_id}`;
  return null;
}
const filteredRecords = computed(() => {
  const keyword = filters.keyword.trim().toLowerCase();
  return records.value.filter((item) => {
    const matchesKeyword =
      !keyword ||
      `${item.name} ${item.object_type} ${item.legal_entity_name ?? ""} ${item.platform_name ?? ""}`
        .toLowerCase()
        .includes(keyword);
    return (
      matchesKeyword && (!filters.status || item.status === filters.status)
    );
  });
});

const filteredBusinessAssets = computed(() => {
  const keyword = businessFilters.keyword.trim().toLowerCase();
  return businessAssets.value.filter((item) => {
    const matchesKeyword = !keyword || `${item.name} ${item.asset_code} ${assetTypeLabel(item.asset_type_id)}`.toLowerCase().includes(keyword);
    return matchesKeyword && (!businessFilters.status || item.status === businessFilters.status);
  });
});

const sourceRows = computed(() =>
  sourcePlans.value.flatMap((plan) => plan.objects.map((item) => ({ ...item, batchId: plan.batch_id }))),
);

const sourceLedgerGroups = computed(() => {
  const groups = new Map<string, typeof sourceRows.value>();
  sourceRows.value.forEach((item) => {
    const label = item.object_type || item.layer_code || "未分类材料";
    const rows = groups.get(label) ?? [];
    rows.push(item);
    groups.set(label, rows);
  });
  return Array.from(groups, ([label, rows]) => ({
    label,
    rows,
    confirmedCount: rows.filter((item) => item.review_status === "approved").length,
    sourceFiles: Array.from(new Set(rows.map((item) => item.source_file).filter(Boolean))),
  }));
});

const sourceLedgerConfirmedCount = computed(
  () => sourceRows.value.filter((item) => item.review_status === "approved").length,
);

const sourceLedgerOpen = reactive<Record<string, boolean>>({});

function sourceGroupIsOpen(label: string) {
  return sourceLedgerOpen[label] ?? true;
}

function toggleSourceGroup(label: string) {
  sourceLedgerOpen[label] = !sourceGroupIsOpen(label);
}

function setSourceGroupsOpen(open: boolean) {
  sourceLedgerGroups.value.forEach((group) => {
    sourceLedgerOpen[group.label] = open;
  });
}

function assetTypeLabel(typeId: string) {
  return businessTypes.value.find((item) => item.id === typeId)?.name ?? "未分类资产";
}

function sourceStatusLabel(status: string) {
  return ({ pending_review: "待确认", approved: "已确认", rejected: "已驳回", archived: "已归档" } as Record<string, string>)[status] ?? status;
}

function sourcePreview(item: ImportProposalObject) {
  const payload = item.normalized_payload ?? {};
  const values = Object.entries(payload)
    .filter(([key, value]) => !["api_key", "api_secret", "password", "secret"].includes(key) && value !== null && value !== "")
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${String(value)}`);
  return values.join(" · ") || item.evidence.slice(0, 2).map((entry) => `${entry.field}: ${entry.value}`).join(" · ") || "原始事实待展开";
}

function sourceField(item: ImportProposalObject, keys: string[], fallback = "—") {
  const payload = item.normalized_payload ?? {};
  const entries = Object.entries(payload);
  const normalizedKeys = keys.map((key) => key.toLowerCase());
  const entry = entries.find(([key, value]) => {
    if (value === null || value === undefined || value === "") return false;
    return normalizedKeys.includes(key.toLowerCase());
  });
  if (!entry) return fallback;
  const value = Array.isArray(entry[1]) ? entry[1].join("、") : String(entry[1]);
  return value || fallback;
}

function sourceLedgerStatus(item: ImportProposalObject) {
  const status = sourceField(item, ["status", "状态"], "");
  return status || sourceStatusLabel(item.review_status);
}

async function selectDisplayMode(mode: DisplayMode) {
  if (displayMode.value === mode && route.query.view === (mode === "business" ? undefined : mode)) return;
  displayMode.value = mode;
  tableView.value = "list";
  const query = { ...route.query };
  if (mode === "business") delete query.view;
  else query.view = mode;
  await router.replace({ query });
  await loadActiveView();
}

async function loadBusiness() {
  const [assetsResponse, typeResponse] = await Promise.all([
    api.assets({ include_archived: businessFilters.include_archived, keyword: businessFilters.keyword }),
    api.assetTypes(),
  ]);
  businessAssets.value = assetsResponse.data;
  businessTypes.value = typeResponse;
  total.value = assetsResponse.pagination.total;
}

async function loadSource() {
  importBatches.value = await api.importBatches();
  const plans = await Promise.all(importBatches.value.map(async (batch) => {
    try { return await api.importPlan(batch.id); }
    catch { return null; }
  }));
  sourcePlans.value = plans.filter((item): item is ImportPlan => item !== null);
  total.value = sourceRows.value.length;
}

async function loadGovernance() {
  loading.value = true;
  error.value = "";
  try {
    const [layerResponses, typeResponse, entityResponse, departmentResponse, analytics] = await Promise.all([
      Promise.all(layerOptions.map((item) => api.layerRecords(item.value))),
      api.assetTypes(),
      api.legalEntities(),
      api.departments(),
      api.analytics(),
    ]);
    layerCounts.value = Object.fromEntries(
      layerOptions.map((item, index) => [item.value, layerResponses[index].length]),
    );
    records.value = layerResponses[layer.value - 1] ?? [];
    total.value = records.value.length;
    types.value = typeResponse;
    entities.value = entityResponse;
    departments.value = departmentResponse;
    categoryChart.value = analytics.by_category;
    if (!form.asset_type_id && types.value[0])
      form.asset_type_id = types.value[0].id;
    if (!form.legal_entity_id && entities.value[0])
      form.legal_entity_id = entities.value[0].id;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

async function loadActiveView() {
  loading.value = true;
  error.value = "";
  try {
    if (displayMode.value === "business") await loadBusiness();
    else if (displayMode.value === "source") await loadSource();
    else await loadGovernance();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

async function changeLayer(value: number) {
  layer.value = value;
  filters.keyword = "";
  filters.status = "";
  tableView.value = "list";
  await loadActiveView();
}

async function createAsset() {
  if (!form.name || !form.asset_type_id || !form.legal_entity_id) {
    error.value = "请填写资产名称、类型和公司主体";
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    await api.createAsset({
      ...form,
      owner_department_id: form.owner_department_id || null,
      expires_at: form.expires_at || null,
    });
    createOpen.value = false;
    form.name = "";
    form.description = "";
    form.expires_at = "";
    message.value = "资产已登记";
    await loadActiveView();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "保存失败";
  } finally {
    saving.value = false;
  }
}

async function previewFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  saving.value = true;
  try {
    importPreview.value = await api.previewImport(file);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "文件校验失败";
  } finally {
    saving.value = false;
  }
}
async function commitImport() {
  if (!importPreview.value) return;
  saving.value = true;
  try {
    await api.commitImport(importPreview.value);
    importOpen.value = false;
    importPreview.value = null;
    message.value = "有效数据已导入";
    await loadActiveView();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "导入失败";
  } finally {
    saving.value = false;
  }
}
onMounted(loadActiveView);
</script>

<template>
  <div class="page-stack">
    <PageHeader
      eyebrow="资产中心"
      title="资产底库"
      :description="currentDisplayMode.description"
    >
      <RouterLink class="secondary-button" to="/map">资产地图</RouterLink
      ><a class="secondary-button" :href="apiPath('/api/v1/exports/assets.xlsx')"
        ><Download :size="16" />导出</a
      ><RouterLink class="secondary-button" to="/imports"
        ><FileUp :size="16" />资料接入</RouterLink
      ><RouterLink class="primary-button" to="/intake"
        ><Plus :size="17" />登记 / 发现资产</RouterLink
      >
    </PageHeader>
    <div v-if="message" class="message-panel success-message">
      {{ message }}
    </div>
    <div v-if="error" class="message-panel error-message">{{ error }}</div>
    <section class="asset-view-tabs" aria-label="资产底库视图">
      <button :class="{ active: displayMode === 'business' }" @click="selectDisplayMode('business')">
        <strong>业务台账</strong><span>日常查看资产、归属和状态</span>
      </button>
      <button :class="{ active: displayMode === 'governance' }" @click="selectDisplayMode('governance')">
        <strong>六层治理</strong><span>管理员查看层级、关系和缺失项</span>
      </button>
      <button :class="{ active: displayMode === 'source' }" @click="selectDisplayMode('source')">
        <strong>原始台账</strong><span>核对来源记录和资产映射</span>
      </button>
    </section>

    <section v-if="displayMode === 'business'" class="ledger-view-identity business-view-identity">
      <div><span class="section-kicker">业务台账回答什么</span><strong>现在有哪些正式资产可以直接管理？</strong></div>
      <span>只看已建立的资产实例，不混入来源文件、候选对象和六层治理字段。</span>
    </section>

    <section v-else-if="displayMode === 'source'" class="ledger-view-identity source-view-identity">
      <div><span class="section-kicker">原始台账回答什么</span><strong>这条数据从哪里来，是否已经映射确认？</strong></div>
      <span>这里保留来源批次、原始记录和候选映射；它不是正式资产清单，也不参与业务资产数量统计。</span>
    </section>

    <section v-if="displayMode === 'business'" class="list-surface business-ledger-surface">
      <div class="section-heading business-ledger-heading">
        <div><span class="section-kicker">默认工作视图</span><h2>真实资产台账</h2><p>不要求先理解六层；需要治理信息时再切换到“六层治理”。</p></div>
        <span class="record-count">{{ filteredBusinessAssets.length }} / {{ total }} 项</span>
      </div>
      <div class="filter-grid business-filter-grid">
        <label class="table-search"><Search :size="17" /><input v-model="businessFilters.keyword" placeholder="搜索资产名称、编号或类型" @keyup.enter="loadActiveView" /></label>
        <label><span>状态</span><select v-model="businessFilters.status"><option value="">全部状态</option><option value="draft">草稿</option><option value="active">在用</option><option value="pending_handover">待接管</option><option value="paused">暂停</option><option value="archived">归档</option></select></label>
        <button class="secondary-button" @click="loadActiveView"><Filter :size="16" />刷新台账</button>
      </div>
      <div class="list-toolbar"><label class="check-label"><input v-model="businessFilters.include_archived" type="checkbox" @change="loadActiveView" />包含已归档</label><div class="toolbar-spacer" /><span class="ledger-note">同一资产在不同视图中使用同一个详情页</span></div>
      <div class="asset-table-wrap">
        <table class="asset-table business-ledger-table"><thead><tr><th>资产名称</th><th>资产类型</th><th>资产编号</th><th>归属范围</th><th>状态</th><th>到期时间</th><th>最后更新</th></tr></thead>
          <tbody><tr v-for="asset in filteredBusinessAssets" :key="asset.id"><td><RouterLink :to="`/assets/${asset.id}`"><strong>{{ asset.name }}</strong><span>查看资产详情</span></RouterLink></td><td><span class="type-tag">{{ assetTypeLabel(asset.asset_type_id) }}</span></td><td>{{ asset.asset_code }}</td><td>{{ asset.ownership_scope || "待确认" }}</td><td><StatusBadge :tone="asset.status === 'active' ? 'success' : 'warning'">{{ displayStatus(asset.status) }}</StatusBadge></td><td>{{ asset.expires_at ? new Date(asset.expires_at).toLocaleDateString('zh-CN') : '未设置' }}</td><td>{{ new Date(asset.updated_at).toLocaleString("zh-CN") }}</td></tr></tbody>
        </table>
        <div v-if="!loading && !filteredBusinessAssets.length" class="empty-state"><span class="empty-icon"><List :size="26" /></span><strong>暂无符合条件的资产</strong><p>可以调整搜索条件，或从“登记 / 发现资产”新增一条真实实例。</p></div>
        <div v-if="loading" class="loading-state">正在读取业务台账…</div>
      </div>
    </section>

    <section v-if="displayMode === 'governance'" class="layer-browser-guide" aria-label="六层浏览器">
      <div class="layer-browser-heading">
        <span class="section-kicker">第一步：选择查看层级</span>
        <h2>你想看什么，就只看什么。</h2>
        <p>
          默认展示第六层实体服务/资源。只有来源中真实存在的对象才会出现在相应层级，空层级不自动补造。
        </p>
      </div>
      <div class="layer-tabs" role="tablist" aria-label="六层数据筛选">
        <button
          v-for="item in layerOptions"
          :key="item.value"
          :class="{ active: layer === item.value }"
          role="tab"
          :aria-selected="layer === item.value"
          @click="changeLayer(item.value)"
        >
          <b>L{{ item.value }}</b
          ><span>{{ item.label }}</span
          ><small>{{ item.hint }} · {{ layerCounts[item.value] ?? "—" }} 项</small>
        </button>
      </div>
    </section>

    <section v-if="displayMode === 'governance'" class="list-surface">
      <div class="filter-grid">
        <label class="table-search"
          ><Search :size="17" /><input
            v-model="filters.keyword"
            :placeholder="`搜索${currentLayer.label}名称、平台或公司`"
        /></label>
        <label
          ><span>状态</span
          ><select v-model="filters.status">
            <option value="">全部状态</option>
            <option value="draft">草稿</option>
            <option value="active">在用</option>
            <option value="pending_handover">待接管</option>
            <option value="paused">暂停</option>
            <option value="archived">归档</option>
          </select></label
        >
        <button class="secondary-button" @click="loadActiveView">
          <Filter :size="16" />刷新本层
        </button>
      </div>
      <div class="list-toolbar">
        <label class="check-label"
          ><input
            v-model="filters.include_archived"
            type="checkbox"
            @change="loadActiveView"
          />包含已归档</label
        >
        <div class="toolbar-spacer" />
        <div class="view-switch">
          <button :class="{ active: tableView === 'list' }" @click="tableView = 'list'">
            <List :size="16" />列表</button
          ><button
            :class="{ active: tableView === 'chart' }"
            @click="tableView = 'chart'"
          >
            <BarChart3 :size="16" />图表
          </button>
        </div>
        <button class="icon-button" aria-label="刷新" @click="loadActiveView">
          <RefreshCw :size="17" />
        </button>
      </div>
      <div v-if="tableView === 'chart'" class="chart-content">
        <SimpleBarChart :data="categoryChart" />
      </div>
      <div v-else class="asset-table-wrap">
        <table class="asset-table">
          <thead>
            <tr>
              <th>{{ currentLayer.label }}</th>
              <template v-if="layer === 1"><th>状态</th></template>
              <template v-else-if="layer === 2"><th>身份类型</th><th>归属性质</th><th>归属公司</th><th>关联平台</th><th>核验状态</th></template>
              <template v-else-if="layer === 3"><th>平台类别</th><th>状态</th></template>
              <template v-else-if="layer === 4"><th>所属平台</th><th>归属公司</th><th>所有权</th><th>账号 / 席位</th><th>核验状态</th></template>
              <template v-else-if="layer === 5"><th>归属公司</th><th>状态</th></template>
              <template v-else><th>对象类型</th><th>公司主体</th><th>所在平台 / 关联对象</th><th>状态</th></template>
              <th>最后更新</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in filteredRecords" :key="record.id">
              <td>
                <RouterLink v-if="detailPath(record)" :to="detailPath(record)!"
                  ><strong>{{ record.name }}</strong><span>查看对象详情</span></RouterLink
                >
                <div v-else>
                  <strong>{{ record.name }}</strong
                  ><span>目录对象</span>
                </div>
              </td>
              <template v-if="layer === 1">
                <td>
                  <StatusBadge tone="success">{{ displayStatus(record.status) }}</StatusBadge>
                </td>
              </template>
              <template v-else-if="layer === 2">
                <td>{{ record.object_type }}</td>
                <td>{{ ownershipLabel(record.ownership_nature) }}</td>
                <td>{{ record.legal_entity_name ?? "未关联" }}</td>
                <td>{{ record.platform_name ?? "未关联" }}</td>
                <td>
                  <StatusBadge tone="success">{{ displayStatus(record.status) }}</StatusBadge>
                </td>
              </template>
              <template v-else-if="layer === 3">
                <td>{{ categoryLabel(record.category) }}</td>
                <td>
                  <StatusBadge tone="success">{{ displayStatus(record.status) }}</StatusBadge>
                </td>
              </template>
              <template v-else-if="layer === 4">
                <td>{{ record.platform_name ?? "未关联" }}</td>
                <td>{{ record.legal_entity_name ?? "未关联" }}</td>
                <td>{{ ownershipLabel(record.ownership_nature) }}</td>
                <td>{{ record.account_count }} 项</td>
                <td>
                  <StatusBadge tone="success">{{ displayStatus(record.status) }}</StatusBadge>
                </td>
              </template>
              <template v-else-if="layer === 5">
                <td>{{ record.legal_entity_name ?? "未关联" }}</td>
                <td>
                  <StatusBadge tone="success">{{ displayStatus(record.status) }}</StatusBadge>
                </td>
              </template>
              <template v-else>
                <td>{{ record.object_type }}</td>
                <td>{{ record.legal_entity_name ?? "—" }}</td>
                <td>
                  <strong v-if="record.platform_name">{{ record.platform_name }}</strong><span v-else>—</span>
                  <small v-if="record.layer === 4">账号与席位 {{ record.account_count }} 项</small>
                </td>
                <td>
                  <StatusBadge tone="success">{{ displayStatus(record.status) }}</StatusBadge>
                </td>
              </template>
              <td>
                {{ new Date(record.updated_at).toLocaleString("zh-CN") }}
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!loading && !filteredRecords.length" class="empty-state">
          <span class="empty-icon"><List :size="26" /></span
          ><strong>{{ currentLayer.label }}暂无已登记对象</strong>
          <p>
            这不是缺失；只有来源中真实存在、需要独立管理的对象才会出现在这一层。
          </p>
        </div>
        <div v-if="loading" class="loading-state">
          正在读取{{ currentLayer.label }}…
        </div>
      </div>
    </section>

    <section v-if="displayMode === 'source'" class="source-ledger-shell">
      <div class="source-ledger-heading">
        <div>
          <span class="section-kicker">老板材料 · AI 资产主台账</span>
          <h2>所有订阅、API、服务和系统统一放在这里看</h2>
          <p>沿用原账号分发系统的业务字段；按材料中的实际类型分组，展开后查看这一组资产的完整台账。</p>
        </div>
        <div class="source-ledger-actions">
          <button class="secondary-button" @click="setSourceGroupsOpen(true)">全部展开</button>
          <button class="secondary-button" @click="setSourceGroupsOpen(false)">全部折叠</button>
        </div>
      </div>

      <div class="source-ledger-kpis">
        <article><span>材料批次</span><strong>{{ importBatches.length }}</strong><small>老板材料来源</small></article>
        <article><span>台账记录</span><strong>{{ sourceRows.length }}</strong><small>按实际类型分组</small></article>
        <article><span>已确认</span><strong>{{ sourceLedgerConfirmedCount }}</strong><small>已完成映射确认</small></article>
        <article><span>待确认</span><strong>{{ sourceRows.length - sourceLedgerConfirmedCount }}</strong><small>保留原始事实</small></article>
      </div>

      <div class="source-ledger-source-strip">
        <FileUp :size="18" />
        <div>
          <strong>来源材料</strong>
          <span>{{ importBatches.map((batch) => batch.file_name).join("、") || "暂未接入老板材料" }}</span>
        </div>
        <RouterLink v-if="importBatches[0]" class="secondary-button" :to="`/imports?batch=${importBatches[0].id}`">打开资料接入</RouterLink>
      </div>

      <div v-if="sourceLedgerGroups.length" class="source-ledger-groups">
        <article v-for="group in sourceLedgerGroups" :key="group.label" class="source-ledger-group">
          <header>
            <button class="source-group-toggle" @click="toggleSourceGroup(group.label)">
              <ChevronDown :size="18" :class="{ rotated: !sourceGroupIsOpen(group.label) }" />
              <span><strong>{{ group.label }}</strong><small>{{ group.rows.length }} 项 · {{ group.confirmedCount }} 项已确认 · {{ group.sourceFiles.join("、") || "来源待确认" }}</small></span>
            </button>
            <StatusBadge :tone="group.confirmedCount === group.rows.length ? 'success' : 'warning'">{{ group.confirmedCount }}/{{ group.rows.length }} 已确认</StatusBadge>
          </header>
          <div v-if="sourceGroupIsOpen(group.label)" class="source-ledger-table-wrap">
            <table class="source-ledger-table">
              <thead><tr><th>资产ID</th><th>类型</th><th>工具 / 服务</th><th>套餐 / 用途</th><th>使用人</th><th>部门</th><th>账号引用</th><th>付款方式</th><th>预算 / 费用</th><th>状态</th><th>续费 / 到期</th><th>备注</th><th>来源 / 映射</th></tr></thead>
              <tbody>
                <tr v-for="item in group.rows" :key="item.id">
                  <td><strong>{{ item.source_reference || item.proposal_key }}</strong><small>{{ item.layer_code }} · {{ item.suggested_name }}</small></td>
                  <td><span class="type-tag">{{ item.object_type }}</span></td>
                  <td>{{ sourceField(item, ["service_name", "service", "platform_name", "product_name", "工具服务", "平台服务"], item.suggested_name) }}</td>
                  <td>{{ sourceField(item, ["usage", "purpose", "subscription_name", "套餐用途", "用途" ]) }}</td>
                  <td>{{ sourceField(item, ["user_name", "user", "owner_name", "owner", "使用人", "负责人" ]) }}</td>
                  <td>{{ sourceField(item, ["department_name", "department", "部门" ]) }}</td>
                  <td>{{ sourceField(item, ["account_ref", "account_reference", "login_identifier", "email", "phone", "账号引用", "手机号", "邮箱" ]) }}</td>
                  <td>{{ sourceField(item, ["payment_method", "payment", "billing_method", "付款方式", "结算方式" ]) }}</td>
                  <td>{{ sourceField(item, ["monthly_budget_usd", "monthly_budget_rmb", "monthly_cost", "amount", "预算", "费用" ]) }}</td>
                  <td><StatusBadge :tone="item.review_status === 'approved' ? 'success' : 'warning'">{{ sourceLedgerStatus(item) }}</StatusBadge></td>
                  <td>{{ sourceField(item, ["renewal_date", "renewal_day", "expires_at", "续费日", "到期时间" ]) }}</td>
                  <td class="source-ledger-note">{{ sourceField(item, ["note", "remark", "description", "备注" ], sourcePreview(item)) }}</td>
                  <td><span>{{ item.source_file || "来源待确认" }}</span><RouterLink v-if="item.matched_asset_id" :to="`/assets/${item.matched_asset_id}`">查看正式资产</RouterLink><small v-else class="missing-value">尚未映射</small></td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>
      </div>
      <div v-else-if="!loading" class="empty-state source-ledger-empty"><span class="empty-icon"><List :size="26" /></span><strong>暂无老板材料台账</strong><p>资料接入并建立规划后，会按照实际类型在这里形成可折叠的业务台账。</p></div>
      <div v-if="loading" class="loading-state">正在读取老板材料台账…</div>
    </section>

    <ModalPanel
      v-if="createOpen"
      title="登记资产"
      description="先保存共性资料，保存后可继续补充责任、关系和专属资料。"
      wide
      @close="createOpen = false"
    >
      <form class="form-grid" @submit.prevent="createAsset">
        <label class="span-2"
          ><span>资产名称 *</span
          ><input
            v-model="form.name"
            required
            placeholder="例如：阿里云企业主账号" /></label
        ><label
          ><span>资产类型 *</span
          ><select v-model="form.asset_type_id" required>
            <option v-for="item in types" :key="item.id" :value="item.id">
              {{ item.name }}
            </option>
          </select></label
        ><label
          ><span>所有权公司 *</span
          ><select v-model="form.legal_entity_id" required>
            <option value="" disabled>请选择</option>
            <option v-for="item in entities" :key="item.id" :value="item.id">
              {{ item.name }}
            </option>
          </select></label
        ><label
          ><span>归属部门</span
          ><select v-model="form.owner_department_id">
            <option value="">待补充</option>
            <option v-for="item in departments" :key="item.id" :value="item.id">
              {{ item.name }}
            </option>
          </select></label
        ><label
          ><span>当前状态</span
          ><select v-model="form.status">
            <option value="draft">草稿</option>
            <option value="active">在用</option>
            <option value="pending_handover">待接管</option>
            <option value="paused">暂停</option>
          </select></label
        ><label
          ><span>重要程度</span
          ><select v-model="form.criticality">
            <option value="normal">普通</option>
            <option value="important">重要</option>
            <option value="critical">关键</option>
          </select></label
        ><label
          ><span>保密级别</span
          ><select v-model="form.confidentiality">
            <option value="public">公开</option>
            <option value="internal">内部</option>
            <option value="sensitive">敏感</option>
            <option value="restricted">严格受限</option>
          </select></label
        ><label
          ><span>到期日期</span
          ><input v-model="form.expires_at" type="date" /></label
        ><label class="span-2"
          ><span>用途与说明</span
          ><textarea
            v-model="form.description"
            rows="3"
            placeholder="说明业务用途、进入方式或待补充事项"
          />
        </label>
        <div class="form-actions span-2">
          <button
            type="button"
            class="secondary-button"
            @click="createOpen = false"
          >
            取消</button
          ><button class="primary-button" :disabled="saving">
            {{ saving ? "保存中…" : "保存并进入底库" }}
          </button>
        </div>
      </form>
    </ModalPanel>

    <ModalPanel
      v-if="importOpen"
      title="Excel批量盘点"
      description="下载模板、填写后上传；系统先校验预览，再正式写入。"
      wide
      @close="importOpen = false"
    >
      <div class="import-panel">
          <a class="secondary-button" :href="apiPath('/api/v1/imports/template')"
          ><Download :size="16" />下载标准模板</a
        ><label class="upload-zone"
          ><FileUp :size="28" /><strong>选择 .xlsx 或 .csv 文件</strong
          ><span>文件不会直接入库，必须先通过预览校验</span
          ><input type="file" accept=".xlsx,.csv" @change="previewFile"
        /></label>
        <div v-if="importPreview" class="import-summary">
          <strong
            >校验完成：{{ importPreview.valid_count }} 条可导入，{{
              importPreview.error_count
            }}
            条有错误</strong
          >
          <div class="preview-rows">
            <div
              v-for="row in importPreview.rows.slice(0, 8)"
              :key="String(row.row_number)"
            >
              <span
                >第 {{ row.row_number }} 行 · {{ row.name || "未命名" }}</span
              ><StatusBadge
                :tone="(row.errors as string[]).length ? 'warning' : 'success'"
                >{{
                  (row.errors as string[]).length
                    ? (row.errors as string[]).join("、")
                    : "可导入"
                }}</StatusBadge
              >
            </div>
          </div>
          <button
            class="primary-button"
            :disabled="saving || !importPreview.valid_count"
            @click="commitImport"
          >
            确认导入有效数据
          </button>
        </div>
      </div>
    </ModalPanel>
  </div>
</template>
