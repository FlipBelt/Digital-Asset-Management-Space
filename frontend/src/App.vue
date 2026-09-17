<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Archive, Bell, Boxes, Building2, ChevronDown, CircleGauge, ClipboardCheck, Database,
  FileInput, GitFork, KeyRound, LayoutDashboard, Network, Plus, Search,
  Settings, UserRound, Users,
} from "lucide-vue-next";

import { useTheme } from "./composables/useTheme";
import { api, setPmSessionToken, clearPmSessionToken, type Asset, type CurrentUser, type DingTalkIdentity, type Person, type PmSessionUser } from "./lib/api";

useTheme();
const router = useRouter();
const route = useRoute();
const query = ref("");
const searchOpen = ref(false);
const searchLoading = ref(false);
const searchResults = ref<{ assets: Asset[]; people: Person[] }>({ assets: [], people: [] });
const dingtalkIdentity = ref<DingTalkIdentity | null>(null);
const currentUser = ref<CurrentUser | null>(null);
const identityState = ref<"idle" | "recognizing" | "authenticated" | "outside" | "failed">("idle");
const identityHint = ref("");
let searchTimer: number | undefined;

declare global {
  interface Window {
    dd?: {
      ready?: (callback: () => void) => void;
      error?: (callback: (error: unknown) => void) => void;
      getAuthCode?: (options: {
        corpId: string;
        onSuccess?: (result: { code?: string; authCode?: string }) => void;
        onFail?: (error: unknown) => void;
      }) => void | Promise<{ code?: string; authCode?: string }>;
      runtime?: { permission?: { requestAuthCode: (options: {
        corpId: string;
        onSuccess: (result: { code: string }) => void;
        onFail: (error: unknown) => void;
      }) => void | Promise<{ code?: string; authCode?: string }> } };
    };
    DingTalkPC?: Window["dd"];
  }
}

type DingTalkBridge = NonNullable<Window["dd"]>;
type DingTalkBridgeSource = "native" | "pc-sdk" | "web-sdk";
type NativeDingTalkBridge = { label: string; source: DingTalkBridgeSource; bridge: DingTalkBridge };

// Official H5 micro-app bridge. It is loaded from index.html before Vue starts;
// the loader below is only a recovery path for a failed initial CDN request.
const DINGTALK_WEB_SDK = "https://g.alicdn.com/dingding/dingtalk-jsapi/2.10.3/dingtalk.open.js";

function supportsAuthCode(bridge: DingTalkBridge | undefined): bridge is DingTalkBridge {
  return Boolean(bridge?.getAuthCode || bridge?.runtime?.permission?.requestAuthCode);
}

function getDingTalkBridge(source: DingTalkBridgeSource = "native"): NativeDingTalkBridge | undefined {
  if (supportsAuthCode(window.dd)) return { label: "dd", source, bridge: window.dd };
  if (supportsAuthCode(window.DingTalkPC)) return { label: "DingTalkPC", source, bridge: window.DingTalkPC };
  return undefined;
}

function waitForDingTalkBridge(timeoutMs = 3000): Promise<NativeDingTalkBridge | undefined> {
  const ready = getDingTalkBridge();
  if (ready) return Promise.resolve(ready);
  return new Promise((resolve) => {
    const started = Date.now();
    const timer = window.setInterval(() => {
      const bridge = getDingTalkBridge();
      if (bridge || Date.now() - started >= timeoutMs) {
        window.clearInterval(timer);
        resolve(bridge);
      }
    }, 80);
  });
}

/**
 * Some desktop versions deliberately do not inject a global bridge into a web app.
 * The legacy PC bundle can expose DingTalkPC while never invoking its auth-code
 * callback on current DingTalk clients.  Use the current H5 JSAPI as the single
 * fallback for both desktop and mobile; a natively injected bridge is always
 * preferred and is never replaced.
 */
function loadDingTalkSdk(source: "web-sdk"): Promise<void> {
  const src = DINGTALK_WEB_SDK;
  const selector = `script[data-account-center-dingtalk-sdk="${source}"]`;
  const existing = document.querySelector<HTMLScriptElement>(selector);
  // The standard JSAPI is injected synchronously by index.html. Do not append
  // a second copy: duplicate bridges can swallow the PC authorization callback.
  if (existing) return Promise.resolve();

  return new Promise((resolve, reject) => {
    const script = existing || document.createElement("script");
    const finish = (error?: Error) => {
      window.clearTimeout(timer);
      if (error) reject(error); else resolve();
    };
    const timer = window.setTimeout(() => finish(new Error("钉钉 JSAPI 加载超时")), 8000);
    script.onload = () => { script.dataset.loaded = "true"; finish(); };
    script.onerror = () => finish(new Error("钉钉 JSAPI 加载失败"));
    if (!existing) {
      script.async = true;
      script.src = src;
      script.dataset.accountCenterDingtalkSdk = source;
      document.head.appendChild(script);
    }
  });
}

async function resolveDingTalkBridge(inDingTalk: boolean): Promise<NativeDingTalkBridge | undefined> {
  const nativeBridge = await waitForDingTalkBridge();
  if (nativeBridge || !inDingTalk) return nativeBridge;

  const source = "web-sdk" as const;
  void sendDingTalkDiagnostic("sdk_load_start", source, "native bridge unavailable; loading matching official SDK");
  try {
    await loadDingTalkSdk(source);
  } catch (reason) {
    void sendDingTalkDiagnostic("sdk_load_failed", source, describeDingTalkError(reason));
    throw reason;
  }
  const bridge = await waitForDingTalkBridge();
  void sendDingTalkDiagnostic(
    bridge ? "sdk_bridge_ready" : "sdk_bridge_unavailable",
    source,
    bridge ? `${bridge.label}:${bridge.bridge.getAuthCode ? "getAuthCode" : "legacy requestAuthCode"}` : "SDK loaded but authorization JSAPI unavailable",
  );
  return bridge;
}

const personalNav = [
  { to: "/", label: "工作台", icon: LayoutDashboard },
  { to: "/my", label: "我的使用", icon: UserRound },
  { to: "/department", label: "部门资产", icon: Building2 },
];
const managementNav = [
  { to: "/scenarios", label: "业务场景", icon: CircleGauge },
  { to: "/map", label: "资产地图", icon: Network },
  { to: "/assets", label: "资产底库", icon: Boxes },
  { to: "/accounts", label: "平台与账号", icon: KeyRound },
  { to: "/organization", label: "人员与授权", icon: Users },
  { to: "/imports", label: "资料接入", icon: FileInput },
  { to: "/governance", label: "治理中心", icon: ClipboardCheck },
  { to: "/services", label: "AI / API 工作台", icon: CircleGauge },
];
const huduNav = [
  { to: "/hudu", label: "资产库", icon: Boxes },
  { to: "/hudu/expirations", label: "到期与交接", icon: ClipboardCheck },
  { to: "/hudu/intake", label: "资料接入", icon: FileInput },
];
const isHuduMode = computed(() => route.path === "/hudu" || route.path.startsWith("/hudu/"));
const isTestEnvironment = window.location.pathname === "/test" || window.location.pathname.startsWith("/test/");
const isLocalDevelopment = ["localhost", "127.0.0.1"].includes(window.location.hostname);
const isSystemAdmin = computed(() => isTestEnvironment || Boolean(currentUser.value?.roles.includes("system_admin")));
const visibleManagementNav = computed(() => managementNav.filter((item) => isTestEnvironment || item.to !== "/scenarios"));
const environmentLabel = computed(() => isLocalDevelopment ? "本地预览" : isTestEnvironment ? "测试环境" : "生产环境");
const environmentTarget = computed(() => isTestEnvironment ? "/" : "/test/");

watch(query, (value) => {
  window.clearTimeout(searchTimer);
  if (!value.trim()) { searchOpen.value = false; return; }
  searchTimer = window.setTimeout(async () => {
    searchLoading.value = true;
    try { searchResults.value = await api.search(value); searchOpen.value = true; }
    finally { searchLoading.value = false; }
  }, 250);
});

function openAsset(id: string) {
  searchOpen.value = false;
  query.value = "";
  router.push(`/assets/${id}`);
}

function closeSearchDelayed() {
  window.setTimeout(() => { searchOpen.value = false; }, 150);
}

function onHotkey(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    document.querySelector<HTMLInputElement>(".global-search input")?.focus();
  }
}

function describeDingTalkError(reason: unknown): string {
  if (reason instanceof Error) return reason.message;
  if (typeof reason === "string") return reason;
  try { return JSON.stringify(reason); } catch { return "未知钉钉客户端错误"; }
}

function requestAuthCode(
  item: NativeDingTalkBridge, corpId: string, timeoutMs = 12000,
): Promise<string> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (code?: string, error?: unknown) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      if (code) resolve(code); else reject(new Error(`${item.label}: ${describeDingTalkError(error)}`));
    };
    const timer = window.setTimeout(() => finish(undefined, "获取授权码超时"), timeoutMs);
    const invoke = () => {
      void sendDingTalkDiagnostic(
        "request_auth_code_invoke",
        item.label,
        item.bridge.getAuthCode ? "getAuthCode" : "runtime.permission.requestAuthCode",
      );
      try {
        const options = {
          corpId,
          onSuccess: ({ code, authCode }: { code?: string; authCode?: string }) => finish(code || authCode, code || authCode ? undefined : "钉钉未返回授权码"),
          onFail: (error: unknown) => finish(undefined, error),
        };
        // Current DingTalk JSAPI.  It may resolve a Promise or use callbacks,
        // depending on the desktop client version; support both once.
        if (item.bridge.getAuthCode) {
          const result = item.bridge.getAuthCode(options);
          if (result && typeof (result as Promise<unknown>).then === "function") {
            void (result as Promise<{ code?: string; authCode?: string }>).then(
              ({ code, authCode }) => finish(code || authCode, code || authCode ? undefined : "钉钉未返回授权码"),
              (error) => finish(undefined, error),
            );
          }
          return;
        }
        // Compatibility only for clients which expose the legacy native bridge.
        const result = item.bridge.runtime?.permission?.requestAuthCode({
          corpId,
          onSuccess: ({ code }) => finish(code),
          onFail: (error) => finish(undefined, error),
        });
        if (result && typeof (result as Promise<unknown>).then === "function") {
          void (result as Promise<{ code?: string; authCode?: string }>).then(
            ({ code, authCode }) => finish(code || authCode, code || authCode ? undefined : "钉钉未返回授权码"),
            (error) => finish(undefined, error),
          );
        }
      } catch (error) { finish(undefined, error); }
    };
    if (!item.bridge.ready) { invoke(); return; }
    item.bridge.error?.((error) => finish(undefined, error));
    item.bridge.ready(() => {
      void sendDingTalkDiagnostic("bridge_ready_callback", item.label, "ready callback fired");
      invoke();
    });
  });
}

async function sendDingTalkDiagnostic(phase: string, bridge: string, message: string) {
  try {
    await api.dingtalkDiagnostic({ phase, bridge, message: message.slice(0, 1000), user_agent: navigator.userAgent });
  } catch { /* diagnostics must not replace the real error */ }
}

function cachedPmUser(): PmSessionUser | null {
  try {
    const value = localStorage.getItem("pm-current-user");
    return value ? JSON.parse(value) as PmSessionUser : null;
  } catch {
    localStorage.removeItem("pm-current-user");
    return null;
  }
}

function resolveCorpId(configuredCorpId: string | null): string | null {
  const read = (params: URLSearchParams) => params.get("corpId") || params.get("corpid");
  return configuredCorpId
    || read(new URLSearchParams(window.location.search))
    || read(new URLSearchParams(window.location.hash.split("?")[1] || ""))
    || localStorage.getItem("pm-dingtalk-corp-id");
}

function rememberPmUser(user: PmSessionUser) {
  setPmSessionToken(user.sessionToken);
  localStorage.setItem("pm-current-user", JSON.stringify(user));
  window.dispatchEvent(new CustomEvent("pm-session-change", { detail: user }));
}

const identityLabel = computed(() => {
  if (dingtalkIdentity.value) return dingtalkIdentity.value.display_name;
  if (currentUser.value) return currentUser.value.display_name || currentUser.value.username;
  if (identityState.value === "recognizing") return "正在识别钉钉身份";
  if (identityState.value === "outside") return "请从钉钉打开";
  if (identityState.value === "failed") return "身份识别失败，点击重试";
  return "访客预览";
});

async function recognizeIdentity() {
  if (identityState.value === "recognizing") return;
  identityState.value = "recognizing";
  identityHint.value = "";
  try {
    const inDingTalk = /DingTalk|AliApp\(DingTalk/i.test(navigator.userAgent);
    let bridge = getDingTalkBridge();
    if (!inDingTalk && !bridge) {
      identityState.value = "outside";
      identityHint.value = "当前是普通浏览器。请从钉钉工作台打开企业应用进行免登。";
      return;
    }
    const status = await api.dingtalkConfig();
    const cachedCorpId = resolveCorpId(status.corp_id);
    if (cachedCorpId) localStorage.setItem("pm-dingtalk-corp-id", cachedCorpId);
    if (!status.configured || !cachedCorpId) throw new Error("钉钉连接尚未配置");
    if (!bridge) bridge = await resolveDingTalkBridge(inDingTalk);
    if (!bridge) {
      identityState.value = inDingTalk ? "failed" : "outside";
      identityHint.value = "钉钉原生 JSAPI 未注入，请检查应用 PC 首页地址、JSAPI 安全域名和客户端版本";
      void sendDingTalkDiagnostic("bridge_unavailable", "none", identityHint.value);
      return;
    }
    void sendDingTalkDiagnostic("bridge_selected", `${bridge.label}:${bridge.source}`, bridge.bridge.getAuthCode ? "getAuthCode" : "legacy requestAuthCode");
    let authCode = "";
    try { authCode = await requestAuthCode(bridge, cachedCorpId); }
    catch (reason) {
      const detail = describeDingTalkError(reason);
      void sendDingTalkDiagnostic("request_auth_code_failed", bridge.label, detail);
      throw reason;
    }
    if (!authCode) throw new Error("钉钉未返回授权码");
    const login = await api.dingtalkLogin(authCode);
    rememberPmUser(login.user);
    currentUser.value = await api.currentSession();
    dingtalkIdentity.value = {
      person_id: currentUser.value.person_id || "",
      display_name: login.user.name,
      department_id: currentUser.value.department_id,
      job_title: currentUser.value.job_title,
      is_department_manager: login.user.roles.includes("department_manager"),
    };
    if (currentUser.value.person_id) localStorage.setItem("account-center-person-id", currentUser.value.person_id);
    identityState.value = "authenticated";
  } catch (reason) {
    identityState.value = /DingTalk/i.test(navigator.userAgent) ? "failed" : "outside";
    identityHint.value = reason instanceof Error ? reason.message : "钉钉身份识别失败";
  }
}

async function bootstrapSession() {
  const cached = cachedPmUser();
  if (cached?.sessionToken) setPmSessionToken(cached.sessionToken);
  try {
    currentUser.value = await api.currentSession();
    if (currentUser.value.person_id) localStorage.setItem("account-center-person-id", currentUser.value.person_id);
    if (currentUser.value.person_id && currentUser.value.display_name) {
      dingtalkIdentity.value = {
        person_id: currentUser.value.person_id,
        display_name: currentUser.value.display_name,
        department_id: currentUser.value.department_id,
        job_title: currentUser.value.job_title,
        is_department_manager: currentUser.value.roles.includes("department_manager"),
      };
      identityState.value = "authenticated";
    }
  } catch {
    if (cached) {
      localStorage.removeItem("pm-current-user");
      clearPmSessionToken();
      window.dispatchEvent(new CustomEvent("pm-session-change", { detail: null }));
    }
    await recognizeIdentity();
  }
}

function onSessionChanged() { void bootstrapSession(); }

onMounted(() => { window.addEventListener("keydown", onHotkey); window.addEventListener("pm-session-change", onSessionChanged); void bootstrapSession(); });
onBeforeUnmount(() => { window.removeEventListener("keydown", onHotkey); window.removeEventListener("pm-session-change", onSessionChanged); });
</script>

<template>
  <div class="app-shell new-shell">
    <aside class="primary-sidebar">
      <div class="brand-block">
        <div class="brand-mark"><GitFork :size="20" /></div>
        <div><strong>集团数字资产中心</strong><span>看清资产 · 明确责任 · 安全交接</span></div>
      </div>
      <div class="sidebar-user-chip">
        <strong>{{ dingtalkIdentity?.display_name || currentUser?.display_name || currentUser?.username || "访客" }} <span>{{ dingtalkIdentity ? (dingtalkIdentity.is_department_manager ? "主管" : "成员") : currentUser ? "本地账号" : "未登录" }}</span></strong>
        <small>{{ dingtalkIdentity?.job_title || (currentUser ? "本地开发会话" : "从钉钉打开后加载个人数据范围") }}</small>
      </div>

      <nav v-if="!isHuduMode" class="primary-nav" aria-label="个人工作">
        <span class="nav-section-label">我的工作</span>
        <RouterLink v-for="item in personalNav" :key="item.to" :to="item.to" class="nav-item">
          <component :is="item.icon" :size="18" /><span>{{ item.label }}</span>
        </RouterLink>
        <span class="nav-section-label">资产管理</span>
        <RouterLink v-for="item in visibleManagementNav" :key="item.to" :to="item.to" class="nav-item">
          <component :is="item.icon" :size="18" /><span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <nav v-else class="primary-nav hudu-sidebar-nav" aria-label="资产库工作区">
        <span class="nav-section-label">资产工作区</span>
        <RouterLink v-for="item in huduNav" :key="item.to" :to="item.to" class="nav-item">
          <component :is="item.icon" :size="18" /><span>{{ item.label }}</span>
        </RouterLink>
        <span class="nav-section-label">其他视图</span>
        <RouterLink to="/assets" class="nav-item"><Archive :size="18" /><span>原始资产底库</span></RouterLink>
      </nav>

      <div class="sidebar-spacer" />
      <div class="sidebar-quick-entry">
        <span>发现新账号、服务或系统？</span>
        <RouterLink :to="isHuduMode ? '/hudu' : '/intake'" class="sidebar-create"><Plus :size="17" />登记 / 发现资产</RouterLink>
      </div>
      <div class="product-switcher">
        <div class="product-item is-active"><Database :size="17" />数字资产管理</div>
        <RouterLink to="/services" class="product-item"><CircleGauge :size="17" />服务与用量</RouterLink>
        <RouterLink v-if="isSystemAdmin" to="/admin" class="product-item"><Settings :size="17" />系统设置</RouterLink>
      </div>
    </aside>

    <section class="application-area">
      <header class="topbar">
        <div class="global-search" @focusout="closeSearchDelayed">
          <Search :size="18" />
          <input v-model="query" aria-label="全局搜索" placeholder="搜索平台、账号、系统、人员或资产" @focus="query && (searchOpen = true)" />
          <kbd>Ctrl K</kbd>
          <div v-if="searchOpen" class="search-popover">
            <span v-if="searchLoading" class="search-caption">正在搜索…</span>
            <template v-else>
              <span class="search-caption">资产</span>
              <button v-for="item in searchResults.assets" :key="item.id" type="button" @click="openAsset(item.id)">
                <Boxes :size="16" /><span><strong>{{ item.name }}</strong><small>{{ item.asset_code }}</small></span>
              </button>
              <span class="search-caption">人员</span>
              <button v-for="item in searchResults.people" :key="item.id" type="button" @click="router.push('/organization'); searchOpen = false">
                <Users :size="16" /><span><strong>{{ item.display_name }}</strong><small>{{ item.email || "未登记邮箱" }}</small></span>
              </button>
            </template>
          </div>
        </div>
        <div class="topbar-actions">
          <RouterLink :to="isHuduMode ? '/hudu' : '/intake'" class="primary-button compact"><Plus :size="16" />登记资产</RouterLink>
          <button class="icon-button" type="button" aria-label="通知"><Bell :size="19" /></button>
          <a v-if="!isLocalDevelopment" class="environment-switcher" :href="environmentTarget" :title="`切换到${isTestEnvironment ? '生产' : '测试'}环境`"><span class="environment-dot" :class="{ test: isTestEnvironment }" /><span>{{ environmentLabel }}</span><ChevronDown :size="14" /></a>
          <button class="user-menu" type="button" :disabled="identityState === 'recognizing'" :title="identityHint || identityLabel" @click="recognizeIdentity">
            <span class="avatar">{{ (dingtalkIdentity?.display_name || currentUser?.display_name || currentUser?.username || "访").slice(0, 1) }}</span>
            <span>{{ identityLabel }}</span>
            <small v-if="dingtalkIdentity">{{ dingtalkIdentity.is_department_manager ? "部门主管" : dingtalkIdentity.job_title || "部门成员" }}</small>
            <ChevronDown :size="16" />
          </button>
        </div>
      </header>
      <main class="content-area">
        <section v-if="!currentUser" class="content-panel auth-session-notice">
          <UserRound :size="22" />
          <div><strong>{{ identityLabel }}</strong><p>{{ identityHint || '请从钉钉工作台打开应用完成身份识别，以加载你的数据范围。' }}</p><RouterLink v-if="!isHuduMode" to="/login" class="hudu-login-link">本地开发登录</RouterLink><RouterLink v-else to="/login?redirect=/hudu" class="hudu-login-link">本地开发登录后查看完整数据</RouterLink></div>
          <button v-if="identityState !== 'recognizing'" class="secondary-button" type="button" @click="recognizeIdentity">重新识别</button>
        </section>
        <!-- Identity state changes must never unmount the business router.  The
             backend remains the authority for protected reads/writes; this
             notice is only a non-blocking client-side status indicator. -->
        <RouterView />
      </main>
    </section>
  </div>
</template>
