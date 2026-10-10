<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import ModalPanel from "./ModalPanel.vue";
import StatusBadge from "./StatusBadge.vue";
import { api, type PlatformDirectoryEntry, type ServiceProduct } from "../lib/api";

defineProps<{ canManage: boolean }>();
const rows = ref<PlatformDirectoryEntry[]>([]), loading = ref(true), saving = ref(false), error = ref(""), message = ref("");
const keyword = ref(""), status = ref(""), selected = ref<PlatformDirectoryEntry | null>(null);
const mode = ref<"details" | "service" | "review" | null>(null);
const filtered = computed(() => rows.value.filter(item => (!status.value || item.review_status === status.value) && `${item.name} ${item.provider_name || ""} ${item.services.map(service => service.name).join(" ")}`.toLowerCase().includes(keyword.value.trim().toLowerCase())));
const labels: Record<string, string> = { approved: "已审核", pending_review: "待审核", rejected: "已退回", incomplete: "待完善登记" };
const details = reactive({ name: "", category: "other", website: "", description: "" });
const service = reactive({ product_id: "", name: "", billing_mode: "subscription", plans: "" });
const review = reactive({ decision: "approved", note: "", source_url: "" });
let requestId = crypto.randomUUID(), previous = "";
async function load() {
  loading.value = true; error.value = "";
  try { rows.value = await api.platformDirectory(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "目录读取失败"; }
  finally { loading.value = false; }
}
function open(item: PlatformDirectoryEntry, action: typeof mode.value, product?: ServiceProduct) {
  selected.value = item; mode.value = action; error.value = ""; message.value = ""; requestId = crypto.randomUUID(); previous = "";
  Object.assign(details, { name: item.name, category: item.category, website: item.website || "", description: item.description || "" });
  Object.assign(service, { product_id: product?.id || "", name: product?.name || "", billing_mode: product?.billing_mode || "subscription", plans: product?.plan_options.join("\n") || "" });
  Object.assign(review, { decision: "approved", note: "", source_url: item.source_url || item.website || "" });
}
async function save() {
  if (saving.value || !selected.value) return;
  const item = selected.value;
  let body: Record<string, unknown>;
  if (mode.value === "details") body = { ...details, provider_id: item.provider_id, website: details.website || null, description: details.description || null };
  else if (mode.value === "service") body = { product_id: service.product_id || null, name: service.name, billing_mode: service.billing_mode, plan_options: service.plans.split("\n").map(value => value.trim()).filter(Boolean) };
  else body = { ...review, source_url: review.source_url || null };
  if (item.kind === "platform") body.expected_revision = item.revision;
  const snapshot = JSON.stringify(body);
  if (previous && previous !== snapshot) requestId = crypto.randomUUID();
  previous = snapshot; body.request_id = requestId; saving.value = true; error.value = "";
  try {
    const updated = item.kind === "provider" ? await api.createDirectoryEntry(body) : mode.value === "details" ? await api.updateDirectoryEntry(item.id, body) : mode.value === "service" ? await api.saveDirectoryService(item.id, body) : await api.reviewDirectoryEntry(item.id, body);
    rows.value = rows.value.filter(row => row.id !== item.id); rows.value.push(updated); rows.value.sort((a, b) => a.name.localeCompare(b.name));
    message.value = mode.value === "review" ? "目录审核已保存。" : "目录已保存，资料和套餐待审核。";
    mode.value = null; selected.value = null;
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "保存失败"; }
  finally { saving.value = false; }
}
onMounted(load);
</script>
<template>
  <div class="platform-directory">
    <div class="directory-filters"><label>搜索平台/供应商<input v-model="keyword" type="search" placeholder="名称或服务" /></label><label>审核状态<select v-model="status"><option value="">全部状态</option><option v-for="(label, value) in labels" :key="value" :value="value">{{ label }}</option></select></label><button class="secondary-button" :disabled="loading" @click="load">刷新目录</button></div>
    <p>平台和供应商在此统一管理。服务及其套餐在同一记录中维护；审核通过后可用于订阅登记。</p>
    <p v-if="message" role="status">{{ message }}</p><p v-if="error && !mode" class="form-error" role="alert">{{ error }}</p>
    <div v-if="loading" class="mini-empty" role="status">正在读取平台/供应商目录…</div>
    <div v-else-if="!filtered.length" class="mini-empty">{{ rows.length ? '没有匹配的目录记录，请调整筛选。' : '目录暂无记录，请登记平台/供应商。' }}</div>
    <article v-for="item in loading ? [] : filtered" :key="item.id" class="directory-record">
      <header><div><h2>{{ item.name }}</h2><p v-if="item.provider_name && item.provider_name !== item.name">服务提供方：{{ item.provider_name }}</p></div><StatusBadge :tone="item.review_status === 'approved' ? 'success' : 'warning'">{{ labels[item.review_status] || '待审核' }}</StatusBadge></header>
      <p v-if="item.description">{{ item.description }}</p><a v-if="item.website" :href="item.website" target="_blank" rel="noopener noreferrer">官方网站</a>
      <ul v-if="item.services.length" class="directory-services"><li v-for="product in item.services" :key="product.id"><div><strong>{{ product.name }}</strong><p>{{ product.plan_options.length ? product.plan_options.join(' · ') : '套餐待补充' }}</p></div><button v-if="canManage" class="secondary-button" @click="open(item, 'service', product)">维护套餐<span class="sr-only">：{{ product.name }}</span></button></li></ul>
      <p v-else>{{ item.kind === 'provider' ? '已有历史提供方记录，请完善平台/供应商登记并审核。' : '尚未维护服务和套餐。' }}</p>
      <p v-if="item.review_note">最近审核：{{ item.review_note }}<a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener noreferrer"> 核验来源</a></p>
      <footer v-if="canManage"><button class="secondary-button" @click="open(item, 'details')">{{ item.kind === 'provider' ? '完善登记' : '维护资料' }}<span class="sr-only">：{{ item.name }}</span></button><template v-if="item.kind === 'platform'"><button class="secondary-button" @click="open(item, 'service')">添加服务与套餐<span class="sr-only">：{{ item.name }}</span></button><button class="primary-button" @click="open(item, 'review')">审核目录<span class="sr-only">：{{ item.name }}</span></button></template></footer>
    </article>
    <ModalPanel v-if="mode && selected" :title="mode === 'details' ? '维护平台/供应商' : mode === 'service' ? '维护服务与套餐' : '审核平台/供应商目录'" @close="!saving && (mode = null)">
      <form class="form-grid one-column" :aria-busy="saving" @submit.prevent="save">
        <p>{{ selected.name }}</p>
        <template v-if="mode === 'details'"><label>平台/供应商名称<input v-model="details.name" required maxlength="200" /></label><label>类别<select v-model="details.category"><option value="other">其他</option><option value="ai">AI</option><option value="cloud">云平台</option><option value="saas">软件服务</option><option value="marketing">电商</option><option value="payment">支付</option></select></label><label>官方网站<input v-model="details.website" type="url" /></label><label>登记说明<textarea v-model="details.description" maxlength="2000" /></label></template>
        <template v-else-if="mode === 'service'"><label>服务名称<input v-model="service.name" required maxlength="200" placeholder="例如：ChatGPT、Claude" /></label><label>计费方式<select v-model="service.billing_mode"><option value="subscription">订阅</option><option value="usage">按量计费</option><option value="free">免费</option><option value="one_time">一次购买</option><option value="other">其他</option></select></label><label>可选套餐，每行一个<textarea v-model="service.plans" rows="6" placeholder="Plus&#10;Pro&#10;Business" /></label><p>按实际提供的套餐填写，保存后需重新审核目录。</p></template>
        <template v-else><div><strong>待核对服务和套餐</strong><p v-for="product in selected.services" :key="product.id">{{ product.name }}：{{ product.plan_options.join('、') || '套餐未配置' }}</p></div><label>审核结果<select v-model="review.decision"><option value="approved">通过目录审核</option><option value="rejected">退回补充</option></select></label><label>核验来源链接<input v-model="review.source_url" type="url" :required="review.decision === 'approved'" /></label><label>审核说明<textarea v-model="review.note" required maxlength="2000" placeholder="说明已核对的名称、官网、套餐，或需要补充的资料" /></label><p>目录审核用于服务和套餐选择；采购、账号权限与报销按原流程确认。</p></template>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p><div class="form-actions"><button type="button" class="secondary-button" :disabled="saving" @click="mode = null">取消</button><button class="primary-button" :disabled="saving">{{ saving ? '正在保存…' : mode === 'review' ? '保存审核结果' : '保存并待审核' }}</button></div>
      </form>
    </ModalPanel>
  </div>
</template>
<style scoped>
.platform-directory { display:grid; gap:16px; min-width:0; }
.platform-directory p { color:var(--muted); margin:0; line-height:1.6; overflow-wrap:anywhere; }
.directory-filters { display:flex; flex-wrap:wrap; gap:12px; align-items:end; }
.directory-filters label { display:grid; gap:8px; flex:1 1 200px; min-width:0; }
.directory-record { display:grid; gap:12px; padding:20px; border:1px solid var(--border); border-radius:var(--radius); min-width:0; }
.directory-record header { display:flex; justify-content:space-between; align-items:start; gap:12px; }
.directory-record h2 { font-size:17px; margin:0; overflow-wrap:anywhere; }
.directory-record footer { display:flex; flex-wrap:wrap; gap:8px; }
.directory-services { list-style:none; padding:0; margin:0; }
.directory-services li { display:flex; justify-content:space-between; gap:12px; padding:12px 0; border-top:1px solid var(--border); }
.directory-record button { white-space:normal; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
@media(max-width:600px) { .directory-record { padding:14px; } .directory-services li { flex-direction:column; align-items:start; } }
</style>
