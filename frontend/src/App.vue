<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, nextTick, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowRight, Bookmark, Boxes, CalendarClock, ChevronDown, Clock3, CreditCard, FileInput,
  Hexagon, Home, LibraryBig, List, Menu, Pencil, Plus, Search, Shield,
  SlidersHorizontal, Sparkles, Star, UserRound, Users, Workflow, LayoutGrid, Send, X,
} from "lucide-vue-next";

import { useTheme } from "./composables/useTheme";
import { assetReturnContext } from "./lib/assetNavigation";
import { isManagementSearchRoute, loadAIDiscoveryAssets } from "./lib/aiDiscovery";
import { legacyWorkspaceEnabled } from "./lib/workspaceNavigation";
import { safeLoginRedirect } from "./lib/loginNavigation";
import { api, ApiError, setPmSessionToken, resetPmSessionCache, type AIRegistrationType, type Asset, type CurrentUser, type DingTalkIdentity, type Person, type PmSessionUser } from "./lib/api";

useTheme();
const router = useRouter();
const route = useRoute();
const inDingTalkClient = /DingTalk|AliApp\(DingTalk/i.test(navigator.userAgent);
if (route.query.dingtalk === "success") resetPmSessionCache();
const query = ref("");
const mobileOpen = ref(false);
const logoUrl = import.meta.env.BASE_URL + "logo.svg";
const searchOpen = ref(false);
const searchLoading = ref(false); const searchError = ref(""); const searchResultTotal = ref(0);
let searchSequence = 0; let aiSearchCatalog: Promise<AIRegistrationType[]> | undefined;
const searchResults = ref<{ assets: Asset[]; people: Person[] }>({ assets: [], people: [] });
const dingtalkIdentity = ref<DingTalkIdentity | null>(null);
const currentUser = ref<CurrentUser | null>(null);
const verifiedRoleLabel = computed(() => {
  const roles = currentUser.value?.roles || [];
  if (roles.includes("system_admin")) return "系统管理员";
  if (roles.includes("asset_manager")) return "资产管理员";
  if (roles.includes("department_manager")) return "部门主管";
  if (roles.includes("group_leader")) return "组长";
  if (roles.includes("auditor")) return "审计员";
  return "成员";
});
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
  { to: "/my", label: "首页", icon: Home },
  { to: "/my/created", label: "创建", icon: Pencil },
  { to: "/my/responsible", label: "负责", icon: Shield },
  { to: "/my/subscriptions", label: "订阅", icon: CreditCard },
  { to: "/my/using", label: "使用", icon: Clock3 },
  { to: "/my/requests", label: "申请", icon: Send },
  { to: "/my/ai", label: "AI 能力", icon: Hexagon },
  { to: "/my/contributions", label: "贡献", icon: Star },
  { to: "/my/drafts", label: "草稿", icon: List },
  { to: "/my/bookmarks", label: "收藏", icon: Bookmark },
];
const sharedNav = [
  { to: "/discover", label: "AI 资产", icon: LayoutGrid },
  { to: "/workflows", label: "AI 工作流", icon: Workflow },
  { to: "/team", label: "团队 AI 空间", icon: Users },
];
const huduNav = [
  { to: "/hudu", label: "资产库", icon: LibraryBig },
  { to: "/hudu/expirations", label: "到期与交接", icon: CalendarClock },
  { to: "/hudu/intake", label: "资料接入", icon: FileInput },
];
const isHuduMode = computed(() => legacyWorkspaceEnabled(import.meta.env.BASE_URL, window.location.hostname) && (route.path === "/hudu" || route.path.startsWith("/hudu/")));
const isTestEnvironment = window.location.pathname === "/test" || window.location.pathname.startsWith("/test/");
const isLocalDevelopment = ["localhost", "127.0.0.1"].includes(window.location.hostname);
const canManage = computed(() => Boolean(currentUser.value?.roles.some(
  role => ["system_admin", "asset_manager", "department_manager", "group_leader", "auditor"].includes(role),
)));
const environmentLabel = computed(() => isLocalDevelopment ? "本地预览" : isTestEnvironment ? "测试环境" : "生产环境");
const environmentTarget = computed(() => isTestEnvironment ? "/" : "/test/");

const navigationContext = computed(() => route.path.startsWith("/discover/")
  ? assetReturnContext(route.query.returnTo)
  : { path: route.path, category: route.query.category === "workflows" ? "workflows" : "all" });
function isNavActive(to: string) {
  if (to === "/workflows") {
    return navigationContext.value.path === "/workflows" || (navigationContext.value.path === "/discover" && navigationContext.value.category === "workflows");
  }
  if (to === "/discover") {
    return (navigationContext.value.path === "/discover" && navigationContext.value.category !== "workflows") || navigationContext.value.path.startsWith("/discover/");
  }
  if (to === "/manage") {
    return ["/manage", "/map", "/assets", "/accounts", "/organization", "/services", "/governance", "/imports", "/admin", "/intake", "/scenarios"]
      .some(path => navigationContext.value.path === path || navigationContext.value.path.startsWith(path + "/"));
  }
  return navigationContext.value.path === to;
}

const managementSearch = computed(() => canManage.value && isManagementSearchRoute(route.path));
watch([query, managementSearch], ([value, management]) => {
  window.clearTimeout(searchTimer);
  const request = ++searchSequence;
  searchError.value = ""; searchResults.value = { assets: [], people: [] }; searchResultTotal.value = 0;
  if (!value.trim()) { searchOpen.value = false; searchLoading.value = false; return; }
  searchOpen.value = true; searchLoading.value = true;
  searchTimer = window.setTimeout(async () => {
    try {
      let result: { assets: Asset[]; people: Person[] };
      let total = 0;
      if (management) {
        result = await api.search(value.trim()); total = result.assets.length;
      } else {
        if (!aiSearchCatalog) {
          aiSearchCatalog = api.aiRegistrationTypes();
          void aiSearchCatalog.catch(() => { aiSearchCatalog = undefined; });
        }
        const catalog = await aiSearchCatalog;
        const matches = await loadAIDiscoveryAssets(catalog, api.spaceAssets, { scope: "discover", keyword: value.trim() });
        result = { assets: matches.slice(0, 8), people: [] }; total = matches.length;
      }
      if (request !== searchSequence) return;
      searchResults.value = result; searchResultTotal.value = total;
    } catch {
      if (request === searchSequence) searchError.value = "暂时无法搜索，请打开相应资产页重试。";
    } finally { if (request === searchSequence) searchLoading.value = false; }
  }, 250);
});

function openAsset(id: string) {
  const returnTo = router.resolve({ path: "/discover", query: { q: query.value.trim() || undefined } }).fullPath;
  const target = managementSearch.value ? { path: `/assets/${id}` } : { path: `/discover/${id}`, query: { returnTo } };
  searchOpen.value = false; query.value = "";
  void router.push(target);
}

function closeSearchDelayed() {
  window.setTimeout(() => { searchOpen.value = false; }, 150);
}

watch(mobileOpen, async (open) => {
  await nextTick();
  if (open) {
    document.querySelector<HTMLElement>(".primary-sidebar .is-active, .primary-sidebar .brand-block")?.focus();
  } else {
    document.querySelector<HTMLButtonElement>(".fusion-mobile-menu")?.focus();
  }
});

function onViewportChange() { if (window.innerWidth > 760) mobileOpen.value = false; }

function onHotkey(event: KeyboardEvent) {
  if (mobileOpen.value && event.key === "Tab") {
    const controls = [...document.querySelectorAll<HTMLElement>(".primary-sidebar a[href], .primary-sidebar button:not(:disabled)")];
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
  if (event.key === "Escape") mobileOpen.value = false;
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
  if (identityState.value === "outside") return "尚未登录";
  if (identityState.value === "failed") return "身份识别失败，点击重试";
  return "访客预览";
});

async function recognizeIdentity() {
  if (identityState.value === "recognizing") return;
  identityState.value = "recognizing";
  identityHint.value = "";
  try {
    const inDingTalk = inDingTalkClient;
    let bridge = getDingTalkBridge();
    if (!inDingTalk) {
      identityState.value = "outside";
      identityHint.value = "使用钉钉扫码登录，即可在浏览器中查看你的资产与订阅。";
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
      is_group_leader: login.user.roles.includes("group_leader"),
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
    try { currentUser.value = await api.currentSession(); }
    catch (reason) {
      // An expired legacy header must not mask a fresh web-login cookie.
      if (!cached?.sessionToken || !(reason instanceof ApiError) || reason.status !== 401) throw reason;
      resetPmSessionCache();
      currentUser.value = await api.currentSession();
    }
    if (currentUser.value.person_id) localStorage.setItem("account-center-person-id", currentUser.value.person_id);
    dingtalkIdentity.value = currentUser.value.person_id && currentUser.value.display_name ? {
      person_id: currentUser.value.person_id,
      display_name: currentUser.value.display_name,
      department_id: currentUser.value.department_id,
      job_title: currentUser.value.job_title,
      is_department_manager: currentUser.value.roles.includes("department_manager"),
      is_group_leader: currentUser.value.roles.includes("group_leader"),
    } : null;
    identityState.value = "authenticated";
    identityHint.value = "";
  } catch {
    currentUser.value = null;
    dingtalkIdentity.value = null;
    resetPmSessionCache();
    await recognizeIdentity();
  }
}

function openIdentityEntry() {
  if (currentUser.value) { void bootstrapSession(); return; }
  if (inDingTalkClient) { void recognizeIdentity(); return; }
  void router.push({ path: "/login", query: { redirect: safeLoginRedirect(route.fullPath) } });
}

function onSessionChanged() { void bootstrapSession(); }

onMounted(() => { window.addEventListener("keydown", onHotkey); window.addEventListener("resize", onViewportChange); window.addEventListener("pm-session-change", onSessionChanged); void bootstrapSession(); });
onBeforeUnmount(() => { window.clearTimeout(searchTimer); ++searchSequence; window.removeEventListener("keydown", onHotkey); window.removeEventListener("resize", onViewportChange); window.removeEventListener("pm-session-change", onSessionChanged); });
</script>

<template>
  <div class="app-shell new-shell">
    <button v-if="mobileOpen" class="fusion-nav-backdrop" aria-label="关闭导航" @click="mobileOpen = false" />
    <aside id="asset-navigation" class="primary-sidebar" :class="{ 'mobile-open': mobileOpen }"
      :role="mobileOpen ? 'dialog' : undefined" :aria-modal="mobileOpen ? true : undefined" aria-label="资产中心导航">
      <button v-if="mobileOpen" class="icon-button fusion-nav-close" aria-label="关闭侧栏" @click="mobileOpen = false"><X :size="20" aria-hidden="true" /></button>
      <RouterLink to="/my" class="brand-block" @click="mobileOpen = false">
        <img :src="logoUrl" alt="FlipBelt" class="fusion-brand-logo" />
        <span>飞比特 · 资产中心</span>
      </RouterLink>
      <nav class="primary-nav" aria-label="资产中心导航">
        <section class="nav-group" aria-labelledby="personal-nav-heading">
          <h2 id="personal-nav-heading" class="nav-section-label">我的空间</h2>
          <RouterLink v-for="item in personalNav" :key="item.to" :to="item.to" class="nav-item"
            active-class="" exact-active-class="" :class="{ 'is-active': isNavActive(item.to) }"
            :aria-current="isNavActive(item.to) ? 'page' : undefined" @click="mobileOpen = false">
            <component :is="item.icon" :size="20" aria-hidden="true" /><span>{{ item.label }}</span>
          </RouterLink>
        </section>
        <section class="nav-group" aria-labelledby="team-nav-heading">
          <h2 id="team-nav-heading" class="nav-section-label">AI 协作</h2>
          <RouterLink v-for="item in sharedNav" :key="item.to" :to="item.to" class="nav-item"
            active-class="" exact-active-class="" :class="{ 'is-active': isNavActive(item.to) }"
            :aria-current="isNavActive(item.to) ? 'page' : undefined" @click="mobileOpen = false">
            <component :is="item.icon" :size="20" aria-hidden="true" /><span>{{ item.label }}</span>
          </RouterLink>
        </section>
        <section class="nav-group" aria-labelledby="growth-nav-heading">
          <h2 id="growth-nav-heading" class="nav-section-label">探索与成长</h2>
          <div class="nav-item nav-item-pending" aria-disabled="true" title="AI 机会尚未开放">
            <Sparkles :size="20" aria-hidden="true" /><span>AI 机会</span><small>待开放</small>
          </div>
        </section>
        <section v-if="canManage" class="nav-group" aria-labelledby="manage-nav-heading">
          <h2 id="manage-nav-heading" class="nav-section-label">管理区</h2>
          <RouterLink to="/manage" class="nav-item" active-class="" exact-active-class=""
            :class="{ 'is-active': isNavActive('/manage') }" :aria-current="isNavActive('/manage') ? 'page' : undefined"
            @click="mobileOpen = false"><SlidersHorizontal :size="20" aria-hidden="true" /><span>公司资产管理</span></RouterLink>
        </section>
        <section v-if="isHuduMode && canManage" class="nav-group" aria-labelledby="hudu-nav-heading">
          <h2 id="hudu-nav-heading" class="nav-section-label">当前工作区</h2>
          <RouterLink v-for="item in huduNav" :key="item.to" :to="item.to" class="nav-item"
            active-class="" exact-active-class="" :class="{ 'is-active': isNavActive(item.to) }"
            :aria-current="isNavActive(item.to) ? 'page' : undefined" @click="mobileOpen = false">
            <component :is="item.icon" :size="20" aria-hidden="true" /><span>{{ item.label }}</span>
          </RouterLink>
        </section>
      </nav>
      <footer class="sidebar-session">
        <span class="avatar"><UserRound :size="18" aria-hidden="true" /></span>
        <div><strong>{{ dingtalkIdentity?.display_name || currentUser?.display_name || currentUser?.username || "访客" }}</strong>
          <small>{{ currentUser ? verifiedRoleLabel : "未登录" }} · {{ environmentLabel }}</small></div>
      </footer>
    </aside>

    <section class="application-area" :inert="mobileOpen || undefined">
      <header class="topbar">
        <button class="icon-button fusion-mobile-menu" aria-label="打开导航" :aria-expanded="mobileOpen" aria-controls="asset-navigation" @click="mobileOpen = !mobileOpen"><Menu :size="22" /></button>
        <div class="global-search" @focusout="closeSearchDelayed">
          <Search :size="18" />
          <input v-model="query" aria-label="全局搜索" :placeholder="managementSearch ? '搜索公司资源、账号或人员' : '搜索 AI 成果、工作问题或关键词'" @focus="query && (searchOpen = true)" />
          <kbd>Ctrl K</kbd>
          <div v-if="searchOpen" class="search-popover">
            <span v-if="searchLoading" class="search-caption">正在搜索…</span>
            <span v-else-if="searchError" class="search-caption" role="alert">{{ searchError }}</span>
            <template v-else>
              <span class="search-caption">{{ managementSearch ? '公司资源' : 'AI 成果' }}</span>
              <button v-for="item in searchResults.assets" :key="item.id" type="button" @click="openAsset(item.id)">
                <Boxes :size="16" /><span><strong>{{ item.name }}</strong><small>{{ item.asset_code }}</small></span>
              </button>
              <span v-if="managementSearch" class="search-caption">人员</span>
              <button v-for="item in searchResults.people" :key="item.id" type="button" @click="router.push('/organization'); searchOpen = false">
                <Users :size="16" /><span><strong>{{ item.display_name }}</strong><small>{{ item.email || "未登记邮箱" }}</small></span>
              </button>
              <span v-if="!searchResults.assets.length && !searchResults.people.length" class="search-caption">没有找到匹配的{{ managementSearch ? '资源或人员' : 'AI 成果' }}</span>
              <RouterLink v-if="!managementSearch" :to="{ path: '/discover', query: { q: query.trim() } }" class="ai-search-more" @click="searchOpen = false">查看全部匹配成果（{{ searchResultTotal }}）<ArrowRight :size="15" aria-hidden="true" /></RouterLink>
            </template>
          </div>
        </div>
        <div class="topbar-actions">
          <RouterLink :to="isHuduMode ? '/hudu' : '/register'" class="primary-button compact"><Plus :size="16" />登记 AI 成果</RouterLink>
          <a v-if="!isLocalDevelopment" class="environment-switcher" :href="environmentTarget" :title="`切换到${isTestEnvironment ? '生产' : '测试'}环境`"><span class="environment-dot" :class="{ test: isTestEnvironment }" /><span>{{ environmentLabel }}</span><ChevronDown :size="14" /></a>
          <button class="user-menu" type="button" :aria-label="identityLabel + (currentUser ? '，刷新登录状态' : '，登录')" :disabled="identityState === 'recognizing'" :title="identityHint || identityLabel" @click="openIdentityEntry">
            <span class="avatar"><UserRound :size="16" aria-hidden="true" /></span>
            <span>{{ identityLabel }}</span>
            <small v-if="dingtalkIdentity">{{ verifiedRoleLabel !== "成员" ? verifiedRoleLabel : dingtalkIdentity.job_title || "部门成员" }}</small>
            <ChevronDown :size="16" />
          </button>
        </div>
      </header>
      <main class="content-area">
        <section v-if="!currentUser && route.path !== '/login'" class="content-panel auth-session-notice">
          <UserRound :size="22" />
          <div><strong>{{ identityLabel }}</strong><p>{{ identityHint || '登录后查看你的资产与订阅；钉钉内支持免登，普通浏览器支持扫码登录。' }}</p></div>
          <button v-if="identityState !== 'recognizing'" class="secondary-button" type="button" @click="openIdentityEntry">{{ inDingTalkClient ? '重新识别' : '钉钉扫码登录' }}</button>
        </section>
        <!-- Identity state changes must never unmount the business router.  The
             backend remains the authority for protected reads/writes; this
             notice is only a non-blocking client-side status indicator. -->
        <RouterView />
      </main>
    </section>
  </div>
</template>
