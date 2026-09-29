<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ScanSearch } from "lucide-vue-next";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import WorkspaceTabs from "../components/WorkspaceTabs.vue";
import { api, type CurrentUser, type Person, type RiskFinding, type WorkflowRequest } from "../lib/api";
const tab = ref("requests"); const loading = ref(true); const saving = ref(false); const message = ref(""); const error = ref("");
const user = ref<CurrentUser | null>(null); const requests = ref<WorkflowRequest[]>([]); const risks = ref<RiskFinding[]>([]); const people = ref<Person[]>([]);
const canWrite = computed(() => Boolean(user.value?.roles.includes("system_admin") || user.value?.permissions.includes("governance.write")));
const globalManager = computed(() => Boolean(user.value?.roles.some(role => ["system_admin", "asset_manager"].includes(role))));
const personName = computed(() => Object.fromEntries(people.value.map(item => [item.id, item.display_name])));
const tabs = computed(() => [{ value: "requests", label: "申请处理", count: requests.value.length }, { value: "risks", label: "风险核对", count: risks.value.filter(item => item.status === "open").length }]);
const labels: Record<string, string> = { draft: "草稿", pending: "待处理", approved: "已批准", rejected: "已驳回", executing: "执行中", completed: "已完成", failed: "执行失败", cancelled: "已撤回", open: "待核对", resolved: "已处理" };
const types: Record<string, string> = { seat: "席位", platform: "平台", account: "账号", permission: "权限", purchase: "采购", quota: "额度" };
const transitions: Record<string, { target: string; label: string }[]> = { draft: [{ target: "pending", label: "提交处理" }], pending: [{ target: "approved", label: "批准" }, { target: "rejected", label: "驳回" }], approved: [{ target: "executing", label: "开始执行" }], executing: [{ target: "completed", label: "确认完成" }, { target: "failed", label: "执行失败" }] };
async function load() {
  loading.value = true; error.value = "";
  try { user.value = await api.currentSession(); const [requestRows, riskRows, personRows] = await Promise.all([api.requests(), api.risks(), api.people()]); requests.value = requestRows; risks.value = riskRows; people.value = personRows; }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "读取失败"; }
  finally { loading.value = false; }
}
async function transition(item: WorkflowRequest, target: string) { saving.value = true; error.value = ""; try { await api.transitionRequest(item.id, target, item.version); message.value = `申请状态已更新：${labels[target]}`; await load(); } catch (reason) { error.value = reason instanceof Error ? reason.message : "处理失败，请刷新后重试"; } finally { saving.value = false; } }
async function scan() { saving.value = true; error.value = ""; try { const created = await api.scanRisks(); message.value = created.length ? `发现 ${created.length} 项新风险` : "扫描完成，没有新增风险"; tab.value = "risks"; await load(); } catch (reason) { error.value = reason instanceof Error ? reason.message : "扫描失败"; } finally { saving.value = false; } }
async function resolve(item: RiskFinding) { saving.value = true; try { await api.resolveRisk(item.id, item.version); await load(); } catch (reason) { error.value = reason instanceof Error ? reason.message : "处理失败"; } finally { saving.value = false; } }
onMounted(load);
</script>
<template>
  <div class="page-stack fusion-space">
    <PageHeader eyebrow="管理区" title="申请处理与风险" description="员工在我的申请提交需求；在这里审核、跟进开通与核对风险。"><RouterLink class="secondary-button" to="/manage">返回管理</RouterLink><button v-if="globalManager && canWrite" class="secondary-button" :disabled="saving" @click="scan"><ScanSearch :size="16" />扫描风险</button></PageHeader>
    <div v-if="message" class="message-panel success-message" role="status">{{ message }}</div><div v-if="error" class="message-panel error-message" role="alert">{{ error }}<button class="secondary-button" :disabled="saving" @click="load">重新读取</button></div>
    <WorkspaceTabs v-model="tab" :tabs="tabs" id-prefix="governance" label="处理事项" />
    <section id="governance-panel" class="content-panel" role="tabpanel" :aria-labelledby="`governance-${tab}`">
      <div v-if="loading" class="loading-state" role="status">正在读取…</div>
      <template v-else-if="tab === 'requests'"><div v-if="requests.length" class="request-records"><article v-for="item in requests" :key="item.id" class="request-record"><header><div><small>{{ types[item.request_type] || item.request_type }}申请 · {{ item.request_no }}</small><h3>{{ item.title }}</h3><p>{{ item.requester_person_id ? personName[item.requester_person_id] || '申请人待核对' : '历史申请，申请人待补充' }}</p></div><StatusBadge :tone="item.status === 'completed' ? 'success' : item.status === 'pending' ? 'warning' : 'default'">{{ labels[item.status] || item.status }}</StatusBadge></header><p>{{ item.detail.purpose || '暂无需求说明' }}</p><footer><time>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</time><div v-if="canWrite" class="row-actions"><button v-for="action in transitions[item.status] || []" :key="action.target" class="secondary-button" :disabled="saving" @click="transition(item, action.target)">{{ action.label }}</button></div></footer></article></div><div v-else class="mini-empty">当前范围没有申请记录。</div></template>
      <template v-else><div v-if="risks.length" class="request-records"><article v-for="item in risks" :key="item.id" class="request-record"><header><h3>{{ item.title }}</h3><StatusBadge :tone="item.status === 'open' ? 'warning' : 'success'">{{ labels[item.status] || item.status }}</StatusBadge></header><footer><span>{{ item.rule_key }}</span><button v-if="canWrite && item.status === 'open'" class="secondary-button" :disabled="saving" @click="resolve(item)">标记已处理</button></footer></article></div><div v-else class="mini-empty">当前范围没有风险记录。</div></template>
    </section>
  </div>
</template>
