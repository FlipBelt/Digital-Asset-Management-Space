<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { Plus, UserRound } from "lucide-vue-next";
import { api, type Account, type CredentialReference, type Department, type Person } from "../lib/api";
import ModalPanel from "./ModalPanel.vue";
import PeoplePicker from "./PeoplePicker.vue";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps<{ assetId: string; legalEntityId: string | null; canManage: boolean }>();
const emit = defineEmits<{ changed: [] }>();
const accounts = ref<Account[]>([]), people = ref<Person[]>([]), departments = ref<Department[]>([]);
const loading = ref(true), saving = ref(false), error = ref(""), message = ref("");
const mode = ref<"create" | "bind" | "credential" | null>(null), selected = ref<Account | null>(null);
const credentials = ref<CredentialReference[]>([]), credential = reactive({ provider: "bitwarden", item_id: "", secure_url: "" });
const bindingPerson = ref<string | null>(null), version = ref(0);
let requestId = crypto.randomUUID(), previousBody = "", loadSequence = 0;
const empty = () => ({ display_name: "", login_identifier: "", primary_person_id: null as string | null,
  account_kind: "member_login", privilege_level: "normal", parent_account_id: "", mfa_status: "unknown", note: "" });
const form = reactive(empty());
const companyPeople = computed(() => people.value.filter(person => person.legal_entity_id === props.legalEntityId));
const ordered = computed(() => {
  const rows: { account: Account; depth: number }[] = [], seen = new Set<string>();
  function visit(account: Account, depth: number) {
    if (seen.has(account.id)) return;
    seen.add(account.id); rows.push({ account, depth });
    accounts.value.filter(row => row.parent_account_id === account.id).forEach(row => visit(row, depth + 1));
  }
  accounts.value.filter(row => !row.parent_account_id || !accounts.value.some(parent => parent.id === row.parent_account_id)).forEach(row => visit(row, 0));
  accounts.value.filter(row => !seen.has(row.id)).forEach(row => visit(row, 0));
  return rows;
});
function personFor(account: Account) { return people.value.find(person => person.id === account.primary_person_id); }
function bindingLabel(account: Account) {
  if (account.account_kind === "service" && !account.primary_person_id) return "服务账号 · 无员工绑定";
  const person = personFor(account);
  return !person ? "未绑定员工" : person.employment_status === "departed" ? `${person.display_name} · 已离职，待交接`
    : person.employment_status !== "active" ? `${person.display_name} · 非在职，待核实` : person.display_name;
}
async function load() {
  const sequence = ++loadSequence; loading.value = true; error.value = "";
  try {
    const [rows, employees, teams, references] = await Promise.all([api.platformAccountChildren(props.assetId), api.people(), api.departments(), api.credentialReferences()]);
    if (sequence !== loadSequence) return;
    accounts.value = rows; people.value = employees; departments.value = teams; credentials.value = references;
  } catch (cause) { if (sequence === loadSequence) error.value = cause instanceof Error ? cause.message : "账号明细读取失败"; }
  finally { if (sequence === loadSequence) loading.value = false; }
}
function openCreate() { Object.assign(form, empty()); selected.value = null; error.value = ""; mode.value = "create"; requestId = crypto.randomUUID(); previousBody = ""; }
function openCredential(account: Account) { selected.value = account; Object.assign(credential, { provider: "bitwarden", item_id: "", secure_url: "" }); error.value = ""; mode.value = "credential"; }
async function openBinding(account: Account) {
  selected.value = account; bindingPerson.value = account.primary_person_id; error.value = "";
  requestId = crypto.randomUUID(); previousBody = ""; saving.value = true;
  try { version.value = (await api.asset(account.asset_id)).version; mode.value = "bind"; }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "账号资料读取失败"; }
  finally { saving.value = false; }
}
async function save() {
  if (saving.value) return;
  const body = mode.value === "create" ? { ...form, parent_account_id: form.parent_account_id || null,
    account_role: form.privilege_level === "normal" ? "member" : "admin", note: form.note || null }
    : mode.value === "credential" ? { ...credential, secure_url: credential.secure_url || null }
    : { primary_person_id: bindingPerson.value, version: version.value };
  const snapshot = JSON.stringify(body);
  if (previousBody && previousBody !== snapshot) requestId = crypto.randomUUID();
  previousBody = snapshot; saving.value = true; error.value = "";
  try {
    if (mode.value === "create") await api.createPlatformAccountChild(props.assetId, { ...body, request_id: requestId });
    else if (selected.value && mode.value === "credential") await api.createCredentialReference({ ...body, account_id: selected.value.id });
    else if (selected.value) await api.bindAccountEmployee(props.assetId, selected.value.id, { ...body, request_id: requestId });
    mode.value = null; message.value = "账号明细已保存。"; await load(); emit("changed");
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "账号明细保存失败"; }
  finally { saving.value = false; }
}
watch(() => form.primary_person_id, id => {
  const person = companyPeople.value.find(row => row.id === id);
  if (person) { form.display_name = person.display_name; form.login_identifier = person.email || ""; }
});
watch(() => props.assetId, () => { mode.value = null; message.value = ""; void load(); }, { immediate: true });
</script>
<template>
  <section class="child-accounts-panel">
    <header><div><h2>子账号与员工席位</h2><p>在当前公司账号内维护子账号、上级关系和绑定员工。</p></div><button v-if="canManage" class="primary-button" :disabled="loading || saving" @click="openCreate"><Plus :size="16" />添加子账号</button></header>
    <p v-if="message" class="success-message" role="status">{{ message }}</p>
    <div v-if="loading" class="mini-empty" role="status">正在读取账号明细…</div>
    <div v-else-if="error && !mode" class="message-panel error-message" role="alert">{{ error }}<button class="secondary-button" @click="load">重新读取</button></div>
    <p v-else-if="!accounts.length" class="mini-empty">尚无子账号。可选择已有员工登记，也可手动登记服务账号。</p>
    <ul v-else class="child-account-list"><li v-for="{ account, depth } in ordered" :key="account.id" :style="{ '--account-depth': Math.min(depth, 3) }"><UserRound :size="18" aria-hidden="true" /><div><strong>{{ account.login_identifier }}</strong><p>{{ bindingLabel(account) }}</p><small v-if="account.parent_account_id">上级：{{ accounts.find(row => row.id === account.parent_account_id)?.login_identifier || '明细待补充' }}</small><template v-if="credentials.find(row => row.account_id === account.id)"><a v-if="credentials.find(row => row.account_id === account.id)?.secure_url" :href="credentials.find(row => row.account_id === account.id)?.secure_url || ''" target="_blank" rel="noopener noreferrer">打开密码库引用</a><small v-else>凭据状态已登记</small></template></div><StatusBadge :tone="personFor(account)?.employment_status === 'active' ? 'success' : account.account_kind === 'service' && !account.primary_person_id ? 'default' : 'warning'">{{ personFor(account)?.employment_status === 'active' ? '已绑定' : personFor(account)?.employment_status === 'departed' ? '待交接' : account.account_kind === 'service' && !account.primary_person_id ? '服务账号' : '待绑定 / 核实' }}</StatusBadge><button v-if="canManage" class="secondary-button" :disabled="saving" :aria-label="`绑定员工 ${account.login_identifier}`" @click="openBinding(account)">{{ account.primary_person_id ? '维护绑定' : '绑定员工' }}</button><button v-if="canManage && !credentials.some(row => row.account_id === account.id)" class="text-button" :disabled="saving" :aria-label="`登记凭据状态 ${account.login_identifier}`" @click="openCredential(account)">登记凭据状态</button></li></ul>
    <ModalPanel v-if="mode" :trap-focus="true" :title="mode === 'create' ? '添加子账号' : mode === 'credential' ? '登记密码库引用' : '维护员工绑定'" @close="!saving && (mode = null)">
      <form class="form-grid one-column" :aria-busy="saving" @submit.prevent="save">
        <p v-if="mode !== 'credential'">绑定员工用于确认账号使用人与交接关系；平台权限需要在实际平台核对。</p>
        <template v-if="mode === 'create'">
          <PeoplePicker id="child-create-person" v-model:person-id="form.primary_person_id" label="绑定已有员工（选填）" :people="companyPeople" :departments="departments" :disabled="saving" hint="选中后带入姓名和邮箱；登录名可按实际平台修改。服务账号可以不绑定员工。" />
          <label>账号名称<input v-model="form.display_name" required maxlength="200" /></label><label>平台登录名<input v-model="form.login_identifier" required maxlength="320" placeholder="邮箱、手机号或用户名" /></label>
          <label>账号用途<select v-model="form.account_kind"><option value="member_login">员工登录账号 / 席位</option><option value="developer">开发账号</option><option value="admin">管理员账号</option><option value="service">服务账号</option></select></label>
          <label>平台权限级别<select v-model="form.privilege_level"><option value="normal">普通</option><option value="admin">管理员</option><option value="root">根权限</option></select></label>
          <label>上级子账号<select v-model="form.parent_account_id"><option value="">直属当前公司账号</option><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.login_identifier }}</option></select></label>
          <label>MFA 状态<select v-model="form.mfa_status"><option value="unknown">未知</option><option value="enabled">已开启</option><option value="disabled">未开启</option></select></label>
          <label>来源说明<textarea v-model="form.note" maxlength="2000" rows="2" /></label>
        </template>
        <template v-else-if="mode === 'credential'"><p>只保存密码库条目 ID 或安全链接，密码和密钥请保留在密码库。</p><label>密码库产品<select v-model="credential.provider"><option value="bitwarden">Bitwarden</option><option value="1password">1Password</option><option value="keeper">Keeper</option><option value="other">其他</option></select></label><label>条目 ID<input v-model="credential.item_id" required /></label><label>安全链接<input v-model="credential.secure_url" type="url" /></label></template>
        <template v-else><p>{{ selected?.login_identifier }}</p><PeoplePicker id="child-bind-person" v-model:person-id="bindingPerson" label="绑定员工" :people="companyPeople" :departments="departments" :disabled="saving" hint="可移除原绑定或选择所属公司的在职员工，离职员工保留在历史记录中。" /></template>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p><div class="form-actions"><button type="button" class="secondary-button" :disabled="saving" @click="mode = null">取消</button><button class="primary-button" :disabled="saving">{{ saving ? '正在保存…' : '保存账号明细' }}</button></div>
      </form>
    </ModalPanel>
  </section>
</template>
<style scoped>
.child-accounts-panel { display:grid; gap:18px; min-width:0; }
header { display:flex; justify-content:space-between; align-items:start; gap:16px; flex-wrap:wrap; }
h2 { margin:0 0 8px; font-size:20px; } p { margin:0; color:var(--muted); line-height:1.6; }
.child-account-list { padding:0; margin:0; list-style:none; display:grid; gap:0; }
.child-account-list li { display:flex; align-items:center; gap:14px; padding:18px 8px 18px calc(8px + var(--account-depth) * 20px); border-top:1px solid var(--border); }
.child-account-list li > div { flex:1; min-width:0; overflow-wrap:anywhere; } small { color:var(--muted); }
@media(max-width:640px) { .child-account-list li { flex-wrap:wrap; gap:10px; } .child-account-list li > div { flex-basis:calc(100% - 40px); } }
</style>
