<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import PageHeader from "../components/PageHeader.vue";
import { api, type Asset, type HuduAssetDetail, type AssetFieldDefinition, type AssetFieldValue } from "../lib/api";
import AssetAttachments from "../components/AssetAttachments.vue";
import { displayReviewStatus } from "../lib/labels";
const route = useRoute();
const items = ref<Asset[]>([]); const total = ref(0); const page = ref(1); const status = ref("pending_review");
const selected = ref<Asset | null>(null); const detail = ref<HuduAssetDetail | null>(null);
const fields = ref<AssetFieldValue[]>([]); const definitions = ref<AssetFieldDefinition[]>([]);
const reason = ref(""); const error = ref(""); const message = ref(""); const loading = ref(false); const busy = ref(false); const selecting = ref(false);
let sequence = 0; let selection = 0;
const names = computed(() => Object.fromEntries(definitions.value.map(f => [f.id, f.label])));
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
  <div class="page-stack fusion-space">
    <PageHeader eyebrow="管理区" title="成果审核" description="核对已确认登记的成果、资料和责任配置，再审核当前版本。业务使用验收由实际验收人确认。"><RouterLink to="/manage" class="secondary-button">返回管理区</RouterLink></PageHeader>
    <RouterLink v-if="route.query.asset" to="/manage/reviews" class="secondary-button">查看全部审核事项</RouterLink>
    <label>审核状态<select v-model="status" :disabled="busy"><option value="pending_review">待审核</option><option value="approved">已通过</option><option value="rejected">已退回</option></select></label>
    <p v-if="error" role="alert">{{ error }} <button class="secondary-button" :disabled="busy" @click="load">刷新并重新核对</button></p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="loading" role="status">正在读取审核队列…</p>
    <div class="review-workspace">
    <section v-if="!loading" class="content-panel"><h2>{{ displayReviewStatus(status) }} · {{ total }} 项</h2><p v-if="!items.length">当前没有符合条件的成果。草稿需先由创建人预览并确认登记。</p><div class="review-list"><button v-for="item in items" :key="item.id" class="secondary-button" :disabled="busy || selecting" @click="select(item)">{{ item.name }} · 版本 {{ item.version }}</button></div><div class="fusion-button-row"><button v-if="page > 1" class="secondary-button" :disabled="busy" @click="page--; load()">上一页</button><button v-if="page * 20 < total" class="secondary-button" :disabled="busy" @click="page++; load()">下一页</button></div></section>
    <p v-if="selecting" role="status">正在读取当前版本…</p>
    <section v-if="selected && detail" class="content-panel">
      <h2>{{ selected.name }} · 版本 {{ selected.version }}</h2><p>{{ selected.description || '说明待补充' }}</p>
      <dl><dt>开发方式</dt><dd>{{ ({vibe_coding: "AI 辅助编程（Vibe Coding）", mixed: "人工与 AI 混合开发"} as Record<string,string>)[selected.development_method || ""] || "待补充" }}</dd><dt>审核状态</dt><dd>{{ displayReviewStatus(selected.review_status) }}</dd><dt>负责人</dt><dd>{{ detail.responsibilities.filter(r => r.role_type === 'responsible').map(r => r.person_name).join('、') || '待管理员确认' }}</dd>
      <template v-if="detail.profile"><template v-for="(value,key) in detail.profile.data" :key="key"><template v-if="profileLabels[key]"><dt>{{ profileLabels[key] }}</dt><dd>{{ value || '待补充' }}</dd></template></template></template>
      <template v-for="field in fields" :key="field.id"><dt>{{ names[field.field_definition_id] || '类型资料' }}</dt><dd>{{ field.value.value }}</dd></template></dl>
      <p v-for="identifier in detail.identifiers" :key="identifier.id">{{ identifier.namespace }} · {{ identifier.identifier_type }} · {{ identifier.identifier_value }}</p>
      <RouterLink :to="'/assets/' + selected.id + '?tab=responsibility'" class="secondary-button">核对责任配置与完整资料</RouterLink>
      <AssetAttachments :key="selected.id" :asset-id="selected.id" />
      <form v-if="selected.review_status === 'pending_review'" @submit.prevent="submit('approved')"><label>审核说明（退回必填）<textarea v-model="reason" maxlength="2000" :disabled="busy" rows="3" /></label><div class="fusion-button-row"><button class="primary-button" :disabled="busy">{{ busy ? '正在处理…' : '通过当前版本' }}</button><button type="button" class="secondary-button" :disabled="busy" @click="submit('rejected')">退回补充</button></div></form>
    </section>
    </div>
  </div>
</template>
<style scoped>
.review-workspace {display:grid;grid-template-columns:minmax(220px,.75fr) minmax(0,1.25fr);gap:20px;align-items:start}
.review-list {display:grid; gap:12px; margin-bottom:16px;max-height:60vh;overflow:auto}
@media(max-width:900px){.review-workspace{grid-template-columns:1fr}.review-list{max-height:240px}}
.review-list button {white-space:normal; text-align:left}
dd {overflow-wrap:anywhere}
</style>
