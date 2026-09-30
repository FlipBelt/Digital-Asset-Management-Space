<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowRight, QrCode } from "lucide-vue-next";

import { api, resetPmSessionCache } from "../lib/api";
import { dingTalkWebLoginError, safeLoginRedirect } from "../lib/loginNavigation";

const router = useRouter();
const route = useRoute();
const logoUrl = import.meta.env.BASE_URL + "logo.svg";
const username = ref("");
const password = ref("");
const error = ref("");
const submitting = ref(false);
const checking = ref(true);
const finishing = ref(route.query.dingtalk === "success");
const webConfigured = ref(false);
const configurationFailed = ref(false);
const webMessage = ref(dingTalkWebLoginError(route.query.dingtalkError));
const returnPath = computed(() => safeLoginRedirect(route.query.redirect));

async function checkWebLogin() {
  checking.value = true;
  configurationFailed.value = false;
  try { webConfigured.value = (await api.dingtalkWebConfig()).configured; }
  catch { configurationFailed.value = true; webConfigured.value = false; }
  finally { checking.value = false; }
}

function startWebLogin() {
  if (!webConfigured.value || finishing.value || submitting.value) return;
  resetPmSessionCache();
  window.location.assign(api.dingtalkWebAuthorizeUrl(returnPath.value));
}

async function finishWebLogin() {
  // The callback sets an HttpOnly cookie. A URL marker itself grants no access.
  resetPmSessionCache();
  try {
    await api.currentSession();
    window.dispatchEvent(new CustomEvent("pm-session-change"));
    await router.replace(returnPath.value);
  } catch {
    webMessage.value = "扫码授权已返回，但未能建立登录会话，请重新登录。";
    await router.replace({ path: "/login", query: { redirect: returnPath.value } });
  } finally { finishing.value = false; }
}

async function submit() {
  error.value = "";
  submitting.value = true;
  resetPmSessionCache();
  try {
    await api.login(username.value, password.value);
    window.dispatchEvent(new CustomEvent("pm-session-change"));
    await router.replace(returnPath.value);
  } catch {
    error.value = "用户名或密码错误，或账户没有访问权限。";
  } finally { submitting.value = false; }
}

onMounted(() => {
  void checkWebLogin();
  if (finishing.value) void finishWebLogin();
});
</script>

<template>
  <main class="login-page">
    <section class="login-card" aria-labelledby="login-title" :aria-busy="finishing">
      <div class="login-brand"><img :src="logoUrl" alt="FlipBelt" /><small>飞比特 · 资产中心</small></div>
      <div><h1 id="login-title">登录资产中心</h1><p class="login-intro">使用企业钉钉身份，继续你的工作。</p></div>
      <p v-if="finishing" class="login-status" role="status">正在确认登录身份…</p>
      <template v-else>
        <button class="primary-button login-qr-button" type="button" :disabled="checking || !webConfigured || submitting" @click="startWebLogin">
          <QrCode :size="20" aria-hidden="true" /><span>{{ checking ? "正在检查登录服务…" : "钉钉扫码登录" }}</span><ArrowRight :size="18" aria-hidden="true" />
        </button>
        <p class="login-help">在钉钉官方页面扫码并确认，完成后自动返回。普通浏览器也可使用。</p>
        <p v-if="webMessage" class="form-error" role="alert">{{ webMessage }}</p>
        <div v-if="configurationFailed" class="login-status" role="status">
          暂时无法连接登录服务。<button class="login-retry" type="button" @click="checkWebLogin">重试</button>
        </div>
        <p v-else-if="!checking && !webConfigured" class="login-status" role="status">扫码登录尚未配置，请联系管理员，或使用已授权的系统账号。</p>
        <details class="login-account" :open="Boolean(error)">
          <summary>使用系统账号登录</summary>
          <form @submit.prevent="submit">
            <p class="login-help">适用于管理员已为你开通的系统账号。</p>
            <label>用户名<input v-model="username" autocomplete="username" required /></label>
            <label>密码<input v-model="password" type="password" autocomplete="current-password" minlength="12" required /></label>
            <p v-if="error" class="form-error" role="alert">{{ error }}</p>
            <button class="secondary-button" type="submit" :disabled="submitting">{{ submitting ? "正在登录…" : "账号登录" }}</button>
          </form>
        </details>
      </template>
    </section>
  </main>
</template>
