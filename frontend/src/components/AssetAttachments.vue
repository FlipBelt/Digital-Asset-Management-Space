<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { api, type OutcomeAttachment } from "../lib/api";
const props = defineProps<{ assetId: string; canUpload?: boolean }>();
const emit = defineEmits<{ uploaded: [] }>();
const items = ref<OutcomeAttachment[]>([]);
const fileInput = ref<HTMLInputElement | null>(null);
const uploadName = ref(""); const uploadedMessage = ref("");
const previews = ref<Record<string, string>>({});
const error = ref(""); const loading = ref(false); const uploading = ref(false);
let sequence = 0;
function release() { Object.values(previews.value).forEach(URL.revokeObjectURL); previews.value = {}; }
async function load() {
  const request = ++sequence; release(); items.value = []; loading.value = true; error.value = "";
  try { const data = await api.assetAttachments(props.assetId); if (request === sequence) items.value = data; }
  catch (e) { if (request === sequence) error.value = e instanceof Error ? e.message : "附件读取失败"; }
  finally { if (request === sequence) loading.value = false; }
}
watch(() => props.assetId, () => { uploadedMessage.value = ""; void load(); }, { immediate: true });
onBeforeUnmount(() => { sequence++; release(); });
async function preview(item: OutcomeAttachment) {
  const request = sequence;
  try {
    const blob = await api.downloadAssetZip(props.assetId, item.id);
    if (request !== sequence) return;
    if (previews.value[item.id]) URL.revokeObjectURL(previews.value[item.id]);
    previews.value[item.id] = URL.createObjectURL(blob);
  } catch (e) { error.value = e instanceof Error ? e.message : "预览失败"; }
}
async function download(item: OutcomeAttachment) {
  try { const blob = await api.downloadAssetZip(props.assetId, item.id); const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = item.file_name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) { error.value = e instanceof Error ? e.message : "下载失败"; }
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement; const file = input.files?.[0];
  if (!file || uploading.value) return;
  error.value = ""; uploadedMessage.value = "";
  if (file.size > 20 * 1024 * 1024 || !/\.(png|jpe?g|webp|zip)$/i.test(file.name)) { error.value = "请选择20MB以内的PNG、JPG、WebP或ZIP文件"; input.value = ""; return; }
  uploading.value = true; uploadName.value = file.name;
  try { await api.uploadAssetZip(props.assetId, file); await load(); uploadedMessage.value = `已上传：${file.name}`; emit("uploaded"); }
  catch (e) { error.value = e instanceof Error ? e.message : "上传失败"; }
  finally { uploading.value = false; input.value = ""; }
}
</script>
<template>
  <section class="content-panel attachment-panel">
    <header><h2>成果附件</h2><p v-if="canUpload">支持 PNG、JPG、WebP 截图或 ZIP 成果包，每份最大 20MB。补充后请重新核对登记版本。</p></header>
    <div v-if="canUpload" class="attachment-upload">
      <input ref="fileInput" hidden aria-label="选择成果附件" type="file" accept=".png,.jpg,.jpeg,.webp,.zip" :disabled="uploading" @change="upload" />
      <button type="button" class="secondary-button" :disabled="uploading" @click="fileInput?.click()">{{ uploading ? '正在上传…' : '选择并上传附件' }}</button>
      <span v-if="!uploading" class="attachment-hint">可上传使用截图或成果文件</span>
      <p v-if="uploading" role="status">正在上传：{{ uploadName }}</p>
      <p v-else-if="uploadedMessage" role="status">{{ uploadedMessage }}</p>
    </div>
    <p v-if="loading" role="status">正在读取附件…</p>
    <div v-if="error" class="attachment-error" role="alert"><span>{{ error }}</span><button type="button" class="secondary-button" :disabled="loading || uploading" @click="load">重新读取</button></div>
    <p v-if="!loading && !error && !items.length" class="attachment-empty">尚未上传成果附件。</p>
    <ul v-if="items.length" class="outcome-attachments"><li v-for="item in items" :key="item.id">
      <div class="attachment-row"><div class="attachment-name"><strong>{{ item.file_name }}</strong><small>{{ Math.ceil(item.size_bytes / 1024) }} KB</small></div><div class="attachment-actions"><button v-if="item.content_type.startsWith('image/')" type="button" class="secondary-button" @click="preview(item)">预览截图</button><button type="button" class="secondary-button" @click="download(item)">下载</button></div></div>
      <img v-if="previews[item.id]" :src="previews[item.id]" :alt="item.file_name" />
    </li></ul>
  </section>
</template>
<style scoped>
.attachment-panel { display:grid; min-width:0; gap:16px; }
.attachment-panel h2, .attachment-panel p { margin:0; }
.attachment-panel header p { margin-top:8px; color:var(--muted); line-height:1.7; }
.attachment-upload, .attachment-row, .attachment-actions, .attachment-error { display:flex; flex-wrap:wrap; align-items:center; gap:12px; min-width:0; }
.attachment-upload p { flex-basis:100%; overflow-wrap:anywhere; }
.attachment-hint, .attachment-empty, .attachment-name small { color:var(--muted); font-size:13px; }
.outcome-attachments { list-style:none; margin:0; padding:0; display:grid; gap:16px; }
.outcome-attachments li { min-width:0; padding-top:16px; border-top:1px solid var(--border); }
.attachment-row { justify-content:space-between; }
.attachment-name { flex:1 1 220px; min-width:0; overflow-wrap:anywhere; }
.attachment-name strong, .attachment-name small { display:block; }
.attachment-name small { margin-top:6px; }
.outcome-attachments img { display:block; max-width:100%; max-height:560px; margin-top:16px; object-fit:contain; }
@media(max-width:600px) { .attachment-upload > button { width:100%; justify-content:center; } .attachment-actions { width:100%; } }
</style>
