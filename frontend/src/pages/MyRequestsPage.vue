<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowRight, CheckCircle2, Clock3, CreditCard, KeyRound, Layers3, Plus, Send } from "lucide-vue-next";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type CurrentUser, type Platform, type WorkflowRequest } from "../lib/api";
const route = useRoute(); const router = useRouter();
const rows = ref<WorkflowRequest[]>([]); const platforms = ref<Platform[]>([]); const user = ref<CurrentUser | null>(null);
const loading = ref(true); const saving = ref(false); const busy = ref(""); const error = ref(""); const formError = ref(""); const feedback = ref(""); const formOpen = ref(false);
const kinds = [{ value: "seat", label: "工具席位", description: "申请已有工具的使用席位", icon: CreditCard },
  { value: "platform", label: "平台使用", description: "申请使用或引入一个平台", icon: Layers3 },
  { value: "account", label: "业务账号", description: "申请开通业务账号或子账号", icon: KeyRound }];
const labels: Record<string, string> = { seat: "席位", platform: "平台", account: "账号", permission: "权限", purchase: "采购", quota: "额度" };
const statuses: Record<string, string> = { draft: "草稿", pending: "待处理", approved: "已批准", rejected: "已驳回", executing: "执行中", completed: "已完成", failed: "执行失败", cancelled: "已撤回" };
const form = reactive({ request_type: "seat", resource_name: "", platform_id: "", purpose: "" });
const requestId = ref(crypto.randomUUID()); let previous = "";
const pending = computed(() => rows.value.filter(item => ["draft", "pending", "approved", "executing"].includes(item.status)).length);
async function load() {
  loading.value = true; error.value = "";
  try {
    user.value = await api.currentSession();
    if (user.value.person_id) rows.value = await api.myRequests();
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "申请读取失败"; }
  finally { loading.value = false; }
}
async function openForm() {
  formOpen.value = true; formError.value = "";
  try { platforms.value = await api.platforms(); }
  catch (reason) { formError.value = reason instanceof Error ? reason.message : "平台目录读取失败，仍可填写名称申请"; }
}
async function submit() {
  if (saving.value) return;
  saving.value = true; formError.value = ""; feedback.value = "";
  const body = { ...form, resource_name: form.resource_name.trim(), purpose: form.purpose.trim(), platform_id: form.platform_id || null };
  const serialized = JSON.stringify(body); if (previous && previous !== serialized) requestId.value = crypto.randomUUID(); previous = serialized;
  try {
    const result = await api.createMyRequest({ ...body, request_id: requestId.value });
    feedback.value = `申请已提交 · ${result.request_no}。可在下方查看处理进度。`;
    formOpen.value = false; form.resource_name = ""; form.purpose = ""; form.platform_id = ""; previous = ""; requestId.value = crypto.randomUUID();
    await router.replace({ query: {} }); await load();
  } catch (reason) { formError.value = reason instanceof Error ? reason.message : "提交失败，请重试"; }
  finally { saving.value = false; }
}
async function cancel(item: WorkflowRequest) {
  if (busy.value) return;
  busy.value = item.id; feedback.value = ""; formError.value = "";
  try { await api.cancelMyRequest(item.id, item.version); feedback.value = `已撤回：${item.title}`; await load(); }
  catch (reason) { formError.value = reason instanceof Error ? reason.message : "撤回失败"; await load(); }
  finally { busy.value = ""; }
}
onMounted(async () => { await load(); if (route.query.new && user.value?.person_id) { if (kinds.some(item => item.value === route.query.new)) form.request_type = String(route.query.new); await openForm(); } });
</script>
<template>
  <div class="page-stack fusion-space requests-space">
    <PageHeader eyebrow="我的空间" title="我的申请" description="申请席位、平台或账号，在这里查看处理进度。">
      <button v-if="user?.person_id && !formOpen" type="button" class="primary-button" @click="openForm"><Plus :size="18" />发起申请</button>
    </PageHeader>
    <p v-if="feedback" class="fusion-feedback" role="status"><CheckCircle2 :size="18" />{{ feedback }}</p>
    <section v-if="loading" class="fusion-empty" role="status">正在读取申请…</section>
    <section v-else-if="error" class="fusion-empty" role="alert"><h2>暂时无法读取申请</h2><p>{{ error }}</p><button class="secondary-button" @click="load">重试</button></section>
    <section v-else-if="!user?.person_id" class="fusion-empty"><h2>尚未关联员工身份</h2><p>请联系管理员关联身份后提交申请。</p></section>
    <template v-else>
      <form v-if="formOpen" class="content-panel employee-request-form" @submit.prevent="submit">
        <header><div><h2>发起使用申请</h2><p>申请仅进入处理流程；批准后由负责人完成开通。</p></div><button class="quiet-button" type="button" :disabled="saving" @click="formOpen = false">收起</button></header>
        <fieldset class="request-kind-options"><legend>申请类型</legend><label v-for="kind in kinds" :key="kind.value" :class="{ active: form.request_type === kind.value }"><input v-model="form.request_type" type="radio" name="request-type" :value="kind.value" :disabled="saving" /><component :is="kind.icon" :size="22" /><strong>{{ kind.label }}</strong><small>{{ kind.description }}</small></label></fieldset>
        <div class="form-grid">
          <label><span>工具、平台或账号名称 *</span><input v-model="form.resource_name" required maxlength="160" :disabled="saving" placeholder="填写需要申请使用的资源名称" /></label>
          <label><span>关联已有平台（选填）</span><select v-model="form.platform_id" :disabled="saving"><option value="">暂无对应平台 / 暂不关联</option><option v-for="item in platforms" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label class="span-2"><span>用途与需求 *</span><textarea v-model="form.purpose" required maxlength="2000" rows="4" :disabled="saving" placeholder="说明用于什么工作、需要哪些能力及预计使用时间；不要填写密码或密钥。" /></label>
          <div class="form-actions span-2"><button class="secondary-button" type="button" :disabled="saving" @click="formOpen = false">取消</button><button class="primary-button" :disabled="saving"><Send :size="17" />{{ saving ? '正在提交…' : '提交申请' }}</button></div>
        </div>
      </form>
      <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>
      <header class="request-list-heading"><h2>申请记录</h2><span><Clock3 :size="16" />{{ pending }} 项处理中 · 共 {{ rows.length }} 项</span></header>
      <div v-if="rows.length" class="request-records">
        <article v-for="item in rows" :key="item.id" class="content-panel request-record"><header><div><small>{{ labels[item.request_type] || item.request_type }}申请 · {{ item.request_no }}</small><h3>{{ item.title }}</h3></div><StatusBadge :tone="item.status === 'completed' ? 'success' : ['failed', 'rejected'].includes(item.status) ? 'warning' : item.status === 'pending' ? 'warning' : 'default'">{{ statuses[item.status] || item.status }}</StatusBadge></header><p>{{ item.detail.purpose || '暂无需求说明' }}</p><footer><time>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</time><button v-if="['draft','pending'].includes(item.status)" class="secondary-button" :disabled="Boolean(busy)" @click="cancel(item)">{{ busy === item.id ? '正在撤回…' : '撤回申请' }}</button></footer></article>
      </div>
      <section v-else class="fusion-empty"><Send :size="28" /><h2>还没有申请记录</h2><p>需要公司工具、平台或账号时，从这里发起申请。</p><button v-if="!formOpen" class="primary-button" @click="openForm">发起申请<ArrowRight :size="17" /></button></section>
    </template>
  </div>
</template>
