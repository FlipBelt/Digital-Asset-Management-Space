<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ArrowRight, Plus, ArchiveRestore } from "lucide-vue-next";
import PageHeader from "../components/PageHeader.vue";
import AdminPage from "./AdminPage.vue";
import { api, type CurrentUser } from "../lib/api";
import { canManageWorkspace, canRegisterBasics, managementItems, registrationKinds } from "../lib/managementWorkspace";
const route = useRoute();
const user = ref<CurrentUser | null>(null); const error = ref(""); const loading = ref(true);
const allowed = computed(() => canManageWorkspace(user.value));
const isAdmin = computed(() => !!user.value?.roles.includes("system_admin"));
const settings = computed(() => route.query.tab === "settings" && isAdmin.value);
const records = computed(() => managementItems(user.value).filter(item => item.group === "records"));
const actions = computed(() => managementItems(user.value).filter(item => item.group === "actions"));
const canDelete = computed(() => !!user.value && (isAdmin.value || (user.value.roles.includes("asset_manager") && user.value.permissions.includes("asset.write"))));
async function load() {
  loading.value = true; error.value = "";
  try { user.value = await api.currentSession(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "管理权限读取失败"; }
  finally { loading.value = false; }
}
onMounted(load);
</script>
<template>
  <div class="page-stack management-home">
    <PageHeader eyebrow="管理区" :title="settings ? '系统设置' : '公司资产管理'" :description="settings ? '统一维护分类、组织同步、连接器和审计配置。' : '从资产开始维护资料，按需登记新对象、审核成果或处理待办。'">
      <RouterLink v-if="!settings && canRegisterBasics(user)" to="/intake" class="primary-button"><Plus :size="16" />登记基础资料</RouterLink>
    </PageHeader>
    <section v-if="loading" class="fusion-empty" role="status">正在核对管理权限…</section>
    <section v-else-if="error" class="fusion-empty" role="alert"><h2>暂时无法读取管理事项</h2><p>{{ error }}</p><button class="secondary-button" @click="load">重试</button></section>
    <section v-else-if="!allowed" class="fusion-empty"><h2>当前身份没有管理权限</h2><p>需要申请席位、平台或账号时，请进入我的申请。</p><RouterLink to="/my/requests" class="primary-button">我的申请</RouterLink><RouterLink to="/my" class="secondary-button">返回我的空间</RouterLink></section>
    <AdminPage v-else-if="settings" embedded />
    <template v-else>
      <section class="management-section"><header><h2>资产与资料</h2><p>查询、维护和核对公司已有记录。</p></header><div class="management-entry-grid">
        <RouterLink v-for="item in records" :key="item.key" :to="item.to" class="management-entry"><div><strong>{{ item.label }}</strong><p>{{ item.description }}</p></div><ArrowRight :size="18" aria-hidden="true" /></RouterLink>
      </div></section>
      <section v-if="actions.length" class="management-section"><header><h2>审核与跟进</h2><p>进入对应队列，按当前权限处理事项。</p></header><div class="management-entry-grid">
        <RouterLink v-for="item in actions" :key="item.key" :to="item.to" class="management-entry"><div><strong>{{ item.label }}</strong><p>{{ item.description }}</p></div><ArrowRight :size="18" aria-hidden="true" /></RouterLink>
      </div></section>
      <details v-if="canRegisterBasics(user)" class="management-registration-guide"><summary>登记新资料 · 按业务对象直接进入</summary><p>已有对象先查询，缺少的关系或资料可以稍后补充。</p><div class="management-registration-links"><RouterLink v-for="item in registrationKinds" :key="item.mode" :to="{ path:'/intake', query:{mode:item.mode} }">{{ item.label }}<ArrowRight :size="15" aria-hidden="true" /></RouterLink></div></details>
      <footer class="management-home-footer"><p>此处维护公司资源。查找和复用 AI 成果，请进入<RouterLink to="/discover">AI 资产</RouterLink>。</p><RouterLink v-if="canDelete" to="/assets?trash=1" class="secondary-button"><ArchiveRestore :size="16" />资产回收站</RouterLink></footer>
    </template>
  </div>
</template>
