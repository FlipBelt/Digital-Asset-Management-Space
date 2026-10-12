<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RefreshCw, Search, ArrowRight } from "lucide-vue-next";
import PageHeader from "../components/PageHeader.vue";
import WorkspaceTabs from "../components/WorkspaceTabs.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type HuduFollowupItem } from "../lib/api";
import { groupFollowupItems } from "../lib/followup";

const items = ref<HuduFollowupItem[]>([]);
const loading = ref(true); const error = ref(""); const query = ref("");
const active = ref("all"); const windowDays = ref<number | null>(null);
const dueBefore = ref("");
function isDue(item: HuduFollowupItem) { return !!item.expires_at && item.expires_at.slice(0, 10) <= dueBefore.value; }
const tabs = computed(() => [
  { value: "all", label: "全部待跟进", count: items.value.length },
  { value: "due", label: "到期事项", count: items.value.filter(isDue).length },
  { value: "owner", label: "待补负责人", count: items.value.filter(item => !item.has_owner).length },
  { value: "children", label: "员工绑定与交接", count: items.value.filter(item => item.pending_child_count).length },
]);
const filtered = computed(() => {
  const term = query.value.trim().toLocaleLowerCase();
  return items.value.filter(item => (active.value === "all" || (active.value === "owner" ? !item.has_owner : active.value === "children" ? !!item.pending_child_count : isDue(item)))
    && `${item.name} ${item.asset_code} ${item.plan_name || ""} ${item.platform_name || ""} ${item.parent_account_name || ""} ${item.owner_department_name || ""} ${item.responsible_person_name || ""} ${item.proposed_responsible_name || ""}`.toLocaleLowerCase().includes(term));
});
const sections = computed(() => {
  const groups = groupFollowupItems(filtered.value);
  return [{ key: "accounts", label: "公司账号与订阅", description: "先定位公司账号，再处理账号下的订阅；未关联账号的订阅按平台归组。" },
    { key: "assets", label: "业务资产", description: "跟进系统、接口、云资源等实际业务资产。" }].map(section => ({ ...section,
      groups: groups.filter(group => group.section === section.key),
      count: filtered.value.filter(item => (item.group_section || "assets") === section.key).length,
    })).filter(section => section.count);
});
function dueLabel(item: HuduFollowupItem) {
  return item.expires_at ? new Date(item.expires_at).toLocaleDateString("zh-CN") : "未记录到期时间";
}
async function load() {
  loading.value = true; error.value = "";
  try {
    const response = await api.huduExpirations(); items.value = response.items; windowDays.value = response.window_days;
    const cutoff = new Date(); cutoff.setDate(cutoff.getDate() + response.window_days);
    dueBefore.value = response.due_before || `${cutoff.getFullYear()}-${String(cutoff.getMonth() + 1).padStart(2, "0")}-${String(cutoff.getDate()).padStart(2, "0")}`;
  }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "跟进事项读取失败"; }
  finally { loading.value = false; }
}
onMounted(load);
</script>
<template>
  <div class="page-stack followup-page">
    <PageHeader eyebrow="管理区" title="到期与责任跟进" description="按公司账号与订阅、业务资产处理到期、责任和员工交接事项。平台目录、个人订阅及子账号明细在平台与账号管理。">
      <button class="secondary-button" :disabled="loading" @click="load"><RefreshCw :size="16" />刷新</button>
    </PageHeader>
    <section v-if="loading" class="fusion-empty" role="status">正在读取跟进事项…</section>
    <section v-else-if="error" class="fusion-empty" role="alert"><h2>暂时无法读取跟进事项</h2><p>{{ error }}</p><button class="secondary-button" @click="load">重试</button></section>
    <template v-else>
      <WorkspaceTabs v-model="active" :tabs="tabs" label="跟进事项" id-prefix="followup-tab" />
      <section id="followup-tab-panel" role="tabpanel" :aria-labelledby="`followup-tab-${active}`" class="content-panel">
        <div class="followup-toolbar"><label class="fusion-search"><Search :size="17" aria-hidden="true" /><input v-model="query" aria-label="搜索跟进资产" placeholder="搜索名称、编号或部门" type="search" /></label><span class="fusion-muted">{{ windowDays === null ? '' : `到期窗口：${windowDays} 天` }} · {{ filtered.length }} 项</span></div>
        <div v-if="!filtered.length" class="empty-state"><strong>{{ query ? '没有匹配的跟进事项' : '当前没有待跟进事项' }}</strong><p>{{ query ? '试试其他名称、编号或部门。' : '有到期或责任待补事项时，会在这里显示。' }}</p><button v-if="query" class="secondary-button" @click="query = ''">清除搜索</button></div>
        <template v-else>
          <section v-for="section in sections" :key="section.key" class="followup-section">
            <header class="followup-section-heading"><div><h2>{{ section.label }} <small>{{ section.count }} 项</small></h2><p>{{ section.description }}</p></div></header>
            <section v-for="group in section.groups" :key="group.key" class="followup-group">
              <header class="followup-group-heading"><div><h3>{{ group.label }}</h3><p v-if="group.section === 'accounts'">{{ group.platform && group.platform !== group.label ? `${group.platform} · ` : '' }}{{ group.items.length }} 项待跟进</p></div><RouterLink v-if="group.href" :to="group.href" class="text-link">查看平台与账号<ArrowRight :size="14" /></RouterLink></header>
              <ul class="followup-list"><li v-for="item in group.items" :key="item.id">
                <div><RouterLink :to="item.management_href || `/assets/${item.id}`"><strong>{{ item.followup_kind === 'subscription' ? item.plan_name || item.name : item.name }}</strong></RouterLink><p>{{ item.asset_code }} · {{ item.followup_kind === 'account' ? '公司账号' : item.followup_kind === 'subscription' ? '订阅' : item.asset_type_name }} · {{ item.owner_department_name || (item.ownership_scope === 'company' ? '公司统一管理' : '归属待确认') }}</p><p v-if="item.followup_kind === 'subscription' && !item.parent_account_name" class="account-link-hint">管理账号尚未关联</p><p>负责人：{{ item.responsible_person_name || (item.proposed_responsible_name ? `建议 ${item.proposed_responsible_name}（待确认）` : '尚未配置') }}<span v-if="item.responsibility_issue && !item.proposed_responsible_name"> · {{ item.responsibility_issue }}</span></p><p v-if="item.pending_child_count">{{ item.pending_child_count }} 个账号明细需绑定员工或完成离职交接</p></div>
                <div class="followup-facts"><span :class="{ 'due-date': isDue(item) }">{{ dueLabel(item) }}</span><StatusBadge v-if="isDue(item)" tone="warning">{{ item.expires_at!.slice(0, 10) < new Date().toISOString().slice(0, 10) ? '已到期' : '即将到期' }}</StatusBadge><StatusBadge v-if="!item.has_owner" tone="warning">{{ item.proposed_responsible_name ? '负责人待确认' : item.responsibility_issue || '待补负责人' }}</StatusBadge></div>
                <RouterLink class="secondary-button" :to="`/assets/${item.id}?tab=${isDue(item) && item.has_owner ? 'overview' : 'responsibility'}`">{{ isDue(item) && item.has_owner ? '核对到期' : item.proposed_responsible_name ? '确认负责人' : '维护责任' }}<ArrowRight :size="15" /></RouterLink>
              </li></ul>
            </section>
          </section>
        </template>
      </section>
    </template>
  </div>
</template>

<style scoped>
.followup-section { margin-top:28px; }
.followup-section-heading h2 { margin:0; font-size:18px; }
.followup-section-heading small { margin-left:8px; color:var(--muted); font-size:13px; font-weight:400; }
.followup-section-heading p, .followup-group-heading p { margin:6px 0 0; color:var(--muted); font-size:13px; }
.followup-group { margin-top:16px; border:1px solid var(--border); border-radius:var(--radius); padding:0 20px; }
.followup-group-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:16px 0; }
.followup-group-heading h3 { margin:0; font-size:15px; }
.followup-group-heading .text-link { display:flex; align-items:center; gap:8px; font-size:13px; }
.followup-list { margin-top:0; }
.followup-facts { max-width:240px; flex-wrap:wrap; gap:8px; }
.due-date { font-weight:600; }
.account-link-hint { color:var(--muted); }
@media (max-width:640px) { .followup-group { padding:0 12px; } .followup-group-heading { align-items:start; flex-wrap:wrap; } }
</style>
