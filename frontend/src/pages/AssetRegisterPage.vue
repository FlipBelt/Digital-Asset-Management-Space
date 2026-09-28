<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import PageHeader from "../components/PageHeader.vue";
import { api, type Asset, type AssetType } from "../lib/api";
const types = ref<AssetType[]>([]); const error = ref(""); const saving = ref(false); const result = ref<Asset | null>(null);
const form = reactive({name: "", description: "", asset_type_id: "", development_method: ""});
const requestId = ref(crypto.randomUUID()); let previous = "";
const zipFile = ref<File | null>(null); const uploaded = ref(false);
function chooseZip(event: Event) { zipFile.value = (event.target as HTMLInputElement).files?.[0] ?? null; }
async function uploadZip() { if (!result.value || !zipFile.value) return; saving.value = true; error.value = ""; try { await api.uploadAssetZip(result.value.id, zipFile.value); uploaded.value = true; } catch(e) { error.value = e instanceof Error ? e.message : "附件上传失败"; } finally { saving.value = false; } }
const isSystem = computed(() => types.value.find(t => t.id === form.asset_type_id)?.code === "internal_system");
async function initialize() { try { types.value = await api.assetTypes(); } catch(e) { error.value = e instanceof Error ? e.message : "类型读取失败"; } }
onMounted(initialize);
async function submit() {
  error.value = ""; saving.value = true;
  const body = {name: form.name.trim(), description: form.description.trim(), asset_type_id: form.asset_type_id,
    source_type: "manual", source_system: "asset-center-web", development_method: isSystem.value && form.development_method ? form.development_method : null};
  const serialized = JSON.stringify(body); if (previous && previous !== serialized) requestId.value = crypto.randomUUID(); previous = serialized;
  try { result.value = await api.createAssetDraft({...body, request_id: requestId.value}); if (zipFile.value) await uploadZip(); }
  catch(e) { error.value = e instanceof Error ? e.message : "保存失败，请重试"; }
  finally { saving.value = false; }
}
</script>
<template>
  <div class="page-stack fusion-space">
    <PageHeader eyebrow="沉淀工作成果" title="登记成果" description="先保存私有草稿，核对附件和共享范围后再确认登记。" />
    <section v-if="result" class="fusion-empty" role="status"><h2>草稿已保存</h2><p>{{ result.name }} · 待人工审核，不代表正式批准使用。</p><p v-if="uploaded">ZIP 附件已保存。</p><p v-if="error" role="alert">{{ error }}</p><button v-if="zipFile && !uploaded" class="secondary-button" :disabled="saving" @click="uploadZip">重试附件上传</button><RouterLink :to="`/discover/${result.id}`" class="primary-button">查看草稿</RouterLink><RouterLink to="/my/drafts" class="secondary-button">我的草稿</RouterLink></section>
    <form v-else class="fusion-register" @submit.prevent="submit">
      <label>成果名称<input v-model="form.name" required maxlength="200" placeholder="例如：竞品视觉拆解" /></label>
      <label>成果类型<select v-model="form.asset_type_id" required><option value="" disabled>请选择</option><option v-for="item in types" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
      <label>一句话说明<textarea v-model="form.description" required maxlength="2000" placeholder="帮助谁解决什么问题？" /></label>
      <label v-if="isSystem">开发方式<select v-model="form.development_method"><option value="">待确认</option><option value="traditional">传统开发</option><option value="low_code">低代码</option><option value="vibe_coding">AI 辅助编程</option><option value="mixed">混合方式</option></select></label>
      <label>成果 ZIP（选填，最多 20 MB）<input type="file" accept=".zip,application/zip" @change="chooseZip" /></label><p>创建人来自当前登录身份。保存后继续核对责任、附件与关系。</p>
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <button v-if="!types.length" type="button" class="secondary-button" @click="initialize">重新读取类型</button>
      <button class="primary-button" :disabled="saving || !types.length">{{ saving ? '正在保存…' : '保存草稿' }}</button>
      <RouterLink to="/intake" class="secondary-button">账号、服务及其他资料登记</RouterLink>
    </form>
  </div>
</template>
