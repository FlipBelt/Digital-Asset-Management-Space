<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ChevronDown, ChevronRight, UserRound, Users } from "lucide-vue-next";
import { api, type Department, type LegalEntity, type Person, type RegistrationIdentity } from "../lib/api";
import PeoplePicker from "./PeoplePicker.vue";
import ModalPanel from "./ModalPanel.vue";
import { contactIdentifier, parseContactRows, type ContactRow } from "../lib/contactRegistration";
defineProps<{ canManage: boolean }>();
const rows = ref<RegistrationIdentity[]>([]), people = ref<Person[]>([]), departments = ref<Department[]>([]), companies = ref<LegalEntity[]>([]);
const loading = ref(true), saving = ref(false), error = ref(""), message = ref(""), query = ref(""), trash = ref(false);
const editing = ref(false), batch = ref(false), input = ref(""), source = ref(""), company = ref("");
const editingIdentity = ref<RegistrationIdentity | null>(null), identityType = ref("phone");
const form = reactive<ContactRow>({ identifier: "", legal_entity_id: null, custodian_person_id: null, owner_department_id: null, source_nature: "company_owned", verification_status: "documented", registration_blocked: false, expected_version: null, note: "" });
const action = ref<"rename" | "delete" | "restore">("rename"), selected = ref<RegistrationIdentity | null>(null), name = ref(""), actionError = ref("");
let requestId = crypto.randomUUID(), previousPayload = "", actionRequestId = crypto.randomUUID(), previousActionPayload = "";
const preview = computed(() => parseContactRows(input.value, people.value, departments.value, rows.value, company.value));
const visible = computed(() => rows.value.filter(row => [row.name, row.identifier, personName(row.custodian_person_id), departmentName(row.owner_department_id), row.note].join(" ").toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase())));
const collapsedGroups = ref<string[]>([]);
const employeeGroups = computed(() => {
  const grouped = new Map<string, { id: string; person: Person | undefined; items: RegistrationIdentity[] }>();
  for (const row of visible.value) {
    const id = row.custodian_person_id || "shared";
    if (!grouped.has(id)) grouped.set(id, { id, person: people.value.find(person => person.id === id), items: [] });
    grouped.get(id)!.items.push(row);
  }
  return [...grouped.values()].sort((a, b) => Number(a.id === "shared") - Number(b.id === "shared") || (a.person?.display_name || "").localeCompare(b.person?.display_name || "", "zh-CN"));
});
function toggleGroup(id: string) { collapsedGroups.value = collapsedGroups.value.includes(id) ? collapsedGroups.value.filter(item => item !== id) : [...collapsedGroups.value, id]; }
function personName(id: string | null) { return people.value.find(row => row.id === id)?.display_name || "部门共用 / 未登记同事"; }
function departmentName(id: string | null | undefined) { return departments.value.find(row => row.id === id)?.name || "未登记使用部门"; }
function typeName(row: RegistrationIdentity) { return ({ phone: "手机号", email: "邮箱", wechat: "微信标识", username: "用户名" }[row.identity_type] || "账号 / 其他标识"); }
async function load() {
  loading.value = true; error.value = "";
  try { [rows.value, people.value, departments.value, companies.value] = await Promise.all([api.registrationIdentities(trash.value), api.people(), api.departments(), api.legalEntities()]); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "注册与登录标识读取失败"; }
  finally { loading.value = false; }
}
async function switchTrash() { trash.value = !trash.value; editing.value = false; query.value = ""; await load(); }
function edit(row?: RegistrationIdentity) {
  batch.value = false; editing.value = true; source.value = ""; error.value = "";
  editingIdentity.value = row || null;
  identityType.value = row ? (["phone", "email", "username", "wechat", "other"].includes(row.identity_type) ? row.identity_type : "other") : "phone";
  requestId = crypto.randomUUID(); previousPayload = "";
  Object.assign(form, { identifier: row?.identifier || "", legal_entity_id: row?.legal_entity_id || null,
    custodian_person_id: row?.custodian_person_id || null, owner_department_id: row?.owner_department_id || null,
    source_nature: row?.source_nature || "company_owned", verification_status: "documented",
    registration_blocked: row?.registration_blocked || false, expected_version: row?.version || null, note: row?.note || "" });
}
function openAction(row: RegistrationIdentity, value: typeof action.value) {
  selected.value = row; action.value = value; name.value = row.name; actionError.value = ""; actionRequestId = crypto.randomUUID(); previousActionPayload = "";
}
function closeAction() { if (!saving.value) selected.value = null; }
async function applyAction() {
  const row = selected.value; if (!row || saving.value) return;
  saving.value = true; actionError.value = "";
  try {
    if (action.value === "rename") {
      const body = { name: name.value.trim(), version: row.version }, snapshot = JSON.stringify(body);
      if (previousActionPayload && previousActionPayload !== snapshot) actionRequestId = crypto.randomUUID();
      previousActionPayload = snapshot;
      await api.renameRegistrationIdentity(row.asset_id, { ...body, request_id: actionRequestId });
    }
    else if (action.value === "delete") await api.deleteAsset(row.asset_id, row.version);
    else await api.restoreAsset(row.asset_id, row.version);
    message.value = action.value === "rename" ? "名称已保存，原登录标识和账号引用保留。" : action.value === "delete" ? "已移入回收站，可在回收站恢复。" : "标识已恢复，可继续被平台账号引用。";
    selected.value = null; await load();
  } catch (cause) { actionError.value = cause instanceof Error ? cause.message : "操作失败，请重试"; }
  finally { saving.value = false; }
}
async function save() {
  if (saving.value) return;
  error.value = ""; message.value = "";
  if (!source.value.trim()) { error.value = "请注明核对资料的来源"; return; }
  let contacts: ContactRow[];
  if (batch.value) {
    if (!preview.value.rows.length || preview.value.errors.length) { error.value = "请先处理预览中的问题"; return; }
    contacts = preview.value.rows;
  } else {
    const identifier = editingIdentity.value && !["phone", "email"].includes(identityType.value)
      ? form.identifier.trim() : contactIdentifier(form.identifier);
    if (!identifier) { error.value = "请填写有效的标识内容，手机号与邮箱请核对格式。"; return; }
    if (editingIdentity.value && ["phone", "email"].includes(identityType.value) && (identifier.includes("@") ? "email" : "phone") !== identityType.value) {
      error.value = "标识内容与所选类型不一致，请核对手机号或邮箱格式。"; return;
    }
    const existing = rows.value.find(row => contactIdentifier(row.identifier) === identifier);
    contacts = [{ ...form, identifier, expected_version: form.expected_version ?? existing?.version ?? null }];
  }
  const target = !batch.value ? editingIdentity.value : null;
  const body = target ? { ...contacts[0], identity_type: identityType.value, source_note: source.value.trim() }
    : { rows: contacts, source_note: source.value.trim() };
  const snapshot = JSON.stringify({ target: target?.asset_id, body });
  if (previousPayload && previousPayload !== snapshot) requestId = crypto.randomUUID();
  previousPayload = snapshot; saving.value = true;
  try {
    if (target) {
      await api.updateRegistrationIdentity(target.asset_id, { ...body, request_id: requestId });
      message.value = "标识资料已保存，原记录编号和平台引用保留；未进行短信或邮箱验证。";
    } else {
      const result = await api.reconcileContacts({ ...body, request_id: requestId });
      message.value = result.length + " 条标识已登记 / 更新；已按资料核对，未进行短信或邮箱验证。";
    }
    editing.value = false; batch.value = false; input.value = ""; requestId = crypto.randomUUID(); previousPayload = "";
    await load();
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "保存失败"; }
  finally { saving.value = false; }
}
onMounted(load);
</script>
<template>
  <section class="content-panel contact-panel">
    <header><div><h2>{{ trash ? '注册与登录标识回收站' : '注册与登录标识' }}</h2><p>统一维护手机号、邮箱及用户名等账号标识，先登记保管同事或使用部门，再由平台账号引用。</p></div><div v-if="canManage" class="contact-actions"><template v-if="!trash"><RouterLink class="secondary-button" to="/intake?mode=identity">登记标识</RouterLink><button class="secondary-button" :disabled="saving" @click="edit()">登记手机号 / 邮箱</button><button class="secondary-button" :disabled="saving" @click="batch = true; editing = true; error = ''; source = ''">批量登记</button></template><button class="secondary-button" :disabled="loading || saving" @click="switchTrash">{{ trash ? '返回标识管理' : '回收站' }}</button></div></header>
    <p v-if="message" class="message-panel success-message" role="status">{{ message }}</p><p v-if="error" class="message-panel error-message" role="alert">{{ error }}</p>
    <form v-if="editing && canManage" class="contact-form" @submit.prevent="save">
      <template v-if="batch"><label>归属公司（共用号码）<select v-model="company" required><option value="" disabled>选择公司</option><option v-for="row in companies" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><label class="wide">粘贴手机号 / 邮箱资料<textarea v-model="input" rows="7" required placeholder="每行：手机号或邮箱〔Tab〕使用人〔Tab〕使用部门〔Tab〕说明。共用使用人填转发器、前台手机或共用。" /></label><p class="wide form-hint">人员按唯一在职姓名匹配，已有标识按原记录更新；无法匹配的行需先核对。</p><p v-for="item in preview.errors" :key="item" class="wide error-message">{{ item }}</p><div v-if="preview.rows.length" class="wide contact-table-wrap"><table><caption>保存预览 · {{ preview.rows.length }} 条</caption><thead><tr><th>标识内容</th><th>同事 / 使用部门</th><th>操作</th><th>使用限制</th></tr></thead><tbody><tr v-for="row in preview.rows" :key="row.identifier"><td>{{ row.identifier }}</td><td>{{ personName(row.custodian_person_id) }}<small>{{ departmentName(row.owner_department_id) }}</small></td><td>{{ row.expected_version ? '更新已有记录' : '新增登记' }}</td><td>{{ row.registration_blocked ? '禁止用于注册' : '未注明限制' }}</td></tr></tbody></table></div></template>
      <template v-else>
        <p v-if="editingIdentity" class="wide form-hint">正在修改 {{ editingIdentity.asset_code }}。更正标识后，原编号和平台引用保留；此操作不会更改外部平台的实际登录账号。</p>
        <label v-if="editingIdentity">标识类型<select v-model="identityType" :disabled="saving"><option value="phone">手机号</option><option value="email">邮箱</option><option value="username">用户名</option><option value="wechat">微信标识</option><option value="other">账号 / 其他标识</option></select></label>
        <label>{{ editingIdentity ? '标识内容' : '手机号 / 邮箱' }}<input v-model="form.identifier" required maxlength="500" :disabled="saving" autocomplete="off" /></label>
        <label>标识归属公司<select v-model="form.legal_entity_id" :required="!editingIdentity" :disabled="saving"><option :value="null" :disabled="!editingIdentity">{{ editingIdentity ? '暂未登记公司' : '选择公司' }}</option><option v-for="row in companies" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><PeoplePicker id="contact-holder" v-model:person-id="form.custodian_person_id" label="保管同事（共用可留空）" :people="people.filter(row => row.legal_entity_id === form.legal_entity_id)" :departments="departments" :disabled="saving" /><label>使用部门<select v-model="form.owner_department_id"><option :value="null">未登记部门</option><option v-for="row in departments.filter(row => row.legal_entity_id === form.legal_entity_id)" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><label class="wide">说明<textarea v-model="form.note" rows="3" /></label><label class="contact-check wide"><input v-model="form.registration_blocked" type="checkbox" />禁止用于平台注册（例如法人保留号码）</label></template>
      <label class="wide">核对资料来源 *<input v-model="source" required placeholder="例如：公司号码使用情况表及核对日期" /></label><div class="contact-actions wide"><button type="button" class="secondary-button" :disabled="saving" @click="editing = false">取消</button><button class="primary-button" :disabled="saving || (batch && (!!preview.errors.length || !preview.rows.length))">{{ saving ? '保存中…' : '保存标识资料' }}</button></div>
    </form>
    <p v-if="loading" role="status">正在读取注册与登录标识…</p>
    <template v-else><label class="contact-search">搜索注册与登录标识<input v-model="query" type="search" placeholder="名称、手机号、邮箱、用户名、同事或部门" /></label><div class="contact-table-wrap"><table><caption>共 {{ visible.length }} 条{{ trash ? '已删除标识' : '注册与登录标识' }} · 按员工分为 {{ employeeGroups.length }} 组</caption><thead><tr><th scope="col">名称 / 登录标识</th><th scope="col">保管同事 / 使用部门</th><th scope="col">资料状态</th><th scope="col">操作</th></tr></thead><tbody v-for="group in employeeGroups" :key="group.id"><tr class="employee-group-heading"><td colspan="4"><button class="employee-group-toggle" :aria-expanded="!collapsedGroups.includes(group.id)" @click="toggleGroup(group.id)"><ChevronRight v-if="collapsedGroups.includes(group.id)" :size="16" aria-hidden="true" /><ChevronDown v-else :size="16" aria-hidden="true" /><UserRound v-if="group.person" :size="18" aria-hidden="true" /><Users v-else :size="18" aria-hidden="true" /><strong>{{ group.person?.display_name || '部门共用 / 待补保管人' }}</strong><span v-if="group.person">{{ departmentName(group.person.department_id) }}{{ group.person.employment_status === 'departed' ? ' · 已离职' : '' }}</span><span class="group-count">{{ group.items.length }} 条标识</span></button></td></tr><tr v-for="row in collapsedGroups.includes(group.id) ? [] : group.items" :key="row.asset_id"><td><strong>{{ row.name }}</strong><small>{{ typeName(row) }} · {{ row.identifier }}</small><small v-if="row.registration_blocked" class="error-message">禁止用于平台注册</small></td><td>{{ personName(row.custodian_person_id) }}<small>{{ departmentName(row.owner_department_id) }}</small></td><td>{{ trash ? '已删除' : row.verification_status === 'documented' ? '已按资料登记' : row.verification_status === 'verified' ? '已核验' : '资料待核对' }}</td><td><div class="row-actions"><template v-if="canManage && !trash"><button class="secondary-button" :disabled="saving" @click="openAction(row, 'rename')">修改名称</button><button class="text-button" :disabled="saving" @click="edit(row)">修改资料</button><button class="text-button deletion-button" :disabled="saving" @click="openAction(row, 'delete')">删除</button></template><button v-if="canManage && trash" class="secondary-button" :disabled="saving" @click="openAction(row, 'restore')">恢复</button><RouterLink v-if="!trash" :to="'/assets/' + row.asset_id + '?tab=relations'">查看引用</RouterLink></div></td></tr></tbody></table><p v-if="!visible.length" class="mini-empty">{{ query ? '没有匹配资料，请调整搜索。' : trash ? '回收站为空。' : '尚未登记注册或登录标识。' }}</p></div></template>
    <ModalPanel v-if="selected" :title="action === 'rename' ? '修改标识名称' : action === 'delete' ? '删除注册与登录标识' : '恢复注册与登录标识'" trap-focus @close="closeAction">
      <p>{{ selected.name }}</p><p>{{ typeName(selected) }} · {{ selected.identifier }}</p>
      <label v-if="action === 'rename'" class="contact-search">名称<input v-model="name" maxlength="200" :disabled="saving" /></label>
      <p v-else>{{ action === 'delete' ? '将移入可恢复的回收站。仍被平台账号或资产引用时，需先解除引用。' : '恢复后保留原名称、标识和历史资料，可继续由平台账号引用。' }}</p>
      <p v-if="actionError" class="message-panel error-message" role="alert">{{ actionError }}</p>
      <template #footer><button class="secondary-button" :disabled="saving" @click="closeAction">取消</button><button class="primary-button" :disabled="saving || (action === 'rename' && !name.trim())" @click="applyAction">{{ saving ? '处理中…' : action === 'rename' ? '保存名称' : action === 'delete' ? '移入回收站' : '恢复标识' }}</button></template>
    </ModalPanel>
  </section>
</template>
<style scoped>
.contact-panel { display:grid; gap:20px; min-width:0; }.contact-panel header, .contact-actions { display:flex; align-items:start; flex-wrap:wrap; justify-content:space-between; gap:12px; }.contact-panel h2 { margin:0; }.contact-panel p { color:var(--muted); line-height:1.7; }.contact-form { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:20px; padding:20px; border:1px solid var(--border); border-radius:var(--radius); }.contact-form label,.contact-search { display:grid; gap:8px; }.wide { grid-column:1/-1; }.contact-panel input,.contact-panel select,.contact-panel textarea { width:100%; min-height:42px; box-sizing:border-box; border:1px solid var(--border); border-radius:var(--radius); padding:10px 12px; background:var(--surface); color:var(--text); }.contact-panel .contact-check { display:flex; align-items:center; }.contact-check input { width:18px; min-height:18px; }.contact-table-wrap { overflow:auto; }table { width:100%; border-collapse:collapse; text-align:left; }caption { text-align:left; padding:10px 0; color:var(--muted); }th,td { padding:14px 10px; border-bottom:1px solid var(--border); vertical-align:top; }td small { display:block; margin-top:5px; color:var(--muted); }td:first-child { overflow-wrap:anywhere; }.row-actions { display:flex; flex-wrap:wrap; align-items:center; gap:10px; min-width:200px; }.employee-group-heading td { padding:0; background:var(--surface-muted, #f6f7f6); }.employee-group-toggle { display:flex; align-items:center; gap:10px; width:100%; min-height:48px; padding:12px 10px; border:0; background:transparent; color:var(--text); text-align:left; cursor:pointer; }.employee-group-toggle span { color:var(--muted); font-size:12px; }.employee-group-toggle .group-count { margin-left:auto; white-space:nowrap; }.deletion-button { color:var(--danger); }.contact-panel :focus-visible { outline:2px solid var(--primary); outline-offset:3px; }@media(max-width:700px) { .contact-form { grid-template-columns:minmax(0,1fr); padding:14px; }table { min-width:680px; } }
</style>
