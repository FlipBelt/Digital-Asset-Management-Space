<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ArrowRight, Building2, ChevronRight, Plus, RefreshCw, Search } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import WorkspaceTabs from "../components/WorkspaceTabs.vue";
import PlatformDirectoryPanel from "../components/PlatformDirectoryPanel.vue";
import PlatformAccountVerification from "../components/PlatformAccountVerification.vue";
import ChildAccountsPanel from "../components/ChildAccountsPanel.vue";
import { api, type AccountHierarchy, type CurrentUser, type HierarchyTenant, type HierarchyAccount, type PlatformDirectoryEntry, type PlatformTenant } from "../lib/api";

const route = useRoute(), router = useRouter();
const user = ref<CurrentUser | null>(null), data = ref<AccountHierarchy>({ platforms: [], unlinked_identities: [] });
const directory = ref<PlatformDirectoryEntry[]>([]), loading = ref(true), error = ref(""), message = ref(""), query = ref("");
const verification = ref<PlatformTenant | null>(null);
let sequence = 0;
const canManage = computed(() => Boolean(user.value?.roles.some(role => ["system_admin", "asset_manager"].includes(role))));
const selected = computed(() => directory.value.find(row => row.id === route.query.platform));
const platform = computed(() => data.value.platforms.find(row => row.id === route.query.platform));
const allTenants = computed(() => [...(platform.value?.company_accounts || []), ...(platform.value?.personal_accounts || [])]);
const selectedTenant = computed(() => allTenants.value.find(row => row.asset_id === route.query.tenant && !row.is_subscription));
const section = computed({ get: () => String(route.query.section || "company"), set: value => { void router.replace({ query: { platform: route.query.platform, section: value } }); } });
function needsEmployeeReview(child: HierarchyAccount) { return (child.account_kind !== "service" || !!child.primary_person_id) && child.employment_status !== "active"; }
const pendingTenants = computed(() => allTenants.value.filter(row => !row.is_subscription && (row.verification_status !== "verified" || row.children.some(needsEmployeeReview))));
const pendingCount = computed(() => pendingTenants.value.length + (platform.value?.pending_identities.length || 0));
const tabs = computed(() => [
  { value: "company", label: "公司账号", count: platform.value?.company_accounts.length || 0 },
  { value: "personal", label: "个人账号", count: platform.value?.personal_accounts.length || 0 },
  { value: "pending", label: "待核验 / 待交接", count: pendingCount.value },
  { value: "identities", label: "注册身份", count: platform.value?.registration_identities.length || 0 },
  { value: "directory", label: "平台资料与套餐" },
]);
const visibleDirectory = computed(() => directory.value.filter(row => `${row.name} ${row.provider_name || ""}`.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase())));
const tenantRows = computed(() => section.value === "personal" ? platform.value?.personal_accounts || [] : section.value === "pending" ? pendingTenants.value : platform.value?.company_accounts || []);
function structureFor(id: string) { return data.value.platforms.find(row => row.id === id); }
function pendingFor(id: string) {
  const item = structureFor(id);
  return item ? [...item.company_accounts, ...item.personal_accounts].filter(row => !row.is_subscription && (row.verification_status !== "verified" || row.children.some(needsEmployeeReview))).length + item.pending_identities.length : 0;
}
function openPlatform(id: string) { query.value = ""; void router.push({ query: { platform: id } }); }
function openTenant(row: HierarchyTenant) {
  if (row.is_subscription) void router.push(`/assets/${row.asset_id}`);
  else void router.push({ query: { platform: route.query.platform, tenant: row.asset_id } });
}
async function load() {
  const current = ++sequence; loading.value = true; error.value = "";
  try {
    const [hierarchy, entries, session] = await Promise.all([api.accountHierarchy(), api.platformDirectory(), api.currentSession()]);
    if (current !== sequence) return;
    data.value = hierarchy; directory.value = entries; user.value = session;
    await openRequestedVerification();
  } catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : "平台账号读取失败"; }
  finally { if (current === sequence) loading.value = false; }
}
async function openRequestedVerification() {
  if (!canManage.value || !route.query.verify) return;
  for (const item of data.value.platforms) {
    const tenant = [...item.company_accounts, ...item.personal_accounts].find(row => row.asset_id === route.query.verify && row.id);
    if (tenant) {
      verification.value = tenant as PlatformTenant;
      if (route.query.platform !== item.id || route.query.tenant !== tenant.asset_id) await router.replace({ query: { platform: item.id, tenant: tenant.asset_id, verify: tenant.asset_id } });
      return;
    }
  }
}
function closeVerification() { verification.value = null; if (route.query.verify) void router.replace({ query: { ...route.query, verify: undefined } }); }
async function verified() { closeVerification(); message.value = "核验结果已保存。"; await load(); }
async function childChanged() { message.value = "账号明细已保存。"; await load(); }
watch(() => route.query.verify, () => { void openRequestedVerification(); });
onMounted(load);
</script>
<template>
  <div class="page-stack platform-accounts-page">
    <PageHeader eyebrow="控制入口" title="平台与账号" description="先选择平台，再管理公司账号、个人账号和待核验资料；子账号在所属账号内维护。">
      <button class="secondary-button" :disabled="loading" @click="load"><RefreshCw :size="16" />刷新</button>
      <RouterLink v-if="canManage" class="primary-button" to="/intake?mode=platform"><Plus :size="16" />登记平台 / 供应商</RouterLink>
    </PageHeader>
    <nav v-if="route.query.platform || route.query.unlinked" class="account-breadcrumbs" aria-label="平台账号路径"><RouterLink to="/accounts">全部平台</RouterLink><ChevronRight :size="15" /><RouterLink v-if="selected" :to="{ query: { platform: selected.id } }">{{ selected.name }}</RouterLink><span v-else>待关联资料</span><template v-if="selectedTenant"><ChevronRight :size="15" /><span aria-current="page">{{ selectedTenant.name }}</span></template></nav>
    <p v-if="message" class="message-panel success-message" role="status">{{ message }}</p>
    <div v-if="loading" class="content-panel mini-empty" role="status">正在读取平台与账号…</div>
    <div v-else-if="error" class="message-panel error-message" role="alert">{{ error }}<button class="secondary-button" @click="load">重试</button></div>
    <section v-else-if="route.query.unlinked" class="content-panel"><h2>待关联平台的注册身份</h2><p>先核对实际平台和员工状态，再补充关联；未知资料保持待核验。</p><ul class="pending-identity-list"><li v-for="item in data.unlinked_identities" :key="item.asset_id"><div><strong>{{ item.name }}</strong><small>{{ item.asset_code }}</small></div><RouterLink class="secondary-button" :to="`/assets/${item.asset_id}?tab=relations`">核对资料</RouterLink></li></ul></section>
    <section v-else-if="route.query.platform && !selected" class="content-panel mini-empty"><strong>平台资料已改变或暂不可读取</strong><RouterLink to="/accounts" class="secondary-button">返回全部平台</RouterLink></section>
    <template v-else-if="selected">
      <section v-if="selectedTenant" class="content-panel tenant-drilldown">
        <header><div><h2>{{ selectedTenant.name }}</h2><p>{{ selectedTenant.company_name || '个人账号' }} · {{ selectedTenant.tenant_identifier ? `平台 ID ${selectedTenant.tenant_identifier}` : '账号标识待补充' }}</p><p>负责人：{{ selectedTenant.responsible_person_name || '尚未配置' }}<span v-if="selectedTenant.responsible_person_name && !selectedTenant.has_owner">（当前责任无效，需交接或更新）</span></p></div><div class="tenant-actions"><StatusBadge :tone="selectedTenant.verification_status === 'verified' ? 'success' : 'warning'">{{ selectedTenant.verification_status === 'verified' ? '已核验' : '待核验' }}</StatusBadge><button v-if="canManage" class="secondary-button" @click="verification = selectedTenant as PlatformTenant">{{ selectedTenant.verification_status === 'verified' ? '查看核验' : '核验账号' }}</button><RouterLink class="secondary-button" :to="`/assets/${selectedTenant.asset_id}?tab=responsibility`">账号资料与责任</RouterLink></div></header>
        <p v-if="selectedTenant.evidence_note" class="form-hint">核验 / 待补充说明：{{ selectedTenant.evidence_note }}</p>
        <ChildAccountsPanel :key="selectedTenant.asset_id" :asset-id="selectedTenant.asset_id" :legal-entity-id="selectedTenant.legal_entity_id || null" :can-manage="canManage" @changed="childChanged" />
      </section>
      <section v-else-if="route.query.tenant" class="content-panel mini-empty"><strong>账号资料已改变或无权读取</strong><RouterLink :to="{ query: { platform: selected.id } }" class="secondary-button">返回平台</RouterLink></section>
      <template v-else>
        <div class="platform-heading"><div><h2>{{ selected.name }}</h2><p>{{ selected.provider_name && selected.provider_name !== selected.name ? `服务提供方：${selected.provider_name}` : '平台与服务提供方统一维护' }}</p></div><RouterLink v-if="canManage && selected.kind === 'platform'" class="primary-button" :to="{ path: '/intake', query: { mode: 'platform-account', platform: selected.id } }"><Plus :size="16" />登记此平台账号</RouterLink></div>
        <WorkspaceTabs v-model="section" :tabs="tabs" label="平台内账号分类" id-prefix="platform-section" />
        <section id="platform-section-panel" class="content-panel" role="tabpanel" :aria-labelledby="`platform-section-${section}`">
          <PlatformDirectoryPanel v-if="section === 'directory'" :entry-id="selected.id" :can-manage="canManage" @changed="load" />
          <template v-else-if="section === 'identities'"><p class="form-hint">注册邮箱、手机号等身份资料集中在所属平台，已核验资料继续保留在此。</p><ul v-if="platform?.registration_identities.length" class="pending-identity-list"><li v-for="item in platform.registration_identities" :key="item.asset_id"><div><strong>{{ item.name }}</strong><small>{{ item.asset_code }} · {{ item.verification_status === 'verified' ? '已核验' : '待核验' }}</small></div><RouterLink class="secondary-button" :to="`/assets/${item.asset_id}`">查看身份资料</RouterLink></li></ul><p v-else class="mini-empty">当前平台暂无已关联的注册身份。</p></template>
          <template v-else>
            <p v-if="section === 'pending'" class="form-hint">核对账号的平台、公司归属、账号标识及依据；子账号需绑定实际在职员工，离职员工的账号进入交接。</p>
            <div v-if="section === 'personal'" class="personal-account-actions"><p class="form-hint">个人账号与个人订阅按已有可见权限展示；个人订阅登记无需审核。</p><RouterLink class="secondary-button" :to="{ path: '/memberships/new', query: { platform: selected.id } }">登记个人订阅</RouterLink><RouterLink v-if="canManage && selected.kind === 'platform'" class="secondary-button" :to="{ path: '/intake', query: { mode: 'platform-account', platform: selected.id, ownership: 'personal_for_company' } }">登记个人账号（公司使用）</RouterLink></div>
            <ul v-if="tenantRows.length" class="platform-tenant-list"><li v-for="row in tenantRows" :key="row.asset_id"><span class="record-icon"><Building2 :size="19" /></span><div><button class="tenant-name" @click="openTenant(row)">{{ row.name }}</button><p>{{ row.is_subscription ? `${row.person_name || '个人登记'} · ${row.plan_name || '套餐待补充'}` : `${row.company_name || '个人账号'} · ${row.children.length} 个子账号` }}</p><small v-if="!row.is_subscription">负责人：{{ row.responsible_person_name || '尚未配置' }}</small></div><StatusBadge :tone="row.is_subscription || row.verification_status === 'verified' ? 'success' : 'warning'">{{ row.is_subscription ? '个人订阅 · 无需审核' : row.verification_status === 'verified' ? '已核验' : '待核验' }}</StatusBadge><button class="secondary-button" :aria-label="`管理账号 ${row.name}`" @click="openTenant(row)">{{ row.is_subscription ? '查看登记' : '管理账号' }}<ArrowRight :size="15" /></button></li></ul>
            <div v-else class="mini-empty">{{ section === 'pending' ? '当前平台没有待核验或交接的账号。' : section === 'personal' ? '当前平台暂无可见的个人账号或订阅。' : '当前平台尚未登记公司账号。' }}</div>
            <ul v-if="section === 'pending' && platform?.pending_identities.length" class="pending-identity-list"><li v-for="item in platform.pending_identities" :key="item.asset_id"><div><strong>{{ item.name }}</strong><small>注册身份 · {{ item.asset_code }}</small></div><RouterLink class="secondary-button" :to="`/assets/${item.asset_id}`">核对资料</RouterLink></li></ul>
          </template>
        </section>
      </template>
    </template>
    <section v-else class="content-panel">
      <label class="fusion-search platform-search"><Search :size="17" aria-hidden="true" /><input v-model="query" type="search" placeholder="搜索平台或供应商" aria-label="搜索平台或供应商" /></label>
      <div v-if="visibleDirectory.length" class="platform-grid"><button v-for="item in visibleDirectory" :key="item.id" class="platform-card" @click="openPlatform(item.id)"><span class="record-icon"><Building2 :size="21" /></span><strong>{{ item.name }}</strong><span>{{ structureFor(item.id)?.company_accounts.length || 0 }} 个公司账号 · {{ structureFor(item.id)?.personal_accounts.length || 0 }} 个个人账号</span><span class="platform-card-footer"><StatusBadge :tone="pendingFor(item.id) ? 'warning' : 'default'">{{ pendingFor(item.id) ? `${pendingFor(item.id)} 项待核验 / 交接` : item.review_status === 'approved' ? '目录已审核' : '目录待完善' }}</StatusBadge><ChevronRight :size="17" aria-hidden="true" /></span></button></div>
      <div v-else class="mini-empty">{{ query ? '没有匹配的平台，请调整搜索。' : '尚未登记平台或供应商。' }}</div>
      <RouterLink v-if="data.unlinked_identities.length && !query" class="unlinked-entry" :to="{ query: { unlinked: '1' } }">待关联平台的注册身份 {{ data.unlinked_identities.length }} 项<ArrowRight :size="16" /></RouterLink>
    </section>
    <PlatformAccountVerification v-if="verification" :tenant="verification" @close="closeVerification" @saved="verified" />
  </div>
</template>
<style scoped>
.account-breadcrumbs,.platform-heading,.tenant-actions,.tenant-drilldown > header { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
.account-breadcrumbs { color:var(--muted); font-size:14px; } .account-breadcrumbs a { color:var(--text); }
.platform-heading,.tenant-drilldown > header { justify-content:space-between; align-items:start; }
h2 { font-size:23px; margin:0 0 8px; } p,small { color:var(--muted); line-height:1.6; } p { margin:0; }
.platform-search { max-width:550px; margin-bottom:24px; }
.platform-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }
.platform-card { display:grid; gap:12px; padding:24px; border:1px solid var(--border); background:var(--surface); border-radius:var(--radius); color:var(--text); text-align:left; cursor:pointer; min-width:0; }
.platform-card:hover { border-color:var(--accent); } .platform-card strong { font-size:18px; overflow-wrap:anywhere; } .platform-card > span { font-size:13px; } .platform-card-footer { display:flex; justify-content:space-between; align-items:center; gap:10px; }
.platform-tenant-list,.pending-identity-list { list-style:none; margin:16px 0 0; padding:0; }
.platform-tenant-list li,.pending-identity-list li { display:flex; align-items:center; gap:16px; border-top:1px solid var(--border); padding:20px 0; }
.platform-tenant-list li > div,.pending-identity-list li > div { flex:1; min-width:0; overflow-wrap:anywhere; }
.pending-identity-list small { display:block; } .tenant-name { text-align:left; border:0; padding:0; background:none; color:var(--text); font-size:16px; font-weight:700; cursor:pointer; }
.tenant-name:hover { text-decoration:underline; } .tenant-drilldown { display:grid; gap:24px; }
.unlinked-entry { display:flex; align-items:center; justify-content:space-between; gap:12px; padding-top:22px; margin-top:22px; border-top:1px solid var(--border); }
.personal-account-actions { display:flex; flex-wrap:wrap; gap:12px; } .personal-account-actions p { flex-basis:100%; }
@media(max-width:980px) { .platform-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media(max-width:640px) { .platform-grid { grid-template-columns:minmax(0,1fr); } .platform-tenant-list li { flex-wrap:wrap; gap:12px; } .platform-tenant-list li > div { flex-basis:calc(100% - 60px); } .platform-card { padding:20px; } }
</style>
