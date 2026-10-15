<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ArrowLeft, Bookmark, ArrowRight } from "lucide-vue-next";
import PageHeader from "../components/PageHeader.vue";
import AssetAttachments from "../components/AssetAttachments.vue";
import AssetConfirmationPanel from "../components/AssetConfirmationPanel.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { api, type Asset, type HuduAssetDetail, type Membership } from "../lib/api";
import { displayStatus } from "../lib/labels";
import { assetReturnContext } from "../lib/assetNavigation";
import { aiTypeName, isAIOutcome } from "../lib/aiDiscovery";
const route = useRoute(); const detail = ref<HuduAssetDetail | null>(null); const asset = ref<Asset | null>(null);
const canManage = ref(false);
const subscription = ref<Membership | null>(null); const bookmarked = ref(false); const person = ref("");
const error = ref(""); const loading = ref(false); const actionError = ref(""); const busy = ref(false); let sequence = 0;
const returnContext = computed(() => assetReturnContext(route.query.returnTo));
const isAI = computed(() => Boolean(asset.value && detail.value && isAIOutcome(asset.value, { code: detail.value.asset.asset_type_code || "" })));
const typeLabel = computed(() => isAI.value && detail.value ? aiTypeName({ id: detail.value.asset.asset_type_id, code: detail.value.asset.asset_type_code || "", name: detail.value.asset.asset_type_name }) : detail.value?.asset.asset_type_name);
const owns = computed(() => Boolean(person.value && asset.value?.created_by_person_id === person.value));
const scopeLabels: Record<string, string> = { private: "仅自己", team: "团队共享", company: "公司共享" };
const fundingLabels: Record<string, string> = { personal: "个人自费", company: "公司付费", department: "部门付费", free: "免费", trial: "试用" };
async function load() {
  const request = ++sequence; detail.value = null; loading.value = true; error.value = "";
  try {
    const id = String(route.params.id); const user = await api.currentSession();
    const [value, original, saved, memberships] = await Promise.all([
      api.huduAsset(id), api.asset(id), user.person_id ? api.spaceBookmarks() : Promise.resolve([]),
      user.person_id ? api.spaceMemberships() : Promise.resolve([]),
    ]);
    if (request === sequence) { detail.value = value; asset.value = original; person.value = user.person_id || "";
      canManage.value = user.roles.some(role => ["system_admin", "asset_manager", "department_manager", "group_leader", "auditor"].includes(role));
      bookmarked.value = saved.includes(id); subscription.value = memberships.find(item => item.asset_id === id) || null; }
  } catch (reason) { if (request === sequence) error.value = reason instanceof Error ? reason.message : "读取失败"; }
  finally { if (request === sequence) loading.value = false; }
}
async function toggleBookmark() {
  if (!asset.value) return; busy.value = true; actionError.value = "";
  try { if (bookmarked.value) await api.removeBookmark(asset.value.id); else await api.addBookmark(asset.value.id); bookmarked.value = !bookmarked.value; }
  catch (reason) { actionError.value = reason instanceof Error ? reason.message : "收藏保存失败"; }
  finally { busy.value = false; }
}
watch(() => route.params.id, load, { immediate: true });
</script>
<template>
  <div class="page-stack fusion-space">
    <RouterLink :to="returnContext.to" class="fusion-back"><ArrowLeft :size="16" aria-hidden="true" />返回{{ returnContext.label }}</RouterLink>
    <section v-if="loading" class="fusion-empty" role="status">正在读取资产…</section>
    <section v-else-if="error" class="fusion-empty" role="alert"><p>{{ error }}</p><button class="secondary-button" @click="load">重试</button></section>
    <template v-else-if="detail && asset">
      <PageHeader :eyebrow="typeLabel" :title="asset.name" :description="asset.description || '说明待补充'">
        <button class="secondary-button" :aria-pressed="bookmarked" :disabled="busy || !person" @click="toggleBookmark"><Bookmark :size="17" />{{ bookmarked ? '已收藏' : '收藏资产' }}</button>
        <StatusBadge :tone="asset.status === 'active' ? 'success' : 'warning'">{{ displayStatus(asset.status) }}</StatusBadge>
      </PageHeader>
      <p v-if="actionError" class="form-error" role="alert">{{ actionError }}</p>
      <section v-if="isAI" class="ai-discovery-intro" aria-label="AI 成果复用">
        <div><h2>将成果用到你的工作</h2><p>先查看说明与附件，确认共享范围；使用后记录解决的问题、采用的方法和实际效果。</p></div>
        <RouterLink to="/my/contributions?new=case" class="secondary-button">记录 AI 案例<ArrowRight :size="16" aria-hidden="true" /></RouterLink>
      </section>
      <div class="fusion-detail-layout">
        <section class="content-panel"><h2>使用与责任</h2><dl><dt>所属团队</dt><dd>{{ detail.asset.owner_department_name || '待确认' }}</dd><dt>负责人</dt><dd>{{ detail.responsibilities.filter(r => r.role_type === 'responsible').map(r => r.person_name || r.department_name).join('、') || '待确认' }}</dd><dt>共享范围</dt><dd>{{ scopeLabels[asset.sharing_scope || ''] || '沿用原资产访问策略' }}</dd><dt>审核状态</dt><dd>{{ displayStatus(asset.review_status || 'pending_review') }} · 版本 {{ asset.version }}</dd><dt>来源</dt><dd>{{ asset.source_system || '未补充' }}{{ asset.source_agent ? ' · ' + asset.source_agent : '' }}</dd></dl><p class="fusion-muted">登记状态不代表所有使用场景都已批准，请按负责人确认的范围使用。</p><RouterLink v-if="canManage" :to="`/assets/${asset.id}`" class="secondary-button">维护台账资料</RouterLink><RouterLink v-else-if="owns && asset.status === 'draft'" :to="`/assets/${asset.id}`" class="secondary-button">补充草稿资料</RouterLink></section>
        <section v-if="subscription" class="content-panel"><h2>订阅与探索</h2><dl><dt>套餐</dt><dd>{{ subscription.subscription_name }}</dd><dt>资金来源</dt><dd>{{ fundingLabels[subscription.funding_source || ''] || '待确认' }}</dd><dt>用途</dt><dd>{{ subscription.primary_purpose || '待补充' }}</dd></dl><RouterLink :to="{ path: '/my/contributions', query: { subscription: subscription.id } }" class="fusion-detail">查看关联实践<ArrowRight :size="17" /></RouterLink><RouterLink v-if="subscription.funding_source === 'personal' && subscription.payer_person_id === person" :to="{ path: '/my/contributions', query: { subscription: subscription.id, new: 'exploration' } }" class="secondary-button">记录自费 AI 探索</RouterLink></section>
      </div>
      <AssetConfirmationPanel v-if="owns && asset.status === 'draft'" :asset-id="asset.id" @confirmed="load" />
      <AssetAttachments :key="`${asset.id}-${asset.version}`" :asset-id="asset.id" />
      <section class="content-panel"><h2>关联资产与工作流</h2><p v-if="!detail.relations.length" class="fusion-muted">尚未登记关联关系。</p><div v-else class="fusion-grid"><RouterLink v-for="relation in detail.relations" :key="relation.id" :to="{ path: `/discover/${relation.related_asset_id}`, query: { returnTo: returnContext.to } }" class="fusion-card"><h2>{{ relation.related_name }}</h2><span class="fusion-detail">查看关联详情<ArrowRight :size="17" /></span></RouterLink></div></section>
    </template>
  </div>
</template>
