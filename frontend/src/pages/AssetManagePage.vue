<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowRight, Boxes, ClipboardCheck, FileInput, KeyRound, Network, Settings, Users, ChartNoAxesCombined, Archive } from "lucide-vue-next";
import PageHeader from "../components/PageHeader.vue";
import { api, type CurrentUser } from "../lib/api";
const user = ref<CurrentUser | null>(null); const error = ref(""); const loading = ref(true);
const allowed = computed(() => Boolean(user.value?.roles.some(role => ["system_admin", "asset_manager", "department_manager", "group_leader", "auditor"].includes(role))));
const isAdmin = computed(() => Boolean(user.value?.roles.includes("system_admin")));
const groupOnly = computed(() => Boolean(user.value?.roles.includes("group_leader") && !user.value?.roles.some(role => ["system_admin", "asset_manager", "department_manager", "auditor"].includes(role))));
const cards = computed(() => [
  { to: "/map", title: "资产地图", description: "查看资产关系、归属及待复核的治理信息。", icon: Network },
  { to: "/assets", title: "资产底库", description: "维护原有资产字段、责任、关系及归档记录。", icon: Boxes },
  { to: "/accounts", title: "平台与账号", description: "公司平台、账号与安全引用。", icon: KeyRound },
  { to: "/organization", title: "人员与授权", description: "组织成员、部门和有效使用授权。", icon: Users },
  { to: "/services", title: "服务与用量", description: "订阅、调用量和连接器用量记录。", icon: ChartNoAxesCombined },
  { to: "/governance", title: "流程与风险", description: "处理既有申请、到期和风险核对。", icon: ClipboardCheck },
  { to: "/hudu", title: "原资产工作区", description: "继续使用原资产库、到期交接和资料接入。", icon: Archive },
  ...(user.value?.roles.some(role => ["system_admin", "asset_manager"].includes(role)) ? [{ to: "/imports", title: "资料接入", description: "导入预览、校验、人工核对和提交。", icon: FileInput }] : []),
  ...(isAdmin.value ? [{ to: "/admin", title: "系统设置与审计", description: "分类、字段、权限、连接器和审计记录。", icon: Settings }] : []),
].filter(card => !groupOnly.value || ["/map", "/assets", "/organization"].includes(card.to)));
async function load() { loading.value = true; error.value = ""; try { user.value = await api.currentSession(); } catch (reason) { error.value = reason instanceof Error ? reason.message : "读取失败"; } finally { loading.value = false; } }
onMounted(load);
</script>
<template>
  <div class="page-stack fusion-space">
    <PageHeader eyebrow="管理工作区" title="管理" description="按工作事项进入管理能力，保留原有业务流程。" />
    <section v-if="loading" class="fusion-empty" role="status">正在核对管理权限…</section>
    <section v-else-if="error" class="fusion-empty" role="alert"><p>{{ error }}</p><button class="secondary-button" @click="load">重试</button></section>
    <section v-else-if="!allowed" class="fusion-empty"><h2>当前身份没有管理权限</h2><p>请联系管理员核对角色与授权范围。</p><RouterLink to="/my" class="secondary-button">返回我的空间</RouterLink></section>
    <template v-else>
      <div class="fusion-grid"><RouterLink v-for="card in cards" :key="card.to" :to="card.to" class="fusion-card fusion-management-card"><component :is="card.icon" :size="24" /><h2>{{ card.title }}</h2><p>{{ card.description }}</p><span class="fusion-detail">进入管理<ArrowRight :size="17" /></span></RouterLink></div>
      <section v-if="isAdmin" class="content-panel fusion-policy-draft"><h2>贡献激励 · 规则草案</h2><p>当前只收集实践与贡献证据，价值和贡献归属由人工核对。预算、周期和奖励规则尚待确认，未向员工发布。</p></section>
    </template>
  </div>
</template>
