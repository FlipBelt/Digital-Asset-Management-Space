<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import {
  Building2,
  ChevronDown,
  ChevronRight,
  Crown,
  Plus,
  RefreshCw,
  Save,
  Search,
  UserRound,
  Users,
} from "lucide-vue-next";

import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import {
  api,
  type Department,
  type DepartmentMembership,
  type DingTalkProfile,
  type LegalEntity,
  type LegalEntityIdentifier,
  type LegalEntityProfile,
  type Person,
} from "../lib/api";

type TreeRow = Department & { depth: number; hasChildren: boolean };

const loading = ref(true);
const syncingDingtalk = ref(false);
const error = ref("");
const search = ref("");
const selectedDepartmentId = ref("");
const expandedDepartmentIds = ref<string[]>([]);
const entities = ref<LegalEntity[]>([]);
const departments = ref<Department[]>([]);
const people = ref<Person[]>([]);
const memberships = ref<DepartmentMembership[]>([]);
const dingtalkProfiles = ref<DingTalkProfile[]>([]);
const selectedEntityId = ref("");
const legalProfile = reactive({ entity_type: "", jurisdiction: "", registration_status: "", legal_representative: "", established_on: "", registered_address: "", registered_capital: "", business_scope: "", source_note: "", verification_status: "pending" });
const legalIdentifiers = ref<LegalEntityIdentifier[]>([]);
const legalIdentifierForm = reactive({ namespace: "cn", identifier_type: "unified_social_credit_code", identifier_value: "", is_primary: true, verification_status: "pending", source_note: "" });
const savingLegalProfile = ref(false);

const peopleById = computed(() => Object.fromEntries(people.value.map((item) => [item.id, item])));
const profilesByPerson = computed(() => Object.fromEntries(dingtalkProfiles.value.map((item) => [item.person_id, item])));
const childrenByParent = computed(() => {
  const grouped: Record<string, Department[]> = {};
  for (const department of departments.value) {
    const key = department.parent_id ?? "root";
    (grouped[key] ??= []).push(department);
  }
  Object.values(grouped).forEach((rows) => rows.sort((a, b) => a.name.localeCompare(b.name, "zh-CN")));
  return grouped;
});
const rootDepartments = computed(() => childrenByParent.value.root ?? []);
const selectedDepartment = computed(() => departments.value.find((item) => item.id === selectedDepartmentId.value));
const selectedEntity = computed(() => entities.value.find((item) => item.id === selectedEntityId.value));
const selectedMemberships = computed(() => memberships.value.filter((item) => item.department_id === selectedDepartmentId.value));
const selectedManagers = computed(() => selectedMemberships.value.filter((item) => item.is_manager));
const selectedMembers = computed(() => {
  const keyword = search.value.trim().toLocaleLowerCase();
  return selectedMemberships.value
    .map((membership) => ({ membership, person: peopleById.value[membership.person_id] }))
    .filter((item): item is { membership: DepartmentMembership; person: Person } => Boolean(item.person))
    .filter(({ person }) => !keyword || `${person.display_name} ${person.employee_no}`.toLocaleLowerCase().includes(keyword))
    .sort((left, right) => Number(right.membership.is_manager) - Number(left.membership.is_manager) || left.person.display_name.localeCompare(right.person.display_name, "zh-CN"));
});
const treeRows = computed<TreeRow[]>(() => {
  const rows: TreeRow[] = [];
  const visit = (department: Department, depth: number) => {
    const children = childrenByParent.value[department.id] ?? [];
    rows.push({ ...department, depth, hasChildren: children.length > 0 });
    if (expandedDepartmentIds.value.includes(department.id)) children.forEach((child) => visit(child, depth + 1));
  };
  rootDepartments.value.forEach((department) => visit(department, 0));
  return rows;
});

function profileFor(person: Person) { return profilesByPerson.value[person.id]; }
function roleLabel(membership: DepartmentMembership) { return membership.is_manager ? "部门主管" : "部门成员"; }
function titleLabel(person: Person) {
  const profile = profileFor(person);
  if (!profile) return "钉钉资料待同步";
  return profile.job_title || "未设置岗位";
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
  try {
    [entities.value, departments.value, people.value, memberships.value, dingtalkProfiles.value] = await Promise.all([
      api.legalEntities(), api.departments(), api.people(), api.departmentMemberships(), api.dingtalkProfiles(),
    ]);
    if (!selectedDepartmentId.value || !departments.value.some((item) => item.id === selectedDepartmentId.value)) {
      selectedDepartmentId.value = rootDepartments.value[0]?.id ?? departments.value[0]?.id ?? "";
    }
    selectedEntityId.value ||= entities.value[0]?.id ?? "";
    await loadLegalProfile();
    expandedDepartmentIds.value = [...new Set([...expandedDepartmentIds.value, ...rootDepartments.value.map((item) => item.id)])];
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "组织数据加载失败";
  } finally {
    loading.value = false;
  }
}
async function loadLegalProfile() {
  if (!selectedEntityId.value) return;
  const [profile, identifiers] = await Promise.all([api.legalEntityProfile(selectedEntityId.value), api.legalEntityIdentifiers(selectedEntityId.value)]);
  Object.assign(legalProfile, { entity_type: profile?.entity_type ?? "", jurisdiction: profile?.jurisdiction ?? "", registration_status: profile?.registration_status ?? "", legal_representative: profile?.legal_representative ?? "", established_on: profile?.established_on ?? "", registered_address: profile?.registered_address ?? "", registered_capital: profile?.registered_capital ?? "", business_scope: profile?.business_scope ?? "", source_note: profile?.source_note ?? "", verification_status: profile?.verification_status ?? "pending" });
  legalIdentifiers.value = identifiers;
}
async function saveLegalProfile() {
  if (!selectedEntityId.value) return;
  savingLegalProfile.value = true; error.value = "";
  try {
    await api.saveLegalEntityProfile(selectedEntityId.value, { ...legalProfile, entity_type: legalProfile.entity_type || null, jurisdiction: legalProfile.jurisdiction || null, registration_status: legalProfile.registration_status || null, legal_representative: legalProfile.legal_representative || null, established_on: legalProfile.established_on || null, registered_address: legalProfile.registered_address || null, registered_capital: legalProfile.registered_capital || null, business_scope: legalProfile.business_scope || null, source_note: legalProfile.source_note || null });
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
async function syncDingtalk() {
  const entity = entities.value[0];
  if (!entity) { error.value = "请先建立公司主体，再同步钉钉组织。"; return; }
  syncingDingtalk.value = true;
  error.value = "";
  try {
    await api.syncDingtalkDirectory(entity.id);
    await load();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "钉钉同步失败";
  } finally {
    syncingDingtalk.value = false;
  }
}

onMounted(load);
watch(selectedEntityId, () => { void loadLegalProfile(); });
</script>

<template>
  <div class="page-stack">
    <PageHeader title="组织架构" description="以钉钉组织树呈现部门层级、成员岗位与部门主管身份，为数字资产归属和责任管理提供依据。">
      <RouterLink class="secondary-button" to="/intake?mode=entity"><Plus :size="16" />登记公司主体</RouterLink><button class="primary-button" :disabled="syncingDingtalk" @click="syncDingtalk"><RefreshCw :size="16" :class="{ spinning: syncingDingtalk }" />{{ syncingDingtalk ? "正在同步…" : "同步钉钉组织" }}</button>
    </PageHeader>

    <div v-if="error" class="message-panel error-message">{{ error }}</div>

    <section class="org-summary" v-if="selectedEntity">
      <div class="org-company"><span class="record-icon"><Building2 :size="19" /></span><div><strong>{{ selectedEntity.name }}</strong><span>钉钉组织已接入 · {{ selectedEntity.code }}</span></div></div>
      <div><strong>{{ departments.length }}</strong><span>部门</span></div>
      <div><strong>{{ people.length }}</strong><span>成员</span></div>
      <div><strong>{{ memberships.filter((item) => item.is_manager).length }}</strong><span>部门主管</span></div>
    </section>

    <section v-if="selectedEntity" class="content-panel legal-entity-profile">
      <header class="panel-heading"><div><p class="eyebrow">L1 法人主体</p><h2>法人主体档案</h2><p>名称和主体标识用于证明实体成立；其余法定资料按证据补充，不影响已有资产和关系。</p></div><select v-model="selectedEntityId"><option v-for="entity in entities" :key="entity.id" :value="entity.id">{{ entity.name }}</option></select></header>
      <form class="legal-profile-form" @submit.prevent="saveLegalProfile"><label><span>主体类型</span><select v-model="legalProfile.entity_type"><option value="">暂未确认</option><option value="domestic_company">境内公司</option><option value="branch">分公司</option><option value="individual_business">个体工商户</option><option value="overseas_entity">境外法人</option><option value="other">其他主体</option></select></label><label><span>司法辖区 / 注册地</span><input v-model="legalProfile.jurisdiction" placeholder="例如：中国浙江省杭州市" /></label><label><span>存续状态</span><select v-model="legalProfile.registration_status"><option value="">暂未确认</option><option value="active">存续</option><option value="inactive">注销 / 停业</option><option value="pending">待核验</option></select></label><label><span>法定代表人</span><input v-model="legalProfile.legal_representative" /></label><label><span>成立日期</span><input v-model="legalProfile.established_on" type="date" /></label><label><span>注册资本</span><input v-model="legalProfile.registered_capital" /></label><label class="wide"><span>注册地址</span><textarea v-model="legalProfile.registered_address" rows="2" /></label><label class="wide"><span>经营范围</span><textarea v-model="legalProfile.business_scope" rows="2" /></label><label class="wide"><span>来源说明</span><textarea v-model="legalProfile.source_note" rows="2" placeholder="例如：工商档案、原始资料文件名或人工核验说明" /></label><label><span>核验状态</span><select v-model="legalProfile.verification_status"><option value="pending">待核验</option><option value="verified">已核验</option><option value="unverified">未核验</option></select></label><div class="form-actions"><button class="primary-button" :disabled="savingLegalProfile"><Save :size="16" />保存法人档案</button></div></form>
      <section class="legal-identifiers"><header><div><h3>主体标识</h3><p>统一社会信用代码、注册号等真实标识；未掌握时可以不填。</p></div></header><div class="identifier-chips"><span v-for="item in legalIdentifiers" :key="item.id" :class="{ primary: item.is_primary }"><small>{{ item.identifier_type }}</small><b>{{ item.identifier_value }}</b></span><span v-if="!legalIdentifiers.length" class="empty-chip">暂无已录入主体标识</span></div><form class="identifier-form-v2" @submit.prevent="addLegalIdentifier"><input v-model="legalIdentifierForm.identifier_type" placeholder="标识类型，如统一社会信用代码" /><input v-model="legalIdentifierForm.identifier_value" placeholder="标识值" required /><input v-model="legalIdentifierForm.source_note" placeholder="来源说明（可选）" /><button class="secondary-button" :disabled="savingLegalProfile"><Plus :size="15" />添加标识</button></form></section>
    </section>

    <section class="content-panel organization-workspace">
      <aside class="organization-tree">
        <div class="tree-heading"><div><strong>组织架构</strong><span>{{ departments.length }} 个部门</span></div></div>
        <div class="tree-root"><Building2 :size="16" /><span>{{ entities[0]?.name || "公司主体" }}</span></div>
        <button
          v-for="department in treeRows"
          :key="department.id"
          class="tree-node"
          :class="{ active: selectedDepartmentId === department.id }"
          :style="{ paddingLeft: `${14 + department.depth * 20}px` }"
          @click="toggleDepartment(department)"
        >
          <ChevronDown v-if="department.hasChildren && expandedDepartmentIds.includes(department.id)" :size="14" />
          <ChevronRight v-else-if="department.hasChildren" :size="14" />
          <i v-else />
          <span>{{ department.name }}</span>
          <small>{{ memberships.filter((item) => item.department_id === department.id).length }}</small>
        </button>
        <div v-if="!loading && !treeRows.length" class="mini-empty">尚未同步部门</div>
      </aside>

      <main class="organization-members">
        <header class="member-heading">
          <div><p class="eyebrow">当前部门</p><h2>{{ selectedDepartment?.name || "请选择部门" }}</h2><span>{{ selectedMembers.length }} 名成员 · {{ selectedManagers.length }} 名主管</span></div>
          <label class="table-search"><Search :size="16" /><input v-model="search" placeholder="搜索成员或工号" /></label>
        </header>
        <div class="member-table-wrap">
          <table class="member-table" v-if="selectedDepartment">
            <thead><tr><th>成员</th><th>组织身份</th><th>岗位</th><th>工号</th></tr></thead>
            <tbody>
              <tr v-for="{ membership, person } in selectedMembers" :key="membership.id">
                <td><div class="member-name"><span class="avatar">{{ person.display_name.slice(0, 1) }}</span><strong>{{ person.display_name }}</strong></div></td>
                <td><span class="role-tag" :class="{ manager: membership.is_manager }"><Crown v-if="membership.is_manager" :size="13" /><UserRound v-else :size="13" />{{ roleLabel(membership) }}</span></td>
                <td>{{ titleLabel(person) }}</td>
                <td>{{ person.employee_no }}</td>
              </tr>
              <tr v-if="!selectedMembers.length"><td colspan="4" class="table-empty">该部门暂无匹配成员</td></tr>
            </tbody>
          </table>
          <div v-else class="large-empty-panel"><Users :size="28" /><strong>请选择左侧部门</strong><p>选择部门后查看成员、岗位以及主管身份。</p></div>
        </div>
      </main>
    </section>

    <p class="organization-note"><StatusBadge tone="success">钉钉同步</StatusBadge> 部门负责人身份来自钉钉的部门主管标记；岗位来自成员详情。</p>

  </div>
</template>
