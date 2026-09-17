<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ArrowLeft, Building2, CheckCircle2, Database, ExternalLink, GitBranch, Layers3, Save, ShieldCheck, Users, X } from "lucide-vue-next";
import { useRoute } from "vue-router";

import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type AssetRelationshipView, type LayerRecord, type LegalEntityIdentifier, type LegalEntityProfile, type Platform, type RelationshipEdge, type RelationshipSection, type RelationshipNode } from "../lib/api";
import { displayStatus } from "../lib/labels";
import { relationshipNodeHref } from "../lib/relationship";

type DirectoryKind = "entity" | "platform" | "grant";

const route = useRoute();
const loading = ref(true);
const error = ref("");
const record = ref<LayerRecord | null>(null);
const relatedRecords = ref<LayerRecord[]>([]);
const entityProfile = ref<LegalEntityProfile | null>(null);
const entityIdentifiers = ref<LegalEntityIdentifier[]>([]);
const platform = ref<Platform | null>(null);
const relationshipGraph = ref<AssetRelationshipView | null>(null);
const editingPlatform = ref(false);
const platformForm = reactive({ name: "", code: "", category: "other", website: "", description: "" });

const kind = computed(() => String(route.params.kind) as DirectoryKind);
const objectId = computed(() => String(route.params.id));
const kindLabel = computed(() => ({ entity: "L1 公司主体", platform: "L3 平台目录", grant: "L5 人员授权" })[kind.value] ?? "目录对象");
const description = computed(() => ({ entity: "公司主体目录对象。先看主体事实和已建立的关联，补充资料按需展开。", platform: "平台目录对象。先看平台事实和已建立的关联，补充资料按需展开。", grant: "人员授权记录。先看授权对象和关联关系，不再误跳到被授权资产。" })[kind.value] ?? "目录对象详情");

function emptyLayerRecord(layer: number, name: string, objectType: string, status: string, id: string): LayerRecord {
  return { id, layer, name, object_type: objectType, legal_entity_name: null, platform_name: null, category: null, ownership_nature: null, account_count: 0, status, asset_id: null, updated_at: new Date().toISOString() };
}

function rowLink(item: LayerRecord) {
  if (item.layer === 1) return `/directory/entity/${item.id.replace("entity:", "")}`;
  if (item.layer === 3) return `/directory/platform/${item.id.replace("platform:", "")}`;
  if (item.layer === 5) return `/directory/grant/${item.id.replace("grant:", "")}`;
  if (item.asset_id) return item.layer === 4 ? `/assets/${item.asset_id}?tab=accounts` : `/assets/${item.asset_id}`;
  return null;
}

const relationSections: RelationshipSection[] = ["structure", "business", "responsibility"];
const relationGroups = computed<Record<RelationshipSection, RelationshipEdge[]>>(() => ({
  structure: relationshipGraph.value?.edges.filter((item) => item.section === "structure") ?? [],
  business: relationshipGraph.value?.edges.filter((item) => item.section === "business") ?? [],
  responsibility: relationshipGraph.value?.edges.filter((item) => item.section === "responsibility") ?? [],
}));
function relationSectionLabel(section: RelationshipSection) {
  return { structure: "关联结构", business: "业务关系", responsibility: "责任与使用" }[section];
}
function relationSectionDescription(section: RelationshipSection) {
  return {
    structure: "企业平台账号和直接平台关联事实",
    business: "通过平台购买或开通的实际服务",
    responsibility: "负责人、使用人员和授权事实",
  }[section];
}
function relationOtherNode(edge: RelationshipEdge) {
  const currentId = relationshipGraph.value?.current_node.id;
  const otherId = edge.source === currentId ? edge.target : edge.source;
  return relationshipGraph.value?.nodes.find((item) => item.id === otherId);
}
function relationDirectionLabel(direction: RelationshipEdge["direction"]) {
  return { upstream: "来源", downstream: "下游", peer: "同级", responsibility: "责任 / 使用" }[direction];
}
function startPlatformEdit() {
  if (!platform.value) return;
  Object.assign(platformForm, {
    name: platform.value.name,
    code: platform.value.code,
    category: platform.value.category,
    website: platform.value.website ?? "",
    description: platform.value.description ?? "",
  });
  editingPlatform.value = true;
}
function cancelPlatformEdit() { editingPlatform.value = false; }
async function savePlatformEdit() {
  if (!platform.value) return;
  try {
    platform.value = await api.updatePlatform(platform.value.id, { ...platformForm });
    record.value = record.value ? { ...record.value, name: platform.value.name, status: platform.value.review_status, updated_at: new Date().toISOString(), category: platform.value.category } : record.value;
    relationshipGraph.value = await api.platformRelationshipView(platform.value.id);
    editingPlatform.value = false;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "平台资料保存失败";
  }
}

async function load() {
  loading.value = true;
  error.value = "";
  record.value = null;
  relatedRecords.value = [];
  relationshipGraph.value = null;
  entityProfile.value = null;
  entityIdentifiers.value = [];
  platform.value = null;
  try {
    if (kind.value === "entity") {
      const entities = await api.legalEntities();
      const entity = entities.find((item) => item.id === objectId.value);
      if (!entity) throw new Error("公司主体不存在或已不可见");
      record.value = emptyLayerRecord(1, entity.name, "公司主体", entity.status, `entity:${entity.id}`);
      const [profile, identifiers, identities, tenants, grants] = await Promise.all([
        api.legalEntityProfile(entity.id),
        api.legalEntityIdentifiers(entity.id),
        api.layerRecords(2),
        api.layerRecords(4),
        api.layerRecords(5),
      ]);
      entityProfile.value = profile;
      entityIdentifiers.value = identifiers;
      relatedRecords.value = [...identities, ...tenants, ...grants].filter((item) => item.legal_entity_name === entity.name);
    } else if (kind.value === "platform") {
      const platforms = await api.platforms();
      const item = platforms.find((row) => row.id === objectId.value);
      if (!item) throw new Error("平台目录对象不存在或已不可见");
      platform.value = item;
      Object.assign(platformForm, { name: item.name, code: item.code, category: item.category, website: item.website ?? "", description: item.description ?? "" });
      record.value = { ...emptyLayerRecord(3, item.name, "平台", item.review_status, `platform:${item.id}`), category: item.category, updated_at: new Date().toISOString() };
      const [identities, tenants, platformRelations] = await Promise.all([api.layerRecords(2), api.layerRecords(4), api.platformRelationshipView(item.id)]);
      relationshipGraph.value = platformRelations;
      relatedRecords.value = [...identities, ...tenants].filter((row) => row.platform_name?.split("、").includes(item.name));
    } else {
      const grants = await api.layerRecords(5);
      const item = grants.find((row) => row.id === `grant:${objectId.value}`);
      if (!item) throw new Error("人员授权记录不存在或已不可见");
      record.value = item;
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "详情加载失败";
  } finally {
    loading.value = false;
  }
}

const profileFields = computed(() => {
  const profile = entityProfile.value;
  if (!profile) return [] as [string, string][];
  return [["主体类型", profile.entity_type], ["注册地 / 司法辖区", profile.jurisdiction], ["存续状态", profile.registration_status], ["法定代表人", profile.legal_representative], ["成立日期", profile.established_on], ["注册地址", profile.registered_address], ["注册资本", profile.registered_capital], ["经营范围", profile.business_scope]].filter(([, value]) => value) as [string, string][];
});

const upstreamRecords = computed(() => [] as LayerRecord[]);
const downstreamRecords = computed(() => relatedRecords.value);
const grantPerson = computed(() => record.value?.name.split(" → ")[0] ?? "待确认人员");
const relationDescription = computed(() => kind.value === "grant" ? "授权本身是人与对象之间的关系；当前先展示授权对象，授权类型和期限下一轮按 L5 字段补齐。" : "已建立的关系优先展示；没有关系时不生成补位对象。" );

function categoryLabel(value: string | null | undefined) {
  return ({ cloud: "云平台", ai: "大模型 / AI", saas: "SaaS / 协作", marketing: "营销 / 电商", payment: "支付", other: "其他" } as Record<string, string>)[value ?? ""] ?? value ?? "未分类";
}

onMounted(load);
watch(() => route.fullPath, load);
</script>

<template>
  <div class="page-stack directory-detail-page">
    <PageHeader eyebrow="对象详情" :title="record?.name ?? kindLabel" :description="description">
      <RouterLink class="secondary-button" to="/assets"><ArrowLeft :size="16" />返回资产底库</RouterLink>
    </PageHeader>

    <div v-if="error" class="message-panel error-message">{{ error }}</div>
    <div v-if="loading" class="loading-state">正在读取对象详情…</div>

    <template v-if="record && !loading">
      <section class="directory-summary detail-surface">
        <div class="directory-summary-icon"><Building2 v-if="kind === 'entity'" :size="28" /><Layers3 v-else-if="kind === 'platform'" :size="28" /><Users v-else :size="28" /></div>
        <div><span class="section-kicker">{{ kindLabel }}</span><h2>{{ record.name }}</h2><p>先看核心事实、关联关系和责任位置；没有数据的字段不强行补齐。</p></div>
        <button v-if="kind === 'platform' && !editingPlatform" class="secondary-button" @click="startPlatformEdit">编辑平台</button>
        <StatusBadge tone="success">{{ displayStatus(record.status) }}</StatusBadge>
      </section>

      <section class="detail-surface directory-info-surface">
        <header><div><span class="section-kicker">核心信息</span><h2>当前对象的最小事实</h2><p>本轮不把不同层级的字段混在一起。</p></div><CheckCircle2 :size="26" /></header>
        <form v-if="kind === 'platform' && editingPlatform" class="directory-edit-form" @submit.prevent="savePlatformEdit">
          <label><span>平台名称</span><input v-model="platformForm.name" required /></label>
          <label><span>平台编码</span><input v-model="platformForm.code" required /></label>
          <label><span>平台类别</span><select v-model="platformForm.category"><option value="cloud">云平台</option><option value="ai">大模型 / AI</option><option value="saas">SaaS / 协作</option><option value="marketing">营销 / 电商</option><option value="payment">支付</option><option value="other">其他</option></select></label>
          <label><span>官网</span><input v-model="platformForm.website" placeholder="https://" /></label>
          <label class="wide"><span>平台说明</span><textarea v-model="platformForm.description" rows="3" /></label>
          <div class="directory-edit-actions"><button class="primary-button" type="submit"><Save :size="16" />保存平台</button><button class="secondary-button" type="button" @click="cancelPlatformEdit"><X :size="16" />取消</button></div>
        </form>
        <div class="directory-field-grid">
          <div><span>对象层级</span><strong>L{{ record.layer }} · {{ record.object_type }}</strong></div>
          <div><span>状态</span><strong>{{ displayStatus(record.status) }}</strong></div>
          <div><span>最后更新</span><strong>{{ new Date(record.updated_at).toLocaleString('zh-CN') }}</strong></div>
          <div v-if="record.legal_entity_name"><span>归属公司</span><strong>{{ record.legal_entity_name }}</strong></div>
          <div v-if="record.platform_name"><span>关联平台</span><strong>{{ record.platform_name }}</strong></div>
          <div v-if="kind === 'platform'"><span>平台类别</span><strong>{{ categoryLabel(record.category) }}</strong></div>
          <div v-if="kind === 'platform' && platform?.code"><span>平台编码</span><strong>{{ platform.code }}</strong></div>
          <div v-if="kind === 'grant'"><span>授权人员</span><strong>{{ grantPerson }}</strong></div>
          <div v-if="kind === 'grant' && record.asset_id"><span>被授权资产</span><RouterLink :to="`/assets/${record.asset_id}`"><strong>查看目标资产</strong><ExternalLink :size="15" /></RouterLink></div>
        </div>
      </section>

      <section class="detail-surface directory-relation-surface">
        <header><div><span class="section-kicker">关联关系</span><h2>按真实数据模型展示关系</h2><p>{{ kind === 'platform' ? '平台本身是目录对象，下面的关系来自企业平台账号、直接平台关联和实际购买记录。' : relationDescription }}</p></div><GitBranch :size="26" /></header>
        <div v-if="relationshipGraph" class="directory-relation-sections">
          <section v-for="section in relationSections" :key="section" class="directory-relation-section">
            <header><div><h3>{{ relationSectionLabel(section) }}</h3><p>{{ relationSectionDescription(section) }}</p></div></header>
            <div v-if="relationGroups[section].length" class="directory-relation-list">
              <RouterLink v-for="item in relationGroups[section]" :key="item.id" :to="relationshipNodeHref(relationOtherNode(item) as RelationshipNode | undefined)">
                <strong>{{ relationOtherNode(item)?.label ?? '关联对象' }}</strong>
                <small>{{ item.label }} · {{ relationDirectionLabel(item.direction) }} · 来源 {{ item.source_model }}</small>
              </RouterLink>
            </div>
            <div v-else class="directory-relation-empty"><Database :size="17" />暂无{{ relationSectionLabel(section) }}</div>
          </section>
        </div>
        <div v-else class="directory-relation-empty"><Database :size="17" />暂无关联数据</div>
      </section>

      <section class="detail-surface directory-responsibility-surface">
        <header><div><span class="section-kicker">责任与使用</span><h2>保留责任位置，但不阻塞建档</h2><p>当前目录对象暂以已有事实展示；负责人和使用人员可以后续补充。</p></div><ShieldCheck :size="26" /></header>
        <div class="directory-field-grid"><div><span>归属</span><strong>{{ record.legal_entity_name ?? (kind === 'entity' ? '主体自身' : '待确认') }}</strong></div><div><span>{{ kind === 'grant' ? '授权人员' : '负责人' }}</span><strong>{{ kind === 'grant' ? grantPerson : '待配置' }}</strong></div><div><span>使用关系</span><strong>{{ kind === 'grant' ? '已形成授权关系' : relatedRecords.length ? `已关联 ${relatedRecords.length} 个对象` : '暂未关联' }}</strong></div></div>
      </section>

      <details class="detail-surface directory-more"><summary><span><ShieldCheck :size="19" /><b>补充资料与历史</b><small>有资料再展开，没有也不影响使用</small></span><strong>展开查看</strong></summary>
        <div class="directory-more-content">
          <template v-if="kind === 'entity'"><div v-if="profileFields.length" class="directory-field-grid"><div v-for="item in profileFields" :key="item[0]"><span>{{ item[0] }}</span><strong>{{ item[1] }}</strong></div></div><div v-else class="directory-relation-empty">暂未补充主体档案。</div><div v-if="entityIdentifiers.length" class="directory-identifiers"><span>主体标识</span><div v-for="item in entityIdentifiers" :key="item.id"><strong>{{ item.identifier_value }}</strong><small>{{ item.identifier_type }} · {{ displayStatus(item.verification_status) }}</small></div></div></template>
          <template v-else-if="kind === 'platform'"><div class="directory-field-grid"><div><span>平台编码</span><strong>{{ platform?.code ?? '未填写' }}</strong></div><div><span>官网</span><a v-if="platform?.website" :href="platform.website" target="_blank">打开官网 <ExternalLink :size="15" /></a><strong v-else>未填写</strong></div></div><p>{{ platform?.description || '暂未填写平台说明。' }}</p></template>
          <template v-else><div class="directory-relation-empty">授权类型、权限角色、有效期和备注将在下一轮按 L5 专属字段补齐；当前先保留授权对象和目标资产。</div></template>
        </div>
      </details>
    </template>
  </div>
</template>

<style scoped>
.directory-summary { display: flex; align-items: center; gap: 20px; padding: 28px; }
.directory-summary > .secondary-button { margin-left: auto; flex: 0 0 auto; }
.directory-summary-icon { display: grid; place-items: center; width: 58px; height: 58px; border-radius: 16px; background: #e8f1ff; color: #1769d2; flex: 0 0 auto; }
.directory-summary > div:nth-child(2) { flex: 1; }
.directory-summary h2 { margin: 5px 0; }
.directory-summary p, .directory-info-surface p, .directory-relation-surface p, .directory-responsibility-surface p { margin: 0; color: #697a96; }
.directory-info-surface, .directory-relation-surface, .directory-responsibility-surface { padding: 28px; }
.directory-info-surface > header, .directory-relation-surface > header, .directory-responsibility-surface > header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 22px; }
.directory-info-surface h2, .directory-relation-surface h2, .directory-responsibility-surface h2 { margin: 5px 0; }
.directory-field-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.directory-field-grid > div { border: 1px solid #dbe4f1; border-radius: 12px; padding: 15px; min-height: 66px; }
.directory-field-grid span, .directory-identifiers > span { display: block; color: #72829d; font-size: 13px; margin-bottom: 7px; }
.directory-field-grid strong { color: #1a2942; }
.directory-field-grid a { color: #1769d2; display: inline-flex; align-items: center; gap: 6px; }
.directory-edit-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-bottom: 22px; }
.directory-edit-form label { display: grid; gap: 7px; color: #72829d; font-size: 13px; }
.directory-edit-form input, .directory-edit-form select, .directory-edit-form textarea { width: 100%; box-sizing: border-box; border: 1px solid #d3deed; border-radius: 9px; padding: 10px 12px; color: #1a2942; background: #fff; font: inherit; }
.directory-edit-form .wide { grid-column: 1 / -1; }
.directory-edit-actions { display: flex; align-items: center; gap: 10px; grid-column: 1 / -1; }
.directory-relation-sections { display: grid; gap: 14px; }
.directory-relation-section { border: 1px solid #dbe4f1; border-radius: 12px; padding: 18px; }
.directory-relation-section > header { margin-bottom: 14px; }
.directory-relation-section h3 { margin: 0 0 5px; }
.directory-relation-section p { margin: 0; color: #72829d; font-size: 13px; }
.directory-relation-empty { display: flex; align-items: center; gap: 7px; }
.directory-relation-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.directory-relation-grid > div { border: 1px solid #dbe4f1; border-radius: 12px; padding: 18px; }
.directory-relation-grid h3 { margin: 0 0 14px; }
.directory-relation-list { display: grid; gap: 9px; }
.directory-relation-list a { display: flex; flex-direction: column; gap: 4px; padding: 11px 12px; border-radius: 10px; background: #f6f9fd; color: #1a2942; }
.directory-relation-list small, .directory-identifiers small { color: #72829d; }
.directory-relation-empty { color: #72829d; padding: 12px 0; }
.directory-more { padding: 0 28px; }
.directory-more summary { display: flex; justify-content: space-between; align-items: center; cursor: pointer; padding: 22px 0; list-style: none; }
.directory-more summary > span { display: flex; align-items: center; gap: 10px; }
.directory-more summary small { color: #72829d; margin-left: 4px; }
.directory-more summary > strong { color: #1769d2; font-size: 13px; }
.directory-more-content { border-top: 1px solid #e5ebf4; padding: 22px 0 28px; }
.directory-identifiers { border-top: 1px solid #e5ebf4; margin-top: 20px; padding-top: 18px; }
.directory-identifiers > div { display: inline-flex; flex-direction: column; margin: 0 20px 0 0; }
@media (max-width: 760px) { .directory-summary { align-items: flex-start; flex-wrap: wrap; } .directory-summary > .secondary-button { margin-left: 0; } .directory-field-grid, .directory-relation-grid, .directory-edit-form { grid-template-columns: 1fr; } .directory-edit-form .wide, .directory-edit-actions { grid-column: auto; } .directory-more { padding: 0 18px; } }
</style>
