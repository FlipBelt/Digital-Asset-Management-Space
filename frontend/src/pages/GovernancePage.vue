<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { AlertTriangle, ArrowRight, ClipboardCheck, Plus, Radar, ScanSearch } from "lucide-vue-next";

import ModalPanel from "../components/ModalPanel.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type Asset, type Person, type RiskFinding, type WorkflowRequest } from "../lib/api";

const tab = ref<"requests" | "risks">("requests"); const modal = ref(false); const loading = ref(true); const saving = ref(false); const message = ref(""); const error = ref("");
const requests = ref<WorkflowRequest[]>([]); const risks = ref<RiskFinding[]>([]); const people = ref<Person[]>([]); const assets = ref<Asset[]>([]);
const form = reactive({ request_type: "account", title: "", requester_person_id: "", asset_id: "", detail: {} });
const assetName = computed(() => Object.fromEntries(assets.value.map((item) => [item.id, item.name])));
const transitions: Record<string, { target: string; label: string }[]> = { draft: [{ target: "pending", label: "提交审批" }], pending: [{ target: "approved", label: "批准" }, { target: "rejected", label: "驳回" }], approved: [{ target: "executing", label: "开始执行" }], executing: [{ target: "completed", label: "完成" }, { target: "failed", label: "执行失败" }] };
async function load() { loading.value = true; try { const [requestRows, riskRows, peopleRows, assetRows] = await Promise.all([api.requests(), api.risks(), api.people(), api.assets()]); requests.value = requestRows; risks.value = riskRows; people.value = peopleRows; assets.value = assetRows.data } finally { loading.value = false } }
async function saveRequest() { saving.value = true; try { await api.createRequest({ ...form, requester_person_id: form.requester_person_id || null, asset_id: form.asset_id || null }); modal.value = false; form.title = ""; await load() } catch (reason) { error.value = reason instanceof Error ? reason.message : "保存失败" } finally { saving.value = false } }
async function transition(item: WorkflowRequest, target: string) { await api.transitionRequest(item.id, target, item.version); await load() }
async function scan() { saving.value = true; try { const created = await api.scanRisks(); message.value = created.length ? `发现 ${created.length} 项新风险` : "扫描完成，没有新增风险"; tab.value = "risks"; await load() } finally { saving.value = false } }
async function resolve(item: RiskFinding) { await api.resolveRisk(item.id, item.version); await load() }
onMounted(load);
</script>

<template>
  <div class="page-stack">
    <PageHeader title="流程与风险" description="第二阶段治理骨架已可用：固定状态流转、风险扫描与处理记录。"><button class="secondary-button" :disabled="saving" @click="scan"><ScanSearch :size="16" />运行风险扫描</button><button class="primary-button" @click="modal = true"><Plus :size="16" />发起申请</button></PageHeader>
    <div v-if="message" class="message-panel success-message">{{ message }}</div><div v-if="error" class="message-panel error-message">{{ error }}</div>
    <section class="metric-grid"><article class="metric-card"><span class="metric-icon"><ClipboardCheck :size="20" /></span><span>进行中申请</span><strong>{{ requests.filter((item) => !['completed','rejected','cancelled'].includes(item.status)).length }}</strong><small>账号、权限、采购及额度</small></article><article class="metric-card attention-card"><span class="metric-icon"><AlertTriangle :size="20" /></span><span>未处理风险</span><strong>{{ risks.filter((item) => item.status === 'open').length }}</strong><small>根据底库资料自动扫描</small></article><article class="metric-card"><span class="metric-icon"><Radar :size="20" /></span><span>风险规则</span><strong>10</strong><small>负责人、MFA、接管、到期等</small></article></section>
    <div class="dimension-tabs"><button :class="{ active: tab === 'requests' }" @click="tab = 'requests'">申请与执行</button><button :class="{ active: tab === 'risks' }" @click="tab = 'risks'">风险发现</button></div>
    <section class="content-panel governance-panel">
      <div v-if="tab === 'requests'" class="record-list"><div v-for="item in requests" :key="item.id"><span class="record-icon"><ClipboardCheck :size="18" /></span><div><strong>{{ item.title }}</strong><span>{{ item.request_no }} · {{ item.request_type }} · {{ new Date(item.created_at).toLocaleString('zh-CN') }}</span></div><StatusBadge :tone="item.status === 'completed' ? 'success' : 'default'">{{ item.status }}</StatusBadge><div class="row-actions"><button v-for="action in transitions[item.status] ?? []" :key="action.target" class="secondary-button" @click="transition(item, action.target)">{{ action.label }}<ArrowRight :size="14" /></button></div></div><div v-if="!requests.length && !loading" class="mini-empty">尚无申请，可从账号、权限、采购或额度申请开始。</div></div>
      <div v-else class="risk-list"><article v-for="item in risks" :key="item.id" :class="`risk-${item.severity}`"><span class="record-icon"><AlertTriangle :size="19" /></span><div><strong>{{ item.title }}</strong><span>{{ item.rule_key }} · {{ assetName[item.asset_id ?? ''] ?? '组织级风险' }}</span><small>{{ new Date(item.detected_at).toLocaleString('zh-CN') }}</small></div><StatusBadge :tone="item.status === 'resolved' ? 'success' : 'warning'">{{ item.severity }} / {{ item.status }}</StatusBadge><button v-if="item.status === 'open'" class="secondary-button" @click="resolve(item)">标记已处理</button></article><div v-if="!risks.length" class="mini-empty">暂无风险记录。点击“运行风险扫描”检查当前资产底库。</div></div>
    </section>
    <ModalPanel v-if="modal" title="发起业务申请" description="当前采用固定状态流转，后续可连接企业审批通知。" @close="modal = false"><form class="form-grid one-column" @submit.prevent="saveRequest"><label><span>申请类型</span><select v-model="form.request_type"><option value="account">账号申请</option><option value="permission">权限申请</option><option value="purchase">资产采购</option><option value="saas_seat">SaaS席位</option><option value="api_quota">API额度</option></select></label><label><span>申请标题 *</span><input v-model="form.title" required /></label><label><span>申请人</span><select v-model="form.requester_person_id"><option value="">本地管理员</option><option v-for="item in people" :key="item.id" :value="item.id">{{ item.display_name }}</option></select></label><label><span>关联资产</span><select v-model="form.asset_id"><option value="">无</option><option v-for="item in assets" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><div class="form-actions"><button type="button" class="secondary-button" @click="modal = false">取消</button><button class="primary-button" :disabled="saving">保存草稿</button></div></form></ModalPanel>
  </div>
</template>
