<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ArrowLeft, CalendarClock, Edit3, ExternalLink, FileText, GitBranch, History, Link2, RefreshCw, ShieldCheck, UserRound } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";

import ModalPanel from "../components/ModalPanel.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type Department, type HuduAssetDetail, type LegalEntity } from "../lib/api";

const route = useRoute();
const router = useRouter();
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const editOpen = ref(false);
const detail = ref<HuduAssetDetail | null>(null);
const entities = ref<LegalEntity[]>([]);
const departments = ref<Department[]>([]);
const form = reactive({ name: "", owner_department_id: "", status: "active", criticality: "normal", expires_at: "", description: "" });

function date(value: string | null) { return value ? new Date(value).toLocaleDateString("zh-CN") : "未设置"; }
function statusLabel(value: string) { return ({ active: "使用中", draft: "草稿", pending_review: "待确认", archived: "已归档", inactive: "停用" } as Record<string, string>)[value] || value; }
function statusTone(value: string) { return value === "active" ? "success" : value === "archived" ? "neutral" : "warning"; }
async function load() {
  loading.value = true; error.value = "";
  try { const [row, departmentRows, entityRows] = await Promise.all([api.huduAsset(String(route.params.id)), api.departments(), api.legalEntities()]); detail.value = row; departments.value = departmentRows; entities.value = entityRows; }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "资产详情加载失败"; }
  finally { loading.value = false; }
}
function openEdit() { if (!detail.value) return; const asset = detail.value.asset; Object.assign(form, { name: asset.name, owner_department_id: asset.owner_department_id || "", status: asset.status, criticality: asset.criticality, expires_at: asset.expires_at?.slice(0, 10) || "", description: asset.description || "" }); editOpen.value = true; }
async function save() {
  if (!detail.value) return; saving.value = true; error.value = "";
  try { await api.updateAsset(detail.value.asset.id, { version: detail.value.asset.version, ...form, owner_department_id: form.owner_department_id || null, expires_at: form.expires_at || null }); editOpen.value = false; await load(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "保存失败"; }
  finally { saving.value = false; }
}
onMounted(load);
</script>

<template>
  <div class="hudu-page">
    <div class="hudu-breadcrumb"><button class="hudu-back" type="button" @click="router.push('/hudu')"><ArrowLeft :size="16" />资产库</button><span>/</span><span>{{ detail?.asset.category_name || "资产详情" }}</span></div>
    <div v-if="error" class="hudu-error">{{ error }} <button type="button" @click="load">重试</button></div>
    <div v-if="loading" class="hudu-surface hudu-empty">正在读取资产详情…</div>
    <template v-else-if="detail">
      <header class="hudu-detail-hero hudu-surface"><div class="hudu-detail-title"><div class="hudu-hero-icon"><ShieldCheck :size="25" /></div><div><span class="hudu-eyebrow">{{ detail.asset.category_name }} · {{ detail.asset.asset_type_name }}</span><h1>{{ detail.asset.name }}</h1><p>{{ detail.asset.asset_code }} · {{ detail.asset.description || "尚未填写说明" }}</p></div></div><div class="hudu-actions"><StatusBadge :tone="statusTone(detail.asset.status)">{{ statusLabel(detail.asset.status) }}</StatusBadge><button class="secondary-button" type="button" @click="load"><RefreshCw :size="15" />刷新</button><button class="primary-button" type="button" @click="openEdit"><Edit3 :size="15" />编辑资产</button></div></header>
      <section class="hudu-detail-grid">
        <main class="hudu-detail-main">
          <section class="hudu-surface hudu-card"><div class="hudu-section-heading"><div><h2>核心信息</h2><span>统一资产卡片的第一层</span></div><FileText :size="18" /></div><div class="hudu-fact-grid"><div><span>资产分类</span><strong>{{ detail.asset.category_name }}</strong><small>{{ detail.asset.asset_type_name }}</small></div><div><span>所属公司</span><strong>{{ detail.asset.legal_entity_name || "待确认" }}</strong><small>{{ detail.asset.ownership_scope || "归属待确认" }}</small></div><div><span>负责部门</span><strong>{{ detail.asset.owner_department_name || "待补负责人" }}</strong><small><UserRound :size="13" />{{ detail.responsibilities.find((item) => item.role_type === "responsible")?.person_name || "尚未指定个人负责人" }}</small></div><div><span>重要级别</span><strong>{{ detail.asset.criticality }}</strong><small>保密级别：{{ detail.asset.confidentiality }}</small></div><div><span>开始使用</span><strong>{{ date(detail.asset.started_at) }}</strong><small>最近核验：{{ date(detail.asset.last_verified_at) }}</small></div><div class="due-fact"><span>到期时间</span><strong>{{ date(detail.asset.expires_at) }}</strong><small><CalendarClock :size="13" />到期前 30 天提醒</small></div></div></section>
          <section v-if="detail.profile" class="hudu-surface hudu-card"><div class="hudu-section-heading"><div><h2>专用信息卡</h2><span>{{ detail.profile.kind === "internal_system" ? "自研系统" : detail.profile.kind === "infrastructure" ? "基础设施" : "资源" }}字段</span></div><Link2 :size="18" /></div><div class="hudu-profile-grid"><div v-for="(value, key) in detail.profile.data" :key="key"><span>{{ key }}</span><strong>{{ value || "未填写" }}</strong></div></div></section>
          <section v-if="detail.account_context" class="hudu-surface hudu-card"><div class="hudu-section-heading"><div><h2>账号上下文</h2><span>密码和 Secret 仍只保留在外部密码库</span></div><ShieldCheck :size="18" /></div><div class="hudu-profile-grid"><div><span>平台</span><strong>{{ detail.account_context.platform_name || "未关联平台" }}</strong></div><div><span>登录标识</span><strong>{{ detail.account_context.login_identifier }}</strong></div><div><span>企业租户</span><strong>{{ detail.account_context.tenant_identifier || "未填写" }}</strong></div><div><span>MFA / 权限</span><strong>{{ detail.account_context.mfa_status }} · {{ detail.account_context.privilege_level }}</strong></div></div></section>
          <section class="hudu-surface hudu-card"><div class="hudu-section-heading"><div><h2>关联对象</h2><span>只展示与当前资产直接相关的上下游对象</span></div><GitBranch :size="18" /></div><div v-if="!detail.relations.length" class="hudu-muted">暂未建立资产关系。后续可从现有资产关系接口添加。</div><RouterLink v-for="relation in detail.relations" :key="relation.id" :to="`/hudu/assets/${relation.related_asset_id}`" class="hudu-related-row"><div class="hudu-related-icon"><GitBranch :size="16" /></div><div><strong>{{ relation.related_name }}</strong><span>{{ relation.direction === "outbound" ? "当前资产 → " : "当前资产 ← " }}{{ relation.relation_type }} · {{ relation.related_type_name }}</span></div><ExternalLink :size="15" /></RouterLink></section>
        </main>
        <aside class="hudu-detail-side">
          <section class="hudu-surface hudu-card"><div class="hudu-section-heading"><div><h2>责任与交接</h2><span>谁负责、谁使用</span></div><UserRound :size="18" /></div><div v-if="!detail.responsibilities.length" class="hudu-muted">还没有责任记录</div><div v-for="item in detail.responsibilities" :key="item.id" class="hudu-responsibility-row"><span class="hudu-avatar"><UserRound :size="15" /></span><div><strong>{{ item.person_name || item.department_name || "未识别" }}</strong><small>{{ item.role_type }}{{ item.is_primary ? " · 主要" : "" }}</small></div></div></section>
          <section class="hudu-surface hudu-card"><div class="hudu-section-heading"><div><h2>外部标识</h2><span>平台、域名或资源编号</span></div><Link2 :size="18" /></div><div v-if="!detail.identifiers.length" class="hudu-muted">暂无外部标识</div><div v-for="item in detail.identifiers" :key="item.id" class="hudu-identifier-row"><span>{{ item.identifier_type }}</span><strong>{{ item.identifier_value }}</strong></div></section>
          <section class="hudu-surface hudu-card"><div class="hudu-section-heading"><div><h2>最近变更</h2><span>保留审计轨迹</span></div><History :size="18" /></div><div v-if="!detail.history.length" class="hudu-muted">暂无变更记录</div><div v-for="item in detail.history.slice(0, 5)" :key="item.id" class="hudu-history-row"><span>{{ item.action }}</span><small>{{ item.created_at ? new Date(item.created_at).toLocaleString("zh-CN") : "" }}</small></div></section>
        </aside>
      </section>
    </template>
    <ModalPanel v-if="editOpen" title="编辑资产" description="编辑会直接写入现有资产底库，并保留版本和审计记录。" wide @close="editOpen = false"><form class="form-grid hudu-form-grid" @submit.prevent="save"><label><span>资产名称 *</span><input v-model="form.name" required /></label><label><span>状态</span><select v-model="form.status"><option value="active">使用中</option><option value="draft">草稿</option><option value="pending_review">待确认</option><option value="inactive">停用</option></select></label><label><span>负责部门</span><select v-model="form.owner_department_id"><option value="">待补负责人</option><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label><span>到期日</span><input v-model="form.expires_at" type="date" /></label><label><span>重要级别</span><select v-model="form.criticality"><option value="normal">普通</option><option value="important">重要</option><option value="critical">关键</option></select></label><label class="wide"><span>说明</span><textarea v-model="form.description" rows="4" /></label><div class="form-actions wide"><button class="secondary-button" type="button" @click="editOpen = false">取消</button><button class="primary-button" type="submit" :disabled="saving">{{ saving ? "保存中…" : "保存修改" }}</button></div></form></ModalPanel>
  </div>
</template>
