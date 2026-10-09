<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { Building2, ChevronDown, ChevronRight, Crown, FolderTree, Plus, RefreshCw, Save, Search, TriangleAlert, UserRound, Users } from "lucide-vue-next";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import {
  api, type Department, type DepartmentMembership, type DingTalkOrganization, type DingTalkProfile,
  type LegalEntity, type LegalEntityIdentifier, type LegalEntityProfile, type Person,
} from "../lib/api";
import { currentDirectoryScope, organizationScope } from "../lib/organizationScope";
import { companyVerificationLabel, organizationStructure } from "../lib/organizationStructure";

type TreeRow = Department & { depth: number; hasChildren: boolean };
const loading = ref(true);
const globalManager = ref(false);
const syncingDingtalk = ref(false);
const refreshingCompanies = ref(false);
const error = ref("");
const success = ref("");
const search = ref("");
const organizationView = ref<"companies" | "departments">("companies");
const selectedCompanyId = ref("");
const selectedDepartmentId = ref("");
const expandedDepartmentIds = ref<string[]>([]);
const showLegalProfile = ref(false);
const entities = ref<LegalEntity[]>([]);
const departments = ref<Department[]>([]);
const people = ref<Person[]>([]);
const memberships = ref<DepartmentMembership[]>([]);
const dingtalkProfiles = ref<DingTalkProfile[]>([]);
const organizationBinding = ref<DingTalkOrganization | null>(null);
const selectedEntityId = ref("");
const legalProfile = reactive({ entity_type: "", jurisdiction: "", registration_status: "", legal_representative: "", established_on: "", registered_address: "", registered_capital: "", business_scope: "", source_note: "", verification_status: "pending" });
const legalIdentifiers = ref<LegalEntityIdentifier[]>([]);
const legalIdentifierForm = reactive({ namespace: "cn", identifier_type: "unified_social_credit_code", identifier_value: "", is_primary: true, verification_status: "pending", source_note: "" });
const savingLegalProfile = ref(false);
const legalProfileReadyId = ref("");
const companyStatutoryProfile = ref<LegalEntityProfile | null>(null);
const loadingCompanyProfile = ref(false);
const companyProfileError = ref("");
const legalProfilePanel = ref<HTMLElement | null>(null);
let companyProfileRequest = 0;

const organizationEntity = computed(() => organizationBinding.value?.status === "bound"
  ? entities.value.find((item) => item.id === organizationBinding.value?.legal_entity_id) : undefined);
const allScoped = computed(() => organizationScope(organizationEntity.value?.id, departments.value, people.value, memberships.value));
const scoped = computed(() => currentDirectoryScope(allScoped.value, [...dingtalkProfiles.value.map(item => item.person_id), ...(organizationBinding.value?.directory_snapshot?.current_person_ids ?? []), ...(organizationBinding.value?.directory_snapshot?.historical_person_ids ?? [])], organizationBinding.value?.directory_snapshot?.current_person_ids));
const historicalPeople = computed(() => allScoped.value.people.filter(item => !scoped.value.people.some(current => current.id === item.id)));
const structure = computed(() => organizationStructure(organizationEntity.value, entities.value, scoped.value,
  dingtalkProfiles.value, organizationBinding.value?.directory_snapshot?.department_codes));
const peopleById = computed(() => Object.fromEntries(scoped.value.people.map((item) => [item.id, item])));
const profilesByPerson = computed(() => Object.fromEntries(dingtalkProfiles.value.map((item) => [item.person_id, item])));
const selectedCompany = computed(() => structure.value.companies.find((item) => item.id === selectedCompanyId.value));
const pendingCompanySelected = computed(() => selectedCompanyId.value === "company-pending");
const childrenByParent = computed(() => {
  const grouped: Record<string, Department[]> = {};
  for (const department of structure.value.departments) {
    (grouped[department.parent_id || "root"] ??= []).push(department);
  }
  Object.values(grouped).forEach((rows) => rows.sort((a, b) => a.name.localeCompare(b.name, "zh-CN")));
  return grouped;
});
const rootDepartments = computed(() => childrenByParent.value.root ?? []);
const selectedDepartment = computed(() => scoped.value.departments.find((item) => item.id === selectedDepartmentId.value));
const selectedDepartmentIsStale = computed(() => structure.value.staleNodes.some((item) => item.id === selectedDepartmentId.value));
const selectedEntity = computed(() => entities.value.find((item) => item.id === selectedEntityId.value));
const selectedMemberships = computed(() => scoped.value.memberships.filter((item) => item.department_id === selectedDepartmentId.value));
const selectedManagers = computed(() => selectedMemberships.value.filter((item) => item.leadership_role === "department_manager"));
const selectedGroupLeaders = computed(() => selectedMemberships.value.filter((item) => item.leadership_role === "group_leader"));
const selectedMembers = computed(() => {
  const keyword = search.value.trim().toLocaleLowerCase();
  return selectedMemberships.value
    .map((membership) => ({ membership, person: peopleById.value[membership.person_id] }))
    .filter((item): item is { membership: DepartmentMembership; person: Person } => Boolean(item.person))
    .filter(({ person }) => !keyword || `${person.display_name} ${person.employee_no}`.toLocaleLowerCase().includes(keyword))
    .sort((a, b) => Number(b.membership.is_manager) - Number(a.membership.is_manager) || a.person.display_name.localeCompare(b.person.display_name, "zh-CN"));
});
const selectedCompanyPeople = computed(() => {
  const rows = pendingCompanySelected.value ? structure.value.pendingCompanyPeople :
    structure.value.companyPeople.get(selectedCompany.value?.name ?? "") ?? [];
  const keyword = search.value.trim().toLocaleLowerCase();
  return rows.filter((person) => !keyword || `${person.display_name} ${person.employee_no}`.toLocaleLowerCase().includes(keyword))
    .slice().sort((a, b) => a.display_name.localeCompare(b.display_name, "zh-CN"));
});
const treeRows = computed<TreeRow[]>(() => {
  const rows: TreeRow[] = [];
  const visited = new Set<string>();
  const visit = (department: Department, depth: number) => {
    if (visited.has(department.id)) return;
    visited.add(department.id);
    const children = childrenByParent.value[department.id] ?? [];
    rows.push({ ...department, depth, hasChildren: children.length > 0 });
    if (expandedDepartmentIds.value.includes(department.id)) children.forEach((child) => visit(child, depth + 1));
  };
  rootDepartments.value.forEach((department) => visit(department, 0));
  return rows;
});

function profileFor(person: Person) { return profilesByPerson.value[person.id]; }
function titleLabel(person: Person) { return profileFor(person)?.job_title || "岗位待补充"; }
function companyLabel(person: Person) {
  const affiliation = profileFor(person)?.company_affiliation;
  return affiliation?.status === "available" ? affiliation.name : "公司归属待核验";
}
function departmentLabel(person: Person) {
  const ids = new Set(structure.value.departments.map((item) => item.id));
  const placements = scoped.value.memberships.filter((item) => item.person_id === person.id && ids.has(item.department_id));
  const primary = placements.find((item) => item.is_primary) ?? placements[0];
  return structure.value.departments.find((item) => item.id === (primary?.department_id || person.department_id))?.name || "部门待核验";
}
function toggleDepartment(department: TreeRow) {
  selectedDepartmentId.value = department.id;
  if (!department.hasChildren) return;
  expandedDepartmentIds.value = expandedDepartmentIds.value.includes(department.id)
    ? expandedDepartmentIds.value.filter((item) => item !== department.id)
    : [...expandedDepartmentIds.value, department.id];
}
async function load() {
  loading.value = true;
  error.value = "";
  try {
    const session = await api.currentSession();
    globalManager.value = session.roles.some(role => ["system_admin", "asset_manager"].includes(role));
    if (!globalManager.value) organizationView.value = "departments";
    [entities.value, departments.value, people.value, memberships.value, dingtalkProfiles.value, organizationBinding.value] = await Promise.all([
      api.legalEntities(), api.departments(), api.people(), api.departmentMemberships(), globalManager.value ? api.dingtalkProfiles() : Promise.resolve([]), api.dingtalkOrganization(),
    ]);
    if (!structure.value.companies.some((item) => item.id === selectedCompanyId.value) && !pendingCompanySelected.value) {
      selectedCompanyId.value = structure.value.companies[0]?.id ?? "";
    }
    if (!structure.value.departments.some((item) => item.id === selectedDepartmentId.value)) {
      selectedDepartmentId.value = rootDepartments.value[0]?.id ?? "";
    }
    if (!entities.value.some((item) => item.id === selectedEntityId.value)) {
      selectedEntityId.value = organizationEntity.value?.id ?? "";
    }
    if (showLegalProfile.value) await loadLegalProfile();
    expandedDepartmentIds.value = [...new Set([...expandedDepartmentIds.value, ...rootDepartments.value.map((item) => item.id)])];
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "组织数据加载失败"; }
  finally { loading.value = false; }
}
async function loadCompanyProfile() {
  const request = ++companyProfileRequest;
  const entityId = selectedCompany.value?.legalEntityId;
  companyStatutoryProfile.value = null;
  companyProfileError.value = "";
  loadingCompanyProfile.value = Boolean(entityId);
  if (!entityId) return;
  try {
    const profile = await api.legalEntityProfile(entityId);
    if (request === companyProfileRequest) companyStatutoryProfile.value = profile;
  } catch (reason) {
    if (request === companyProfileRequest) companyProfileError.value = reason instanceof Error ? reason.message : "公司主体档案加载失败";
  } finally {
    if (request === companyProfileRequest) loadingCompanyProfile.value = false;
  }
}
async function openCompanyProfile() {
  const entityId = selectedCompany.value?.legalEntityId;
  if (!entityId) return;
  selectedEntityId.value = entityId;
  await nextTick();
  showLegalProfile.value = true;
  await nextTick();
  legalProfilePanel.value?.scrollIntoView({ block: "start" });
}
async function loadLegalProfile() {
  const entityId = selectedEntityId.value;
  legalProfileReadyId.value = "";
  if (!entityId) return;
  const [profile, identifiers] = await Promise.all([api.legalEntityProfile(entityId), api.legalEntityIdentifiers(entityId)]);
  if (entityId !== selectedEntityId.value) return;
  Object.assign(legalProfile, { entity_type: profile?.entity_type ?? "", jurisdiction: profile?.jurisdiction ?? "", registration_status: profile?.registration_status ?? "", legal_representative: profile?.legal_representative ?? "", established_on: profile?.established_on ?? "", registered_address: profile?.registered_address ?? "", registered_capital: profile?.registered_capital ?? "", business_scope: profile?.business_scope ?? "", source_note: profile?.source_note ?? "", verification_status: profile?.verification_status ?? "pending" });
  legalIdentifiers.value = identifiers;
  legalProfileReadyId.value = entityId;
}
async function saveLegalProfile() {
  if (!selectedEntityId.value || legalProfileReadyId.value !== selectedEntityId.value) return;
  const entityId = selectedEntityId.value;
  savingLegalProfile.value = true; error.value = "";
  try {
    const saved = await api.saveLegalEntityProfile(entityId, { ...legalProfile, entity_type: legalProfile.entity_type || null, jurisdiction: legalProfile.jurisdiction || null, registration_status: legalProfile.registration_status || null, legal_representative: legalProfile.legal_representative || null, established_on: legalProfile.established_on || null, registered_address: legalProfile.registered_address || null, registered_capital: legalProfile.registered_capital || null, business_scope: legalProfile.business_scope || null, source_note: legalProfile.source_note || null });
    if (selectedCompany.value?.legalEntityId === entityId) {
      companyProfileRequest += 1;
      companyStatutoryProfile.value = saved;
      loadingCompanyProfile.value = false;
      companyProfileError.value = "";
    }
    success.value = "公司主体档案已保存。";
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "法人档案保存失败"; }
  finally { savingLegalProfile.value = false; }
}
async function addLegalIdentifier() {
  if (!selectedEntityId.value || !legalIdentifierForm.identifier_value) return;
  savingLegalProfile.value = true; error.value = "";
  try {
    await api.createLegalEntityIdentifier(selectedEntityId.value, { ...legalIdentifierForm, source_note: legalIdentifierForm.source_note || null });
    Object.assign(legalIdentifierForm, { namespace: "cn", identifier_type: "unified_social_credit_code", identifier_value: "", is_primary: false, verification_status: "pending", source_note: "" });
    await loadLegalProfile();
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "主体标识保存失败"; }
  finally { savingLegalProfile.value = false; }
}

async function refreshCompanies() {
  const entity = organizationEntity.value;
  if (!entity) return;
  refreshingCompanies.value = true; error.value = ""; success.value = "";
  try {
    const result = await api.refreshCompanyAffiliations(entity.id);
    await load();
    if (!error.value) success.value = `已核对 ${result.checked} 名成员的公司字段；${result.available} 名有可用公司归属，${Number(result.checked) - Number(result.available)} 名待核验。`;
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "公司归属核对失败"; }
  finally { refreshingCompanies.value = false; }
}
async function syncDingtalk() {
  const entity = organizationEntity.value;
  if (!entity) return;
  syncingDingtalk.value = true; error.value = ""; success.value = "";
  try {
    const result = await api.syncDingtalkDirectory(entity.id);
    await load();
    if (!error.value) success.value = `同步完成：当前 ${result.people_current} 名成员，新增 ${result.people_created} 名、更新 ${result.people_updated} 名；保留 ${result.people_historical} 份历史档案。`;
  }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "钉钉同步失败"; }
  finally { syncingDingtalk.value = false; }
}
onMounted(load);
watch(organizationView, () => { search.value = ""; });
watch(() => selectedCompany.value?.legalEntityId, loadCompanyProfile);
watch(selectedEntityId, async () => {
  if (loading.value || !showLegalProfile.value) return;
  try { await loadLegalProfile(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "法人档案加载失败"; }
});
watch(showLegalProfile, async (visible) => {
  if (!visible || loading.value) return;
  try { await loadLegalProfile(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "法人档案加载失败"; }
});
</script>

<template>
  <div class="page-stack">
    <PageHeader title="组织架构" description="分别查看公司主体归属与部门协作关系，找到成员、岗位和需要核验的组织资料。">
      <button v-if="globalManager" class="secondary-button" :aria-expanded="showLegalProfile" @click="showLegalProfile = !showLegalProfile"><Building2 :size="16" />主体档案</button>
      <RouterLink v-if="globalManager" class="secondary-button" to="/intake?mode=entity"><Plus :size="16" />登记公司主体</RouterLink>
      <button v-if="globalManager" class="secondary-button" :disabled="loading || syncingDingtalk || refreshingCompanies || !organizationEntity" @click="syncDingtalk"><RefreshCw :size="16" :class="{ spinning: syncingDingtalk }" />{{ syncingDingtalk ? "正在同步…" : "同步通讯录" }}</button>
      <button v-if="globalManager" class="primary-button" :disabled="loading || syncingDingtalk || refreshingCompanies || !organizationEntity" @click="refreshCompanies"><RefreshCw :size="16" :class="{ spinning: refreshingCompanies }" />{{ refreshingCompanies ? "正在核对…" : "核对公司归属" }}</button>
    </PageHeader>
    <div v-if="error" class="message-panel error-message" role="alert">{{ error }}</div>
    <div v-if="success" class="message-panel" role="status">{{ success }}</div>
    <section class="org-summary" v-if="organizationEntity">
      <div class="org-company"><span class="record-icon"><Building2 :size="19" /></span><div><strong>{{ organizationEntity.name }}</strong><span>钉钉组织 · {{ organizationEntity.code }}</span></div></div>
      <div><strong>{{ structure.companies.length }}</strong><span>公司</span></div>
      <div><strong>{{ structure.departments.length }}</strong><span>部门</span></div>
      <div><strong>{{ scoped.people.length }}</strong><span>当前成员</span></div>
    </section>
    <div v-else-if="loading" class="message-panel" role="status">正在加载组织…</div>
    <div v-else-if="!error" class="message-panel" role="status">{{ organizationBinding?.message || "暂未确定钉钉组织主体，请先核实绑定。" }}</div>
    <div v-if="organizationEntity && (structure.pendingCompanyPeople.length || structure.staleNodes.length)" class="organization-review-note" role="status">
      <TriangleAlert :size="17" />
      <span>{{ structure.pendingCompanyPeople.length }} 名成员的公司归属待核验<span v-if="structure.unavailablePeople.length">，其中 {{ structure.unavailablePeople.length }} 名的源资料不可查询</span><span v-if="structure.staleNodes.length">；{{ structure.staleNodes.length }} 个历史节点待核验</span>。</span>
    </div>

    <div class="organization-view-tabs" role="group" aria-label="组织查看方式">
      <button v-if="globalManager" :class="{ active: organizationView === 'companies' }" :aria-pressed="organizationView === 'companies'" @click="organizationView = 'companies'"><Building2 :size="17" />公司<span>{{ structure.companies.length }}</span></button>
      <button :class="{ active: organizationView === 'departments' }" :aria-pressed="organizationView === 'departments'" @click="organizationView = 'departments'"><FolderTree :size="17" />部门<span>{{ structure.departments.length }}</span></button>
    </div>
    <section v-if="organizationView === 'companies'" class="content-panel organization-workspace">
      <aside class="organization-tree">
        <div class="tree-heading"><div><strong>公司</strong><span>成员按钉钉公司主体字段分组</span></div></div>
        <button v-for="company in structure.companies" :key="company.id" class="company-node" :class="{ active: selectedCompanyId === company.id }" :aria-pressed="selectedCompanyId === company.id" @click="selectedCompanyId = company.id; search = ''">
          <Building2 :size="16" /><span>{{ company.name }}</span><small>{{ structure.companyPeople.get(company.name)?.length ?? 0 }}</small>
        </button>
        <button v-if="structure.pendingCompanyPeople.length" class="company-node pending-node" :class="{ active: pendingCompanySelected }" :aria-pressed="pendingCompanySelected" @click="selectedCompanyId = 'company-pending'; search = ''">
          <TriangleAlert :size="16" /><span>公司归属待核验</span><small>{{ structure.pendingCompanyPeople.length }}</small>
        </button>
        <div v-if="!loading && !structure.companies.length" class="mini-empty">暂无可查看的公司</div>
      </aside>
      <main class="organization-members">
        <header class="member-heading">
          <div><p class="eyebrow">{{ pendingCompanySelected ? "待核验资料" : "当前公司" }}</p><h2>{{ pendingCompanySelected ? "公司归属待核验" : selectedCompany?.name || "请选择公司" }}</h2><span>{{ selectedCompanyPeople.length }} 名{{ search ? "匹配" : "" }}成员<span v-if="selectedCompany"> · {{ selectedCompany.legalEntityId ? "已有主体档案" : "主体档案待登记" }}</span></span></div>
          <label class="table-search"><Search :size="16" /><input v-model="search" placeholder="搜索成员或工号" aria-label="搜索公司成员或工号" /></label>
        </header>
        <section v-if="selectedCompany" class="company-statutory-panel" aria-label="公司法定资料">
          <div v-if="loadingCompanyProfile" role="status">正在读取公司主体档案…</div>
          <div v-else-if="companyProfileError" class="company-profile-error" role="alert">{{ companyProfileError }}<button class="text-button" @click="loadCompanyProfile">重新加载</button></div>
          <template v-else>
            <dl>
              <div><dt>法定代表人</dt><dd>{{ companyStatutoryProfile?.legal_representative || "待补充" }}</dd></div>
              <div><dt>法定资料状态</dt><dd><span class="role-tag" :class="{ 'verification-pending': !companyStatutoryProfile?.legal_representative || companyStatutoryProfile.verification_status !== 'verified' }">{{ !companyStatutoryProfile?.legal_representative ? "待补充" : companyStatutoryProfile.verification_status === "verified" ? "档案已核验" : "待工商资料核验" }}</span></dd></div>
            </dl>
            <p>{{ companyStatutoryProfile?.source_note || "法定代表人依据独立公司档案维护，不从部门成员或社保公司字段推断。" }}</p>
            <button v-if="selectedCompany.legalEntityId" class="text-button" @click="openCompanyProfile">查看 / 编辑主体档案<ChevronRight :size="14" /></button>
            <span v-else class="muted-text">尚未登记公司主体档案</span>
          </template>
        </section>
        <p class="organization-source-note">以下为公司成员，归属来源：钉钉“主体（社保公司）”；与法定代表人、部门主管分别维护。</p>
        <div class="member-table-wrap">
          <table v-if="selectedCompany || pendingCompanySelected" class="member-table company-member-table">
            <thead><tr><th>成员</th><th>部门</th><th>岗位</th><th>资料状态</th></tr></thead>
            <tbody>
              <tr v-for="person in selectedCompanyPeople" :key="person.id">
                <td><div class="member-name"><span class="avatar">{{ person.display_name.slice(0, 1) }}</span><strong>{{ person.display_name }}</strong></div></td>
                <td>{{ departmentLabel(person) }}</td><td>{{ titleLabel(person) }}</td>
                <td><span class="role-tag" :class="{ 'verification-pending': profileFor(person)?.company_affiliation?.status !== 'available' }">{{ companyVerificationLabel(profileFor(person)) }}</span></td>
              </tr>
              <tr v-if="!selectedCompanyPeople.length"><td colspan="4" class="table-empty">{{ search ? "没有匹配成员，请调整搜索词。" : "暂无已核对的公司成员，可通过“核对公司归属”补充资料。" }}</td></tr>
            </tbody>
          </table>
          <div v-else class="large-empty-panel"><Building2 :size="28" /><strong>请选择左侧公司</strong><p>查看公司主体字段对应的成员及其部门。</p></div>
        </div>
      </main>
    </section>

    <section v-else class="content-panel organization-workspace">
      <aside class="organization-tree">
        <div class="tree-heading"><div><strong>部门</strong><span>{{ structure.departments.length }} 个部门及小组 · 数字为直接成员</span></div></div>
        <div class="tree-root"><FolderTree :size="16" /><span>部门协作架构</span></div>
        <button v-for="department in treeRows" :key="department.id" class="tree-node" :class="{ active: selectedDepartmentId === department.id }" :style="{ paddingLeft: `${14 + department.depth * 20}px` }" :aria-pressed="selectedDepartmentId === department.id" @click="toggleDepartment(department)">
          <ChevronDown v-if="department.hasChildren && expandedDepartmentIds.includes(department.id)" :size="14" /><ChevronRight v-else-if="department.hasChildren" :size="14" /><i v-else />
          <span>{{ department.name }}</span><small>{{ scoped.memberships.filter((item) => item.department_id === department.id).length }}</small>
        </button>
        <div v-if="structure.staleNodes.length" class="stale-node-group">
          <strong>历史节点待核验</strong>
          <button v-for="node in structure.staleNodes" :key="node.id" class="tree-node" :class="{ active: selectedDepartmentId === node.id }" @click="selectedDepartmentId = node.id; search = ''"><TriangleAlert :size="14" /><span>{{ node.name }}</span><small>待核验</small></button>
        </div>
        <div v-if="!loading && !treeRows.length" class="mini-empty">尚未同步职能部门</div>
      </aside>
      <main class="organization-members">
        <header class="member-heading">
          <div><p class="eyebrow">{{ selectedDepartmentIsStale ? "历史节点" : "当前部门" }}</p><h2>{{ selectedDepartment?.name || "请选择部门" }}</h2><span>{{ selectedMemberships.length }} 名成员 · {{ selectedManagers.length }} 名主管 · {{ selectedGroupLeaders.length }} 名组长<span v-if="search"> · {{ selectedMembers.length }} 名匹配成员</span></span></div>
          <label class="table-search"><Search :size="16" /><input v-model="search" placeholder="搜索成员或工号" aria-label="搜索部门成员或工号" /></label>
        </header>
        <p v-if="selectedDepartmentIsStale" class="organization-source-note">该节点不在最近可见的钉钉目录中，以下为保留的历史关系，需核验后再更新。</p>
        <div class="member-table-wrap">
          <table class="member-table department-member-table" v-if="selectedDepartment">
            <thead><tr><th>成员</th><th>部门身份</th><th>岗位</th><th>公司主体</th></tr></thead>
            <tbody>
              <tr v-for="{ membership, person } in selectedMembers" :key="membership.id">
                <td><div class="member-name"><span class="avatar">{{ person.display_name.slice(0, 1) }}</span><strong>{{ person.display_name }}</strong></div></td>
                <td><span class="role-tag" :class="{ manager: membership.is_manager }"><Crown v-if="membership.is_manager" :size="13" /><UserRound v-else :size="13" />{{ membership.leadership_role === "group_leader" ? "组长" : membership.leadership_role === "department_manager" ? "部门主管" : membership.is_manager ? "负责人待核验" : "部门成员" }}</span></td>
                <td>{{ titleLabel(person) }}</td><td>{{ companyLabel(person) }}<small v-if="profileFor(person)?.company_affiliation?.status !== 'available'" class="member-verification-note">{{ companyVerificationLabel(profileFor(person)) }}</small></td>
              </tr>
              <tr v-if="!selectedMembers.length"><td colspan="4" class="table-empty">{{ search ? "没有匹配成员，请调整搜索词。" : "该部门暂无已同步成员" }}</td></tr>
            </tbody>
          </table>
          <div v-else class="large-empty-panel"><Users :size="28" /><strong>请选择左侧部门</strong><p>选择部门后查看成员、岗位以及主管身份。</p></div>
        </div>
      </main>
    </section>
    <details v-if="historicalPeople.length" class="content-panel" style="padding: 20px;">
      <summary>保留的历史档案 · {{ historicalPeople.length }} 人</summary>
      <p class="organization-source-note">以下人员未出现在本次钉钉目录中，原挂靠、账号与授权仍保留，需管理员核验后再处理。</p>
      <div class="member-table-wrap"><table class="member-table"><thead><tr><th>人员</th><th>原岗位</th></tr></thead><tbody><tr v-for="person in historicalPeople" :key="person.id"><td>{{ person.display_name }}</td><td>{{ titleLabel(person) }}</td></tr></tbody></table></div>
    </details>
    <section ref="legalProfilePanel" v-if="showLegalProfile && selectedEntity" class="content-panel legal-entity-profile">
      <header class="panel-heading"><div><p class="eyebrow">公司主体</p><h2>法人主体档案</h2><p>名称和主体标识用于证明实体成立；其余法定资料按证据补充，不影响已有资产和关系。</p></div><select v-model="selectedEntityId"><option v-for="entity in entities" :key="entity.id" :value="entity.id">{{ entity.name }}</option></select></header>
      <form class="legal-profile-form" @submit.prevent="saveLegalProfile"><label><span>主体类型</span><select v-model="legalProfile.entity_type"><option value="">暂未确认</option><option value="domestic_company">境内公司</option><option value="branch">分公司</option><option value="individual_business">个体工商户</option><option value="overseas_entity">境外法人</option><option value="other">其他主体</option></select></label><label><span>司法辖区 / 注册地</span><input v-model="legalProfile.jurisdiction" placeholder="例如：中国浙江省杭州市" /></label><label><span>存续状态</span><select v-model="legalProfile.registration_status"><option value="">暂未确认</option><option value="active">存续</option><option value="inactive">注销 / 停业</option><option value="pending">待核验</option></select></label><label><span>法定代表人</span><input v-model="legalProfile.legal_representative" /></label><label><span>成立日期</span><input v-model="legalProfile.established_on" type="date" /></label><label><span>注册资本</span><input v-model="legalProfile.registered_capital" /></label><label class="wide"><span>注册地址</span><textarea v-model="legalProfile.registered_address" rows="2" /></label><label class="wide"><span>经营范围</span><textarea v-model="legalProfile.business_scope" rows="2" /></label><label class="wide"><span>来源说明</span><textarea v-model="legalProfile.source_note" rows="2" placeholder="例如：工商档案、原始资料文件名或人工核验说明" /></label><label><span>核验状态</span><select v-model="legalProfile.verification_status"><option value="pending">待核验</option><option value="verified">已核验</option><option value="unverified">未核验</option></select></label><div class="form-actions"><button class="primary-button" :disabled="savingLegalProfile || legalProfileReadyId !== selectedEntityId"><Save :size="16" />保存法人档案</button></div></form>
      <section class="legal-identifiers"><header><div><h3>主体标识</h3><p>统一社会信用代码、注册号等真实标识；未掌握时可以不填。</p></div></header><div class="identifier-chips"><span v-for="item in legalIdentifiers" :key="item.id" :class="{ primary: item.is_primary }"><small>{{ item.identifier_type }}</small><b>{{ item.identifier_value }}</b></span><span v-if="!legalIdentifiers.length" class="empty-chip">暂无已录入主体标识</span></div><form class="identifier-form-v2" @submit.prevent="addLegalIdentifier"><input v-model="legalIdentifierForm.identifier_type" placeholder="标识类型，如统一社会信用代码" /><input v-model="legalIdentifierForm.identifier_value" placeholder="标识值" required /><input v-model="legalIdentifierForm.source_note" placeholder="来源说明（可选）" /><button class="secondary-button" :disabled="savingLegalProfile"><Plus :size="15" />添加标识</button></form></section>
    </section>
    <p class="organization-note"><StatusBadge tone="success">钉钉资料</StatusBadge> 公司字段与部门挂靠分别展示；主体档案和组织同步范围独立维护。</p>
  </div>
</template>
