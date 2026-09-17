<script setup lang="ts">
import { ArrowLeft, FileInput, UploadCloud } from "lucide-vue-next";
import { useRouter } from "vue-router";
const router = useRouter();
</script>

<template>
  <div class="hudu-page"><div class="hudu-breadcrumb"><button class="hudu-back" type="button" @click="router.push('/hudu')"><ArrowLeft :size="16" />资产库</button><span>/ 资料接入</span></div><header class="hudu-page-header"><div><span class="hudu-eyebrow">资料接入</span><h1>把资料变成资产</h1><p>先上传或粘贴原始资料，再在现有导入工作台中完成识别、复核和入库。</p></div></header><section class="hudu-intake-grid"><RouterLink to="/imports" class="hudu-surface hudu-intake-card"><span class="hudu-intake-icon"><UploadCloud :size="23" /></span><strong>打开导入工作台</strong><span>支持 Excel、CSV、截图和粘贴文本，先预览再入库。</span><b>进入工作台 →</b></RouterLink><RouterLink to="/intake" class="hudu-surface hudu-intake-card"><span class="hudu-intake-icon"><FileInput :size="23" /></span><strong>快速登记一条资产</strong><span>适合临时发现的平台账号、服务、系统或资源。</span><b>打开登记表单 →</b></RouterLink></section><section class="hudu-surface hudu-intake-note"><strong>入库原则</strong><span>资产库保留业务事实和外部引用；密码、Secret、私钥和恢复码不会写入本系统。</span></section></div>
</template>
