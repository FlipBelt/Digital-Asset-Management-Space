<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Blocks, Database, Palette, Play, Plug, Plus, Shield, Users } from "lucide-vue-next";

import CatalogRulesPanel from "../components/CatalogRulesPanel.vue";
import ModalPanel from "../components/ModalPanel.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type AssetCategory, type AssetType, type AuditLog, type ConnectorDefinition, type LegalEntity, type ProviderConnection } from "../lib/api";

const active = ref("catalog"); const loading = ref(true); const saving = ref(false); const modal = ref<"type" | "connection" | null>(null); const message = ref(""); const error = ref("");
const categories = ref<AssetCategory[]>([]); const types = ref<AssetType[]>([]); const definitions = ref<ConnectorDefinition[]>([]); const connections = ref<ProviderConnection[]>([]); const entities = ref<LegalEntity[]>([]); const logs = ref<AuditLog[]>([]);
const typeForm = reactive({ category_id: "", code: "", name: "", profile_kind: "generic", code_prefix: "AST", ownership_default: "manual" });
const connectionForm = reactive({ connector_definition_id: "", legal_entity_id: "", name: "", status: "disabled", configuration: {} });
const modules = [{ id: "catalog", title: "分类与规则", text: "资产类型、专属字段、关系白名单", icon: Blocks }, { id: "organization", title: "组织与权限", text: "公司、部门、人员和数据范围", icon: Users }, { id: "data", title: "数据与导入", text: "导入批次与数据质量", icon: Database }, { id: "connections", title: "外部集成", text: "连接器和同步状态", icon: Plug }, { id: "appearance", title: "外观与功能", text: "默认主题与模块开关", icon: Palette }, { id: "audit", title: "审计与系统", text: "操作记录与健康状态", icon: Shield }];
const definitionName = computed(() => Object.fromEntries(definitions.value.map((item) => [item.id, item.name])));

async function load() { loading.value = true; try { [categories.value, types.value, definitions.value, connections.value, entities.value, logs.value] = await Promise.all([api.assetCategories(), api.assetTypes(), api.connectorDefinitions(), api.connections(), api.legalEntities(), api.auditLogs()]); typeForm.category_id ||= categories.value[0]?.id ?? ""; connectionForm.connector_definition_id ||= definitions.value[0]?.id ?? ""; connectionForm.legal_entity_id ||= entities.value[0]?.id ?? ""; } finally { loading.value = false; } }
async function save() { saving.value = true; error.value = ""; try { if (modal.value === "type") await api.createAssetType(typeForm); if (modal.value === "connection") await api.createConnection(connectionForm); modal.value = null; await load(); message.value = "配置已保存"; } catch (reason) { error.value = reason instanceof Error ? reason.message : "保存失败"; } finally { saving.value = false; } }
async function testConnection(item: ProviderConnection) { const result = await api.testConnection(item.id); message.value = result.message; }
async function syncConnection(item: ProviderConnection) { await api.syncConnection(item.id); message.value = "同步任务已提交"; await load(); }
onMounted(load);
</script>

<template>
  <div class="page-stack admin-page">
    <PageHeader eyebrow="Admin Console" title="管理员控制台" description="集中维护集团资产的类型、字段模板、关系规则、集成和审计。" />
    <div v-if="message" class="message-panel success-message">{{ message }}</div><div v-if="error" class="message-panel error-message">{{ error }}</div>
    <div class="admin-layout"><aside class="admin-menu"><button v-for="item in modules" :key="item.id" :class="{ active: active === item.id }" @click="active = item.id"><span><component :is="item.icon" :size="19" /></span><div><strong>{{ item.title }}</strong><small>{{ item.text }}</small></div></button></aside>
      <section class="content-panel admin-content">
        <CatalogRulesPanel v-if="active === 'catalog' && !loading" :types="types" />
        <template v-else-if="active === 'organization'"><div class="large-empty-panel"><Users :size="28" /><strong>组织与权限</strong><p>公司、部门和人员在“组织管理”维护；资产详情页负责设置公司级、部门级或待确认归属。</p><RouterLink class="primary-button" to="/organization">进入组织管理</RouterLink></div></template>
        <template v-else-if="active === 'data'"><div class="large-empty-panel"><Database :size="28" /><strong>数据与导入</strong><p>导入批次、字段校验和资产清单统一在资产中心执行。</p><RouterLink class="primary-button" to="/assets">进入资产中心</RouterLink></div></template>
        <template v-else-if="active === 'connections'"><div class="panel-heading"><div><h2>外部集成</h2><p>真实连接须先在外部密码库创建安全引用，本系统不保存 Secret 明文。</p></div><button class="primary-button" @click="modal = 'connection'"><Plus :size="16" />新增连接</button></div><div class="record-list"><div v-for="item in connections" :key="item.id"><span class="record-icon"><Plug :size="18" /></span><div><strong>{{ item.name }}</strong><span>{{ definitionName[item.connector_definition_id] }} · {{ item.last_synced_at ? new Date(item.last_synced_at).toLocaleString('zh-CN') : '尚未同步' }}</span></div><StatusBadge :tone="item.status === 'healthy' ? 'success' : 'default'">{{ item.status }}</StatusBadge><button class="secondary-button" @click="testConnection(item)">测试</button><button class="secondary-button" @click="syncConnection(item)"><Play :size="14" />同步</button></div><div v-if="!connections.length" class="mini-empty">尚未建立公司连接配置</div></div></template>
        <template v-else-if="active === 'appearance'"><div class="panel-heading"><div><h2>外观与功能</h2><p>全系统统一采用 FlipBelt v4 视觉语言，业务数据、路由和接口保持不变。</p></div></div><div class="appearance-fixed-card"><span class="appearance-swatch" /><div><strong>FlipBelt v4 式</strong><p>深色侧栏、浅灰工作区、白色卡片、清晰表格与更舒适的字号间距。</p></div><StatusBadge tone="success">当前启用</StatusBadge></div></template>
        <template v-else-if="active === 'audit'"><div class="panel-heading"><div><h2>审计与系统</h2><p>写操作、导入和系统事件统一留痕。</p></div></div><div class="audit-table"><div v-for="item in logs" :key="item.id"><time>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</time><strong>{{ item.action }}</strong><span>{{ item.object_type }}</span><code>{{ item.object_id || '系统级' }}</code></div><div v-if="!logs.length" class="mini-empty">暂无审计日志</div></div></template>
        <div v-else class="loading-state">正在加载配置…</div>
      </section>
    </div>
    <button v-if="active === 'catalog'" class="floating-action" @click="modal = 'type'"><Plus :size="16" />新增资产类型</button>
    <ModalPanel v-if="modal" :title="modal === 'type' ? '新增资产类型' : '新增外部连接'" @close="modal = null"><form class="form-grid one-column" @submit.prevent="save"><template v-if="modal === 'type'"><label><span>所属分类</span><select v-model="typeForm.category_id" required><option v-for="item in categories" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label><span>类型编码</span><input v-model="typeForm.code" required /></label><label><span>显示名称</span><input v-model="typeForm.name" required /></label><label><span>内部编号前缀</span><input v-model="typeForm.code_prefix" required /></label><label><span>资料模板</span><select v-model="typeForm.profile_kind"><option value="generic">通用</option><option value="internal_system">自研系统</option><option value="service_instance">服务实例</option><option value="infrastructure">基础设施</option></select></label></template><template v-else><label><span>连接器</span><select v-model="connectionForm.connector_definition_id" required><option v-for="item in definitions" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label><span>公司主体</span><select v-model="connectionForm.legal_entity_id" required><option v-for="item in entities" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label><span>连接名称</span><input v-model="connectionForm.name" required /></label></template><div class="form-actions"><button type="button" class="secondary-button" @click="modal = null">取消</button><button class="primary-button" :disabled="saving">保存</button></div></form></ModalPanel>
  </div>
</template>
