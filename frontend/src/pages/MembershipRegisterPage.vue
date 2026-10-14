<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import PageHeader from "../components/PageHeader.vue";
import { api, type Asset, type SubscriptionOption } from "../lib/api";
const products = ref<SubscriptionOption[]>([]), error = ref(""), loading = ref(true), saving = ref(false), result = ref<Asset | null>(null);
const route = useRoute();
const availableProducts = computed(() => products.value.filter(item => !route.query.platform || item.platform_id === route.query.platform));
const selectedPlan = ref(""), customPlan = ref("");
const form = reactive({ service_product_id: "", funding_source: "personal", starts_at: "", usage_frequency: "weekly", primary_purpose: "" });
const product = computed(() => products.value.find(item => item.id === form.service_product_id));
const plans = computed(() => product.value?.plan_options || []);
const plan = computed(() => selectedPlan.value === "__custom__" ? customPlan.value.trim() : selectedPlan.value);
let requestId = crypto.randomUUID(), previous = "";
watch(() => form.service_product_id, () => { selectedPlan.value = ""; customPlan.value = ""; });
watch(plans, values => { if (selectedPlan.value !== "__custom__" && !values.includes(selectedPlan.value)) selectedPlan.value = ""; });
async function initialize() {
  loading.value = true; error.value = "";
  try { products.value = await api.subscriptionOptions(); if (form.service_product_id && !product.value) form.service_product_id = ""; if (!form.service_product_id && route.query.platform && availableProducts.value.length === 1) form.service_product_id = availableProducts.value[0]!.id; }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "服务目录读取失败"; }
  finally { loading.value = false; }
}
onMounted(initialize);
async function submit() {
  if (saving.value || !plan.value) return;
  saving.value = true; error.value = "";
  const body = { ...form, plan: plan.value, catalog_plan: selectedPlan.value === "__custom__" ? null : plan.value };
  const snapshot = JSON.stringify(body);
  if (previous && snapshot !== previous) requestId = crypto.randomUUID();
  previous = snapshot;
  try { result.value = await api.registerMembership({ ...body, request_id: requestId }); }
  catch (reason) { error.value = reason instanceof Error ? reason.message : "登记失败"; }
  finally { saving.value = false; }
}
</script>
<template>
  <div class="page-stack fusion-space"><PageHeader eyebrow="我的订阅" title="登记订阅" description="选择实际使用的服务和套餐，个人自费投入不直接换算奖励。" />
    <section v-if="result" class="fusion-empty"><h2>个人订阅已登记，无需审核</h2><p>记录默认为本人和资产管理员可见，资金来源单独记录。</p><RouterLink to="/my/subscriptions" class="primary-button">查看我的订阅</RouterLink></section>
    <form v-else class="fusion-register" :aria-busy="loading || saving" @submit.prevent="submit">
      <p v-if="loading" role="status">正在读取已审核的服务与套餐…</p>
      <label>服务（平台/供应商）<select v-model="form.service_product_id" required :disabled="loading || saving"><option value="" disabled>请选择服务</option><option v-for="item in availableProducts" :key="item.id" :value="item.id">{{ item.name }} · {{ item.platform_name }}</option></select></label>
      <p v-if="!loading && !availableProducts.length">当前平台暂无已审核的可选服务，请联系管理员完善平台资料与套餐。</p>
      <label>套餐<select v-model="selectedPlan" required :disabled="!product || saving"><option value="" disabled>{{ product ? '请选择实际套餐' : '请先选择服务' }}</option><option v-for="name in plans" :key="name" :value="name">{{ name === 'Team' && product?.name === 'ChatGPT' ? 'Team（历史名称）' : name }}</option><option value="__custom__">其他套餐（补充实际名称）</option></select></label>
      <label v-if="selectedPlan === '__custom__'">实际套餐名称<input v-model="customPlan" required maxlength="200" :disabled="saving" placeholder="按订单或订阅页面填写" /></label>
      <p v-if="product && !plans.length">该服务的套餐目录尚待补充，可先登记实际套餐名称。</p>
      <label>资金来源<select v-model="form.funding_source" :disabled="saving"><option value="personal">个人自费</option><option value="company">公司</option><option value="department">部门</option><option value="free">免费</option><option value="trial">试用</option></select></label>
      <label>开始时间<input v-model="form.starts_at" type="date" required :disabled="saving" /></label>
      <label>使用频率<select v-model="form.usage_frequency" :disabled="saving"><option value="daily">每天</option><option value="weekly">每周</option><option value="monthly">每月</option><option value="rarely">偶尔</option></select></label>
      <label>主要用途<textarea v-model="form.primary_purpose" required maxlength="500" :disabled="saving" /></label>
      <p>登记不代表公司采购获批、工具准入或报销批准。</p><p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <button type="button" class="secondary-button" :disabled="loading || saving" @click="initialize">重新读取目录</button><button class="primary-button" :disabled="loading || saving || !products.length || !plan">{{ saving ? '正在保存…' : '保存订阅登记' }}</button>
    </form>
  </div>
</template>
