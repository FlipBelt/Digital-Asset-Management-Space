<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Plus, ArrowRight } from "lucide-vue-next";
import PageHeader from "../components/PageHeader.vue";
import { api, type AssetEvidence, type Membership } from "../lib/api";
const route = useRoute(); const router = useRouter();
const items = ref<AssetEvidence[]>([]); const memberships = ref<Membership[]>([]);
const loading = ref(false); const saving = ref(false); const error = ref(""); const success = ref("");
const page = ref(1); const total = ref(0); const personId = ref(""); let sequence = 0;
const formOpen = ref(Boolean(route.query.new)); const form = reactive({
  kind: "case", title: "", problem: "", method: "", output: "", observed_effect: "", subscription_id: "",
});
const labels: Record<string, string> = { exploration: "自费 AI 探索", case: "AI 应用案例", method_share: "方法分享", usage: "使用记录" };
const linked = computed(() => memberships.value.find(item => item.id === String(route.query.subscription || "")));
const personal = computed(() => memberships.value.filter(item => item.funding_source === "personal" && item.payer_person_id === personId.value));
let requestId = crypto.randomUUID(); let lastBody = "";
async function load() {
  const request = ++sequence; loading.value = true; error.value = "";
  try {
    const result = await api.spaceEvidence({ page: String(page.value), ...(route.query.subscription ? { subscription_id: String(route.query.subscription) } : {}) });
    if (request === sequence) { items.value = result.data; total.value = result.pagination.total; }
  } catch (reason) { if (request === sequence) error.value = reason instanceof Error ? reason.message : "证据读取失败"; }
  finally { if (request === sequence) loading.value = false; }
}
function open(kind = "case") {
  success.value = ""; form.kind = kind; form.subscription_id = String(route.query.subscription || "");
  formOpen.value = true;
}
async function initialize() {
  loading.value = true; error.value = "";
  try {
    const user = await api.currentSession(); personId.value = user.person_id || "";
    memberships.value = await api.spaceMemberships();
    if (route.query.new) open(String(route.query.new));
    await load();
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "初始化失败"; loading.value = false; }
}
async function submit() {
  saving.value = true; error.value = ""; success.value = "";
  const body = { ...form, title: form.title.trim(), problem: form.problem.trim(),
    method: form.method.trim(), output: form.output.trim(), observed_effect: form.observed_effect.trim() || null,
    subscription_id: form.subscription_id || null };
  const serialized = JSON.stringify(body); if (lastBody && serialized !== lastBody) requestId = crypto.randomUUID(); lastBody = serialized;
  try {
    await api.createEvidence({ ...body, request_id: requestId });
    success.value = "实践已保存，价值和贡献归属待人工核对。"; formOpen.value = false;
    Object.assign(form, { title: "", problem: "", method: "", output: "", observed_effect: "", subscription_id: "" });
    requestId = crypto.randomUUID(); lastBody = ""; page.value = 1; await load();
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "保存失败"; }
  finally { saving.value = false; }
}
onMounted(initialize);
watch(() => route.query.subscription, () => { page.value = 1; void load(); });
watch(() => route.query.new, value => { if (value) open(String(value)); });
</script>
<template>
  <div class="page-stack fusion-space">
    <PageHeader eyebrow="我的空间" :title="linked ? '订阅关联实践' : '我的贡献'" description="记录问题、方法和成果，保留可核对的实践证据。">
      <button v-if="linked?.funding_source === 'personal' && linked.payer_person_id === personId" class="secondary-button" @click="open('exploration')">记录自费 AI 探索</button>
      <button class="primary-button" @click="open('case')"><Plus :size="18" />记录实践</button>
    </PageHeader>
    <RouterLink v-if="linked" to="/my/subscriptions" class="fusion-back">← 返回我的订阅 · {{ linked.subscription_name }}</RouterLink>
    <p v-if="success" class="fusion-success" role="status">{{ success }}</p>
    <form v-if="formOpen" class="fusion-register" @submit.prevent="submit">
      <div class="fusion-form-heading"><h2>{{ labels[form.kind] || '记录实践' }}</h2><button class="secondary-button" type="button" :disabled="saving" @click="formOpen = false">取消</button></div>
      <label>记录类型<select v-model="form.kind"><option v-for="(label, value) in labels" :key="value" :value="value">{{ label }}</option></select></label>
      <label v-if="form.kind === 'exploration'">本人自费订阅<select v-model="form.subscription_id" required><option value="" disabled>选择已经登记的订阅</option><option v-for="item in personal" :key="item.id" :value="item.id">{{ item.subscription_name || '未命名套餐' }}</option></select></label>
      <p v-if="form.kind === 'exploration' && !personal.length">尚未登记本人自费订阅。<RouterLink to="/memberships/new">先登记订阅 →</RouterLink></p>
      <label>实践名称<input v-model="form.title" maxlength="200" required placeholder="例如：自费订阅用于商品评论整理" /></label>
      <label>要解决的问题<textarea v-model="form.problem" maxlength="2000" required /></label>
      <label>尝试的方法<textarea v-model="form.method" maxlength="2000" required /></label>
      <label>留下的成果<textarea v-model="form.output" maxlength="2000" required /></label>
      <label>观察到的变化（选填）<textarea v-model="form.observed_effect" maxlength="2000" /></label>
      <p>记录来自当前登录身份。自费金额不直接计为贡献，所述效果待人工核对。</p>
      <button class="primary-button" :disabled="saving || (form.kind === 'exploration' && !personal.length)">{{ saving ? '正在保存…' : '保存实践记录' }}</button>
    </form>
    <section v-if="error" class="fusion-empty" role="alert"><p>{{ error }}</p><button class="secondary-button" @click="initialize">重试</button></section>
    <section v-else-if="loading" class="fusion-empty" role="status">正在读取实践记录…</section>
    <template v-else>
      <p class="fusion-count">共 {{ total }} 条实践记录 · 价值待人工核对</p>
      <div v-if="items.length" class="fusion-grid">
        <article v-for="item in items" :key="item.id" class="fusion-card fusion-evidence-card">
          <div class="fusion-card-meta"><span>{{ labels[item.kind] || item.kind }}</span><span class="fusion-status">待人工核对</span></div>
          <h2>{{ item.title }}</h2><p>{{ item.problem }}</p>
          <details><summary>查看实践证据</summary><dl><dt>方法</dt><dd>{{ item.method }}</dd><dt>成果</dt><dd>{{ item.output }}</dd><dt>观察到的变化</dt><dd>{{ item.observed_effect || '尚未记录' }}</dd></dl></details>
          <small>{{ new Date(item.created_at).toLocaleDateString('zh-CN') }} · 本人记录</small>
          <RouterLink v-if="item.asset_id" :to="`/discover/${item.asset_id}`" class="fusion-detail">查看关联资产<ArrowRight :size="17" /></RouterLink>
        </article>
      </div>
      <section v-else-if="!formOpen" class="fusion-empty"><h2>还没有实践记录</h2><p>从一个真实问题开始，记录你采用的方法和留下的成果。</p><button class="primary-button" @click="open()">记录第一次实践</button></section>
      <div v-if="total > 24" class="fusion-pagination"><button :disabled="page === 1" @click="page--; load()">上一页</button><span>第 {{ page }} 页</span><button :disabled="page * 24 >= total" @click="page++; load()">下一页</button></div>
    </template>
  </div>
</template>
