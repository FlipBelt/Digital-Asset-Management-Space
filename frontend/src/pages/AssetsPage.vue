<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
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
import AssetStructureGuide from "../components/AssetStructureGuide.vue";
import { assetStructureCategories } from "../lib/assetStructure";
import PageHeader from "../components/PageHeader.vue";
import SimpleBarChart from "../components/SimpleBarChart.vue";
import StatusBadge from "../components/StatusBadge.vue";
import WorkspaceTabs from "../components/WorkspaceTabs.vue";
import { canRegisterBasics } from "../lib/managementWorkspace";
import {
  api,
  apiPath,
  type Asset,
  type CurrentUser,
  type AssetType,
  type AssetCategory,
  type Department,
  type ImportPreview,
  type ImportBatch,
  type ImportPlan,
  type ImportProposalObject,
  type LayerRecord,
  type LegalEntity,
} from "../lib/api";
import { displayStatus } from "../lib/labels";
import { isPersonalSubscription, subscriptionStatus } from "../lib/personalSubscriptions";

const loading = ref(true);
let loadSequence = 0;
const saving = ref(false);
const error = ref("");
const message = ref("");
const records = ref<LayerRecord[]>([]);
const total = ref(0);
const businessAssets = ref<Asset[]>([]);
const businessTypes = ref<AssetType[]>([]);
const businessCategories = ref<AssetCategory[]>([]);
const currentUser = ref<CurrentUser | null>(null);
const trashOpen = ref(false);
const businessPage = ref(1);
const pageSize = 50;
const mutationTarget = ref<Asset | null>(null);
const mutationKind = ref<"delete" | "restore">("delete");
const mutationBusy = ref(false);
const mutationError = ref("");
const canDelete = computed(() => {
  const user = currentUser.value;
  return !!user && (user.roles.includes("system_admin") ||
    (user.roles.includes("asset_manager") && user.permissions.includes("asset.write")));
});
function openMutation(asset: Asset, kind: "delete" | "restore") {
  mutationTarget.value = asset;
  mutationKind.value = kind;
  mutationError.value = "";
}
function closeMutation() {
  if (!mutationBusy.value) mutationTarget.value = null;
}
async function mutateAsset() {
  const asset = mutationTarget.value;
  if (!asset || mutationBusy.value) return;
  mutationBusy.value = true;
  mutationError.value = "";
  try {
    if (mutationKind.value === "delete") await api.deleteAsset(asset.id, asset.version);
    else await api.restoreAsset(asset.id, asset.version);
    message.value = mutationKind.value === "delete"
      ? `已删除“${asset.name}”，可在回收站恢复。`
      : `已恢复“${asset.name}”${asset.sharing_scope ? "，请重新核对、确认并审核当前版本。" : "。"}`;
    mutationTarget.value = null;
    await loadActiveView();
  } catch (cause) {
    mutationError.value = cause instanceof Error ? cause.message : "操作失败，请重试";
  } finally { mutationBusy.value = false; }
}
async function refreshBusiness() {
  businessPage.value = 1;
  await loadActiveView();
}
async function switchTrash() {
  trashOpen.value = !trashOpen.value;
  await router.replace({ query: { ...route.query, trash: trashOpen.value ? "1" : undefined } });
  businessFilters.status = "";
  await refreshBusiness();
}
async function changeBusinessPage(delta: number) {
  businessPage.value += delta;
  await loadActiveView();
}
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
trashOpen.value = route.query.trash === "1";
const router = useRouter();
type DisplayMode = "business" | "governance" | "source";
function normalizeDisplayMode(value: unknown): DisplayMode {
  return value === "governance" || value === "source" ? value : "business";
}
const displayMode = ref<DisplayMode>(normalizeDisplayMode(route.query.view));
function queryText(value: unknown) { return typeof value === "string" ? value : ""; }
const businessCategory = ref(queryText(route.query.category) || "all");
const businessFilters = reactive({ keyword: "", status: "", department_id: "", asset_type_id: queryText(route.query.type), include_archived: false });
const hasBusinessFilters = computed(() => !!(businessFilters.keyword || businessFilters.status || businessFilters.department_id || businessFilters.asset_type_id || businessFilters.include_archived));
const businessCategoryTabs = computed(() => [{ value: "all", label: "全部资产" }, ...[...businessCategories.value]
  .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name, "zh-CN"))
  .map(item => ({ value: item.id, label: item.name }))]);
const availableBusinessTypes = computed(() => businessTypes.value.filter(item => businessCategory.value === "all" || item.category_id === businessCategory.value));
const selectedCategoryName = computed(() => businessCategoryTabs.value.find(item => item.value === businessCategory.value)?.label || "所选分类");
async function selectBusinessCategory(value: string) {
  if (businessCategory.value === value) return;
  businessCategory.value = value; businessFilters.asset_type_id = ""; businessPage.value = 1;
  await router.replace({ query: { ...route.query, category: value === "all" ? undefined : value, type: undefined } });
  await loadActiveView();
}
async function selectBusinessType() {
  businessPage.value = 1;
  await router.replace({ query: { ...route.query, type: businessFilters.asset_type_id || undefined } });
  await loadActiveView();
}
async function clearBusinessFilters() {
  Object.assign(businessFilters, { keyword: "", status: "", department_id: "", asset_type_id: "", include_archived: false });
  await selectBusinessType();
}
function departmentLabel(asset: Asset) {
  return departments.value.find(item => item.id === asset.owner_department_id)?.name || ownershipScopeLabel(asset.ownership_scope);
}
const layerOptions = assetStructureCategories;
const currentLayer = computed(
  () =>
    layerOptions.find((item) => item.value === layer.value) ?? layerOptions[5],
);
const displayModeMeta: Record<DisplayMode, { label: string; description: string }> = {
  business: { label: "资产清单", description: "按分类查看公司资产，搜索名称、编号，或筛选类型、部门和状态。" },
  governance: { label: "账号与资源结构", description: "按公司、登录身份、平台、企业账号、人员授权和具体资源查看；各类资料独立登记，关联按实际情况补充。" },
  source: { label: "来源资料", description: "查看资料来源，以及它们与正式资产的关联和确认状态。" },
};
const currentDisplayMode = computed(() => displayModeMeta[displayMode.value]);
function ownershipScopeLabel(value: string | null | undefined) {
  return ({ company: "公司统一管理", department: "部门管理", pending: "待确认" } as Record<string,string>)[value ?? ""] ?? value ?? "待确认";
}
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

const filteredBusinessAssets = computed(() => businessAssets.value);

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

async function loadBusiness(sequence = loadSequence) {
  const [assetsResponse, typeResponse, user, departmentRows, categoryRows] = await Promise.all([
    api.assets({ include_archived: !trashOpen.value && businessFilters.include_archived,
      deleted_only: trashOpen.value, keyword: businessFilters.keyword,
      status: businessFilters.status, department_id: businessFilters.department_id || undefined,
      category_id: businessCategory.value === "all" ? undefined : businessCategory.value,
      asset_type_id: businessFilters.asset_type_id || undefined, page: businessPage.value, page_size: pageSize }),
    api.assetTypes(),
    api.currentSession(),
    api.departments(),
    api.assetCategories(),
  ]);
  if (sequence !== loadSequence) return;
  currentUser.value = user;
  departments.value = departmentRows;
  businessCategories.value = categoryRows;
  if (businessPage.value > 1 && !assetsResponse.data.length) {
    businessPage.value = Math.max(1, Math.ceil(assetsResponse.pagination.total / pageSize));
    return loadBusiness(sequence);
  }
  businessAssets.value = assetsResponse.data;
  businessTypes.value = typeResponse;
  total.value = assetsResponse.pagination.total;
}

async function loadSource(sequence = loadSequence) {
  const batches = await api.importBatches();
  const plans = await Promise.all(batches.map(async (batch) => {
    try { return await api.importPlan(batch.id); }
    catch { return null; }
  }));
  if (sequence !== loadSequence) return;
  importBatches.value = batches;
  sourcePlans.value = plans.filter((item): item is ImportPlan => item !== null);
  total.value = sourceRows.value.length;
}

async function loadGovernance(sequence = loadSequence) {
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
    if (sequence !== loadSequence) return;
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
    if (sequence === loadSequence) error.value = reason instanceof Error ? reason.message : "加载失败";
  } finally {
    if (sequence === loadSequence) loading.value = false;
  }
}

async function loadActiveView() {
  const sequence = ++loadSequence;
  loading.value = true;
  error.value = "";
  try {
    if (displayMode.value === "business") await loadBusiness(sequence);
    else if (displayMode.value === "source") await loadSource(sequence);
    else await loadGovernance(sequence);
  } catch (reason) {
    if (sequence === loadSequence) error.value = reason instanceof Error ? reason.message : "加载失败";
  } finally {
    if (sequence === loadSequence) loading.value = false;
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
watch(() => [route.query.trash, route.query.view, route.query.category, route.query.type], async ([trash, view, category, type]) => {
  const nextTrash = trash === "1"; const nextMode = normalizeDisplayMode(view);
  const nextCategory = queryText(category) || "all"; const nextType = queryText(type);
  if (nextTrash === trashOpen.value && nextMode === displayMode.value && nextCategory === businessCategory.value && nextType === businessFilters.asset_type_id) return;
  trashOpen.value = nextTrash; displayMode.value = nextMode; businessPage.value = 1; tableView.value = "list";
  businessCategory.value = nextCategory; businessFilters.asset_type_id = nextType;
  await loadActiveView();
});
onMounted(loadActiveView);
</script>

<template>
  <div class="page-stack">
    <PageHeader eyebrow="管理区" :title="trashOpen && displayMode === 'business' ? '资产回收站' : '资产库'" :description="currentDisplayMode.description">
      <a class="secondary-button" :href="apiPath('/api/v1/exports/assets.xlsx')"><Download :size="16" />导出</a>
      <RouterLink v-if="canRegisterBasics(currentUser)" class="primary-button" to="/intake"><Plus :size="17" />登记资产</RouterLink>
    </PageHeader>
    <div v-if="message" role="status" class="message-panel success-message">{{ message }}</div>
    <div v-if="error" role="alert" class="message-panel error-message">{{ error }}<button class="secondary-button" :disabled="loading" @click="loadActiveView">重试</button></div>
    <div class="asset-library-tools">
      <label><span>查看</span><select :value="displayMode" aria-label="资产视图" @change="selectDisplayMode(($event.target as HTMLSelectElement).value as DisplayMode)"><option value="business">资产清单</option><option value="governance">账号与关联</option><option value="source">来源资料</option></select></label>
      <div><RouterLink to="/discover">浏览 AI 成果</RouterLink><RouterLink v-if="canRegisterBasics(currentUser)" to="/imports">批量导入资料</RouterLink></div>
    </div>

    <section v-if="displayMode === 'business'" class="list-surface asset-library-surface">
      <WorkspaceTabs :model-value="businessCategory" :tabs="businessCategoryTabs" label="资产分类" id-prefix="asset-category" @update:model-value="selectBusinessCategory" />
      <div id="asset-category-panel" role="tabpanel" :aria-labelledby="`asset-category-${businessCategory}`" :aria-busy="loading">
        <form class="asset-library-filters" role="search" aria-label="筛选资产" @submit.prevent="refreshBusiness">
          <label class="asset-library-search"><span class="sr-only">搜索资产</span><Search :size="17" aria-hidden="true" /><input v-model="businessFilters.keyword" type="search" placeholder="搜索名称、编号或平台标识" /></label>
          <label><span class="sr-only">资产类型</span><select v-model="businessFilters.asset_type_id" aria-label="筛选资产类型" @change="selectBusinessType"><option value="">全部类型</option><option v-for="item in availableBusinessTypes" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label><span class="sr-only">归属部门</span><select v-model="businessFilters.department_id" aria-label="筛选归属部门" @change="refreshBusiness"><option value="">全部部门</option><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label v-if="!trashOpen"><span class="sr-only">资产状态</span><select v-model="businessFilters.status" aria-label="筛选资产状态" @change="refreshBusiness"><option value="">全部状态</option><option value="draft">草稿</option><option value="active">在用</option><option value="pending_handover">待接管</option><option value="paused">暂停</option><option value="archived">归档</option></select></label>
          <button class="secondary-button" :disabled="loading"><Search :size="16" />搜索</button>
        </form>
        <div class="asset-library-summary">
          <span role="status">{{ selectedCategoryName }} · {{ loading ? '读取中…' : `共 ${total} 项` }}</span>
          <div><label v-if="!trashOpen" class="check-label"><input v-model="businessFilters.include_archived" type="checkbox" @change="refreshBusiness" />包含已归档</label><button v-if="hasBusinessFilters" class="fusion-clear-button" @click="clearBusinessFilters">清除筛选</button><button v-if="canDelete" class="secondary-button" :disabled="loading" @click="switchTrash">{{ trashOpen ? '返回资产库' : '回收站' }}</button></div>
        </div>
        <p v-if="trashOpen" class="ledger-note">删除的资产保留资料、附件和审计，可恢复。恢复 AI 成果后需重新确认和审核。</p>
        <div v-if="loading" role="status" class="loading-state">正在读取资产…</div>
        <div v-else-if="!error && !filteredBusinessAssets.length" class="empty-state"><List :size="26" aria-hidden="true" /><strong>{{ trashOpen ? '回收站暂无符合条件的资产' : '暂无符合条件的资产' }}</strong><p>{{ hasBusinessFilters ? '可以调整或清除筛选条件。' : '可以切换分类查看其他资产。' }}</p><button v-if="hasBusinessFilters" class="secondary-button" @click="clearBusinessFilters">清除筛选</button><button v-else-if="businessCategory !== 'all'" class="secondary-button" @click="selectBusinessCategory('all')">查看全部资产</button><RouterLink v-else-if="canRegisterBasics(currentUser) && !trashOpen" to="/intake" class="secondary-button">登记资产</RouterLink></div>
        <div v-else-if="!error" class="asset-table-wrap">
          <table class="asset-table asset-library-table"><caption class="sr-only">{{ selectedCategoryName }}，共 {{ total }} 项资产，第 {{ businessPage }} 页</caption>
            <thead><tr><th scope="col">资产</th><th scope="col">类型</th><th scope="col">归属</th><th scope="col">状态</th><th scope="col">到期</th><th v-if="canDelete" scope="col">操作</th></tr></thead>
            <tbody><tr v-for="asset in filteredBusinessAssets" :key="asset.id">
              <td><strong v-if="asset.archived_at">{{ asset.name }}</strong><RouterLink v-else :to="`/assets/${asset.id}`" class="asset-name-link">{{ asset.name }}</RouterLink><small class="asset-code">{{ asset.asset_code }}</small></td>
              <td>{{ assetTypeLabel(asset.asset_type_id) }}<small v-if="isPersonalSubscription(asset)" class="asset-code"><StatusBadge>个人订阅</StatusBadge></small></td>
              <td><span>{{ departmentLabel(asset) }}</span><small v-if="isPersonalSubscription(asset)" class="asset-code">个人登记 · 无需审核</small><small v-else-if="asset.owner_department_id" class="asset-code">{{ ownershipScopeLabel(asset.ownership_scope) }}</small></td>
              <td><StatusBadge :tone="asset.status === 'active' || isPersonalSubscription(asset) && asset.status === 'draft' ? 'success' : 'warning'">{{ subscriptionStatus(asset) }}</StatusBadge></td>
              <td>{{ asset.expires_at ? new Date(asset.expires_at).toLocaleDateString('zh-CN') : '—' }}</td>
              <td v-if="canDelete"><button v-if="asset.archived_at" class="asset-row-action" :disabled="loading" :aria-label="`恢复资产 ${asset.name}`" @click="openMutation(asset, 'restore')">恢复</button><button v-if="!trashOpen" class="asset-row-action deletion-button" :disabled="loading" :aria-label="`删除资产 ${asset.name}`" @click="openMutation(asset, 'delete')">删除</button></td>
            </tr></tbody>
          </table>
        </div>
        <div v-if="!error" class="asset-library-pagination" aria-label="资产分页"><span>第 {{ businessPage }} / {{ Math.max(1, Math.ceil(total / pageSize)) }} 页</span><div><button class="secondary-button" :disabled="loading || businessPage <= 1" @click="changeBusinessPage(-1)">上一页</button><button class="secondary-button" :disabled="loading || businessPage * pageSize >= total" @click="changeBusinessPage(1)">下一页</button></div></div>
      </div>
    </section>

    <section v-if="displayMode === 'governance'" class="layer-browser-guide" aria-label="账号与资源分类">
      <div class="layer-browser-heading">
        <span class="section-kicker">选择要查看的资料</span>
        <h2>按业务名称查看，不用记层级编号。</h2>
        <p>
          默认查看系统、订阅与资源。公司、登录身份和账号独立维护，不需要为一项资产补齐所有类别。
        </p>
      </div>
      <div class="layer-tabs" role="group" aria-label="按资料类别筛选">
        <button
          v-for="item in layerOptions"
          :key="item.value"
          :class="{ active: layer === item.value }"
          :aria-pressed="layer === item.value"
          @click="changeLayer(item.value)"
        >
          <span>{{ item.label }}</span
          ><small>{{ item.hint }} · {{ layerCounts[item.value] ?? "—" }} 项</small>
        </button>
      </div>
    </section>

    <section v-if="displayMode === 'governance'" class="governance-context content-panel"><div><h3>{{ currentLayer.label }}：{{ currentLayer.hint }}</h3><p>例如：{{ currentLayer.example }}。{{ currentLayer.when }}</p></div><RouterLink :to="{path:'/intake',query:{mode:currentLayer.mode}}" class="secondary-button">{{ layer === 5 ? '分配使用权' : '登记这类资料' }}</RouterLink></section>
    <AssetStructureGuide v-if="displayMode === 'governance'" />

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
          <span class="section-kicker">来源资料</span>
          <h2>核对来源与资产关联</h2>
          <p>按资料中的实际类型分组，查看原始记录、确认状态与关联的资产。</p>
        </div>
        <div class="source-ledger-actions">
          <button class="secondary-button" @click="setSourceGroupsOpen(true)">全部展开</button>
          <button class="secondary-button" @click="setSourceGroupsOpen(false)">全部折叠</button>
        </div>
      </div>

      <div class="source-ledger-kpis">
        <article><span>材料批次</span><strong>{{ importBatches.length }}</strong><small>保留资料来源</small></article>
        <article><span>资产记录</span><strong>{{ sourceRows.length }}</strong><small>按实际类型分组</small></article>
        <article><span>已确认</span><strong>{{ sourceLedgerConfirmedCount }}</strong><small>已完成映射确认</small></article>
        <article><span>待确认</span><strong>{{ sourceRows.length - sourceLedgerConfirmedCount }}</strong><small>保留原始事实</small></article>
      </div>

      <div class="source-ledger-source-strip">
        <FileUp :size="18" />
        <div>
          <strong>来源材料</strong>
          <span>{{ importBatches.map((batch) => batch.file_name).join("、") || "暂未接入资料" }}</span>
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
                  <td><strong>{{ item.source_reference || item.proposal_key }}</strong><small>{{ item.suggested_name }}</small></td>
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
      <div v-else-if="!loading" class="empty-state source-ledger-empty"><span class="empty-icon"><List :size="26" /></span><strong>暂无来源资料</strong><p>接入资料后，按实际类型在这里查看原始记录和资产关联。</p></div>
      <div v-if="loading" class="loading-state">正在读取来源资料…</div>
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
    <ModalPanel v-if="mutationTarget" :title="mutationKind === 'delete' ? '删除资产' : '恢复资产'" description="请核对本次操作的资产" trap-focus @close="closeMutation">
      <div class="asset-mutation-body" :aria-busy="mutationBusy" @keydown.esc="closeMutation">
        <strong>{{ mutationTarget.name }}</strong>
        <p>资产编号：{{ mutationTarget.asset_code }} · 资料修订 {{ mutationTarget.version }}</p>
        <p v-if="mutationKind === 'delete'">删除后移入回收站，可由资产管理员恢复。保留资料、附件与审计记录；不删除仓库，也不注销外部账号或资源。</p>
        <p v-else>{{ mutationTarget.sharing_scope ? "恢复为待核验草稿，需重新确认和审核；不会沿用旧版的通过状态。" : "恢复后重新显示在资产。" }}</p>
        <p v-if="mutationError" role="alert" class="error-banner">{{ mutationError }}；可取消后刷新资产列表，重新核对再操作。</p>
      </div>
      <template #footer><button class="secondary-button" :disabled="mutationBusy" @click="closeMutation">取消</button><button :class="['primary-button', { 'deletion-confirm': mutationKind === 'delete' }]" :disabled="mutationBusy" @click="mutateAsset">{{ mutationBusy ? "正在处理…" : mutationKind === 'delete' ? "确认删除" : "确认恢复" }}</button></template>
    </ModalPanel>
  </div>
</template>

<style scoped>
.asset-library-tools { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; color:var(--muted); }
.asset-library-tools label, .asset-library-tools > div { display:flex; align-items:center; gap:16px; }
.asset-library-tools select { min-width:140px; }
.asset-library-tools a { font-size:13px; text-decoration:underline; text-underline-offset:4px; }
.asset-library-surface { overflow:hidden; }
.asset-library-surface :deep(.workspace-tabs) { padding:0 20px; gap:24px; background:var(--surface); }
.asset-library-surface :deep(.workspace-tabs button) { min-height:52px; padding:15px 0; }
.asset-library-surface :deep(.workspace-tabs button.active) { border-bottom:3px solid var(--accent); }
.asset-library-filters { display:grid; grid-template-columns:minmax(210px,2fr) repeat(3,minmax(120px,1fr)) auto; align-items:center; gap:12px; padding:20px 20px 12px; }
.asset-library-filters > label { min-width:0; }
.asset-library-filters select { width:100%; }
.asset-library-search { display:flex; align-items:center; gap:10px; min-width:0; padding:0 12px; border:1px solid var(--border); border-radius:8px; color:var(--muted); }
.asset-library-search input { width:100%; min-width:0; padding:10px 0; border:0; background:transparent; box-shadow:none; }
.asset-library-search:focus-within { outline:2px solid var(--focus); outline-offset:2px; }
.asset-library-search input:focus-visible { outline:none; }
.asset-library-summary { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; padding:0 20px 16px; color:var(--muted); font-size:13px; }
.asset-library-summary > div { display:flex; align-items:center; flex-wrap:wrap; gap:16px; }
.asset-library-summary .secondary-button { min-height:36px; padding:7px 12px; }
.asset-library-table { min-width:720px; }
.asset-library-table th, .asset-library-table td { padding:16px 20px; font-size:14px; white-space:normal; }
.asset-library-table th { color:var(--muted); background:var(--surface-soft); font-size:12px; }
.asset-library-table th:first-child { width:34%; }
.asset-library-table td:first-child { min-width:240px; max-width:360px; }
.asset-library-table td { vertical-align:middle; }
.asset-library-table td:nth-child(5), .asset-library-table td:last-child { white-space:nowrap; }
.asset-name-link { font-weight:650; line-height:1.5; overflow-wrap:anywhere; }
.asset-name-link:hover { text-decoration:underline; text-underline-offset:3px; }
.asset-code { display:block; margin-top:5px; color:var(--muted); font-size:12px; overflow-wrap:anywhere; }
.asset-row-action { border:0; padding:8px 2px; background:transparent; font:inherit; cursor:pointer; }
.asset-row-action:hover { text-decoration:underline; text-underline-offset:4px; }
.asset-library-pagination { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:16px 20px; border-top:1px solid var(--border); color:var(--muted); font-size:13px; }
.asset-library-pagination > div { display:flex; gap:10px; }
.deletion-button { color:#a92a22; }
.page-stack :deep(.modal-panel) .deletion-confirm { background:#a92a22; color:#fff; }
.asset-mutation-body { overflow-wrap:anywhere; line-height:1.7; }
.asset-mutation-body p { margin:12px 0; }

.governance-context { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:16px; }
.governance-context > div { flex:1 1 300px; min-width:0; }
.governance-context h3, .governance-context p { margin:0; }
.governance-context p { margin-top:8px; color:var(--muted); line-height:1.7; }
.layer-browser-guide { grid-template-columns:1fr; }
.layer-tabs { grid-template-columns:repeat(3,minmax(0,1fr)); }
@media(max-width:1150px) {
  .asset-library-filters { grid-template-columns:repeat(3,minmax(0,1fr)); }
  .asset-library-search { grid-column:span 2; }
}
@media(max-width:650px) {
  .layer-tabs { grid-template-columns:1fr 1fr; }
  .asset-library-filters { grid-template-columns:1fr 1fr; padding:16px; }
  .asset-library-search { grid-column:span 2; }
  .asset-library-summary, .asset-library-pagination { padding:12px 16px; }
  .asset-library-summary > div { gap:10px; }
  .asset-library-tools { gap:16px; }
  .page-stack :deep(.page-actions) { width:100%; flex-wrap:wrap; }
}
</style>
