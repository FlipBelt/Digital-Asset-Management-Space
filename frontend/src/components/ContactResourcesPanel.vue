<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { api, type Department, type LegalEntity, type Person, type RegistrationIdentity } from "../lib/api";
import PeoplePicker from "./PeoplePicker.vue";
import { contactIdentifier, parseContactRows, type ContactRow } from "../lib/contactRegistration";

const props = defineProps<{ canManage: boolean }>();
const rows = ref<RegistrationIdentity[]>([]), people = ref<Person[]>([]), departments = ref<Department[]>([]), companies = ref<LegalEntity[]>([]);
const loading = ref(true), saving = ref(false), error = ref(""), message = ref(""), query = ref("");
const editing = ref(false), batch = ref(false), input = ref(""), source = ref(""), company = ref("");
const form = reactive<ContactRow>({ identifier: "", legal_entity_id: null, custodian_person_id: null, owner_department_id: null, source_nature: "company_owned", verification_status: "documented", registration_blocked: false, expected_version: null, note: "" });
let requestId = crypto.randomUUID(), previousPayload = "";
const preview = computed(() => parseContactRows(input.value, people.value, departments.value, rows.value, company.value));
const visible = computed(() => rows.value.filter(row => `${row.identifier} ${personName(row.custodian_person_id)} ${departmentName(row.owner_department_id)} ${row.note || ''}`.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase())));
function personName(id: string | null) { return people.value.find(row => row.id === id)?.display_name || "部门共用 / 未登记同事"; }
function departmentName(id: string | null | undefined) { return departments.value.find(row => row.id === id)?.name || "未登记使用部门"; }
async function load() {
  loading.value = true; error.value = "";
  try { [rows.value, people.value, departments.value, companies.value] = await Promise.all([api.registrationIdentities(), api.people(), api.departments(), api.legalEntities()]); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "通讯资源读取失败"; }
  finally { loading.value = false; }
}
function edit(row?: RegistrationIdentity) {
  batch.value = false; editing.value = true; source.value = ""; error.value = "";
  Object.assign(form, { identifier: row?.identifier || "", legal_entity_id: row?.legal_entity_id || null,
    custodian_person_id: row?.custodian_person_id || null, owner_department_id: row?.owner_department_id || null,
    source_nature: row?.source_nature || "company_owned", verification_status: "documented",
    registration_blocked: row?.registration_blocked || false, expected_version: row?.version || null, note: row?.note || "" });
}
async function save() {
  error.value = ""; message.value = "";
  if (!source.value.trim()) { error.value = "请注明核对资料的来源"; return; }
  let contacts: ContactRow[];
  if (batch.value) {
    if (!preview.value.rows.length || preview.value.errors.length) { error.value = "请先处理预览中的问题"; return; }
    contacts = preview.value.rows;
  } else {
    const identifier = contactIdentifier(form.identifier);
    if (!identifier) { error.value = "请填写有效手机号或邮箱"; return; }
    const existing = rows.value.find(row => contactIdentifier(row.identifier) === identifier);
    contacts = [{ ...form, identifier, expected_version: form.expected_version ?? existing?.version ?? null }];
  }
  const body = { rows: contacts, source_note: source.value.trim() }, snapshot = JSON.stringify(body);
  if (previousPayload && previousPayload !== snapshot) requestId = crypto.randomUUID();
  previousPayload = snapshot; saving.value = true;
  try {
    const result = await api.reconcileContacts({ ...body, request_id: requestId });
    message.value = `${result.length} 条通讯资源已登记 / 更新；已按资料核对，未进行短信或邮箱验证。`;
    editing.value = false; batch.value = false; input.value = ""; requestId = crypto.randomUUID(); previousPayload = "";
    await load();
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "保存失败"; }
  finally { saving.value = false; }
}
onMounted(load);
</script>
<template>
  <section class="content-panel contact-panel">
    <header><div><h2>手机号与邮箱</h2><p>先登记保管同事或使用部门，再由平台账号引用。通讯资源的持有人、账号归属公司分别维护。</p></div><div v-if="canManage" class="contact-actions"><button class="secondary-button" @click="edit()">登记手机号 / 邮箱</button><button class="secondary-button" @click="batch = true; editing = true; error = ''; source = ''">批量登记</button></div></header>
    <p v-if="message" class="message-panel success-message" role="status">{{ message }}</p><p v-if="error" class="message-panel error-message" role="alert">{{ error }}</p>
    <form v-if="editing" class="contact-form" @submit.prevent="save">
      <template v-if="batch"><label>归属公司（共用号码）<select v-model="company" required><option value="" disabled>选择公司</option><option v-for="row in companies" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><label class="wide">粘贴号码资料<textarea v-model="input" rows="7" required placeholder="每行：手机号或邮箱〔Tab〕使用人〔Tab〕使用部门〔Tab〕说明。共用使用人填转发器、前台手机或共用。" /></label><p class="wide form-hint">人员按唯一在职姓名匹配，旧号码按号码更新；无法匹配的行需先核对。部门沿用现有组织，原部门表述保留在说明中。</p><p v-for="item in preview.errors" :key="item" class="wide error-message">{{ item }}</p><div v-if="preview.rows.length" class="wide contact-table-wrap"><table><caption>保存预览 · {{ preview.rows.length }} 条</caption><thead><tr><th>号码 / 邮箱</th><th>同事 / 使用部门</th><th>操作</th><th>使用限制</th></tr></thead><tbody><tr v-for="row in preview.rows" :key="row.identifier"><td>{{ row.identifier }}</td><td>{{ personName(row.custodian_person_id) }}<small>{{ departmentName(row.owner_department_id) }}</small></td><td>{{ row.expected_version ? '更新已有记录' : '新增登记' }}</td><td>{{ row.registration_blocked ? '禁止用于注册' : '未注明限制' }}</td></tr></tbody></table></div></template>
      <template v-else><label>手机号 / 邮箱<input v-model="form.identifier" required :disabled="!!form.expected_version" /></label><label>通讯资源归属公司<select v-model="form.legal_entity_id" required><option :value="null" disabled>选择公司</option><option v-for="row in companies" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><PeoplePicker id="contact-holder" v-model:person-id="form.custodian_person_id" label="保管同事（共用可留空）" :people="people.filter(row => row.legal_entity_id === form.legal_entity_id)" :departments="departments" :disabled="saving" /><label>使用部门<select v-model="form.owner_department_id"><option :value="null">未登记部门</option><option v-for="row in departments.filter(row => row.legal_entity_id === form.legal_entity_id)" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><label class="wide">说明<textarea v-model="form.note" rows="3" /></label><label class="contact-check wide"><input v-model="form.registration_blocked" type="checkbox" />禁止用于平台注册（例如法人保留号码）</label></template>
      <label class="wide">核对资料来源 *<input v-model="source" required placeholder="例如：公司号码使用情况表及核对日期" /></label><div class="contact-actions wide"><button type="button" class="secondary-button" :disabled="saving" @click="editing = false">取消</button><button class="primary-button" :disabled="saving || (batch && (!!preview.errors.length || !preview.rows.length))">{{ saving ? '保存中…' : '保存通讯资源' }}</button></div>
    </form>
    <p v-if="loading" role="status">正在读取手机号与邮箱…</p>
    <template v-else><label class="contact-search">搜索通讯资源<input v-model="query" type="search" placeholder="号码、邮箱、同事或部门" /></label><div class="contact-table-wrap"><table><caption>共 {{ visible.length }} 条通讯资源</caption><thead><tr><th>手机号 / 邮箱</th><th>保管同事 / 使用部门</th><th>资料状态</th><th>操作</th></tr></thead><tbody><tr v-for="row in visible" :key="row.asset_id"><td>{{ row.identifier }}<small v-if="row.registration_blocked" class="error-message">禁止用于平台注册</small></td><td>{{ personName(row.custodian_person_id) }}<small>{{ departmentName(row.owner_department_id) }}</small></td><td>{{ row.verification_status === 'documented' ? '已按资料登记' : row.verification_status === 'verified' ? '已核验' : '资料待核对' }}</td><td><button v-if="canManage" class="secondary-button" :aria-label="`修改通讯资源 ${row.identifier}`" @click="edit(row)">修改</button><RouterLink :to="`/assets/${row.asset_id}?tab=relations`">查看引用</RouterLink></td></tr></tbody></table><p v-if="!visible.length" class="mini-empty">{{ query ? '没有匹配资料，请调整搜索。' : '尚未登记手机号或邮箱。' }}</p></div></template>
  </section>
</template>
<style scoped>
.contact-panel { display:grid; gap:20px; min-width:0; }.contact-panel header, .contact-actions { display:flex; align-items:start; flex-wrap:wrap; justify-content:space-between; gap:12px; }.contact-panel h2 { margin:0; }.contact-panel p { color:var(--muted); line-height:1.7; }.contact-form { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:20px; padding:20px; border:1px solid var(--border); border-radius:var(--radius); }.contact-form label,.contact-search { display:grid; gap:8px; }.wide { grid-column:1/-1; }.contact-panel input,.contact-panel select,.contact-panel textarea { width:100%; min-height:42px; box-sizing:border-box; border:1px solid var(--border); border-radius:var(--radius); padding:10px 12px; background:var(--surface); color:var(--text); }.contact-panel .contact-check { display:flex; align-items:center; }.contact-check input { width:18px; min-height:18px; }.contact-table-wrap { overflow:auto; }table { width:100%; border-collapse:collapse; text-align:left; }caption { text-align:left; padding:10px 0; color:var(--muted); }th,td { padding:14px 10px; border-bottom:1px solid var(--border); }td small { display:block; margin-top:5px; color:var(--muted); }td:last-child { white-space:nowrap; }td a { margin-left:12px; }.contact-panel :focus-visible { outline:2px solid var(--primary); outline-offset:3px; }@media(max-width:700px) { .contact-form { grid-template-columns:minmax(0,1fr); padding:14px; }table { min-width:640px; } }
</style>
