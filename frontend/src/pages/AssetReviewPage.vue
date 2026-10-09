<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import PageHeader from "../components/PageHeader.vue";
import { api, type Asset, type HuduAssetDetail, type AssetFieldDefinition, type AssetFieldValue } from "../lib/api";
import AssetAttachments from "../components/AssetAttachments.vue";
import { displayReviewStatus } from "../lib/labels";
import { displayOutcomeVersion } from "../lib/assetVersions";
const route = useRoute();
const items = ref<Asset[]>([]); const total = ref(0); const page = ref(1); const status = ref("pending_review");
const selected = ref<Asset | null>(null); const detail = ref<HuduAssetDetail | null>(null);
const fields = ref<AssetFieldValue[]>([]); const definitions = ref<AssetFieldDefinition[]>([]);
const reason = ref(""); const error = ref(""); const message = ref(""); const loading = ref(false); const busy = ref(false); const selecting = ref(false);
let sequence = 0; let selection = 0;
const names = computed(() => Object.fromEntries(definitions.value.map(f => [f.id, f.label])));
const externalIdentifiers = computed(() => detail.value?.identifiers.filter(item => !item.namespace.startsWith("internal:")) ?? []);
const profileLabels: Record<string,string> = {repository_url:"代码仓库",production_url:"生产访问地址",tech_stack:"技术栈",deployment_guide_url:"部署说明",recovery_guide_url:"恢复说明",backup_description:"备份方式"};
async function load() {
  const request = ++sequence; loading.value = true; error.value = ""; items.value = [];
  selected.value = null; detail.value = null; selection++;
  try { const response = await api.assetReviews(status.value, page.value, typeof route.query.asset === "string" ? route.query.asset : undefined);
    if (request === sequence) { items.value = response.data; total.value = response.pagination.total;
      const target = items.value.find(item => item.id === route.query.asset);
      if (target) await select(target);
    }
  } catch(e) { if(request === sequence) error.value = e instanceof Error ? e.message : "审核队列读取失败"; }
  finally { if(request === sequence) loading.value = false; }
}
async function select(item: Asset) {
  const request = ++selection; selecting.value = true; selected.value = null; detail.value = null; reason.value = ""; error.value = "";
  try { const [asset, facts, values] = await Promise.all([api.asset(item.id), api.huduAsset(item.id), api.assetFieldValues(item.id)]);
    const defs = await api.assetFields(asset.asset_type_id);
    if(request === selection) { selected.value = asset; detail.value = facts; fields.value = values; definitions.value = defs; }
  } catch(e) { if(request === selection) error.value = e instanceof Error ? e.message : "成果读取失败"; }
  finally { if(request === selection) selecting.value = false; }
}
async function submit(decision: "approved" | "rejected") {
  if (!selected.value || busy.value) return;
  if (decision === "rejected" && !reason.value.trim()) { error.value = "退回时请填写原因"; return; }
  busy.value = true; error.value = ""; message.value = "";
  try { await api.reviewAsset(selected.value.id, selected.value.version, decision, reason.value);
    message.value = decision === "approved" ? "该版本已审核通过" : "该版本已退回，原因已记入证据与历史";
    await load();
  } catch(e) { error.value = e instanceof Error ? e.message : "审核失败"; }
  finally { busy.value = false; }
}
watch(status, () => { page.value = 1; void load(); });
watch(() => route.query.asset, () => { page.value = 1; void load(); });
onMounted(load);
</script>
<template>
  <div class="page-stack fusion-space review-page">
    <PageHeader eyebrow="管理区" title="成果审核" description="核对已确认登记的成果、资料和责任配置，再审核当前版本。业务使用验收由实际验收人确认。"><RouterLink to="/manage" class="secondary-button">返回管理区</RouterLink></PageHeader>
    <div class="review-toolbar"><label class="review-filter"><span>审核状态</span><select v-model="status" :disabled="busy"><option value="pending_review">待审核</option><option value="approved">已通过</option><option value="rejected">已退回</option></select></label><RouterLink v-if="route.query.asset" to="/manage/reviews" class="secondary-button">查看全部审核事项</RouterLink></div>
    <div v-if="error" class="message-panel error-message" role="alert">{{ error }} <button class="secondary-button" :disabled="busy" @click="load">刷新并重新核对</button></div>
    <p v-if="message" class="message-panel success-message" role="status">{{ message }}</p>
    <p v-if="loading" role="status">正在读取审核队列…</p>
    <div class="review-workspace">
      <section v-if="!loading" class="content-panel review-queue">
        <h2>{{ displayReviewStatus(status) }} · {{ total }} 项</h2>
        <p v-if="!items.length">当前没有符合条件的成果。草稿需先由创建人预览并确认登记。</p>
        <div class="review-list"><button v-for="item in items" :key="item.id" class="secondary-button" :class="{active:selected?.id === item.id}" :aria-pressed="selected?.id === item.id" :disabled="busy || selecting" @click="select(item)"><span>{{ item.name }}</span><small>{{ displayOutcomeVersion(item) }}</small></button></div>
        <div class="review-actions"><button v-if="page > 1" class="secondary-button" :disabled="busy" @click="page--; load()">上一页</button><button v-if="page * 20 < total" class="secondary-button" :disabled="busy" @click="page++; load()">下一页</button></div>
      </section>
      <p v-if="selecting" role="status">正在读取当前版本…</p>
      <section v-else-if="selected && detail" class="content-panel review-detail">
        <header><h2>{{ selected.name }}</h2><p class="review-version">{{ displayOutcomeVersion(selected) }} · {{ displayReviewStatus(selected.review_status) }}</p><p class="review-description">{{ selected.description || '说明待补充' }}</p></header>
        <dl class="review-facts">
          <dt>资产编号</dt><dd>{{ selected.asset_code }}</dd>
          <dt>开发方式</dt><dd>{{ ({vibe_coding: "AI 辅助编程（Vibe Coding）", mixed: "人工与 AI 混合开发"} as Record<string,string>)[selected.development_method || ""] || "待补充" }}</dd>
          <dt>负责人</dt><dd>{{ detail.responsibilities.filter(r => r.role_type === 'responsible').map(r => r.person_name).join('、') || '待管理员确认' }}</dd>
          <dt>登记人</dt><dd>{{ detail.asset.created_by_person_name || '历史登记人待核对' }}</dd>
          <template v-if="detail.profile"><template v-for="(value,key) in detail.profile.data" :key="key"><template v-if="profileLabels[key]"><dt>{{ profileLabels[key] }}</dt><dd>{{ value || '待补充' }}</dd></template></template></template>
          <template v-for="field in fields" :key="field.id"><dt>{{ names[field.field_definition_id] || '类型资料' }}</dt><dd>{{ field.value.value }}</dd></template>
        </dl>
        <details v-if="externalIdentifiers.length" class="review-identifiers"><summary>平台与历史标识（{{ externalIdentifiers.length }}）</summary><dl class="review-facts"><template v-for="identifier in externalIdentifiers" :key="identifier.id"><dt>{{ identifier.namespace }} · {{ identifier.identifier_type }}</dt><dd>{{ identifier.identifier_value }}</dd></template></dl></details>
        <div class="review-actions"><RouterLink :to="'/assets/' + selected.id + '?tab=responsibility'" class="secondary-button">核对责任配置与完整资料</RouterLink></div>
        <AssetAttachments :key="selected.id" :asset-id="selected.id" />
        <form v-if="selected.review_status === 'pending_review'" class="review-decision" @submit.prevent="submit('approved')">
          <div><h3>审核当前版本</h3><p id="review-reason-help">通过时可选填说明；退回时请写明需要补充的内容。</p></div>
          <label for="review-reason">审核说明（退回必填）</label>
          <textarea id="review-reason" v-model="reason" maxlength="2000" :disabled="busy" rows="5" aria-describedby="review-reason-help" placeholder="例如：请补充使用截图，以及部署和备份说明。" />
          <div class="review-actions"><button class="primary-button" :disabled="busy">{{ busy ? '正在处理…' : '通过当前版本' }}</button><button type="button" class="secondary-button" :disabled="busy" @click="submit('rejected')">退回补充</button></div>
        </form>
      </section>
      <section v-else-if="!loading && items.length" class="content-panel review-placeholder">选择左侧成果，核对当前版本的资料、责任和附件。</section>
    </div>
  </div>
</template>
<style scoped>
.review-toolbar, .review-actions { display:flex; flex-wrap:wrap; align-items:center; gap:12px; }
.review-filter { display:grid; gap:8px; width:220px; max-width:100%; font-size:13px; }
.review-filter select { width:100%; min-height:42px; padding:10px 12px; border:1px solid var(--border); border-radius:var(--radius); background:var(--surface); color:var(--text); }
.review-workspace { display:grid; grid-template-columns:minmax(230px,.65fr) minmax(0,1.35fr); gap:24px; align-items:start; }
.review-queue, .review-detail { min-width:0; }
.review-queue h2, .review-detail h2, .review-decision h3 { margin:0; line-height:1.5; }
.review-list { display:grid; gap:12px; margin-top:16px; max-height:60vh; overflow:auto; }
.review-list button { display:grid; justify-content:start; gap:6px; white-space:normal; text-align:left; overflow-wrap:anywhere; }
.review-list button small { color:var(--muted); font-weight:400; }
.review-page .review-list button { display:flex; flex-direction:column; align-items:flex-start; }
.review-list button.active { border-color:var(--primary); background:var(--surface-soft); }
.review-queue > .review-actions { margin-top:16px; }
.review-detail { display:grid; gap:24px; }
.review-version { margin:8px 0 12px; color:var(--muted); }
.review-description { margin:0; line-height:1.8; overflow-wrap:anywhere; }
.review-facts { display:grid; grid-template-columns:120px minmax(0,1fr); gap:14px 20px; margin:0; }
.review-facts dt { color:var(--muted); }
.review-facts dd { margin:0; overflow-wrap:anywhere; }
.review-identifiers summary { cursor:pointer; color:var(--muted); }
.review-identifiers .review-facts { margin-top:16px; }
.review-decision { display:grid; gap:14px; padding-top:24px; border-top:1px solid var(--border); }
.review-decision p { margin:6px 0 0; color:var(--muted); line-height:1.7; }
.review-decision label { font-weight:600; font-size:13px; }
.review-decision textarea { display:block; box-sizing:border-box; width:100%; min-width:0; min-height:132px; padding:12px; resize:vertical; border:1px solid var(--border); border-radius:var(--radius); color:var(--text); background:var(--surface); font:inherit; line-height:1.6; }
.review-placeholder { color:var(--muted); line-height:1.7; }
@media(max-width:1000px) { .review-workspace { grid-template-columns:1fr; } .review-list { max-height:240px; } }
@media(max-width:600px) { .review-facts { grid-template-columns:1fr; gap:6px; } .review-facts dd { margin-bottom:12px; } .review-actions > * { flex:1 1 auto; justify-content:center; white-space:normal; } }
</style>
