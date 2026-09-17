<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Boxes, CheckCircle2, KeyRound, UserRound } from "lucide-vue-next";

import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type Asset } from "../lib/api";

const assets = ref<Asset[]>([]); const loading = ref(true); const identityKnown = ref(false);
onMounted(async () => {
  const personId = localStorage.getItem("account-center-person-id"); identityKnown.value = Boolean(personId);
  try {
    if (!personId) { assets.value = []; return; }
    assets.value = await api.myAssets();
  } finally { loading.value = false; }
});
</script>

<template>
  <div class="page-stack">
    <PageHeader eyebrow="个人视角" title="我的使用" description="只展示与你有关的平台、授权、服务和待确认事项。" />
    <section v-if="!identityKnown" class="personal-empty"><UserRound :size="32" /><h2>请从钉钉打开应用</h2><p>识别身份后，这里会自动显示你负责或被授权使用的数字资产。</p></section>
    <section v-else class="personal-assets"><div class="section-heading"><div><h2>我负责的资产</h2><p>根据责任关系自动汇总。</p></div><StatusBadge tone="success">{{ assets.length }} 项</StatusBadge></div><div class="personal-asset-grid"><RouterLink v-for="asset in assets" :key="asset.id" :to="`/assets/${asset.id}`"><span><Boxes :size="19" /></span><div><strong>{{ asset.name }}</strong><small>{{ asset.asset_code }}</small></div><StatusBadge :tone="asset.status === 'active' ? 'success' : 'warning'">{{ asset.status }}</StatusBadge></RouterLink></div><div v-if="!loading && !assets.length" class="large-empty-panel"><CheckCircle2 :size="28" /><strong>目前没有分配给你的资产</strong><p>你仍可通过“登记 / 发现资产”提交新发现。</p><RouterLink to="/intake" class="primary-button"><KeyRound :size="16" />登记发现</RouterLink></div></section>
  </div>
</template>
