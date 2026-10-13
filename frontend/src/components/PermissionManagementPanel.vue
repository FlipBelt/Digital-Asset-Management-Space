<script lang="ts">
export interface PermissionRoleAssignment {
  id: string | null; role_code: string; role_name: string; scope_type: string;
  scope_id: string | null; scope_label: string; source: "manual" | "stored" | "directory"; revocable: boolean;
}
export interface PermissionResourceGrant {
  id: string; asset_id: string | null; asset_name: string; scope_label: string;
  source: "direct" | "department"; grant_role: string; starts_at: string | null;
  ends_at: string | null; revocable: boolean;
}
export interface PermissionUserSummary {
  id: string; person_id: string | null; display_name: string; employee_no: string | null;
  department: string; is_active: boolean; is_effective: boolean; employment_status: string | null;
  roles: string[]; revision: string;
}
export interface PermissionUser extends PermissionUserSummary {
  assignments: PermissionRoleAssignment[]; resource_grants: PermissionResourceGrant[];
}
export interface PermissionCatalog {
  current_user_id: string;
  roles: { code: string; name: string; scope_type: string; scope_label: string }[];
  departments: { id: string; name: string; role_codes: string[] }[];
  resources: { id: string; name: string; asset_code: string }[];
}
export interface PermissionRequest { request_id: string; expected_revision: string; reason: string }
export interface PermissionManagementClient {
  permissionCatalog(): Promise<PermissionCatalog>;
  permissionUsers(keyword?: string): Promise<{ items: PermissionUserSummary[]; total: number }>;
  permissionUser(id: string): Promise<PermissionUser>;
  grantPermissionRole(id: string, body: PermissionRequest & { role_code: string; department_id: string | null }): Promise<PermissionUser>;
  revokePermissionRole(id: string, assignment: string, body: PermissionRequest): Promise<PermissionUser>;
  setPermissionAccess(id: string, body: PermissionRequest & { enabled: boolean }): Promise<PermissionUser>;
  grantPermissionResource(id: string, body: PermissionRequest & { asset_id: string; starts_at: string | null; ends_at: string | null }): Promise<PermissionUser>;
  revokePermissionResource(id: string, grant: string, body: PermissionRequest): Promise<PermissionUser>;
}
</script>
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { KeyRound, RefreshCw, Search, ShieldCheck } from "lucide-vue-next";
import ModalPanel from "./ModalPanel.vue";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps<{ client: PermissionManagementClient }>();
const emit = defineEmits<{ changed: [] }>();
const catalog = ref<PermissionCatalog | null>(null), users = ref<PermissionUserSummary[]>([]);
const selected = ref<PermissionUser | null>(null), selectedId = ref("");
const query = ref(""), total = ref(0), loading = ref(true), loadingUser = ref(false), saving = ref(false);
const error = ref(""), formError = ref(""), message = ref("");
type Action = "role" | "revoke-role" | "resource" | "revoke-resource" | "access";
const action = ref<Action | null>(null), assignment = ref<PermissionRoleAssignment | null>(null);
const resourceGrant = ref<PermissionResourceGrant | null>(null);
const form = reactive({ role_code: "", department_id: "", asset_id: "", reason: "", starts_at: "", ends_at: "" });
let requestId = "", previousBody = "", userRequest = 0;
const departments = computed(() => catalog.value?.departments.filter(row => row.role_codes.includes(form.role_code)) ?? []);
const selectedRole = computed(() => catalog.value?.roles.find(row => row.code === form.role_code));
const modalTitle = computed(() => ({ role: "授予预置角色", "revoke-role": "撤销人工角色授权", resource: "授予资源查看权限", "revoke-resource": "撤销直接资源授权", access: selected.value?.is_active ? "暂停本系统访问" : "恢复本系统访问" })[action.value || "role"]);

async function selectUser(id: string) {
  const request = ++userRequest;
  selectedId.value = id; selected.value = null; loadingUser.value = true; error.value = "";
  try { const data = await props.client.permissionUser(id); if (request === userRequest) selected.value = data; }
  catch (cause) { if (request === userRequest) error.value = cause instanceof Error ? cause.message : "员工权限读取失败"; }
  finally { if (request === userRequest) loadingUser.value = false; }
}
async function loadUsers() {
  loading.value = true; error.value = "";
  try {
    const result = await props.client.permissionUsers(query.value);
    users.value = result.items; total.value = result.total;
    const id = users.value.some(row => row.id === selectedId.value) ? selectedId.value : users.value[0]?.id;
    if (id) await selectUser(id); else { selected.value = null; selectedId.value = ""; }
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "员工账号读取失败"; }
  finally { loading.value = false; }
}
async function load() {
  loading.value = true; error.value = "";
  try { catalog.value = await props.client.permissionCatalog(); await loadUsers(); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "权限目录读取失败"; loading.value = false; }
}
function open(mode: Action, role?: PermissionRoleAssignment, grant?: PermissionResourceGrant) {
  if (!selected.value) return;
  action.value = mode; assignment.value = role || null; resourceGrant.value = grant || null;
  Object.assign(form, { role_code: "", department_id: "", asset_id: "", reason: "", starts_at: "", ends_at: "" });
  formError.value = ""; requestId = crypto.randomUUID(); previousBody = "";
}
async function save() {
  const person = selected.value, mode = action.value;
  if (!person || !mode || saving.value) return;
  const base = { expected_revision: person.revision, reason: form.reason.trim() };
  const specific = mode === "role" ? { role_code: form.role_code, department_id: form.department_id || null }
    : mode === "resource" ? { asset_id: form.asset_id, starts_at: form.starts_at || null, ends_at: form.ends_at || null }
      : mode === "access" ? { enabled: !person.is_active } : {};
  const snapshot = JSON.stringify({ ...base, ...specific });
  if (previousBody && previousBody !== snapshot) requestId = crypto.randomUUID();
  previousBody = snapshot; saving.value = true; formError.value = "";
  const body = { ...base, request_id: requestId };
  try {
    if (mode === "role") await props.client.grantPermissionRole(person.id, { ...body, role_code: form.role_code, department_id: form.department_id || null });
    else if (mode === "revoke-role" && assignment.value?.id) await props.client.revokePermissionRole(person.id, assignment.value.id, body);
    else if (mode === "resource") await props.client.grantPermissionResource(person.id, { ...body, asset_id: form.asset_id, starts_at: form.starts_at || null, ends_at: form.ends_at || null });
    else if (mode === "revoke-resource" && resourceGrant.value) await props.client.revokePermissionResource(person.id, resourceGrant.value.id, body);
    else if (mode === "access") await props.client.setPermissionAccess(person.id, { ...body, enabled: !person.is_active });
    message.value = mode === "revoke-role" ? "人工授权已撤销；通讯录派生权限仍按来源生效。"
      : mode === "revoke-resource" ? "这项直接授权已撤销；其他共享范围和部门授权继续单独管理。"
        : mode === "access" ? (person.is_active ? "本系统访问已暂停，原登录会话已撤销。" : "本系统访问已恢复，请员工重新登录。") : "授权已保存。";
    action.value = null; await loadUsers(); emit("changed");
  } catch (cause) { formError.value = cause instanceof Error ? cause.message : "权限保存失败，请核对后重试"; }
  finally { saving.value = false; }
}
onMounted(load);
</script>
<template>
  <section class="permission-management">
    <header><div><h2>权限管理</h2><p>系统管理员管理本系统角色和资源访问。系统、资产管理员作用于全集团；部门负责人和组长限定在所选组织范围。</p></div><button class="secondary-button" :disabled="loading || saving" @click="load"><RefreshCw :size="16" />刷新</button></header>
    <p v-if="message" class="message-panel success-message" role="status">{{ message }}</p>
    <p v-if="error" class="message-panel error-message" role="alert">{{ error }}<button class="text-button" @click="load">重新读取</button></p>
    <div v-if="loading" class="mini-empty" role="status">正在读取员工账号及权限来源…</div>
    <div v-else-if="catalog" class="permission-workspace">
      <aside class="content-panel permission-users"><form @submit.prevent="loadUsers"><label class="fusion-search"><Search :size="16" /><input v-model="query" type="search" aria-label="搜索权限管理员工" placeholder="姓名、工号或部门" /></label><button class="secondary-button" type="submit">搜索</button></form><p>{{ total }} 个本系统登录账号<span v-if="total > users.length">，当前显示 {{ users.length }} 个，请缩小搜索范围</span></p><ul><li v-for="person in users" :key="person.id"><button :class="{ selected: selectedId === person.id }" :aria-pressed="selectedId === person.id" @click="selectUser(person.id)"><strong>{{ person.display_name }}</strong><small>{{ person.department }}</small><small v-if="!person.is_effective">{{ person.employment_status === 'departed' ? '已离职' : '访问已暂停或资料待核实' }}</small></button></li></ul><p v-if="!users.length" class="mini-empty">没有匹配的登录账号。员工档案需先完成本人登录，再设置本系统权限。</p></aside>
      <div v-if="loadingUser" class="content-panel mini-empty" role="status">正在读取所选员工权限…</div>
      <section v-else-if="selected" class="content-panel permission-detail">
        <header><div><h3>{{ selected.display_name }}</h3><p>{{ selected.employee_no || '本地管理账号' }} · {{ selected.department }}</p></div><button class="secondary-button" :disabled="saving || selected.id === catalog.current_user_id || selected.employment_status === 'departed'" @click="open('access')">{{ selected.is_active ? '暂停访问' : '恢复访问' }}</button></header>
        <div class="permission-section-heading"><h3><ShieldCheck :size="18" />系统角色</h3><button class="primary-button" :disabled="!selected.is_effective || saving" @click="open('role')">授予角色</button></div>
        <ul class="permission-list"><li v-for="role in selected.assignments" :key="role.id || `${role.role_code}:${role.scope_id}:source`"><div><strong>{{ role.role_name }}</strong><small>{{ role.scope_label }} · {{ role.source === 'directory' ? '通讯录主管资料派生' : role.source === 'manual' ? '人工授予' : '已有角色授权' }}</small></div><button v-if="role.revocable" class="text-button danger-text" :aria-label="`撤销${role.role_name}人工授权`" @click="open('revoke-role', role)">撤销</button><span v-else class="muted-text">在通讯录来源管理</span></li></ul>
        <p v-if="!selected.assignments.length" class="mini-empty">尚无有效系统角色。</p>
        <div class="permission-section-heading"><h3><KeyRound :size="18" />资源访问</h3><button class="secondary-button" :disabled="!selected.is_effective || !selected.person_id || saving" @click="open('resource')">授予查看权限</button></div>
        <p>直接授权用于查看指定公司资源。已有共享范围、部门授权和负责人权限分别保留；子账号由父账号管理。</p>
        <ul class="permission-list"><li v-for="grant in selected.resource_grants" :key="grant.id"><div><strong>{{ grant.asset_name }}</strong><small>{{ grant.scope_label }} · {{ grant.source === 'direct' ? '直接授权' : '部门共享授权' }}<span v-if="grant.ends_at"> · 截止 {{ grant.ends_at }}</span></small></div><button v-if="grant.revocable" class="text-button danger-text" :aria-label="`撤销${grant.asset_name}直接授权`" @click="open('revoke-resource', undefined, grant)">撤销</button><StatusBadge v-else>部门共享</StatusBadge></li></ul>
        <p v-if="!selected.resource_grants.length" class="mini-empty">尚无直接或部门资源授权。公共共享资源仍按原共享范围可见。</p>
      </section>
      <div v-else class="content-panel mini-empty">选择员工，查看本系统权限和授权来源。</div>
    </div>
    <ModalPanel v-if="action && selected && catalog" :title="modalTitle" :trap-focus="true" @close="!saving && (action = null)">
      <form class="form-grid one-column" :aria-busy="saving" @submit.prevent="save"><p><strong>{{ selected.display_name }}</strong> · {{ selected.department }}</p>
        <template v-if="action === 'role'"><label>预置角色<select v-model="form.role_code" required @change="form.department_id = ''"><option value="">选择预置角色</option><option v-for="role in catalog.roles" :key="role.code" :value="role.code">{{ role.name }} · {{ role.scope_label }}</option></select></label><label v-if="selectedRole?.scope_type === 'department'">组织范围<select v-model="form.department_id" required><option value="">选择部门或小组</option><option v-for="department in departments" :key="department.id" :value="department.id">{{ department.name }}</option></select></label><p v-if="selectedRole?.scope_type === 'company'" class="form-hint">此角色适用于全集团。系统管理员可继续管理其他员工权限，资产管理员可维护集团资产及账号。</p></template>
        <p v-else-if="action === 'revoke-role'" class="form-hint">撤销 {{ assignment?.role_name }} 的人工授权。若同时存在通讯录派生权限，派生项会保留并显示来源；最后一位可登录系统管理员不能撤销。</p>
        <template v-else-if="action === 'resource'"><label>公司资源<select v-model="form.asset_id" required><option value="">选择已有公司资源</option><option v-for="resource in catalog.resources" :key="resource.id" :value="resource.id">{{ resource.name }} · {{ resource.asset_code }}</option></select></label><label>开始日期（可选）<input v-model="form.starts_at" type="date" /></label><label>结束日期（可选）<input v-model="form.ends_at" type="date" /></label></template>
        <p v-else-if="action === 'revoke-resource'" class="form-hint">撤销 {{ resourceGrant?.asset_name }} 的这项直接授权。公共共享、部门共享或其他角色仍可能提供访问。</p>
        <p v-else class="form-hint">{{ selected.is_active ? '暂停本系统访问并撤销现有登录会话。员工记录、角色和资源授权保留，外部平台权限需在对应平台处理。' : '恢复本系统访问，已有角色按当前配置生效；员工需重新登录。' }}</p>
        <label>调整原因<textarea v-model="form.reason" rows="3" required maxlength="1000" placeholder="说明授权用途或调整依据" /></label><p v-if="formError" class="form-error" role="alert">{{ formError }}</p><div class="form-actions"><button class="secondary-button" type="button" :disabled="saving" @click="action = null">取消</button><button class="primary-button" :disabled="saving">{{ saving ? '正在保存…' : '确认保存' }}</button></div>
      </form>
    </ModalPanel>
  </section>
</template>
<style scoped>
.permission-management,.permission-detail { display:grid; gap:20px; min-width:0; }
header,.permission-section-heading { display:flex; align-items:center; justify-content:space-between; gap:14px; flex-wrap:wrap; }
h2,h3,p { margin:0; } h2 { font-size:23px; margin-bottom:9px; } h3 { display:flex; gap:8px; align-items:center; font-size:18px; }
p,small { color:var(--muted); line-height:1.6; overflow-wrap:anywhere; } small { display:block; }
.permission-workspace { display:grid; grid-template-columns:minmax(220px, .35fr) minmax(0, 1fr); gap:20px; min-width:0; }
.permission-users { align-self:start; display:grid; gap:14px; padding:18px; }
.permission-users form { display:flex; flex-wrap:wrap; gap:8px; } .fusion-search { min-width:0; flex:1; }
.permission-users ul,.permission-list { margin:0; padding:0; list-style:none; }
.permission-users li button { display:block; text-align:left; width:100%; border:1px solid transparent; background:transparent; padding:12px; border-radius:8px; }
.permission-users li button.selected { border-color:var(--border); background:var(--paper-deep); }
.permission-users li button:focus-visible { outline:2px solid var(--ink); outline-offset:2px; }
.permission-list li { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:16px 0; border-top:1px solid var(--border); }
.permission-list li > div { flex:1; min-width:0; } .permission-detail { align-content:start; }
.danger-text { color:var(--red); } .muted-text { color:var(--muted); font-size:12px; }
@media(max-width:760px) { .permission-workspace { grid-template-columns:1fr; } .permission-users ul { max-height:300px; overflow:auto; } .permission-list li { flex-wrap:wrap; } }
</style>
