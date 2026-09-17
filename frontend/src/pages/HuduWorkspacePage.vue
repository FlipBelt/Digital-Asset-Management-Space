<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Archive, CalendarClock, ChevronRight, CircleAlert, FolderOpen, Plus, RefreshCw, Search, ShieldCheck, UserRound } from "lucide-vue-next";

import ModalPanel from "../components/ModalPanel.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type AssetCategory, type AssetType, type Department, type HuduAssetItem, type HuduOverview, type LegalEntity } from "../lib/api";

const loading = ref(true);
const saving = ref(false);
const error = ref("");
const modal = ref(false);
const overview = ref<HuduOverview | null>(null);
const result = ref<{ items: HuduAssetItem[]; total: number; categories: { id: string; code: string; name: string; count: number }[]; types: { id: string; code: string; name: string; category_id: string; count: number }[] }>({ items: [], total: 0, categories: [], types: [] });
const categories = ref<AssetCategory[]>([]);
const types = ref<AssetType[]>([]);
const entities = ref<LegalEntity[]>([]);
const departments = ref<Department[]>([]);
const filters = reactive({ keyword: "", category_id: "", status: "", only_due: false });
const form = reactive({ name: "", asset_type_id: "", legal_entity_id: "", owner_department_id: "", status: "active", criticality: "normal", expires_at: "", description: "" });

const visibleTypes = computed(() => types.value.filter((item) => !filters.category_id || item.category_id === filters.category_id));

function date(value: string | null) { return value ? new Date(value).toLocaleDateString("zh-CN") : "未设置"; }
function statusLabel(value: string) { return ({ active: "使用中", draft: "草稿", pending_review: "待确认", archived: "已归档", inactive: "停用" } as Record<string, string>)[value] || value; }
function statusTone(value: string) { return value === "active" ? "success" : value === "archived" ? "neutral" : "warning"; }
function typeName(id: string) { return types.value.find((item) => item.id === id)?.name || "选择资产类型"; }

async function load() {
  loading.value = true; error.value = "";
  try {
    const [summary, assets, categoryRows, typeRows, entityRows, departmentRows] = await Promise.all([
      api.huduOverview(), api.huduAssets(filters), api.assetCategories(), api.assetTypes(), api.legalEntities(), api.departments(),
    ]);
    overview.value = summary; result.value = assets; categories.value = categoryRows; types.value = typeRows; entities.value = entityRows; departments.value = departmentRows;
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "资产库加载失败"; }
  finally { loading.value = false; }
}
function resetForm() { Object.assign(form, { name: "", asset_type_id: visibleTypes.value[0]?.id || types.value[0]?.id || "", legal_entity_id: entities.value[0]?.id || "", owner_department_id: "", status: "active", criticality: "normal", expires_at: "", description: "" }); }
function openCreate() { resetForm(); modal.value = true; }
async function createAsset() {
  saving.value = true; error.value = "";
  try { await api.createAsset({ ...form, owner_department_id: form.owner_department_id || null, legal_entity_id: form.legal_entity_id || null, expires_at: form.expires_at || null }); modal.value = false; await load(); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "保存失败"; }
  finally { saving.value = false; }
}
onMounted(load);
</script>

<template>
  <div class="hudu-page">
    <header class="hudu-page-header">
      <div><span class="hudu-eyebrow">资产库 / 工作区</span><h1>全部资产</h1><p>把平台、账号、系统和资源放在同一张可维护的清单里。</p></div>
      <div class="hudu-actions"><button class="secondary-button" type="button" @click="load"><RefreshCw :size="16" />刷新</button><button class="primary-button" type="button" @click="openCreate"><Plus :size="17" />新增资产</button></div>
    </header>

    <div v-if="error" class="hudu-error"><CircleAlert :size="18" />{{ error }}</div>
    <section class="hudu-stat-grid">
      <article><span>资产总数</span><strong>{{ overview?.total_assets ?? "—" }}</strong><small>当前可见的有效资产</small></article>
      <article><span>使用中</span><strong>{{ overview?.active_assets ?? "—" }}</strong><small>已完成登记并可使用</small></article>
      <article class="warn"><span>30 天内到期</span><strong>{{ overview?.expiring_soon ?? "—" }}</strong><small>进入到期与交接跟进</small></article>
      <article class="soft"><span>待补负责人</span><strong>{{ overview?.missing_owner ?? "—" }}</strong><small>需要补齐责任关系</small></article>
    </section>

    <section class="hudu-toolbar hudu-surface">
      <div class="hudu-search"><Search :size="17" /><input v-model="filters.keyword" placeholder="搜索名称、编号或外部标识" @keyup.enter="load" /></div>
      <select v-model="filters.category_id" @change="load"><option value="">全部资产分类</option><option v-for="item in categories" :key="item.id" :value="item.id">{{ item.name }}</option></select>
      <select v-model="filters.status" @change="load"><option value="">全部状态</option><option value="active">使用中</option><option value="draft">草稿</option><option value="pending_review">待确认</option></select>
      <label class="hudu-check"><input v-model="filters.only_due" type="checkbox" @change="load" />只看待跟进</label>
    </section>

    <section class="hudu-layout">
      <div class="hudu-surface hudu-list-panel">
        <div class="hudu-section-heading"><div><h2>资产清单</h2><span>{{ result.total }} 条记录 · 按最近更新排序</span></div><RouterLink to="/hudu/expirations" class="hudu-link">到期与交接 <ChevronRight :size="15" /></RouterLink></div>
        <div v-if="loading" class="hudu-empty">正在读取资产库…</div>
        <div v-else-if="!result.items.length" class="hudu-empty"><Archive :size="27" /><strong>还没有匹配的资产</strong><span>调整筛选条件，或直接新增一条资产。</span><button class="primary-button" type="button" @click="openCreate"><Plus :size="16" />新增资产</button></div>
        <div v-else class="hudu-asset-list">
          <RouterLink v-for="item in result.items" :key="item.id" :to="`/hudu/assets/${item.id}`" class="hudu-asset-row">
            <div class="hudu-asset-icon"><ShieldCheck :size="19" /></div><div class="hudu-asset-main"><strong>{{ item.name }}</strong><span>{{ item.asset_code }} · {{ item.asset_type_name }} · {{ item.category_name }}</span><small><UserRound :size="13" />{{ item.owner_department_name || "待补负责人" }} <i>·</i> 到期 {{ date(item.expires_at) }}</small></div><StatusBadge :tone="statusTone(item.status)">{{ statusLabel(item.status) }}</StatusBadge><ChevronRight class="hudu-row-arrow" :size="18" />
          </RouterLink>
        </div>
      </div>
      <aside class="hudu-side-column">
        <div class="hudu-surface hudu-side-card"><div class="hudu-section-heading"><div><h2>按分类浏览</h2><span>来自同一资产底库</span></div><FolderOpen :size="18" /></div><button v-for="item in result.categories.slice(0, 8)" :key="item.id" class="hudu-category-row" type="button" @click="filters.category_id = item.id; load()"><span>{{ item.name }}</span><b>{{ item.count }}</b><ChevronRight :size="14" /></button><div v-if="!result.categories.length" class="hudu-muted">暂无分类数据</div></div>
        <div class="hudu-surface hudu-side-card"><div class="hudu-section-heading"><div><h2>最近到期</h2><span>提前 30 天提醒</span></div><CalendarClock :size="18" /></div><RouterLink v-for="item in (overview?.due_items || []).slice(0, 4)" :key="item.id" :to="`/hudu/assets/${item.id}`" class="hudu-due-row"><span class="hudu-due-dot" :class="{ late: item.expires_at && item.expires_at < new Date().toISOString() }" /><div><strong>{{ item.name }}</strong><small>{{ item.expires_at ? date(item.expires_at) : "待补负责人" }}</small></div></RouterLink><div v-if="!overview?.due_items?.length" class="hudu-muted">暂无需要跟进的资产</div><RouterLink to="/hudu/expirations" class="hudu-link hudu-side-link">查看全部 <ChevronRight :size="14" /></RouterLink></div>
      </aside>
    </section>

    <ModalPanel v-if="modal" title="新增资产" description="先填写最少的核心信息，其他卡片可以在详情页补充。" wide @close="modal = false"><form class="form-grid hudu-form-grid" @submit.prevent="createAsset"><label><span>资产名称 *</span><input v-model="form.name" required placeholder="例如：集团官网生产系统" /></label><label><span>资产类型 *</span><select v-model="form.asset_type_id" required><option v-for="item in visibleTypes" :key="item.id" :value="item.id">{{ item.name }} · {{ item.code }}</option></select></label><label><span>所属公司</span><select v-model="form.legal_entity_id"><option value="">待确认</option><option v-for="item in entities" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label><span>负责部门</span><select v-model="form.owner_department_id"><option value="">待补负责人</option><option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label><span>状态</span><select v-model="form.status"><option value="active">使用中</option><option value="draft">草稿</option><option value="pending_review">待确认</option></select></label><label><span>到期日</span><input v-model="form.expires_at" type="date" /></label><label class="wide"><span>说明</span><textarea v-model="form.description" rows="4" placeholder="记录用途、交接提示或资料来源" /></label><div class="form-actions wide"><button class="secondary-button" type="button" @click="modal = false">取消</button><button class="primary-button" type="submit" :disabled="saving">{{ saving ? "保存中…" : `创建 ${typeName(form.asset_type_id)}` }}</button></div></form></ModalPanel>
  </div>
</template>
