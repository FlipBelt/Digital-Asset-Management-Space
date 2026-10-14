<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Search, RefreshCw } from "lucide-vue-next";
import { api, type EmployeeLifecycle } from "../lib/api";
import ModalPanel from "./ModalPanel.vue";
import StatusBadge from "./StatusBadge.vue";
import WorkspaceTabs from "./WorkspaceTabs.vue";

const emit = defineEmits<{ changed: [] }>();
const items = ref<EmployeeLifecycle[]>([]), loading = ref(true), saving = ref(false);
const error = ref(""), message = ref(""), query = ref(""), active = ref("departed");
const selected = ref<EmployeeLifecycle | null>(null), mode = ref<"departure" | "correction" | "handover" | null>(null);
const form = reactive({ departed_on: "", evidence_note: "" });
let requestId = crypto.randomUUID(), previousBody = "";
function remaining(person: EmployeeLifecycle) { return person.handover.accounts.length + person.handover.responsibilities.length + person.handover.grants.length; }
const tabs = computed(() => [
  { value: "working", label: "在职 / 待核实", count: items.value.filter(row => row.employment_status !== "departed").length },
  { value: "departed", label: "已离职", count: items.value.filter(row => row.employment_status === "departed").length },
  { value: "handover", label: "离职待交接", count: items.value.filter(row => row.employment_status === "departed" && remaining(row)).length },
]);
const filtered = computed(() => items.value.filter(row =>
  (active.value === "working" ? row.employment_status !== "departed" : row.employment_status === "departed" && (active.value !== "handover" || remaining(row)))
  && `${row.display_name} ${row.employee_no}`.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase())));
async function load() {
  loading.value = true; error.value = "";
  try { items.value = (await api.employeeLifecycle()).items; }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "员工状态读取失败"; }
  finally { loading.value = false; }
}
function open(person: EmployeeLifecycle, action: typeof mode.value) {
  selected.value = person; mode.value = action; error.value = "";
  form.departed_on = ""; form.evidence_note = ""; requestId = crypto.randomUUID(); previousBody = "";
}
async function save() {
  if (!selected.value || saving.value) return;
  const body = { expected_updated_at: selected.value.updated_at,
    employment_status: mode.value === "departure" ? "departed" : "active",
    departed_on: mode.value === "departure" ? form.departed_on : null, evidence_note: form.evidence_note };
  const snapshot = JSON.stringify(body);
  if (previousBody && previousBody !== snapshot) requestId = crypto.randomUUID();
  previousBody = snapshot; saving.value = true; error.value = "";
  try {
    await api.changeEmployeeLifecycle(selected.value.id, { ...body, request_id: requestId });
    message.value = mode.value === "departure" ? "离职已登记，本系统登录已停用；请继续处理账号和责任交接。" : "已纠正为在职。本系统登录和平台授权需单独确认。";
    mode.value = null; selected.value = null; await load(); emit("changed");
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "员工状态保存失败，请重新读取后操作"; }
  finally { saving.value = false; }
}
onMounted(load);
</script>
<template>
  <section class="employee-lifecycle">
    <header><div><h2>离职员工与交接</h2><p>依据实际离职信息登记。通讯录不可查询、公司归属待核验的员工，保持原状态供核实。</p></div><div class="lifecycle-actions"><button class="secondary-button" :disabled="loading" @click="load"><RefreshCw :size="16" />刷新</button><button class="primary-button" @click="active = 'working'; query = ''">登记离职</button></div></header>
    <p v-if="message" class="message-panel success-message" role="status">{{ message }}</p>
    <div v-if="loading" class="mini-empty" role="status">正在读取员工状态与交接事项…</div>
    <div v-else-if="error && !mode" class="message-panel error-message" role="alert">{{ error }}<button class="secondary-button" @click="load">重新读取</button></div>
    <template v-else>
      <WorkspaceTabs v-model="active" :tabs="tabs" label="员工状态" id-prefix="employee-lifecycle" />
      <section id="employee-lifecycle-panel" role="tabpanel" :aria-labelledby="`employee-lifecycle-${active}`" class="content-panel">
        <label class="fusion-search"><Search :size="17" aria-hidden="true" /><input v-model="query" type="search" aria-label="搜索员工姓名或工号" placeholder="搜索姓名或工号" /></label>
        <ul v-if="filtered.length" class="lifecycle-list"><li v-for="person in filtered" :key="person.id"><div><strong>{{ person.display_name }}</strong><small>{{ person.employee_no }}<span v-if="person.last_event?.departed_on"> · 离职日期 {{ person.last_event.departed_on }}</span></small><p v-if="person.last_event">登记依据：{{ person.last_event.evidence_note }}</p><p v-if="person.employment_status === 'departed'">{{ person.handover.accounts.length }} 个关联账号 · {{ person.handover.responsibilities.length }} 项负责资产 · {{ person.handover.grants.length }} 项授权待核对</p></div><StatusBadge :tone="person.employment_status === 'departed' ? 'default' : person.employment_status === 'active' ? 'success' : 'warning'">{{ person.employment_status === 'departed' ? '已离职' : person.employment_status === 'active' ? '在职' : '非在职，待核实' }}</StatusBadge><div class="lifecycle-actions"><template v-if="person.employment_status === 'departed'"><button class="secondary-button" :aria-label="`查看交接 ${person.display_name}`" @click="open(person, 'handover')">查看交接</button><button class="text-button" :aria-label="`纠正员工状态 ${person.display_name}`" @click="open(person, 'correction')">纠正状态</button></template><button v-else class="secondary-button" :aria-label="`登记离职 ${person.display_name}`" @click="open(person, 'departure')">登记离职</button></div></li></ul>
        <div v-else class="mini-empty">{{ query ? '没有匹配的员工，请调整搜索。' : active === 'working' ? '没有可登记的员工。' : active === 'handover' ? '当前没有离职待交接事项。' : '尚无已确认离职的员工。可选择“登记离职”后，按实际依据登记。' }}</div>
      </section>
    </template>
    <ModalPanel v-if="mode && selected" :trap-focus="true" :title="mode === 'departure' ? '登记员工离职' : mode === 'correction' ? '纠正员工状态' : '离职交接事项'" @close="!saving && (mode = null)">
      <form v-if="mode !== 'handover'" class="form-grid one-column" :aria-busy="saving" @submit.prevent="save">
        <p><strong>{{ selected.display_name }}</strong> · {{ selected.employee_no }}</p>
        <template v-if="mode === 'departure'"><div class="form-hint">确认离职后将停用该员工的本系统登录，并撤销当前登录会话。平台账号、授权和负责资产保留，供逐项交接。</div><p>现有 {{ selected.handover.accounts.length }} 个关联账号、{{ selected.handover.responsibilities.length }} 项负责资产、{{ selected.handover.grants.length }} 项授权。</p><label>实际离职日期<input v-model="form.departed_on" type="date" required /></label></template>
        <p v-else class="form-hint">仅纠正为在职状态。本系统登录与平台授权需要管理员单独确认。</p>
        <label>登记依据 / 纠正原因<textarea v-model="form.evidence_note" required maxlength="2000" rows="4" placeholder="填写已核对的离职通知、人员名单或核实说明" /></label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p><div class="form-actions"><button class="secondary-button" type="button" :disabled="saving" @click="mode = null">取消</button><button class="primary-button" :disabled="saving">{{ saving ? '正在保存…' : mode === 'departure' ? '确认离职并停用登录' : '确认纠正为在职' }}</button></div>
      </form>
      <div v-else class="handover-sections"><p>{{ selected.display_name }} · 已离职。外部平台权限需在对应平台核对和回收。</p><template v-for="(rows, kind) in { accounts: selected.handover.accounts, responsibilities: selected.handover.responsibilities, grants: selected.handover.grants }" :key="kind"><h3>{{ kind === 'accounts' ? '账号绑定' : kind === 'responsibilities' ? '负责资产' : '已有授权' }}</h3><ul v-if="rows.length"><li v-for="(row, index) in rows" :key="index"><div><strong>{{ row.name }}</strong><small v-if="row.login_identifier">{{ row.login_identifier }}</small></div><RouterLink class="secondary-button" :to="row.grant_id ? `/directory/grant/${row.grant_id}` : row.href" @click="mode = null">{{ kind === 'accounts' ? '维护员工绑定' : kind === 'responsibilities' ? '移交责任' : '查看授权' }}</RouterLink></li></ul><p v-else>当前无此类待交接记录。</p></template></div>
    </ModalPanel>
  </section>
</template>
<style scoped>
.employee-lifecycle,.handover-sections { display:grid; gap:20px; min-width:0; }
header,.lifecycle-actions { display:flex; align-items:start; justify-content:space-between; gap:12px; flex-wrap:wrap; }
h2 { margin:0 0 10px; font-size:23px; } p,small { color:var(--muted); line-height:1.6; overflow-wrap:anywhere; } p { margin:0; } small { display:block; }
.fusion-search { max-width:520px; margin-bottom:16px; }
.lifecycle-list,.handover-sections ul { list-style:none; padding:0; margin:0; }
.lifecycle-list li,.handover-sections li { display:flex; gap:16px; align-items:center; border-top:1px solid var(--border); padding:20px 0; }
.lifecycle-list li > div:first-child,.handover-sections li > div { flex:1; min-width:0; }
.lifecycle-list strong { font-size:16px; } .handover-sections h3 { margin:0; font-size:17px; }
@media(max-width:640px) { .lifecycle-list li,.handover-sections li { flex-wrap:wrap; gap:10px; } .lifecycle-list li > div:first-child,.handover-sections li > div { flex-basis:100%; } }
</style>
