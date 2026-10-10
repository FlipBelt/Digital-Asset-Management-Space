<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { Building, ExternalLink, KeyRound, LockKeyhole, Plus, UserRound } from "lucide-vue-next";

import { useRoute } from "vue-router";
import ModalPanel from "../components/ModalPanel.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import PlatformDirectoryPanel from "../components/PlatformDirectoryPanel.vue";
import { api, type Account, type Asset, type CurrentUser, type CredentialReference, type Platform, type PlatformTenant } from "../lib/api";

const route = useRoute();
const user = ref<CurrentUser | null>(null); const canRegister = computed(() => Boolean(user.value?.roles.some(role => ["system_admin", "asset_manager"].includes(role))));
const tab = ref<"directory" | "tenants" | "accounts">("tenants"); const modal = ref<"credential" | null>(null); const saving = ref(false); const error = ref("");
const platforms = ref<Platform[]>([]); const tenants = ref<PlatformTenant[]>([]); const accounts = ref<Account[]>([]); const credentials = ref<CredentialReference[]>([]); const assets = ref<Asset[]>([]); const credentialAccount = ref("");
const credentialForm = reactive({ provider: "bitwarden", item_id: "", secure_url: "" });
const assetName = computed(() => Object.fromEntries(assets.value.map((item) => [item.id, item.name]))); const platformName = computed(() => Object.fromEntries(platforms.value.map((item) => [item.id, item.name]))); const tenantName = computed(() => Object.fromEntries(tenants.value.map((item) => [item.id, item.tenant_identifier])));
async function load() { try { const [platformRows, tenantRows, accountRows, credentialRows, assetRows, session] = await Promise.all([api.platforms(), api.platformTenants(), api.accounts(), api.credentialReferences(), api.assets(), api.currentSession()]); platforms.value = platformRows; tenants.value = tenantRows; accounts.value = accountRows; credentials.value = credentialRows; assets.value = assetRows.data; user.value = session; } catch (reason) { error.value = reason instanceof Error ? reason.message : "加载失败" } }
async function save() {
  saving.value = true; error.value = "";
  try {
    if (modal.value === "credential") await api.createCredentialReference({ account_id: credentialAccount.value, provider: credentialForm.provider, item_id: credentialForm.item_id, secure_url: credentialForm.secure_url || null });
    modal.value = null; await load();
  } catch (reason) { error.value = reason instanceof Error ? reason.message : "保存失败" }
  finally { saving.value = false }
}
function openCredential(accountId: string) { credentialAccount.value = accountId; modal.value = "credential" }
function restoreTab() { const value = String(route.query.tab || "tenants"); if (["platforms", "providers", "directory"].includes(value)) tab.value = "directory"; else if (["tenants", "accounts"].includes(value)) tab.value = value as typeof tab.value; }
watch(() => route.query.tab, restoreTab);
onMounted(() => { restoreTab(); void load(); });
</script>

<template>
  <div class="page-stack">
    <PageHeader eyebrow="控制入口" title="平台与账号" description="统一维护平台/供应商及其服务套餐，再管理公司账号和人员授权。"><RouterLink v-if="canRegister" class="secondary-button" to="/intake?mode=platform"><Plus :size="16" />登记平台/供应商</RouterLink><RouterLink v-if="canRegister" class="primary-button" to="/intake?mode=platform-account"><Plus :size="16" />登记平台账号</RouterLink><RouterLink v-else class="primary-button" to="/my/requests?new=account">申请使用</RouterLink></PageHeader>
    <div v-if="error" class="message-panel error-message">{{ error }}</div>
    <div class="dimension-tabs"><button :class="{ active: tab === 'tenants' }" @click="tab = 'tenants'">公司平台账号 {{ tenants.length }}</button><button :class="{ active: tab === 'accounts' }" @click="tab = 'accounts'">访问账号与授权 {{ accounts.length }}</button><button :class="{ active: tab === 'directory' }" @click="tab = 'directory'">平台/供应商与套餐</button></div>
    <section class="content-panel accounts-panel">
      <div v-if="tab === 'accounts'" class="account-grid"><article v-for="item in accounts" :key="item.id"><header><span class="record-icon"><UserRound :size="19" /></span><div><strong>{{ assetName[item.asset_id] ?? item.login_identifier }}</strong><span>{{ item.login_identifier }}</span></div><StatusBadge tone="success">{{ item.account_role || item.privilege_level }}</StatusBadge></header><dl><div><dt>所属公司账号</dt><dd>{{ tenantName[item.platform_tenant_id] || '未命名账号' }}</dd></div><div><dt>访问账号类型</dt><dd>{{ item.account_kind || item.account_type }}</dd></div><div><dt>登录方式</dt><dd>{{ item.login_method || item.registration_identity_type }}</dd></div><div><dt>权限角色</dt><dd>{{ item.account_role || item.privilege_level }}</dd></div></dl><footer><div v-if="credentials.find((row) => row.account_id === item.id)" class="credential-link"><LockKeyhole :size="15" /><span>凭据已登记</span><a v-if="credentials.find((row) => row.account_id === item.id)?.secure_url" :href="credentials.find((row) => row.account_id === item.id)?.secure_url ?? ''" target="_blank"><ExternalLink :size="14" /></a></div><button v-else class="secondary-button" @click="openCredential(item.id)"><KeyRound :size="14" />登记凭据状态</button></footer></article><div v-if="!accounts.length" class="large-empty-panel"><KeyRound :size="28" /><strong>尚未登记访问账号</strong><p>简单平台可以没有这一层；阿里云 RAM、工具子账号和员工席位在这里管理。</p></div></div>
      <div v-if="tab === 'tenants'" class="record-list"><div v-for="item in tenants" :key="item.id"><span class="record-icon"><Building :size="18" /></span><div><strong>{{ assetName[item.asset_id] ?? '未命名公司账号' }}</strong><span>{{ platformName[item.platform_id] }} · {{ item.tenant_identifier ? `平台 ID ${item.tenant_identifier}` : '未提供平台 UID' }}</span></div><StatusBadge :tone="item.verification_status === 'verified' ? 'success' : 'warning'">{{ item.verification_status === 'verified' ? '已核验' : '待核验' }}</StatusBadge></div><div v-if="!tenants.length" class="mini-empty">尚未登记公司平台账号</div></div>
      <PlatformDirectoryPanel v-if="tab === 'directory'" :can-manage="canRegister" />
    </section>
    <ModalPanel v-if="modal" title="添加密码库引用" @close="modal = null"><form class="form-grid one-column" @submit.prevent="save"><div class="form-hint">只保存外部密码库条目ID或安全链接，禁止填写密码、Secret、私钥和恢复码。</div><label><span>密码库产品</span><select v-model="credentialForm.provider"><option value="bitwarden">Bitwarden</option><option value="1password">1Password</option><option value="keeper">Keeper</option><option value="other">其他</option></select></label><label><span>条目ID *</span><input v-model="credentialForm.item_id" required /></label><label><span>安全跳转链接</span><input v-model="credentialForm.secure_url" /></label><div class="form-actions"><button type="button" class="secondary-button" @click="modal = null">取消</button><button class="primary-button" :disabled="saving">保存</button></div></form></ModalPanel>
  </div>
</template>
