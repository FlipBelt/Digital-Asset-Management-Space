<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ArrowRight, CheckCircle2, Clock3, FileInput, Network, Plus, ShieldCheck } from "lucide-vue-next";

import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type DashboardData } from "../lib/api";

const loading = ref(true);
const error = ref("");
const dashboard = ref<DashboardData | null>(null);

onMounted(async () => {
  try { dashboard.value = await api.dashboard("company"); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "工作台加载失败"; }
  finally { loading.value = false; }
});
</script>

<template>
  <div class="page-stack workbench-page">
    <PageHeader eyebrow="今天从这里开始" title="数字资产工作台" description="只处理与你有关的确认、登记和交接；完整底库由资产管理员维护。">
      <RouterLink to="/intake" class="primary-button"><Plus :size="17" />登记 / 发现资产</RouterLink>
    </PageHeader>

    <div v-if="error" class="message-panel error-message">{{ error }}</div>

    <section class="workbench-hero">
      <div>
        <span class="hero-kicker">集团数字资产网络</span>
        <h2>知道资产在哪里，也知道由谁负责</h2>
        <p>平台账号、云资源、业务系统和人员授权已经可以在同一张关系图中查看。</p>
        <div class="hero-actions">
          <RouterLink to="/map" class="primary-button"><Network :size="17" />打开资产地图</RouterLink>
          <RouterLink to="/imports" class="secondary-button"><FileInput :size="17" />导入已有资料</RouterLink>
        </div>
      </div>
      <div class="hero-orbit" aria-hidden="true">
        <span class="orbit-center">公司</span><span class="orbit-node one">阿里云</span><span class="orbit-node two">系统</span><span class="orbit-node three">人员</span>
      </div>
    </section>

    <section class="workbench-task-section">
      <div class="section-heading"><div><h2>待我处理</h2><p>系统把复杂底表转换成具体任务。</p></div><StatusBadge tone="warning">3 项</StatusBadge></div>
      <div class="task-grid">
        <RouterLink to="/imports" class="task-card"><span class="task-icon amber"><FileInput :size="20" /></span><div><strong>确认导入资料</strong><span>各部门现有表格和 IT 资料可先进入待整理区</span></div><ArrowRight :size="18" /></RouterLink>
        <RouterLink to="/assets" class="task-card"><span class="task-icon blue"><CheckCircle2 :size="20" /></span><div><strong>补全资产归属</strong><span>{{ dashboard?.metrics.missing_department ?? 0 }} 项资产尚未明确归属部门</span></div><ArrowRight :size="18" /></RouterLink>
        <RouterLink to="/governance" class="task-card"><span class="task-icon violet"><Clock3 :size="20" /></span><div><strong>检查到期与交接</strong><span>{{ dashboard?.metrics.expiring_soon ?? 0 }} 项将在 30 天内到期</span></div><ArrowRight :size="18" /></RouterLink>
      </div>
    </section>

    <section class="workbench-overview">
      <div class="section-heading"><div><h2>公司资产概况</h2><p>这里只显示能帮助决策的数据。</p></div></div>
      <div class="metric-grid four">
        <article class="metric-card"><span class="metric-icon"><Network :size="20" /></span><span>已登记资产</span><strong>{{ loading ? "—" : dashboard?.metrics.assets ?? 0 }}</strong><small>账号、服务、资源与系统</small></article>
        <article class="metric-card"><span class="metric-icon"><ShieldCheck :size="20" /></span><span>关键资产</span><strong>{{ loading ? "—" : dashboard?.metrics.critical_assets ?? 0 }}</strong><small>需要明确责任和交接</small></article>
        <article class="metric-card"><span class="metric-icon"><Clock3 :size="20" /></span><span>临近到期</span><strong>{{ loading ? "—" : dashboard?.metrics.expiring_soon ?? 0 }}</strong><small>30 天内</small></article>
        <article class="metric-card"><span class="metric-icon"><CheckCircle2 :size="20" /></span><span>待补归属</span><strong>{{ loading ? "—" : dashboard?.metrics.missing_department ?? 0 }}</strong><small>需要部门确认</small></article>
      </div>
    </section>
  </div>
</template>
