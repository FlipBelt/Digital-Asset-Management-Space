<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { api, type OutcomeAttachment } from "../lib/api";
const props = defineProps<{ assetId: string; canUpload?: boolean }>();
const emit = defineEmits<{ uploaded: [] }>();
const items = ref<OutcomeAttachment[]>([]);
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
watch(() => props.assetId, load, { immediate: true });
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
  error.value = "";
  if (file.size > 20 * 1024 * 1024 || !/\.(png|jpe?g|webp|zip)$/i.test(file.name)) { error.value = "请选择20MB以内的PNG、JPG、WebP或ZIP文件"; input.value = ""; return; }
  uploading.value = true;
  try { await api.uploadAssetZip(props.assetId, file); await load(); emit("uploaded"); }
  catch (e) { error.value = e instanceof Error ? e.message : "上传失败"; }
  finally { uploading.value = false; input.value = ""; }
}
</script>
<template>
  <section class="content-panel">
    <h2>成果附件</h2>
    <template v-if="canUpload"><p>支持PNG、JPG、WebP截图或ZIP成果包，每份最大20MB。补充后请重新核对登记版本。</p><label class="secondary-button">上传成果附件<input aria-label="选择成果附件" type="file" accept=".png,.jpg,.jpeg,.webp,.zip" :disabled="uploading" @change="upload" /></label><p v-if="uploading" role="status">正在上传…</p></template>
    <p v-if="loading" role="status">正在读取…</p>
    <p v-if="error" role="alert">{{ error }} <button class="secondary-button" @click="load">重新读取</button></p>
    <p v-if="!loading && !items.length">尚未上传成果附件。</p>
    <ul v-else class="outcome-attachments"><li v-for="item in items" :key="item.id">
      <strong>{{ item.file_name }}</strong> · {{ Math.ceil(item.size_bytes / 1024) }} KB
      <button v-if="item.content_type.startsWith('image/')" class="secondary-button" @click="preview(item)">预览截图</button>
      <button class="secondary-button" @click="download(item)">下载</button>
      <img v-if="previews[item.id]" :src="previews[item.id]" :alt="item.file_name" />
    </li></ul>
  </section>
</template>
<style scoped>
.outcome-attachments {list-style:none; padding:0; display:grid; gap:16px}
.outcome-attachments li {overflow-wrap:anywhere}
.outcome-attachments img {display:block; max-width:100%; max-height:560px; margin-top:12px; object-fit:contain}
input[type=file] {max-width:100%}
</style>
