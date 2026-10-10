<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RefreshCw, Search, ArrowRight } from "lucide-vue-next";
import PageHeader from "../components/PageHeader.vue";
import WorkspaceTabs from "../components/WorkspaceTabs.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type HuduAssetItem } from "../lib/api";

const items = ref<HuduAssetItem[]>([]);
const loading = ref(true); const error = ref(""); const query = ref("");
const active = ref("all"); const windowDays = ref<number | null>(null);
const dueBefore = ref("");
function isDue(item: HuduAssetItem) { return !!item.expires_at && item.expires_at.slice(0, 10) <= dueBefore.value; }
const tabs = computed(() => [
  { value: "all", label: "全部待跟进", count: items.value.length },
  { value: "due", label: "到期事项", count: items.value.filter(isDue).length },
  { value: "owner", label: "待补负责人", count: items.value.filter(item => !item.has_owner).length },
  { value: "children", label: "账号待核实 / 交接", count: items.value.filter(item => item.pending_child_count).length },
]);
const filtered = computed(() => {
  const term = query.value.trim().toLocaleLowerCase();
  return items.value.filter(item => (active.value === "all" || (active.value === "owner" ? !item.has_owner : active.value === "children" ? !!item.pending_child_count : isDue(item)))
    && `${item.name} ${item.asset_code} ${item.owner_department_name || ""} ${item.responsible_person_name || ""}`.toLocaleLowerCase().includes(term));
});
function dueLabel(item: HuduAssetItem) {
  return item.expires_at ? new Date(item.expires_at).toLocaleDateString("zh-CN") : "未记录到期时间";
}
async function load() {
  loading.value = true; error.value = "";
  try {
    const response = await api.huduExpirations(); items.value = response.items; windowDays.value = response.window_days;
    const cutoff = new Date(); cutoff.setDate(cutoff.getDate() + response.window_days);
    dueBefore.value = `${cutoff.getFullYear()}-${String(cutoff.getMonth() + 1).padStart(2, "0")}-${String(cutoff.getDate()).padStart(2, "0")}`;
  }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "跟进事项读取失败"; }
  finally { loading.value = false; }
}
onMounted(load);
</script>
<template>
  <div class="page-stack followup-page">
    <PageHeader eyebrow="管理区" title="到期与责任跟进" description="先找到需要跟进的资产，再进入资产详情补充责任或核对到期资料。">
      <button class="secondary-button" :disabled="loading" @click="load"><RefreshCw :size="16" />刷新</button>
    </PageHeader>
    <section v-if="loading" class="fusion-empty" role="status">正在读取跟进事项…</section>
    <section v-else-if="error" class="fusion-empty" role="alert"><h2>暂时无法读取跟进事项</h2><p>{{ error }}</p><button class="secondary-button" @click="load">重试</button></section>
    <template v-else>
      <WorkspaceTabs v-model="active" :tabs="tabs" label="跟进事项" id-prefix="followup-tab" />
      <section id="followup-tab-panel" role="tabpanel" :aria-labelledby="`followup-tab-${active}`" class="content-panel">
        <div class="followup-toolbar"><label class="fusion-search"><Search :size="17" aria-hidden="true" /><input v-model="query" aria-label="搜索跟进资产" placeholder="搜索名称、编号或部门" type="search" /></label><span class="fusion-muted">{{ windowDays === null ? '' : `到期窗口：${windowDays} 天` }} · {{ filtered.length }} 项</span></div>
        <div v-if="!filtered.length" class="empty-state"><strong>{{ query ? '没有匹配的跟进事项' : '当前没有待跟进事项' }}</strong><p>{{ query ? '试试其他名称、编号或部门。' : '有到期或责任待补事项时，会在这里显示。' }}</p><button v-if="query" class="secondary-button" @click="query = ''">清除搜索</button></div>
        <ul v-else class="followup-list"><li v-for="item in filtered" :key="item.id">
          <div><RouterLink :to="item.management_href || `/assets/${item.id}`"><strong>{{ item.name }}</strong></RouterLink><p>{{ item.asset_code }} · {{ item.asset_type_name }} · {{ item.owner_department_name || (item.ownership_scope === 'company' ? '公司统一管理' : '归属待确认') }}</p><p>负责人：{{ item.responsible_person_name || '尚未配置' }}<span v-if="item.responsibility_issue"> · {{ item.responsibility_issue }}</span></p><p v-if="item.pending_child_count">{{ item.pending_child_count }} 个子账号待绑定员工、核实状态或交接</p></div>
          <div class="followup-facts"><span>{{ dueLabel(item) }}</span><StatusBadge v-if="!item.has_owner" tone="warning">{{ item.responsibility_issue || '待补负责人' }}</StatusBadge><StatusBadge v-else tone="success">负责人已配置</StatusBadge></div>
          <RouterLink class="secondary-button" :to="item.management_href || `/assets/${item.id}?tab=responsibility`">{{ item.management_href ? '管理账号' : '维护责任' }}<ArrowRight :size="15" /></RouterLink>
        </li></ul>
      </section>
    </template>
  </div>
</template>
