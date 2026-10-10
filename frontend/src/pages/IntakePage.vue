<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { ArrowLeft, Boxes, Building2, CheckCircle2, ChevronRight, CircleDot, KeyRound, Layers3, Network, Sparkles, UserPlus, Users, Truck } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";

import PageHeader from "../components/PageHeader.vue";
import PeoplePicker from "../components/PeoplePicker.vue";
import AssetStructureGuide from "../components/AssetStructureGuide.vue";
import { registrationKinds, registrationMode, type RegistrationMode } from "../lib/managementWorkspace";
import { api, type Account, type Asset, type AssetType, type CurrentUser, type Department, type IntakeResult, type LegalEntity, type Person, type Platform, type PlatformTenant, type Provider, type RegistrationIdentity } from "../lib/api";

type Mode = RegistrationMode;
type Receipt = Omit<IntakeResult, "id" | "asset_id"> & { id: string; asset_id: string | null };

const route = useRoute(); const router = useRouter();
const initializing = ref(true); const optionError = ref("");
const mode = ref<Mode>(registrationMode(route.query.mode)); const saving = ref(false); const error = ref(""); const message = ref(""); const receipt = ref<Receipt | null>(null); const currentUser = ref<CurrentUser | null>(null);
const entities = ref<LegalEntity[]>([]); const departments = ref<Department[]>([]); const people = ref<Person[]>([]); const platforms = ref<Platform[]>([]); const providers = ref<Provider[]>([]); const identities = ref<RegistrationIdentity[]>([]); const types = ref<AssetType[]>([]); const tenants = ref<PlatformTenant[]>([]); const accounts = ref<Account[]>([]); const assets = ref<Asset[]>([]); const canAssignAccess = ref(false);
const identity = reactive({ identifier: "", identity_type: "", legal_entity_id: "", platform_id: "", source_nature: "", custodian_person_id: "", verification_status: "pending", note: "" });
const platform = reactive({ provider_id: "", name: "", code: "", category: "other", website: "", description: "", review_status: "pending_review" });
const platformRelation = reactive({ identity_asset_ids: [] as string[], resource_asset_ids: [] as string[] });
const platformAccount = reactive({ platform_id: "", legal_entity_id: "", internal_name: "", registration_identity_asset_id: "", external_identifier_type: "", external_identifier_value: "", evidence_note: "", ownership_nature: "company_owned", account_scope: "primary_account", status: "active", description: "", historical_unknown: false, ownership_scope: "company", owner_department_id: "", responsible_person_id: "", user_person_ids: [] as string[] });
const resource = reactive({ legal_entity_id: "", asset_type_id: "", resource_family: "platform_service", name: "", business_purpose: "", managed_under_account_id: "", platform_id: "", platform_relation_type: "uses", owner_department_id: "", responsible_person_id: "", user_person_ids: [] as string[], external_identifier_type: "", external_identifier_value: "", management_url: "", status: "draft", criticality: "normal" });
const grant = reactive({ account_id: "", asset_id: "", person_id: "", department_id: "", grant_type: "seat", grant_role: "member", monthly_budget: "", currency: "CNY", renewal_day: "", note: "" });
const entity = reactive({ name: "" });
const provider = reactive({ code: "", name: "", website: "" });
const entityProfile = reactive({ entity_type: "", jurisdiction: "", registration_status: "", legal_representative: "", established_on: "", registered_address: "", registered_capital: "", business_scope: "", source_note: "", verification_status: "pending" });
const entityIdentifier = reactive({ identifier_type: "unified_social_credit_code", identifier_value: "" });

const selectedRegistration = computed(() => registrationKinds.find(item => item.mode === mode.value));
const selectedPlatform = computed(() => platforms.value.find((item) => item.id === platformAccount.platform_id));
const selectedIdentity = computed(() => identities.value.find((item) => item.asset_id === platformAccount.registration_identity_asset_id));
const selectedResponsible = computed(() => people.value.find((item) => item.id === platformAccount.responsible_person_id));
const selectedDepartment = computed(() => departments.value.find((item) => item.id === platformAccount.owner_department_id));
const resourceAssets = computed(() => {
  const excluded = new Set(["registration_identity", "platform_tenant", "platform_account"]);
  const typeCodes = new Map(types.value.map((item) => [item.id, item.code]));
  return assets.value.filter((item) => !excluded.has(typeCodes.get(item.asset_type_id) ?? ""));
});

async function loadOptions() {
  const [session, entityRows, departmentRows, personRows, platformRows, identityRows, typeRows, tenantRows, accountRows, assetRows, providerRows] = await Promise.all([api.currentSession(), api.legalEntities(), api.departments(), api.people(), api.platforms(), api.registrationIdentities(), api.assetTypes(), api.platformTenants(), api.accounts(), api.assets(), api.providers()]);
  currentUser.value = session; entities.value = entityRows; departments.value = departmentRows; people.value = personRows; platforms.value = platformRows; identities.value = identityRows; types.value = typeRows; tenants.value = tenantRows; accounts.value = accountRows; assets.value = assetRows.data; providers.value = providerRows;
  canAssignAccess.value = session.permissions.includes("asset.write");
}

async function choose(value: Mode) {
  mode.value = value; receipt.value = null; error.value = ""; message.value = "";
  if (value === "platform") { platformRelation.identity_asset_ids = []; platformRelation.resource_asset_ids = []; }
  await router.replace({ query: { ...route.query, mode: value || undefined } });
  await nextTick();
  if (typeof document !== "undefined") document.getElementById(value ? "intake-form-title" : "intake-choice-title")?.focus();
}
function chooseGrant() {
  if (!canAssignAccess.value) { error.value = "当前账号暂无分配人员使用权的权限，请联系资产管理员"; return; }
  choose("grant");
}
function receiptFromIdentity(item: RegistrationIdentity): Receipt {
  const custodian = people.value.find((person) => person.id === item.custodian_person_id);
  return { id: item.id, asset_id: item.asset_id, asset_code: item.asset_code, name: item.name, object_type: "registration_identity", completion_percent: custodian ? 80 : 65, links: custodian ? [{ kind: "person", label: custodian.display_name, relation: "当前保管人", asset_id: null }] : [], next_actions: [{ key: "register_account", label: "用这个身份登记平台账号", description: "注册身份已经保存，可直接继续选择所属平台。", target: `/intake?mode=platform-account&identity=${item.asset_id}`, required: false }, { key: "view_asset", label: "查看身份资料", description: "确认保管人、来源性质和后续关联。", target: `/assets/${item.asset_id}?tab=overview`, required: false }] };
}
function receiptFromPlatform(item: Platform): Receipt {
  return { id: item.id, asset_id: null, asset_code: "平台目录", name: item.name, object_type: "platform", completion_percent: 70, links: [], next_actions: [{ key: "register_account", label: "登记这个平台的公司账号", description: "继续选择注册手机号或邮箱并建立账号。", target: `/intake?mode=platform-account&platform=${item.id}`, required: false }, { key: "view_assets", label: "查看平台与账号", description: "继续核对平台目录和已有账号。", target: "/accounts", required: false }] };
}

async function save() {
  if (saving.value) return;
  saving.value = true; error.value = ""; message.value = "";
  try {
    if (mode.value === "entity") {
      const name = entity.name.trim();
      if (!name) throw new Error("请填写公司主体名称");
      const created = await api.createLegalEntity({ code: `ENTITY-${Date.now()}`, name });
      const profilePayload = { ...entityProfile, entity_type: entityProfile.entity_type || null, jurisdiction: entityProfile.jurisdiction || null, registration_status: entityProfile.registration_status || null, legal_representative: entityProfile.legal_representative || null, established_on: entityProfile.established_on || null, registered_address: entityProfile.registered_address || null, registered_capital: entityProfile.registered_capital || null, business_scope: entityProfile.business_scope || null, source_note: entityProfile.source_note || null };
      const hasProfile = Object.values(profilePayload).some((value) => value !== null && value !== "pending");
      if (hasProfile) await api.saveLegalEntityProfile(created.id, profilePayload);
      if (entityIdentifier.identifier_value.trim()) await api.createLegalEntityIdentifier(created.id, { namespace: "cn", identifier_type: entityIdentifier.identifier_type || "other", identifier_value: entityIdentifier.identifier_value.trim(), is_primary: true, verification_status: "pending", source_note: null });
      receipt.value = { id: created.id, asset_id: null, asset_code: created.code, name: created.name, object_type: "legal_entity", completion_percent: hasProfile || Boolean(entityIdentifier.identifier_value.trim()) ? 60 : 25, links: [], next_actions: [{ key: "complete_entity_profile", label: "补充主体档案", description: "法人资料和主体标识可以稍后在组织架构中继续补充。", target: "/organization", required: false }] };
    }
    if (mode.value === "provider") {
      const created = await api.createProvider({ code: provider.code.trim(), name: provider.name.trim(), website: provider.website.trim() || null });
      receipt.value = { id: created.id, asset_id: null, asset_code: created.code, name: created.name, object_type: "provider", completion_percent: 100, links: [], next_actions: [{ key: "providers", label: "查看供应商目录", description: "供应商目录已保存，可供平台和服务引用。", target: "/accounts?tab=providers", required: false }] };
    }
    if (mode.value === "identity") {
      if (!identity.source_nature) throw new Error("请选择归属性质");
      receipt.value = receiptFromIdentity(await api.createRegistrationIdentity({ ...identity, identity_type: identity.identity_type || null, legal_entity_id: identity.legal_entity_id || null, platform_id: identity.platform_id || null, custodian_person_id: identity.custodian_person_id || null }));
    }
    if (mode.value === "platform") {
      const created = await api.createPlatform({ ...platform, code: platform.code || `USER-${Date.now()}`, provider_id: platform.provider_id || null, submitted_by_person_id: currentUser.value?.person_id ?? null });
      const links = [
        ...platformRelation.identity_asset_ids.map((asset_id) => ({ asset_id, relation_type: "registered_on", note: "平台登记时建立的显式关联" })),
        ...platformRelation.resource_asset_ids.map((asset_id) => ({ asset_id, relation_type: "uses", note: "平台登记时建立的显式关联" })),
      ];
      if (links.length) await Promise.all(links.map((link) => api.createAssetPlatformLink(link.asset_id, { platform_id: created.id, relation_type: link.relation_type, review_status: "pending_review", note: link.note })));
      receipt.value = receiptFromPlatform(created);
    }
    if (mode.value === "platform-account") receipt.value = await api.createCompanyPlatformAccount({ ...platformAccount, registration_identity_asset_id: platformAccount.historical_unknown ? null : platformAccount.registration_identity_asset_id || null, external_identifier_type: platformAccount.external_identifier_type || null, external_identifier_value: platformAccount.external_identifier_value || null, evidence_note: platformAccount.evidence_note || null, owner_department_id: platformAccount.ownership_scope === "department" ? platformAccount.owner_department_id || null : null, responsible_person_id: platformAccount.responsible_person_id || null });
    if (mode.value === "resource") receipt.value = await api.createResource({ ...resource, legal_entity_id: resource.legal_entity_id || null, platform_id: resource.platform_id || null, business_purpose: resource.business_purpose || null, managed_under_account_id: resource.managed_under_account_id || null, owner_department_id: resource.owner_department_id || null, responsible_person_id: resource.responsible_person_id || null, external_identifier_type: resource.external_identifier_type || null, external_identifier_value: resource.external_identifier_value || null, management_url: resource.management_url || null });
    if (mode.value === "grant") { if (!grant.person_id) throw new Error("请选择一名授权人员"); if (!grant.account_id && !grant.asset_id) throw new Error("请选择被授权的账号或服务"); const created = await api.createAccessGrant({ ...grant, account_id: grant.account_id || null, asset_id: grant.asset_id || null, person_id: grant.person_id || null, department_id: null, monthly_budget: grant.monthly_budget ? Number(grant.monthly_budget) : null, renewal_day: grant.renewal_day ? Number(grant.renewal_day) : null }); const person = people.value.find((item) => item.id === grant.person_id); receipt.value = { id: created.id, asset_id: null, asset_code: "使用授权", name: person ? `${person.display_name}的使用权` : "使用权登记", object_type: "access_grant", completion_percent: 100, links: person ? [{ kind: "person", label: person.display_name, relation: "授权人员", asset_id: null }] : [], next_actions: [{ key: "workbench", label: "查看我的工作台", description: "确认授权对象已经进入人员使用清单。", target: "/my/using", required: false }] }; }
    mode.value = ""; await loadOptions(); window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "保存失败"; }
  finally { saving.value = false; }
}

async function openNext(target: string) {
  if (!target.startsWith("/intake")) { await router.push(target); return; }
  const preset = new URL(target, window.location.origin);
  receipt.value = null; mode.value = registrationMode(preset.searchParams.get("mode"));
  platformAccount.platform_id = preset.searchParams.get("platform") || platformAccount.platform_id;
  platformAccount.registration_identity_asset_id = preset.searchParams.get("identity") || platformAccount.registration_identity_asset_id;
  resource.managed_under_account_id = preset.searchParams.get("account") || resource.managed_under_account_id;
  await router.replace(target); window.scrollTo({ top: 0, behavior: "smooth" });
}
function finishReceipt() { receipt.value = null; mode.value = ""; void router.replace("/intake"); }
function applyRoutePreset() {
  mode.value = registrationMode(route.query.mode);
  if (route.query.platform) platformAccount.platform_id = String(route.query.platform);
  if (route.query.identity) platformAccount.registration_identity_asset_id = String(route.query.identity);
  if (route.query.account) resource.managed_under_account_id = String(route.query.account);
}

watch(() => platformAccount.registration_identity_asset_id, (assetId) => {
  const selected = identities.value.find((item) => item.asset_id === assetId);
  if (!selected) return;
  platformAccount.legal_entity_id = selected.legal_entity_id ?? "";
  if (selected.custodian_person_id) platformAccount.responsible_person_id = selected.custodian_person_id;
});
watch(() => platformAccount.ownership_scope, (scope) => { if (scope !== "department") platformAccount.owner_department_id = ""; else if (!platformAccount.owner_department_id) platformAccount.owner_department_id = selectedResponsible.value?.department_id ?? ""; });
watch(() => resource.responsible_person_id, personId => { resource.user_person_ids = resource.user_person_ids.filter(id => id !== personId); });
watch(() => platformAccount.responsible_person_id, () => { platformAccount.user_person_ids = platformAccount.user_person_ids.filter(id => id !== platformAccount.responsible_person_id); if (platformAccount.ownership_scope === "department" && !platformAccount.owner_department_id) platformAccount.owner_department_id = selectedResponsible.value?.department_id ?? ""; });
watch(() => route.fullPath, applyRoutePreset);
async function initialize() {
  initializing.value = true; optionError.value = ""; applyRoutePreset();
  try { await loadOptions(); } catch (reason) { optionError.value = reason instanceof Error ? reason.message : "基础资料读取失败"; }
  finally { initializing.value = false; }
}
onMounted(initialize);
</script>

<template>
  <div class="page-stack intake-page">
    <PageHeader eyebrow="管理区" title="登记基础资料" description="登记已经存在的资料；需要开通或使用资源，请进入我的申请。"><RouterLink class="secondary-button" to="/manage">返回管理</RouterLink></PageHeader>
    <div v-if="message" class="message-panel success-message" role="status">{{ message }}</div><div v-if="error" class="message-panel error-message" role="alert">{{ error }}</div>

    <section v-if="initializing" class="fusion-empty" role="status">正在读取登记所需资料…</section>
    <section v-else-if="optionError" class="fusion-empty" role="alert"><h2>暂时无法读取基础资料</h2><p>{{ optionError }}</p><button class="secondary-button" @click="initialize">重新读取</button><RouterLink to="/my/requests" class="secondary-button">我的申请</RouterLink></section>
    <section v-else-if="receipt" class="intake-receipt">
      <header><div class="receipt-icon"><CheckCircle2 :size="34" /></div><div><span>核心登记完成</span><h2>{{ receipt.name }}</h2><p>已经保存到：资产中心 / {{ receipt.asset_code }}</p></div><div class="receipt-score"><strong>已建档</strong><small>完整资料可按需补充</small></div></header>
      <div class="receipt-summary"><article><span>系统编号</span><strong>{{ receipt.asset_code }}</strong><small>后续可直接用编号搜索和沟通</small></article><article><span>保存位置</span><strong>{{ receipt.asset_id ? '正式资产底库' : '基础目录 / 授权记录' }}</strong><small>{{ receipt.asset_id ? '关系、责任和资料统一归档' : '后续资产会引用这项记录' }}</small></article><article><span>当前状态</span><strong>{{ receipt.next_actions.some((item) => item.required) ? '已保存，待确认' : '已保存' }}</strong><small>现在可以退出，也可以继续完善</small></article></div>
      <section class="receipt-links"><div class="receipt-section-title"><Network :size="18" /><div><strong>已自动联动</strong><small>这些信息不需要去详情页重复选择</small></div></div><div v-if="receipt.links.length" class="receipt-link-grid"><article v-for="item in receipt.links" :key="`${item.kind}-${item.label}`"><CircleDot :size="16" /><span>{{ item.relation }}</span><strong>{{ item.label }}</strong></article></div><div v-else class="receipt-empty">当前对象没有必须建立的关联，后续可按需补充。</div></section>
      <section class="receipt-actions"><div class="receipt-section-title"><Sparkles :size="18" /><div><strong>接下来可以做什么</strong><small>带“建议确认”的是核心资料，其余都可以稍后处理</small></div></div><div class="receipt-action-grid"><button v-for="item in receipt.next_actions" :key="item.key" @click="openNext(item.target)"><span v-if="item.required">建议确认</span><strong>{{ item.label }}</strong><small>{{ item.description }}</small><ChevronRight :size="18" /></button></div></section>
      <footer><button class="secondary-button" @click="finishReceipt">暂时不补充，完成登记</button><button v-if="receipt.asset_id" class="primary-button" @click="router.push(`/assets/${receipt.asset_id}`)">查看刚登记的资产</button></footer>
    </section>

    <div v-else-if="!mode" class="intake-start">
      <div class="intake-start-intro"><h2 id="intake-choice-title" tabindex="-1">选择要登记的资料</h2><p>系统、订阅和云资源从“系统、订阅与资源”开始；已有平台和公司直接关联。</p></div>
      <section class="intake-choice-grid" aria-label="登记资料类型">
        <button v-for="item in registrationKinds" :key="item.mode" type="button" :disabled="item.mode === 'grant' && !canAssignAccess" @click="item.mode === 'grant' ? chooseGrant() : choose(item.mode)"><div><strong>{{ item.label }}</strong><small>{{ item.description }}</small></div><ChevronRight :size="18" aria-hidden="true" /></button>
        <RouterLink to="/imports"><div><strong>批量导入</strong><small>已有 Excel、文本或清单时，先预览再确认。</small></div><ChevronRight :size="18" aria-hidden="true" /></RouterLink>
      </section>
      <AssetStructureGuide />
    </div>

    <section v-else class="intake-form-surface">
      <button class="quiet-button intake-back" @click="choose('')"><ArrowLeft :size="16" />返回选择</button>
      <div class="intake-form-heading"><div><h2 id="intake-form-title" tabindex="-1">登记{{ selectedRegistration?.label }}</h2><p>{{ selectedRegistration?.description }} 标有 * 的信息必填，其他资料按需展开。</p></div></div>
      <form @submit.prevent="save" :aria-busy="saving">
        <template v-if="mode === 'provider'">
          <label><span>供应商名称 *</span><input v-model="provider.name" required maxlength="200" placeholder="填写供应商名称" /></label>
          <label><span>供应商编码 *</span><input v-model="provider.code" required maxlength="80" placeholder="填写现有编码或稳定的唯一标识" /></label>
          <label class="span-2"><span>官方网站（选填）</span><input v-model="provider.website" type="url" placeholder="https://" /></label>
        </template>
        <template v-if="mode === 'entity'">
          <label class="span-2"><span>公司主体名称 *</span><input v-model="entity.name" required placeholder="例如：杭州飞比特体育用品有限公司" /></label>
          <details class="intake-optional span-2"><summary>补充主体资料（选填）</summary><div class="optional-grid"><label><span>主体类型</span><select v-model="entityProfile.entity_type"><option value="">暂不确定</option><option value="domestic_company">境内公司</option><option value="branch">分公司</option><option value="individual_business">个体工商户</option><option value="overseas_entity">境外法人</option><option value="other">其他主体</option></select></label><label><span>注册地 / 司法辖区</span><input v-model="entityProfile.jurisdiction" placeholder="例如：中国浙江省杭州市" /></label><label><span>存续状态</span><select v-model="entityProfile.registration_status"><option value="">暂不确定</option><option value="active">存续</option><option value="inactive">注销 / 停业</option><option value="pending">待核验</option></select></label><label><span>法定代表人</span><input v-model="entityProfile.legal_representative" placeholder="可稍后补充" /></label><label><span>成立日期</span><input v-model="entityProfile.established_on" type="date" /></label><label><span>注册资本</span><input v-model="entityProfile.registered_capital" placeholder="例如：100 万元" /></label><label class="wide"><span>注册地址</span><textarea v-model="entityProfile.registered_address" rows="2" placeholder="可稍后补充" /></label><label class="wide"><span>经营范围</span><textarea v-model="entityProfile.business_scope" rows="2" placeholder="可稍后补充" /></label><label class="wide"><span>来源说明</span><textarea v-model="entityProfile.source_note" rows="2" placeholder="例如：工商资料、原始清单或人工确认" /></label></div></details>
          <details class="intake-optional span-2"><summary>补充主体标识（选填）</summary><div class="optional-grid"><label><span>标识类型</span><select v-model="entityIdentifier.identifier_type"><option value="unified_social_credit_code">统一社会信用代码</option><option value="registration_number">注册号</option><option value="overseas_registration_number">境外注册编号</option><option value="other">其他标识</option></select></label><label><span>标识值</span><input v-model="entityIdentifier.identifier_value" placeholder="知道就填，不知道可留空" /></label></div></details>
        </template>
        <template v-if="mode === 'identity'">
          <label class="span-2"><span>手机号 / 邮箱 / 身份内容 *</span><input v-model="identity.identifier" required placeholder="输入实际内容，系统自动识别类型" /></label>
          <label><span>归属性质 *</span><select v-model="identity.source_nature" required><option value="" disabled>请选择</option><option value="company_owned">公司所有</option><option value="personal_for_company">个人注册、公司使用</option><option value="unknown">归属待确认</option></select></label>
          <details class="intake-optional span-2"><summary>关联已有对象（选填：公司、平台）</summary><div class="optional-grid"><label><span>归属公司</span><select v-model="identity.legal_entity_id"><option value="">暂不确定</option><option v-for="item in entities" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label><span>关联平台</span><select v-model="identity.platform_id"><option value="">暂不关联</option><option v-for="item in platforms" :key="item.id" :value="item.id">{{ item.name }}</option></select></label></div></details>
          <details class="intake-optional span-2"><summary>补充身份资料（类型、保管人、说明）</summary><div class="optional-grid"><label><span>身份类型</span><select v-model="identity.identity_type"><option value="">自动识别</option><option value="phone">手机号</option><option value="email">邮箱</option><option value="wechat">微信身份</option><option value="other">其他</option></select></label><PeoplePicker id="identity-custodian" :person-id="identity.custodian_person_id" @update:person-id="identity.custodian_person_id = $event || ''" label="当前保管人（选填）" :people="people" :departments="departments" :disabled="saving" /><label class="wide"><span>说明</span><textarea v-model="identity.note" rows="3" placeholder="例如：技术部门公共注册手机号" /></label></div></details>
        </template>
        <template v-if="mode === 'platform'">
          <label class="span-2"><span>服务提供方（选填）</span><select v-model="platform.provider_id"><option value="">暂不关联供应商</option><option v-for="item in providers" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label class="span-2"><span>平台名称 *</span><input v-model="platform.name" required placeholder="例如：火山引擎" /></label>
          <details class="intake-optional span-2"><summary>关联已有对象（选填：注册身份、服务 / 资源）</summary><div class="optional-grid"><label><span>已有注册身份</span><select v-model="platformRelation.identity_asset_ids" multiple size="4"><option v-for="item in identities" :key="item.asset_id" :value="item.asset_id">{{ item.identifier }} · {{ item.name }}</option></select><small>按住 Ctrl 可多选；不选也可以先保存平台。</small></label><label><span>已有服务 / 资源</span><select v-model="platformRelation.resource_asset_ids" multiple size="4"><option v-for="item in resourceAssets" :key="item.id" :value="item.id">{{ item.name }}</option></select><small>只保存已选择的关联；企业账号需要单独登记。</small></label></div></details>
          <details class="intake-optional span-2"><summary>补充平台资料（类别、官网、说明）</summary><div class="optional-grid"><label><span>平台类别</span><select v-model="platform.category"><option value="cloud">云平台</option><option value="ai">大模型 / AI</option><option value="saas">SaaS / 协作</option><option value="marketing">营销 / 电商</option><option value="payment">支付</option><option value="other">其他</option></select></label><label><span>官方网站</span><input v-model="platform.website" placeholder="https://" /></label><label class="wide"><span>说明</span><textarea v-model="platform.description" rows="3" /></label></div></details>
        </template>
        <template v-if="mode === 'platform-account'">
          <label><span>所属平台 *</span><select v-model="platformAccount.platform_id" required><option value="" disabled>选择平台</option><option v-for="item in platforms" :key="item.id" :value="item.id">{{ item.name }}{{ item.review_status === 'pending_review' ? '（待审核）' : '' }}</option></select></label>
          <label class="span-2"><span>内部使用名称 *</span><input v-model="platformAccount.internal_name" required placeholder="例如：MiniMax · AI 工作流主账号" /></label>
          <label><span>归属公司 *</span><select v-model="platformAccount.legal_entity_id" required><option v-for="item in entities" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label><span>账号/租户存在证据 *</span><input v-model="platformAccount.evidence_note" required placeholder="企业后台、明确主账号、Workspace ID 等来源说明" /></label>
          <section class="intake-link-preview span-2"><header><Sparkles :size="18" /><div><strong>已知关联（选填）</strong><small>有证据才关联；空位不会生成占位对象</small></div></header><div><span><i class="platform" />所属平台<b>{{ selectedPlatform?.name || '待选择' }}</b></span><span><i class="identity" />注册身份<b>{{ platformAccount.historical_unknown ? '暂无明确证据' : selectedIdentity?.name || '暂未关联' }}</b></span><span><i class="person" />建议负责人<b>{{ selectedResponsible?.display_name || '暂未登记' }}</b></span><span><i class="department" />归属范围<b>{{ platformAccount.ownership_scope === 'department' ? selectedDepartment?.name || '待选择部门' : platformAccount.ownership_scope === 'company' ? '公司级' : '待确认' }}</b></span></div></section>
          <details class="intake-optional span-2"><summary>补充账号资料（注册身份、原生 ID、人员、部门、用途）</summary><div class="optional-grid"><label><span>主要注册身份</span><select v-model="platformAccount.registration_identity_asset_id" :disabled="platformAccount.historical_unknown"><option value="">暂不关联</option><option v-for="item in identities" :key="item.id" :value="item.asset_id">{{ item.identifier }} · {{ item.name }}</option></select><span class="inline-check"><input v-model="platformAccount.historical_unknown" type="checkbox" />历史账号，注册身份暂不清楚</span></label><label><span>平台账号 ID / UID</span><input v-model="platformAccount.external_identifier_value" placeholder="平台未提供时留空" /></label><label><span>ID 类型</span><input v-model="platformAccount.external_identifier_type" placeholder="UID、组织 ID、Workspace ID" /></label><label><span>所有权</span><select v-model="platformAccount.ownership_nature"><option value="company_owned">公司所有</option><option value="personal_for_company">个人注册、公司使用</option><option value="unknown">待确认</option></select></label><label><span>归属范围</span><select v-model="platformAccount.ownership_scope"><option value="company">公司级，不绑定部门</option><option value="department">部门级</option><option value="pending">暂不确定</option></select></label><label v-if="platformAccount.ownership_scope === 'department'"><span>归属部门</span><select v-model="platformAccount.owner_department_id" required><option value="" disabled>选择部门</option><option v-for="item in departments.filter((row) => row.legal_entity_id === platformAccount.legal_entity_id)" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><PeoplePicker id="platform-responsible" :person-id="platformAccount.responsible_person_id" @update:person-id="platformAccount.responsible_person_id = $event || ''" label="建议负责人" :people="people.filter(row => row.legal_entity_id === platformAccount.legal_entity_id)" :departments="departments" :disabled="saving" /><PeoplePicker id="platform-users" v-model:person-ids="platformAccount.user_person_ids" multiple label="协同使用人员（选填）" :people="people.filter(row => row.legal_entity_id === platformAccount.legal_entity_id)" :departments="departments" :disabled="saving" :excluded-ids="platformAccount.responsible_person_id ? [platformAccount.responsible_person_id] : []" /><label class="wide"><span>用途说明</span><textarea v-model="platformAccount.description" rows="3" /></label></div></details>
        </template>
        <template v-if="mode === 'resource'">
          <label><span>资源大类 *</span><select v-model="resource.resource_family"><option value="cloud_infrastructure">云与基础设施</option><option value="platform_service">平台服务 / 订阅</option><option value="system_application">系统 / 应用</option><option value="data_content">数据 / 内容</option><option value="digital_channel">数字渠道 / 业务账号</option><option value="domain_qualification">域名 / 资质 / 知识产权</option><option value="hardware_license">硬件 / 软件许可</option><option value="other">其他</option></select></label>
          <label><span>具体类型 *</span><select v-model="resource.asset_type_id" required><option value="" disabled>选择类型</option><option v-for="item in types.filter((row) => !['registration_identity','platform_tenant','platform_account'].includes(row.code))" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label class="span-2"><span>内部使用名称 *</span><input v-model="resource.name" required placeholder="例如：阿里云 ECS · 集团中台服务器" /></label>
          <label><span>归属公司（可选）</span><select v-model="resource.legal_entity_id"><option value="">暂不确定</option><option v-for="item in entities" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label><span>所属平台（可选）</span><select v-model="resource.platform_id"><option value="">暂不关联</option><option v-for="item in platforms" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <section class="intake-link-preview span-2"><header><Sparkles :size="18" /><div><strong>已知关联（选填）</strong><small>管理账号、负责人和使用人员有证据时再关联</small></div></header><div><span><i class="platform" />管理账号<b>{{ resource.managed_under_account_id ? '已选择' : '暂未关联' }}</b></span><span><i class="identity" />注册身份<b>可从关联账号追溯</b></span><span><i class="person" />建议负责人<b>{{ resource.responsible_person_id ? '已选择' : '暂未登记' }}</b></span><span><i class="department" />归属主体<b>{{ entities.find((item) => item.id === resource.legal_entity_id)?.name || '待选择' }}</b></span></div></section>
          <details class="intake-optional span-2"><summary>补充服务资料（用途、管理账号、人员、标识、管理地址）</summary><div class="optional-grid"><label class="wide"><span>业务用途</span><textarea v-model="resource.business_purpose" rows="3" placeholder="它用于什么业务、服务谁、为什么需要保留" /></label><label><span>管理来源</span><select v-model="resource.managed_under_account_id"><option value="">不适用 / 暂不清楚</option><option v-for="item in tenants" :key="item.id" :value="item.id">{{ platforms.find((row) => row.id === item.platform_id)?.name }} · {{ item.tenant_identifier || '未填写 UID' }}</option></select></label><label><span>建议归属组织</span><select v-model="resource.owner_department_id"><option value="">公司主体 / 待确认</option><option v-for="item in departments.filter((row) => !resource.legal_entity_id || row.legal_entity_id === resource.legal_entity_id)" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><PeoplePicker id="resource-responsible" :person-id="resource.responsible_person_id" @update:person-id="resource.responsible_person_id = $event || ''" label="建议负责人" :people="people.filter(row => !resource.legal_entity_id || row.legal_entity_id === resource.legal_entity_id)" :departments="departments" :disabled="saving" /><PeoplePicker id="resource-users" v-model:person-ids="resource.user_person_ids" multiple label="建议使用人员（选填）" :people="people.filter(row => !resource.legal_entity_id || row.legal_entity_id === resource.legal_entity_id)" :departments="departments" :disabled="saving" :excluded-ids="resource.responsible_person_id ? [resource.responsible_person_id] : []" /><label><span>平台资源 ID</span><input v-model="resource.external_identifier_value" /></label><label><span>管理地址</span><input v-model="resource.management_url" placeholder="https://" /></label></div></details>
        </template>
        <template v-if="mode === 'grant'">
          <PeoplePicker id="grant-person" :person-id="grant.person_id" @update:person-id="grant.person_id = $event || ''" label="授权人员（必选一人）" :people="people" :departments="departments" :disabled="saving" /><label><span>被授权服务 / 资源</span><select v-model="grant.asset_id"><option value="">如授权给具体账号，可留空</option><option v-for="item in assets" :key="item.id" :value="item.id">{{ item.name }} · {{ item.asset_code }}</option></select></label>
          <label><span>访问账号</span><select v-model="grant.account_id"><option value="">如授权给服务，可留空</option><option v-for="item in accounts" :key="item.id" :value="item.id">{{ item.login_identifier }}</option></select></label><label><span>授权类型</span><select v-model="grant.grant_type"><option value="seat">工具席位</option><option value="subscription">订阅使用权</option><option value="platform_permission">平台权限</option><option value="resource_permission">资源权限</option><option value="api_usage">API 使用权</option></select></label>
          <label class="span-2"><span>权限角色</span><select v-model="grant.grant_role"><option value="member">普通成员</option><option value="admin">管理员</option><option value="readonly">只读</option><option value="service">服务账号</option></select></label>
          <details class="intake-optional span-2"><summary>补充授权资料（费用、币种、备注）</summary><div class="optional-grid"><label><span>月度费用</span><input v-model="grant.monthly_budget" type="number" min="0" step="0.01" /></label><label><span>币种</span><select v-model="grant.currency"><option>CNY</option><option>USD</option></select></label><label class="wide"><span>备注</span><textarea v-model="grant.note" rows="3" /></label></div></details>
        </template>
        <div class="form-actions span-2"><span class="intake-save-note">保存后可查看记录及后续补充事项。</span><button type="button" class="secondary-button" @click="choose('')">取消</button><button class="primary-button" :disabled="saving">{{ saving ? "保存中…" : "保存资料" }}</button></div>
      </form>
    </section>
  </div>
</template>

<style scoped>
.intake-start { display:grid; gap:20px; min-width:0; }
.intake-start-intro h2 { margin:0; }
.intake-start-intro p, .intake-filling-note { color:var(--muted); line-height:1.7; }
.intake-filling-note { padding:14px 16px; border-radius:var(--radius); background:var(--surface-soft); }
@media(max-width:700px) {
  .intake-form-surface form, .intake-optional .optional-grid { grid-template-columns:minmax(0,1fr); }
  .intake-form-surface .span-2, .intake-form-surface .intake-form-heading, .intake-optional .optional-grid .wide { grid-column:1 / -1; }
}
</style>
