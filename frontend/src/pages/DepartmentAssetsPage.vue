<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { Building2, Network } from "lucide-vue-next";

import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type Asset, type Department } from "../lib/api";

const departments = ref<Department[]>([]); const departmentId = ref(""); const assets = ref<Asset[]>([]); const loading = ref(true);
async function loadAssets() { if (!departmentId.value) return; loading.value = true; try { assets.value = (await api.assets({ department_id: departmentId.value })).data; } finally { loading.value = false; } }
onMounted(async () => { departments.value = await api.departments(); departmentId.value = departments.value[0]?.id ?? ""; await loadAssets(); });
watch(departmentId, loadAssets);
</script>

<template>
  <div class="page-stack">
    <PageHeader eyebrow="部门视角" title="部门资产" description="查看一个部门负责、使用和需要交接的账号、服务、资源与系统。"><label class="header-select"><span>当前部门</span><select v-model="departmentId"><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select></label></PageHeader>
    <section class="department-summary"><div><Building2 :size="24" /><span>部门资产</span><strong>{{ assets.length }}</strong></div><div><Network :size="24" /><span>关系已建立</span><strong>{{ assets.filter((asset) => asset.owner_department_id).length }}</strong></div></section>
    <section class="list-surface"><div class="department-asset-list"><RouterLink v-for="asset in assets" :key="asset.id" :to="`/assets/${asset.id}`"><div><strong>{{ asset.name }}</strong><span>{{ asset.asset_code }}</span></div><StatusBadge :tone="asset.status === 'active' ? 'success' : 'warning'">{{ asset.status }}</StatusBadge></RouterLink><div v-if="!loading && !assets.length" class="large-empty-panel"><Building2 :size="28" /><strong>该部门尚未明确资产</strong><p>可以先提交发现，之后由负责人确认归属。</p></div></div></section>
  </div>
</template>
