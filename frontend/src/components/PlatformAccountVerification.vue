<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import ModalPanel from "./ModalPanel.vue";
import { api, type Asset, type PlatformAccountContext, type PlatformTenant } from "../lib/api";

const props = defineProps<{ tenant: PlatformTenant }>();
const emit = defineEmits<{ close: []; saved: [PlatformTenant] }>();
const asset = ref<Asset | null>(null);
const context = ref<PlatformAccountContext | null>(null);
const company = ref("");
const loading = ref(true); const saving = ref(false); const error = ref("");
const form = reactive({ decision: "verified", tenant_identifier: "", identifier_unavailable: false,
  ownership_nature: "company_owned", platform_confirmed: false, company_confirmed: false,
  identifier_confirmed: false, evidence_note: "" });
let requestId = crypto.randomUUID(); let submitted = "";
const natureLabels: Record<string, string> = { company_owned: "公司所有", company_managed: "公司管理", personal_owned: "个人所有，供公司使用", pending: "归属待确认" };
async function load() {
  loading.value = true; error.value = ""; asset.value = null;
  try {
    const [original, facts, entities] = await Promise.all([
      api.asset(props.tenant.asset_id), api.platformAccountContext(props.tenant.asset_id), api.legalEntities(),
    ]);
    asset.value = original; context.value = facts;
    company.value = entities.find(item => item.id === original.legal_entity_id)?.name || "公司主体待补充";
    form.tenant_identifier = facts.tenant_identifier || "";
    form.ownership_nature = facts.ownership_nature in natureLabels ? facts.ownership_nature : "pending";
    form.evidence_note = facts.evidence_note || "";
    form.platform_confirmed = false; form.company_confirmed = false; form.identifier_confirmed = false;
    form.identifier_unavailable = false; requestId = crypto.randomUUID(); submitted = "";
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "读取账号失败"; }
  finally { loading.value = false; }
}
async function save() {
  if (!asset.value) return;
  error.value = "";
  if (form.decision === "verified" && !(form.platform_confirmed && form.company_confirmed && form.identifier_confirmed)) {
    error.value = "请逐项完成平台、公司归属和账号标识核对。"; return;
  }
  const facts = { ...form, version: asset.value.version, tenant_identifier: form.tenant_identifier.trim() || null, evidence_note: form.evidence_note.trim() };
  const current = JSON.stringify(facts);
  if (submitted && submitted !== current) requestId = crypto.randomUUID();
  submitted = current; saving.value = true;
  try { emit("saved", await api.verifyPlatformTenant(props.tenant.id, { ...facts, request_id: requestId })); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "核验保存失败"; }
  finally { saving.value = false; }
}
onMounted(load);
</script>

<template>
  <ModalPanel title="核验公司平台账号" description="核对实际账号及公司归属，填写依据后保存核验结果。" trap-focus @close="!saving && emit('close')">
    <p v-if="loading" role="status">正在读取账号资料…</p>
    <form v-else-if="asset && context" class="form-grid one-column" :aria-busy="saving" @submit.prevent="save">
      <div class="verification-facts"><h3>{{ asset.name }}</h3><dl><dt>平台</dt><dd>{{ context.platform_name }} <a v-if="context.platform_website" :href="context.platform_website" target="_blank" rel="noopener noreferrer">官网</a></dd><dt>所属公司</dt><dd>{{ company }}</dd><dt>注册身份</dt><dd>{{ context.registration_identities.map(item => item.identifier).join('、') || '暂未关联，可在依据中说明实际核对方式' }}</dd><dt>当前状态</dt><dd>{{ context.verification_status === 'verified' ? '已核验' : '待核验' }}</dd></dl></div>
      <label>核验结果<select v-model="form.decision"><option value="verified">已完成核验</option><option value="pending">资料不足，待补充</option></select></label>
      <label>账号归属性质<select v-model="form.ownership_nature"><option v-for="(label, value) in natureLabels" :key="value" :value="value">{{ label }}</option></select></label>
      <label>平台账号编号（UID / 租户 ID）<input v-model="form.tenant_identifier" maxlength="200" :required="form.decision === 'verified' && !form.identifier_unavailable" :disabled="form.identifier_unavailable" placeholder="从平台账号或组织后台核对" /></label>
      <label class="check-label"><input v-model="form.identifier_unavailable" type="checkbox" @change="form.identifier_unavailable && (form.tenant_identifier = '')" />平台确实不提供账号编号（请在依据中说明）</label>
      <fieldset v-if="form.decision === 'verified'" class="verification-checks"><legend>逐项核对</legend><label class="check-label"><input v-model="form.platform_confirmed" type="checkbox" />实际使用的平台与上方平台一致</label><label class="check-label"><input v-model="form.company_confirmed" type="checkbox" />公司主体和账号归属已与实名或授权资料核对</label><label class="check-label"><input v-model="form.identifier_confirmed" type="checkbox" />账号编号、注册身份或后台账号页已核对</label></fieldset>
      <label>核验依据 / 待补充内容<textarea v-model="form.evidence_note" required maxlength="2000" rows="4" placeholder="填写核对的资料位置和结论；没有账号编号时说明原因及核对方式。资料不足则列出缺少的内容。" /></label>
      <p class="form-hint">只填写资料位置和核对结论，无需提供登录密码。账号核验记录事实；服务套餐在平台目录中维护。</p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div class="form-actions"><button type="button" class="secondary-button" :disabled="saving" @click="load">重新读取资料</button><button type="button" class="secondary-button" :disabled="saving" @click="emit('close')">取消</button><button class="primary-button" :disabled="saving">{{ saving ? '正在保存…' : '保存核验结果' }}</button></div>
    </form>
    <div v-else role="alert"><p>{{ error }}</p><button class="secondary-button" @click="load">重试</button></div>
  </ModalPanel>
</template>

<style scoped>
.verification-facts, .verification-checks { min-width:0; padding:16px; border:1px solid var(--border); border-radius:var(--radius); }
.verification-facts h3 { margin:0 0 12px; overflow-wrap:anywhere; }
.verification-facts dl { display:grid; grid-template-columns:auto minmax(0,1fr); gap:8px 16px; margin:0; }
.verification-facts dd { margin:0; overflow-wrap:anywhere; }
.verification-checks { display:grid; gap:12px; }
.verification-checks legend { font-weight:600; }
.form-grid .check-label { display:flex; flex-direction:row; align-items:start; gap:10px; }
.form-grid .check-label input[type="checkbox"] { flex:0 0 16px; width:16px; height:16px; min-height:16px; padding:0; margin:3px 0 0; }
</style>
