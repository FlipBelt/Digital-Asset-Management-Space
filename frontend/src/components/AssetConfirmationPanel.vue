<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { api, type Asset, type AssetConfirmation } from "../lib/api";
const props = defineProps<{ assetId: string }>(); const emit = defineEmits<{ confirmed: [] }>();
const asset = ref<Asset | null>(null); const person = ref(""); const receipt = ref<AssetConfirmation | null>(null);
const scope = ref("private"); const acknowledged = ref(false); const busy = ref(false); const error = ref(""); let sequence = 0;
const ownsDraft = computed(() => asset.value?.status === "draft" && asset.value.created_by_person_id === person.value);
const scopeLabels: Record<string, string> = { private: "仅自己", team: "团队共享", company: "公司共享" };
async function load() {
  const request = ++sequence; error.value = ""; receipt.value = null; acknowledged.value = false; asset.value = null;
  try { const [value, user] = await Promise.all([api.asset(props.assetId), api.currentSession()]); if (request === sequence) { asset.value = value; person.value = user.person_id || ""; } }
  catch (reason) { if (request === sequence) error.value = reason instanceof Error ? reason.message : "草稿读取失败"; }
}
async function prepare() {
  busy.value = true; error.value = ""; acknowledged.value = false;
  try {
    asset.value = await api.asset(props.assetId);
    receipt.value = await api.prepareAssetConfirmation(props.assetId, { request_id: crypto.randomUUID(), version: asset.value.version, sharing_scope: scope.value });
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "预览失败"; receipt.value = null; }
  finally { busy.value = false; }
}
async function confirm() {
  if (!receipt.value || !acknowledged.value) return;
  busy.value = true; error.value = "";
  try {
    asset.value = await api.confirmAssetDraft(props.assetId, { confirmation_id: receipt.value.id, version: receipt.value.asset_version,
      content_digest: receipt.value.content_digest, confirmed: true });
    receipt.value = null; emit("confirmed");
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "确认失败"; }
  finally { busy.value = false; }
}
async function cancel() {
  if (!receipt.value) return;
  busy.value = true; error.value = "";
  try { await api.cancelAssetConfirmation(props.assetId, receipt.value.id); receipt.value = null; acknowledged.value = false; }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "取消失败"; }
  finally { busy.value = false; }
}
watch(() => props.assetId, load, { immediate: true });
</script>
<template>
  <section v-if="ownsDraft || error" class="content-panel fusion-confirmation">
    <h2>预览并确认登记</h2>
    <p>确认将保存这份草稿的具体版本。登记完成后，价值、归属和使用批准仍待人工核对。</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <template v-if="ownsDraft && !receipt"><label>共享范围<select v-model="scope" :disabled="busy"><option value="private">仅自己</option><option value="team">团队共享</option><option value="company">公司共享</option></select></label><button class="primary-button" :disabled="busy" @click="prepare">{{ busy ? '正在准备…' : '预览此版本' }}</button></template>
    <template v-if="receipt && asset">
      <dl><dt>确认版本</dt><dd>{{ receipt.preview.asset.name }} · 版本 {{ receipt.asset_version }}</dd><dt>说明</dt><dd>{{ receipt.preview.asset.description }}</dd><dt>共享范围</dt><dd>{{ scopeLabels[receipt.sharing_scope] }}</dd><dt>来源</dt><dd>{{ receipt.preview.asset.source_system || '手动登记' }}{{ receipt.preview.asset.source_agent ? ' · ' + receipt.preview.asset.source_agent : '' }}</dd><dt>成果附件</dt><dd>{{ receipt.preview.attachments.map(file => file.file_name).join('、') || '暂无附件' }}</dd><template v-for="subscription in receipt.preview.subscriptions" :key="subscription.id"><dt>订阅套餐</dt><dd>{{ subscription.subscription_name }}</dd><dt>资金来源</dt><dd>{{ ({personal: '本人自费', company: '公司购买', department: '部门购买', trial: '试用'} as Record<string, string>)[subscription.funding_source || ''] || '待核对' }}</dd><dt>主要用途</dt><dd>{{ subscription.primary_purpose }}</dd></template></dl>
      <label class="fusion-checkbox"><input v-model="acknowledged" type="checkbox" :disabled="busy" />我已核对版本 {{ receipt.asset_version }} 的说明、附件与共享范围</label>
      <div class="fusion-button-row"><button class="primary-button" :disabled="busy || !acknowledged" @click="confirm">{{ busy ? '正在处理…' : '确认登记此版本' }}</button><button class="secondary-button" :disabled="busy" @click="cancel">取消确认</button></div>
    </template>
  </section>
</template>
