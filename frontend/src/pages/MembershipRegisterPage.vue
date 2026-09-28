<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import PageHeader from "../components/PageHeader.vue";
import { api, type Asset } from "../lib/api";
const products = ref<{id:string;name:string}[]>([]);const error=ref("");const saving=ref(false);const result=ref<Asset|null>(null);
const form=reactive({service_product_id:"",plan:"",funding_source:"personal",starts_at:"",usage_frequency:"weekly",primary_purpose:""});
let requestId=crypto.randomUUID(),previous="";
async function initialize(){error.value="";try{products.value=await api.serviceProducts();}catch(e){error.value=e instanceof Error?e.message:"服务目录读取失败";}}
onMounted(initialize);
async function submit(){saving.value=true;error.value="";const snapshot=JSON.stringify(form);if(previous&&snapshot!==previous)requestId=crypto.randomUUID();previous=snapshot;try{result.value=await api.registerMembership({...form,request_id:requestId});}catch(e){error.value=e instanceof Error?e.message:"登记失败";}finally{saving.value=false;}}
</script>
<template><div class="page-stack fusion-space"><PageHeader eyebrow="我的订阅" title="登记订阅" description="登记你实际使用的服务和套餐，个人自费投入不直接换算奖励。" />
<section v-if="result" class="fusion-empty"><h2>会员登记已保存</h2><p>记录默认为本人和资产管理员可见，尚未确认为公司资产。</p><RouterLink to="/my/subscriptions" class="primary-button">查看我的订阅</RouterLink></section>
<form v-else class="fusion-register" @submit.prevent="submit"><label>服务<select v-model="form.service_product_id" required><option value="" disabled>请选择服务</option><option v-for="p in products" :key="p.id" :value="p.id">{{ p.name }}</option></select></label><p v-if="!products.length">目录尚无可选服务，请联系管理员补充。</p><label>套餐<input v-model="form.plan" required maxlength="200" /></label><label>资金来源<select v-model="form.funding_source"><option value="personal">个人自费</option><option value="company">公司</option><option value="department">部门</option><option value="free">免费</option><option value="trial">试用</option></select></label><label>开始时间<input v-model="form.starts_at" type="date" required /></label><label>使用频率<select v-model="form.usage_frequency"><option value="daily">每天</option><option value="weekly">每周</option><option value="monthly">每月</option><option value="rarely">偶尔</option></select></label><label>主要用途<textarea v-model="form.primary_purpose" required maxlength="500" /></label><p>登记不代表公司采购获批、工具准入或报销批准。</p><p v-if="error" class="form-error" role="alert">{{ error }}</p><button v-if="!products.length" type="button" @click="initialize">重新读取目录</button><button class="primary-button" :disabled="saving||!products.length">{{ saving?'正在保存…':'保存会员登记' }}</button></form></div></template>
