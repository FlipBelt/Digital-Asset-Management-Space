<script setup lang="ts">
import { ref, watch } from "vue";
import { api } from "../lib/api";
const props = defineProps<{assetId: string}>();
const items = ref<{id: string; file_name: string; size_bytes: number}[]>([]); const error = ref(""); const loading = ref(false); let sequence = 0;
async function load() { const request=++sequence; loading.value=true; error.value=""; try { const data=await api.assetAttachments(props.assetId); if(request===sequence)items.value=data; } catch(e) { if(request===sequence)error.value=e instanceof Error?e.message:"附件读取失败"; } finally{if(request===sequence)loading.value=false;} }
watch(()=>props.assetId,load,{immediate:true});
async function download(item: {id:string;file_name:string}) { try { const blob=await api.downloadAssetZip(props.assetId,item.id); const url=URL.createObjectURL(blob); const a=document.createElement("a");a.href=url;a.download=item.file_name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }catch(e){error.value=e instanceof Error?e.message:"下载失败";} }
</script>
<template><section class="content-panel"><h2>成果附件</h2><p v-if="loading" role="status">正在读取…</p><p v-else-if="error" role="alert">{{ error }} <button class="secondary-button" @click="load">重试</button></p><p v-else-if="!items.length">尚未上传成果附件。</p><ul v-else><li v-for="item in items" :key="item.id"><button class="secondary-button" @click="download(item)">{{ item.file_name }} · {{ Math.ceil(item.size_bytes/1024) }} KB · 下载</button></li></ul></section></template>
