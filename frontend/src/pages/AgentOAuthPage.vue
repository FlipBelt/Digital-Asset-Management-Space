<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, ApiError, request } from "../lib/api";
import { safeLoginRedirect } from "../lib/loginNavigation";

type OAuthPreview = {
  client_name: string;
  scopes: string[];
  expires_in_seconds: number;
  client_identity_note?: string;
};
type OAuthDecision = { redirect_url: string };
type OAuthGrant = { id: string; client_name: string; scopes: string[]; expires_at: string | null; revoked_at: string | null };

const route = useRoute();
const router = useRouter();
const preview = ref<OAuthPreview | null>(null);
const loading = ref(false);
const submitting = ref(false);
const completed = ref(false);
const error = ref("");
const message = ref("");
const grants = ref<OAuthGrant[]>([]);
const grantsLoading = ref(false);
const grantsLoaded = ref(false);
const grantsError = ref("");
const grantsMessage = ref("");
const revokingId = ref("");
const restoredRequestToken = ref("");
const recoveryFailed = ref(false);
const loginRequired = ref(false);
let loadSequence = 0;
let previewToken = "";
let restoringRequest = false;
let redirectingToLogin = false;
const recoveryStorageKey = "asset-center:oauth-consent:" + router.options.history.base;
const recoveryLifetimeMs = 10 * 60_000;
const recoveryError = "无法恢复连接请求，请从 AI 助手重新发起连接。";

const scopeDescriptions: Record<string, string> = {
  "asset:read": "读取你有权访问的 AI 成果",
  "asset:draft": "创建和修改你自己的私有成果草稿",
  "incubation:read": "读取你自己的孵化摘要",
  "incubation:write": "保存和修改你自己的孵化摘要",
};
const unknownScopes = computed(() => preview.value?.scopes.some(scope => !Object.hasOwn(scopeDescriptions, scope)) ?? false);
const expiryMinutes = computed(() => Math.max(1, Math.ceil((preview.value?.expires_in_seconds ?? 0) / 60)));
const hasRequestToken = computed(() => route.query.request_token !== undefined || !!restoredRequestToken.value || recoveryFailed.value);

function scopeDescription(scope: string) {
  return Object.hasOwn(scopeDescriptions, scope) ? scopeDescriptions[scope] : "未识别的申请权限，暂不能批准";
}

function requestToken(): string {
  const value = route.query.request_token ?? restoredRequestToken.value;
  return typeof value === "string" && value.length > 0 && value.length <= 1024
    && !/[\s\u0000-\u001f\u007f]/.test(value) ? value : "";
}

async function restoreRequest() {
  const handle = route.query.resume;
  if (handle === undefined) return;
  restoringRequest = true;
  try {
    if (typeof handle !== "string" || !/^[0-9a-f-]{36}$/.test(handle) || route.query.request_token !== undefined) {
      throw new Error("Invalid recovery handle");
    }
    const stored = window.sessionStorage.getItem(recoveryStorageKey);
    if (!stored) throw new Error("Missing recovery record");
    const record = JSON.parse(stored) as { handle?: unknown; request_token?: unknown; expires_at?: unknown };
    if (record.handle !== handle) throw new Error("Mismatched recovery handle");
    window.sessionStorage.removeItem(recoveryStorageKey);
    if (typeof record.expires_at !== "number" || record.expires_at <= Date.now()
      || typeof record.request_token !== "string" || !record.request_token || record.request_token.length > 1024
      || /[\s\u0000-\u001f\u007f]/.test(record.request_token)) throw new Error("Invalid recovery record");
    restoredRequestToken.value = record.request_token;
  } catch {
    recoveryFailed.value = true;
  }
  // The one-time local handle is no longer needed after this page reads it.
  try { await router.replace({ path: "/agent/oauth" }); }
  finally { restoringRequest = false; }
}

function loginWithoutRequest() {
  return router.replace({ path: "/login", query: { redirect: "/agent/oauth?restart=1" } });
}

async function fail(reason: unknown) {
  preview.value = null;
  loading.value = false;
  submitting.value = false;
  if (reason instanceof ApiError && reason.status === 401) {
    if (redirectingToLogin) return;
    redirectingToLogin = true;
    const token = requestToken();
    let returnPath = route.query.restart === "1" ? "/agent/oauth?restart=1" : "/agent/oauth";
    if (token) {
      try {
        const handle = crypto.randomUUID();
        window.sessionStorage.setItem(recoveryStorageKey, JSON.stringify({
          handle, request_token: token, expires_at: Date.now() + recoveryLifetimeMs,
        }));
        returnPath += "?" + new URLSearchParams({ resume: handle });
      } catch {
        loginRequired.value = true;
        error.value = "浏览器无法暂存连接请求。请先登录资产中心，再从 AI 助手重新发起连接。";
        return;
      }
    }
    await router.replace({ path: "/login", query: { redirect: safeLoginRedirect(returnPath) } });
    return;
  }
  error.value = reason instanceof ApiError && [400, 404, 410].includes(reason.status)
    ? "连接请求已失效或已被处理，请返回 AI 助手重新发起连接。"
    : reason instanceof ApiError && reason.status === 403
      ? "当前账号无法批准此连接，请确认账号权限或重新发起请求。"
      : "暂时无法处理连接请求，请重试。";
}

async function load() {
  const sequence = ++loadSequence;
  const token = requestToken();
  preview.value = null;
  previewToken = "";
  loading.value = false;
  submitting.value = false;
  error.value = route.query.restart === "1" && !hasRequestToken.value
    ? "请返回 AI 助手重新发起连接请求，再核对并决定是否授权。" : "";
  message.value = "";
  completed.value = false;
  redirectingToLogin = false;
  loginRequired.value = false;
  if (recoveryFailed.value) {
    error.value = recoveryError;
    return;
  }
  if (hasRequestToken.value && !token) {
    error.value = "连接请求缺失或无效，请从 AI 助手重新打开授权页。";
    return;
  }
  loading.value = true;
  try {
    await api.currentSession();
    if (sequence !== loadSequence) return;
    void loadGrants(sequence);
    if (!token) return;
    const result = await request<OAuthPreview>("/api/v1/agent/oauth/preview", {
      method: "POST", body: JSON.stringify({ request_token: token }), referrerPolicy: "no-referrer",
    });
    if (sequence !== loadSequence) return;
    if (typeof result.client_name !== "string" || !Array.isArray(result.scopes)
      || result.scopes.length === 0 || result.scopes.some(scope => typeof scope !== "string")) {
      throw new Error("Invalid authorization preview");
    }
    if (!Number.isFinite(result.expires_in_seconds) || result.expires_in_seconds <= 0) {
      throw new ApiError(410, "Expired authorization request");
    }
    preview.value = result;
    previewToken = token;
  } catch (reason) {
    if (sequence === loadSequence) await fail(reason);
  } finally {
    if (sequence === loadSequence) loading.value = false;
  }
}

async function decide(approved: boolean) {
  if (loading.value || submitting.value || completed.value || !preview.value || (approved && unknownScopes.value)) return;
  const token = requestToken();
  if (!token || token !== previewToken) return;
  const sequence = loadSequence;
  submitting.value = true;
  error.value = "";
  try {
    const result = await request<OAuthDecision>("/api/v1/agent/oauth/approve", {
      method: "POST", body: JSON.stringify({ request_token: token, approved }), referrerPolicy: "no-referrer",
    });
    if (sequence !== loadSequence) return;
    if (typeof result.redirect_url !== "string" || !result.redirect_url) throw new Error("Invalid authorization response");
    completed.value = true;
    message.value = approved ? "已允许连接，正在返回 AI 助手…" : "已拒绝连接，正在返回 AI 助手…";
    window.location.assign(result.redirect_url);
  } catch (reason) {
    if (sequence === loadSequence) {
      if (completed.value) error.value = "请求已处理，请返回 AI 助手继续。";
      else await fail(reason);
    }
  } finally {
    if (sequence === loadSequence) submitting.value = false;
  }
}

async function loadGrants(sequence = loadSequence) {
  grantsLoading.value = true;
  grantsError.value = "";
  try {
    const result = await request<OAuthGrant[]>("/api/v1/agent/oauth/grants", { referrerPolicy: "no-referrer" });
    if (sequence === loadSequence) { grants.value = result; grantsLoaded.value = true; }
  } catch (reason) {
    if (sequence !== loadSequence) return;
    if (reason instanceof ApiError && reason.status === 401) await fail(reason);
    else grantsError.value = "暂时无法读取已授权应用，请重试。";
  } finally {
    if (sequence === loadSequence) grantsLoading.value = false;
  }
}

async function revoke(grant: OAuthGrant) {
  if (revokingId.value || grant.revoked_at) return;
  revokingId.value = grant.id;
  grantsError.value = "";
  grantsMessage.value = "";
  try {
    const result = await request<{ status: "revoked" }>("/api/v1/agent/oauth/grants/" + encodeURIComponent(grant.id), {
      method: "DELETE", referrerPolicy: "no-referrer",
    });
    if (result.status !== "revoked") throw new Error("Invalid revocation response");
    grantsMessage.value = "授权已撤销，已保存的私有草稿会保留。";
    await loadGrants();
  } catch (reason) {
    if (reason instanceof ApiError && reason.status === 401) await fail(reason);
    else grantsError.value = "撤销未完成，请重试。";
  } finally { revokingId.value = ""; }
}

onMounted(async () => { await restoreRequest(); void load(); });
watch(() => route.query.request_token, () => {
  if (route.path === "/agent/oauth" && !restoringRequest) {
    restoredRequestToken.value = "";
    recoveryFailed.value = false;
    void load();
  }
});
onBeforeUnmount(() => { loadSequence++; restoredRequestToken.value = ""; });
</script>

<template>
  <main class="agent-oauth content-panel" :aria-busy="loading || submitting" aria-labelledby="agent-oauth-title">
    <h1 id="agent-oauth-title">AI 助手连接授权</h1>
    <p v-if="hasRequestToken">请核对连接请求，只批准你本人刚刚发起的连接。</p>
    <p v-else>查看你已授权的应用，或撤销不再需要的连接。</p>
    <p v-if="loading" role="status">{{ hasRequestToken ? "正在读取连接请求…" : "正在确认登录身份…" }}</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <button v-if="loginRequired" type="button" class="primary-button" @click="loginWithoutRequest">前往登录</button>
    <section v-if="preview && !completed" aria-labelledby="agent-oauth-client">
      <p class="client-caption">客户端自报名称（未经平台核验）</p>
      <h2 id="agent-oauth-client">{{ preview.client_name }}</h2>
      <p>本次连接请求将在约 {{ expiryMinutes }} 分钟后失效。</p>
      <h3>申请的权限</h3>
      <ul>
        <li v-for="scope in preview.scopes" :key="scope">{{ scopeDescription(scope) }}</li>
      </ul>
      <p>保存的成果和孵化内容保持私有。此授权不会发布成果；正式登记或共享前，仍须你在网页核对并确认确切的草稿版本。</p>
      <p v-if="unknownScopes" class="form-error" role="alert">请求包含未识别的权限，请拒绝并联系管理员核对。</p>
      <div class="decision-actions">
        <button type="button" class="primary-button" :disabled="submitting || unknownScopes" @click="decide(true)">{{ submitting ? "正在处理…" : "允许连接" }}</button>
        <button type="button" class="secondary-button" :disabled="submitting" @click="decide(false)">拒绝</button>
      </div>
    </section>
    <button v-if="error && !loading && !completed && requestToken()" type="button" class="secondary-button" @click="load">重新读取请求</button>
    <section aria-labelledby="agent-oauth-grants" :aria-busy="grantsLoading">
      <h2 id="agent-oauth-grants">已授权应用</h2>
      <p>名称由客户端自行提供。撤销后，该连接不能继续访问你的资产和草稿。</p>
      <p v-if="grantsLoading" role="status">正在读取已授权应用…</p>
      <p v-if="grantsError" class="form-error" role="alert">{{ grantsError }}</p>
      <p v-if="grantsMessage" role="status">{{ grantsMessage }}</p>
      <button v-if="grantsError && !grantsLoading" type="button" class="secondary-button" @click="loadGrants()">重试读取授权</button>
      <p v-if="grantsLoaded && !grantsLoading && !grantsError && !grants.length">尚无已授权的应用。</p>
      <ul v-if="grants.length" class="grant-list">
        <li v-for="grant in grants" :key="grant.id">
          <div><strong>{{ grant.client_name }}</strong><p>{{ grant.revoked_at ? "已撤销" : "已授权" }}</p><p>{{ grant.scopes.map(scopeDescription).join("；") }}</p></div>
          <button v-if="!grant.revoked_at" type="button" class="secondary-button" :disabled="!!revokingId" @click="revoke(grant)">{{ revokingId === grant.id ? "正在撤销…" : "撤销授权" }}</button>
        </li>
      </ul>
    </section>
  </main>
</template>

<style scoped>
.agent-oauth { max-width: 760px; margin: 24px auto; padding: 24px; }
.agent-oauth > p, section p { line-height: 1.7; }
section { margin-top: 24px; padding: 24px; background: var(--surface-muted, #f6f7f6); border-radius: 12px; }
.client-caption { color: var(--text-muted, #677164); font-size: 13px; margin-bottom: 8px; }
h2 { overflow-wrap: anywhere; }
li { margin: 12px 0; }
.decision-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; }
.grant-list { padding-left: 0; list-style: none; }
.grant-list li { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
.grant-list strong { overflow-wrap: anywhere; }
.grant-list p { margin: 4px 0; }
@media (max-width: 600px) { .agent-oauth { padding: 16px; margin: 16px auto; } section { padding: 16px; } }
</style>
