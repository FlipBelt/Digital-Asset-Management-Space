<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import PageHeader from "../components/PageHeader.vue";
import { api, type Asset, type AIRegistrationType } from "../lib/api";
const route = useRoute();
const types = ref<AIRegistrationType[]>([]);
const error = ref(""); const loading = ref(true); const saving = ref(false); const result = ref<Asset | null>(null);
const form = reactive({name: "", description: "", asset_type_id: "", development_method: ""});
const requestId = ref(crypto.randomUUID()); let previous = "";
const zipFile = ref<File | null>(null); const uploaded = ref(false);
const selectedType = computed(() => types.value.find(item => item.id === form.asset_type_id));
const requiresAIDevelopment = computed(() => Boolean(selectedType.value?.requires_ai_development));
watch(() => form.asset_type_id, () => { form.development_method = ""; });
function chooseZip(event: Event) { zipFile.value = (event.target as HTMLInputElement).files?.[0] ?? null; }
async function uploadZip() { if (!result.value || !zipFile.value) return; saving.value = true; error.value = ""; try { await api.uploadAssetZip(result.value.id, zipFile.value); uploaded.value = true; } catch(e) { error.value = e instanceof Error ? e.message : "附件上传失败"; } finally { saving.value = false; } }
async function initialize() {
  loading.value = true; error.value = "";
  try {
    types.value = await api.aiRegistrationTypes();
    const preset = typeof route.query.type === "string" ? route.query.type : "";
    if (!form.asset_type_id) form.asset_type_id = types.value.find(item => item.code === preset)?.id ?? "";
  } catch(e) { error.value = e instanceof Error ? e.message : "AI 成果类型读取失败"; }
  finally { loading.value = false; }
}
onMounted(initialize);
async function submit() {
  error.value = "";
  if (!selectedType.value) { error.value = "请选择可登记的 AI 成果类型"; return; }
  saving.value = true;
  const body = {name: form.name.trim(), description: form.description.trim(), asset_type_id: form.asset_type_id,
    source_type: "manual", source_system: "asset-center-web", development_method: requiresAIDevelopment.value ? form.development_method || null : null};
  const serialized = JSON.stringify(body); if (previous && previous !== serialized) requestId.value = crypto.randomUUID(); previous = serialized;
  try { result.value = await api.createAssetDraft({...body, request_id: requestId.value}); if (zipFile.value) await uploadZip(); }
  catch(e) { error.value = e instanceof Error ? e.message : "保存失败，请重试"; }
  finally { saving.value = false; }
}
</script>
<template>
  <div class="page-stack fusion-space">
    <PageHeader eyebrow="沉淀 AI 工作成果" title="登记 AI 成果" description="登记可复用的 AI 技能、插件、智能体、工作流或 AI 辅助开发成果，先保存私有草稿，再核对并确认。" />
    <p class="fusion-muted">订阅请在<RouterLink to="/my/subscriptions">我的订阅</RouterLink>登记；平台、账号、设备和其他公司资产由管理后台登记。</p>
    <section v-if="result" class="fusion-empty" role="status"><h2>AI 成果草稿已保存</h2><p>{{ result.name }} · 待人工审核，不代表正式批准使用。</p><p v-if="uploaded">ZIP 附件已保存。</p><p v-if="error" role="alert">{{ error }}</p><button v-if="zipFile && !uploaded" class="secondary-button" :disabled="saving" @click="uploadZip">重试附件上传</button><RouterLink :to="{ path: `/discover/${result.id}`, query: { returnTo: '/my/drafts' } }" class="primary-button">查看草稿</RouterLink><RouterLink to="/my/drafts" class="secondary-button">我的草稿</RouterLink></section>
    <section v-else-if="loading" class="fusion-empty" role="status" aria-busy="true">正在读取 AI 成果类型…</section>
    <form v-else class="fusion-register" @submit.prevent="submit">
      <label>成果名称<input v-model="form.name" required maxlength="200" placeholder="例如：竞品视觉拆解" /></label>
      <label>AI 成果类型<select v-model="form.asset_type_id" required><option value="" disabled>请选择 AI 成果类型</option><option v-for="item in types" :key="item.id" :value="item.id">{{ item.registration_name }}</option></select></label>
      <label>一句话说明<textarea v-model="form.description" required maxlength="2000" placeholder="AI 如何参与？帮助谁解决什么问题？" /></label>
      <label v-if="requiresAIDevelopment">AI 参与方式<select v-model="form.development_method" required><option value="" disabled>请选择开发方式</option><option value="vibe_coding">AI 辅助编程</option><option value="mixed">人工与 AI 混合开发</option></select></label>
      <label>成果 ZIP（选填，最多 20 MB）<input type="file" accept=".zip,application/zip" @change="chooseZip" /></label><p>创建人来自当前登录身份。保存后继续核对责任、附件与关系。</p>
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <button v-if="!types.length" type="button" class="secondary-button" @click="initialize">重新读取类型</button>
      <button class="primary-button" :disabled="saving || !types.length">{{ saving ? '正在保存…' : '保存 AI 草稿' }}</button>
    </form>
  </div>
</template>
