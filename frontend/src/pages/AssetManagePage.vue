<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowRight, Boxes, Building2, ChartNoAxesCombined, ClipboardCheck, FileInput, KeyRound, Layers3, Truck, Users } from "lucide-vue-next";
import PageHeader from "../components/PageHeader.vue";
import WorkspaceTabs from "../components/WorkspaceTabs.vue";
import AdminPage from "./AdminPage.vue";
import { api, type CurrentUser } from "../lib/api";
import { legacyWorkspaceEnabled } from "../lib/workspaceNavigation";
const route = useRoute(); const router = useRouter();
const user = ref<CurrentUser | null>(null); const error = ref(""); const loading = ref(true);
const allowed = computed(() => Boolean(user.value?.roles.some(role => ["system_admin", "asset_manager", "department_manager", "group_leader", "auditor"].includes(role))));
const isAdmin = computed(() => Boolean(user.value?.roles.includes("system_admin")));
const globalManager = computed(() => Boolean(user.value?.roles.some(role => ["system_admin", "asset_manager"].includes(role))));
const groupOnly = computed(() => Boolean(user.value?.roles.includes("group_leader") && !user.value?.roles.some(role => ["system_admin", "asset_manager", "department_manager", "auditor"].includes(role))));
const active = computed(() => route.query.tab === "settings" && isAdmin.value ? "settings" : "operations");
const tabs = computed(() => [{ value: "operations", label: "资产管理" }, ...(isAdmin.value ? [{ value: "settings", label: "系统设置" }] : [])]);
const registrations = [
  { to: "/intake?mode=platform", title: "登记平台", text: "补充平台目录", icon: Layers3 },
  { to: "/intake?mode=entity", title: "登记公司主体", text: "新建法人主体档案", icon: Building2 },
  { to: "/intake?mode=provider", title: "登记供应商", text: "维护服务提供方", icon: Truck },
  { to: "/intake?mode=identity", title: "登记注册身份", text: "手机号、邮箱等标识", icon: KeyRound },
  { to: "/intake?mode=platform-account", title: "登记平台账号", text: "公司账号或租户", icon: Users },
  { to: "/intake?mode=resource", title: "登记服务与资源", text: "服务、系统与云资源", icon: Boxes },
];
const records = computed(() => [
  { to: "/assets", title: "公司资产台账", description: "维护 AI 成果与公司资源的分类、责任和归档记录。", icon: Boxes },
  { to: "/accounts", title: "平台与账号", description: "维护公司平台、账号及安全引用。", icon: KeyRound },
  { to: "/organization", title: "组织与授权", description: "核对公司、部门、成员与有效使用授权。", icon: Users },
  { to: "/services", title: "订阅与用量", description: "核对服务订阅、费用及调用记录。", icon: ChartNoAxesCombined },
  { to: "/governance", title: "申请处理与风险", description: "处理员工申请，核对到期和风险事项。", icon: ClipboardCheck },
  ...(globalManager.value ? [{ to: "/imports", title: "批量导入", description: "预览、校验并确认已有资料清单。", icon: FileInput }] : []),
  ...(legacyWorkspaceEnabled(import.meta.env.BASE_URL, window.location.hostname) ? [{ to: "/hudu", title: "原资产工作区", description: "查看历史资产工作区。", icon: Boxes }] : []),
].filter(item => !groupOnly.value || ["/assets", "/organization"].includes(item.to)));
function selectTab(value: string) { void router.replace({ query: value === "settings" ? { tab: "settings" } : {} }); }
async function load() { loading.value = true; error.value = ""; try { user.value = await api.currentSession(); } catch (reason) { error.value = reason instanceof Error ? reason.message : "读取失败"; } finally { loading.value = false; } }
onMounted(load);
</script>
<template>
  <div class="page-stack fusion-space management-space">
    <PageHeader eyebrow="管理区" title="公司资产管理" description="维护平台、账号、供应商与基础设施，处理员工申请。AI 成果的查找与复用请进入 AI 资产。"><RouterLink to="/discover" class="secondary-button">浏览 AI 成果<ArrowRight :size="16" /></RouterLink></PageHeader>
    <section v-if="loading" class="fusion-empty" role="status">正在核对管理权限…</section>
    <section v-else-if="error" class="fusion-empty" role="alert"><p>{{ error }}</p><button class="secondary-button" @click="load">重试</button></section>
    <section v-else-if="!allowed" class="fusion-empty"><h2>当前身份没有管理权限</h2><p>需要申请席位、平台或账号时，请进入我的申请。</p><RouterLink to="/my/requests" class="primary-button">我的申请</RouterLink><RouterLink to="/my" class="secondary-button">返回我的空间</RouterLink></section>
    <template v-else>
      <WorkspaceTabs :model-value="active" :tabs="tabs" id-prefix="manage-tab" label="管理事项" @update:model-value="selectTab" />
      <div id="manage-tab-panel" role="tabpanel" :aria-labelledby="`manage-tab-${active}`">
        <AdminPage v-if="active === 'settings' && isAdmin" embedded />
        <div v-else class="management-operations">
          <section v-if="globalManager" class="management-registration"><header><div><h2>登记基础资料</h2><p>选择对象后直接填写，已有资料先查重再补充。</p></div><RouterLink to="/assets" class="text-button">查询公司资产台账<ArrowRight :size="16" /></RouterLink></header><div class="registration-shortcuts"><RouterLink v-for="item in registrations" :key="item.to" :to="item.to"><component :is="item.icon" :size="22" /><div><strong>{{ item.title }}</strong><small>{{ item.text }}</small></div><ArrowRight :size="16" /></RouterLink></div></section>
          <section class="content-panel management-records"><header><h2>维护与处理</h2><span>按当前角色展示可用事项</span></header><RouterLink v-for="item in records" :key="item.to" :to="item.to" class="management-record-link"><component :is="item.icon" :size="21" /><div><strong>{{ item.title }}</strong><p>{{ item.description }}</p></div><ArrowRight :size="18" /></RouterLink></section>
          <section v-if="isAdmin" class="content-panel fusion-policy-draft"><h2>贡献激励 · 规则草案</h2><p>当前收集实践与贡献证据；价值、贡献归属和奖励规则由人工核对，尚未向员工发布。</p></section>
        </div>
      </div>
    </template>
  </div>
</template>
