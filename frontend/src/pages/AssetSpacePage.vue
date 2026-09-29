<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowRight, CheckCircle2, CreditCard, FileSearch, LoaderCircle, Pencil, Plus, Search, Shield, Star } from "lucide-vue-next";
import PageHeader from "../components/PageHeader.vue";
import AssetCard from "../components/AssetCard.vue";
import WorkspaceTabs from "../components/WorkspaceTabs.vue";
import { assetCategoryLabel, workflowView } from "../lib/workspaceNavigation";
import { assetListPage } from "../lib/assetNavigation";
import { api, type Asset, type AssetCategory, type AssetType, type Department, type Membership, type SpaceSummary } from "../lib/api";

const props = defineProps<{ scope: "mine" | "discover" | "team" | "workflows" }>();
const route = useRoute(); const router = useRouter();
const assets = ref<Asset[]>([]); const types = ref<AssetType[]>([]); const departments = ref<Department[]>([]);
const categories = ref<AssetCategory[]>([]); const groupCounts = ref<Record<string, number>>({}); const catalogTotal = ref(0);
const group = ref("all"); const aiTypeIds = ref<string[]>([]);
const isWorkflow = computed(() => props.scope === "workflows");
const activeWorkflowView = computed(() => workflowView(route.query.view));
const workflowTabs = [{ value: "all", label: "全部工作流" }, { value: "created", label: "我创建的" }, { value: "bookmarks", label: "我的收藏" }];
const subscriptions = ref<Membership[]>([]); const saved = ref<string[]>([]);
const counts = ref<SpaceSummary | null>(null);
const keyword = ref(""); const type = ref(""); const department = ref(""); const defaultDepartment = ref("");
const feedback = ref("");
const loading = ref(false); const error = ref(""); const actionError = ref(""); const total = ref(0); const page = ref(1);
const identityKnown = ref(true); const bookmarkBusy = ref(""); let sequence = 0; let ready = false;
const personalLabels: Record<string, string> = {
  all: "我的首页", created: "我创建的", responsible: "我负责的", using: "我使用的",
  subscriptions: "我的订阅", ai: "我的 AI 能力", drafts: "我的草稿", bookmarks: "我的收藏",
};
const category = computed(() => {
  if (isWorkflow.value) return "workflows";
  const value = String(route.params.category || route.query.category || "all");
  return props.scope === "mine" ? (value in personalLabels ? value : "all") : (value === "workflows" ? value : "all");
});
const isHome = computed(() => props.scope === "mine" && category.value === "all");
const title = computed(() => props.scope === "mine" ? personalLabels[category.value] : props.scope === "team" ? "团队空间" : category.value === "workflows" ? "工作流" : "资产发现");
const description = computed(() => {
  if (category.value === "workflows") return "浏览可复用的工作流成果，查看使用方式与关联资产。";
  if (props.scope === "team") return "在团队中共享成果，找到资产和相应负责人。";
  if (props.scope === "discover") return "按分类查找公司资源和可复用成果，查看资料、负责人及使用方式。";
  return ({
    all: "从自己的成果、订阅与实践开始，让经验持续积累。",
    created: "查看你登记的 AI 成果和订阅记录，继续完善说明、附件和共享范围。",
    responsible: "查看需要你维护的资产，及时补充说明与使用范围。",
    subscriptions: "管理已登记的订阅，关联本人自费 AI 探索记录。",
    using: "找到与你的使用实践和授权关联的资产。",
    ai: "查看已沉淀的 AI 成果。能力与业务价值依据证据人工评审。",
    drafts: "继续整理未确认的 AI 成果或订阅记录，核对后再确认登记。",
    bookmarks: "把常用的资产放在一起，方便下次查找与复用。",
  } as Record<string, string>)[category.value];
});
const emptyAction = computed(() => {
  if (isWorkflow.value) return activeWorkflowView.value === "bookmarks"
    ? { to: "/workflows", label: "浏览全部工作流" }
    : { to: "/register?type=ai_workflow", label: "登记 AI 工作流" };
  if (category.value === "subscriptions") return { to: "/memberships/new", label: "登记订阅" };
  if (["bookmarks", "using", "responsible", "ai"].includes(category.value)) return { to: "/discover", label: "发现资产" };
  return { to: "/register", label: "登记 AI 成果" };
});
const filterTypes = computed(() => {
  if (props.scope !== "mine" && group.value !== "all") return types.value.filter(item => item.category_id === group.value);
  if (category.value === "workflows") return types.value.filter(item => item.code === "ai_workflow");
  if (category.value === "ai") return types.value.filter(item => aiTypeIds.value.includes(item.id));
  if (category.value === "subscriptions") return types.value.filter(item =>
    item.profile_kind === "service_instance" || assets.value.some(asset => asset.asset_type_id === item.id) || item.id === type.value);
  return types.value;
});
const hasFilters = computed(() => Boolean(keyword.value.trim() || type.value || group.value !== "all" ||
  (props.scope === "team" && department.value && department.value !== defaultDepartment.value)));
function queryText(value: unknown) { return typeof value === "string" ? value : ""; }
function restoreFilters() {
  keyword.value = queryText(route.query.q).slice(0, 200);
  const selectedGroup = queryText(route.query.group);
  group.value = props.scope !== "mine" && !isWorkflow.value && categories.value.some(item => item.id === selectedGroup) ? selectedGroup : "all";
  const selectedType = queryText(route.query.type);
  type.value = filterTypes.value.some(item => item.id === selectedType) ? selectedType : "";
  const selectedTeam = queryText(route.query.team);
  department.value = props.scope === "team" && departments.value.some(item => item.id === selectedTeam) ? selectedTeam : defaultDepartment.value;
  page.value = assetListPage(route.query.page);
}
async function syncFilters() {
  const query = { ...route.query, group: group.value === "all" ? undefined : group.value, q: keyword.value.trim() || undefined, type: type.value || undefined,
    team: props.scope === "team" && department.value !== defaultDepartment.value ? department.value || undefined : undefined,
    page: page.value > 1 ? String(page.value) : undefined };
  const target = router.resolve({ path: route.path, query }).fullPath;
  if (target === route.fullPath) await load();
  else await router.replace({ query });
}
function search() { page.value = 1; void syncFilters(); }
function clearFilters() {
  keyword.value = ""; type.value = ""; group.value = "all"; department.value = defaultDepartment.value; page.value = 1;
  if (isWorkflow.value) { void router.replace({ query: { ...route.query, q: undefined, type: undefined, group: undefined, page: undefined } }); }
  else void syncFilters();
}
function goPage(value: number) { page.value = value; void syncFilters(); }

const fundingLabels: Record<string, string> = { personal: "个人自费", company: "公司付费", department: "部门付费", free: "免费", trial: "试用" };
const discoveryTabs = computed(() => [
  { value: "all", label: "全部资产", count: catalogTotal.value },
  ...categories.value.map(item => ({ value: item.id, label: assetCategoryLabel(item), count: groupCounts.value[item.id] ?? 0 })),
]);
const sections = computed(() => {
  if (props.scope === "mine" || group.value !== "all" || category.value === "workflows") return [{ id: "current", label: "", assets: assets.value }];
  const grouped = categories.value.map(item => ({ id: item.id, label: assetCategoryLabel(item), assets: assets.value.filter(asset => types.value.find(type => type.id === asset.asset_type_id)?.category_id === item.id) })).filter(item => item.assets.length);
  const known = new Set(grouped.flatMap(item => item.assets.map(asset => asset.id)));
  const other = assets.value.filter(asset => !known.has(asset.id));
  if (other.length) grouped.push({ id: "uncatalogued", label: "类型待核对", assets: other });
  return grouped;
});
function selectWorkflow(value: string) {
  void router.replace({ query: { ...route.query, view: value === "all" ? undefined : workflowView(value), group: undefined, type: undefined, page: undefined } });
}
function selectGroup(value: string) {
  void router.replace({ query: { ...route.query, group: value === "all" ? undefined : value,
    category: undefined, type: undefined, page: undefined } });
}

async function load() {
  const request = ++sequence; loading.value = true; error.value = ""; assets.value = [];
  try {
    const params = {
      scope: isWorkflow.value ? "discover" : props.scope, category: category.value, keyword: keyword.value, page: String(page.value),
      ...(isWorkflow.value ? { workflow_view: activeWorkflowView.value } : {}),
      page_size: isHome.value ? "6" : "24", ...(type.value ? { asset_type_id: type.value } : {}),
      ...(department.value && props.scope === "team" ? { department_id: department.value } : {}),
      ...(props.scope !== "mine" && group.value !== "all" ? { asset_category_id: group.value } : {}),
    };
    const [result, groups] = await Promise.all([api.spaceAssets(params), props.scope === "mine" || isWorkflow.value ? Promise.resolve(null) : api.spaceGroups({ scope: props.scope, ...(props.scope === "team" && department.value ? { department_id: department.value } : {}) })]);
    if (request !== sequence) return;
    if (groups) { categories.value = groups.categories; catalogTotal.value = groups.total; groupCounts.value = Object.fromEntries(groups.categories.map(item => [item.id, item.count])); }
    total.value = result.pagination.total;
    const lastPage = Math.max(1, Math.ceil(total.value / 24));
    if (!isHome.value && page.value > lastPage) { page.value = lastPage; await syncFilters(); return; }
    assets.value = result.data;
  } catch (reason) { if (request === sequence) error.value = reason instanceof Error ? reason.message : "暂时无法读取资产"; }
  finally { if (request === sequence) loading.value = false; }
}
async function initialize() {
  loading.value = true; error.value = "";
  try {
    const user = await api.currentSession();
    identityKnown.value = Boolean(user.person_id);
    const [catalog, categoryRows, teams, bookmarks, summary, memberships, aiCatalog] = await Promise.all([
      api.assetTypes(), api.assetCategories(), api.departments(), user.person_id ? api.spaceBookmarks() : Promise.resolve([]),
      api.spaceSummary(), user.person_id ? api.spaceMemberships() : Promise.resolve([]), api.aiRegistrationTypes(),
    ]);
    aiTypeIds.value = aiCatalog.map(item => item.id);
    types.value = catalog; categories.value = categoryRows; departments.value = teams; saved.value = bookmarks;
    counts.value = summary; subscriptions.value = memberships; defaultDepartment.value = user.department_id ?? "";
    restoreFilters(); ready = true; await load();
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "初始化失败"; loading.value = false; }
}
async function toggleBookmark(asset: Asset) {
  if (bookmarkBusy.value) return;
  bookmarkBusy.value = asset.id; actionError.value = ""; feedback.value = "";
  try {
    const exists = saved.value.includes(asset.id);
    if (exists) await api.removeBookmark(asset.id); else await api.addBookmark(asset.id);
    saved.value = exists ? saved.value.filter(id => id !== asset.id) : [...saved.value, asset.id];
    if (category.value === "bookmarks") await load();
    feedback.value = `${exists ? '已取消收藏' : '已收藏'}：${asset.name}`;
  } catch (reason) { actionError.value = reason instanceof Error ? reason.message : "收藏保存失败"; }
  finally { bookmarkBusy.value = ""; }
}
onMounted(initialize);
watch(() => [props.scope, route.path, category.value, route.query.q, route.query.type, route.query.team, route.query.page, route.query.group, route.query.view], () => {
  actionError.value = ""; feedback.value = "";
  restoreFilters();
  if (ready) void load();
});
</script>
<template>
  <div class="page-stack fusion-space">
    <PageHeader :eyebrow="scope === 'mine' ? '我的空间' : '团队资产中心'" :title="title" :description="description">
      <RouterLink v-if="category === 'subscriptions'" to="/memberships/new" class="primary-button"><Plus :size="18" />登记订阅</RouterLink>
      <template v-else><RouterLink v-if="scope !== 'mine' || category === 'using'" to="/my/requests?new=seat" class="secondary-button">申请使用</RouterLink><RouterLink to="/my/contributions?new=case" class="secondary-button">记录 AI 案例</RouterLink><RouterLink :to="isWorkflow ? '/register?type=ai_workflow' : '/register'" class="primary-button"><Plus :size="18" />{{ isWorkflow ? '登记 AI 工作流' : '登记 AI 成果' }}</RouterLink></template>
    </PageHeader>
    <div v-if="isHome && counts" class="fusion-stat-grid">
      <RouterLink to="/my/created" class="fusion-stat"><span class="fusion-stat-label"><Pencil :size="17" aria-hidden="true" />我创建的记录</span><strong>{{ counts.created }}</strong><small>AI 成果与订阅 <ArrowRight :size="14" /></small></RouterLink>
      <RouterLink to="/my/responsible" class="fusion-stat"><span class="fusion-stat-label"><Shield :size="17" aria-hidden="true" />我负责的资产</span><strong>{{ counts.responsible }}</strong><small>维护责任 <ArrowRight :size="14" /></small></RouterLink>
      <RouterLink to="/my/subscriptions" class="fusion-stat"><span class="fusion-stat-label"><CreditCard :size="17" aria-hidden="true" />我的订阅</span><strong>{{ counts.subscriptions }}</strong><small>订阅与探索 <ArrowRight :size="14" /></small></RouterLink>
      <RouterLink to="/my/contributions" class="fusion-stat"><span class="fusion-stat-label"><Star :size="17" aria-hidden="true" />已记录的实践</span><strong>{{ counts.evidence }}</strong><small>查看证据 <ArrowRight :size="14" /></small></RouterLink>
    </div>
    <RouterLink v-if="isHome && counts?.drafts" to="/my/drafts" class="fusion-resume"><div><small>继续整理</small><h2>{{ counts.drafts }} 份草稿待确认</h2><p>核对说明、附件和共享范围，再确认登记。</p></div><span>打开我的草稿 <ArrowRight :size="18" /></span></RouterLink>
    <RouterLink v-if="isHome" to="/my/requests?new=seat" class="fusion-resume request-entry"><div><small>申请使用</small><h2>需要席位、平台或账号？</h2><p>提交申请，在我的申请中查看处理进度。</p></div><span>发起申请 <ArrowRight :size="18" /></span></RouterLink>
    <WorkspaceTabs v-if="isWorkflow" :model-value="activeWorkflowView" :tabs="workflowTabs" id-prefix="workflow-view" label="工作流视图" @update:model-value="selectWorkflow" />
    <WorkspaceTabs v-else-if="scope !== 'mine'" :model-value="group" :tabs="discoveryTabs" id-prefix="discovery-group" label="资产分类" @update:model-value="selectGroup" />
    <h2 v-if="isHome" class="fusion-section-title">最近更新的资产</h2>
    <form v-if="!isHome" class="fusion-filters" role="search" aria-label="筛选资产" @submit.prevent="search">
      <label class="fusion-search"><Search :size="18" /><input v-model="keyword" aria-label="搜索资产" placeholder="搜索资产名称、场景或关键词" maxlength="200" /></label>
      <select v-if="filterTypes.length > 1" v-model="type" aria-label="资产类型" @change="search"><option value="">全部类型</option><option v-for="item in filterTypes" :key="item.id" :value="item.id">{{ item.name }}</option></select>
      <select v-if="scope === 'team'" v-model="department" aria-label="团队" @change="search"><option value="">我的部门</option><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select>
      <button class="secondary-button" type="submit">搜索</button>
      <button v-if="hasFilters" class="fusion-clear-button" type="button" @click="clearFilters">清空筛选</button>
    </form>
    <div :id="isWorkflow ? 'workflow-view-panel' : scope !== 'mine' ? 'discovery-group-panel' : undefined" :role="scope !== 'mine' ? 'tabpanel' : undefined" :aria-labelledby="isWorkflow ? `workflow-view-${activeWorkflowView}` : scope !== 'mine' ? `discovery-group-${group}` : undefined" class="discovery-result-panel">
    <p v-if="feedback" class="fusion-feedback" role="status"><CheckCircle2 :size="17" aria-hidden="true" />{{ feedback }}</p>
    <p v-if="bookmarkBusy" class="fusion-muted" role="status">正在保存收藏…</p>
    <p v-if="actionError" class="form-error" role="alert">{{ actionError }}</p>
    <section v-if="error" class="fusion-empty" role="alert"><h2>暂时无法读取资产</h2><p>{{ error }}</p><button class="secondary-button" @click="ready ? load() : initialize()">重试</button></section>
    <section v-else-if="loading" class="fusion-empty" aria-busy="true" role="status"><LoaderCircle :size="26" class="fusion-spinner" aria-hidden="true" /><h2>正在读取资产…</h2></section>
    <section v-else-if="scope === 'mine' && !identityKnown" class="fusion-empty"><h2>尚未关联员工身份</h2><p>请联系管理员关联身份后查看你的资产。</p></section>
    <template v-else>
      <p v-if="!isHome" class="fusion-count">共 <strong>{{ total }}</strong> 项可见{{ isWorkflow ? '工作流' : '资产' }}</p>
      <div v-if="assets.length" class="discovery-sections">
        <section v-for="section in sections" :key="section.id" class="discovery-section"><h2 v-if="section.label" class="discovery-section-heading">{{ section.label }}<span>本页 {{ section.assets.length }} 项</span></h2><div class="fusion-grid">
        <template v-for="asset in section.assets" :key="asset.id">
          <div v-if="category === 'subscriptions'" class="fusion-subscription">
            <AssetCard :asset="asset" :type-name="types.find(t => t.id === asset.asset_type_id)?.name" :type-code="types.find(t => t.id === asset.asset_type_id)?.code" :team-name="departments.find(d => d.id === asset.owner_department_id)?.name" :bookmarked="saved.includes(asset.id)" :busy="Boolean(bookmarkBusy)" :return-to="route.fullPath" @bookmark="toggleBookmark" />
            <div class="fusion-subscription-facts"><span>{{ fundingLabels[subscriptions.find(s => s.asset_id === asset.id)?.funding_source || ''] || '资金来源待确认' }}</span><span>{{ subscriptions.find(s => s.asset_id === asset.id)?.subscription_name || '套餐待补充' }}</span><RouterLink :to="{ path: '/my/contributions', query: { subscription: subscriptions.find(s => s.asset_id === asset.id)?.id } }">查看关联实践 →</RouterLink></div>
          </div>
          <AssetCard v-else :asset="asset" :type-name="types.find(t => t.id === asset.asset_type_id)?.name" :type-code="types.find(t => t.id === asset.asset_type_id)?.code" :team-name="departments.find(d => d.id === asset.owner_department_id)?.name" :bookmarked="saved.includes(asset.id)" :busy="Boolean(bookmarkBusy)" :return-to="route.fullPath" @bookmark="toggleBookmark" />
        </template>
        </div></section>
      </div>
      <section v-else class="fusion-empty">
        <FileSearch :size="30" aria-hidden="true" />
        <h2>{{ isWorkflow ? hasFilters ? '没有找到匹配的工作流' : activeWorkflowView === 'created' ? '你还没有登记 AI 工作流' : activeWorkflowView === 'bookmarks' ? '你还没有收藏工作流' : '这里还没有可见的工作流' : hasFilters ? '没有找到匹配的资产' : '这里还没有匹配的资产' }}</h2>
        <p>{{ hasFilters ? '调整关键词或类型，也可以清空筛选重新查找。' : category === 'bookmarks' ? '在资产详情或卡片上收藏，之后可在这里找到。' : category === 'using' || category === 'responsible' || category === 'ai' ? '前往资产发现，寻找可复用的成果。' : isWorkflow ? activeWorkflowView === 'bookmarks' ? '浏览工作流并收藏常用内容，之后可以在这里快速找到。' : '登记已有 AI 工作流，逐步补充使用方法和关联成果。' : '从一项已有 AI 成果开始，逐步积累可复用的经验。' }}</p>
        <button v-if="hasFilters" class="primary-button" type="button" @click="clearFilters">清空筛选</button>
        <RouterLink v-else :to="emptyAction.to" class="primary-button">{{ emptyAction.label }}<ArrowRight :size="16" aria-hidden="true" /></RouterLink>
      </section>
      <div v-if="!isHome && total > 24" class="fusion-pagination"><button :disabled="page === 1" @click="goPage(page - 1)">上一页</button><span>第 {{ page }} / {{ Math.ceil(total / 24) }} 页</span><button :disabled="page * 24 >= total" @click="goPage(page + 1)">下一页</button></div>
    </template>
    </div>
  </div>
</template>
