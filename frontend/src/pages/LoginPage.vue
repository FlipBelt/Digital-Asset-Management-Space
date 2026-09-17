<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { KeyRound } from "lucide-vue-next";

import { api } from "../lib/api";

const router = useRouter();
const route = useRoute();
const username = ref("");
const password = ref("");
const error = ref("");
const submitting = ref(false);

async function submit() {
  error.value = "";
  submitting.value = true;
  try {
    await api.login(username.value, password.value);
    window.dispatchEvent(new CustomEvent("pm-session-change"));
    const redirect = typeof route.query.redirect === "string" && route.query.redirect.startsWith("/") ? route.query.redirect : "/";
    await router.replace(redirect);
  } catch {
    error.value = "用户名或密码错误，或账户没有访问权限。";
  } finally {
    submitting.value = false;
  }
}

</script>

<template>
  <main class="login-page">
    <form class="login-card" @submit.prevent="submit">
      <div class="login-brand"><span class="brand-mark"><KeyRound :size="22" /></span><div><strong>集团账号中台</strong><small>数字资产统一底库</small></div></div>
      <h1>登录</h1>
      <p>请使用已授权的系统账号访问。</p>
      <label>用户名<input v-model="username" autocomplete="username" required /></label>
      <label>密码<input v-model="password" type="password" autocomplete="current-password" minlength="12" required /></label>
      <p v-if="error" class="form-error">{{ error }}</p>
      <button class="primary-button" type="submit" :disabled="submitting">{{ submitting ? "正在登录…" : "登录" }}</button>
    </form>
  </main>
</template>
