<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ApiError, request } from "../lib/api";
type Grant = { id: string; client_name: string; expires_at: string | null; revoked_at: string | null };
const ttl = ref(24); const code = ref(""); const client = ref(""); const grants = ref<Grant[]>([]);
const busy = ref(false); const message = ref(""); const error = ref("");
function fail(reason: unknown) {
  client.value = "";
  error.value = reason instanceof ApiError && reason.status === 401
    ? "请先登录资产中心，再返回此页授权。" : reason instanceof Error ? reason.message : "请求失败，请重试";
}
async function load() {
  try { grants.value = await request<Grant[]>("/api/v1/agent/grants"); }
  catch (reason) { fail(reason); }
}
async function preview() {
  busy.value = true; error.value = ""; message.value = ""; client.value = "";
  code.value = code.value.replace(/[ -]/g, "").toUpperCase();
  try {
    const result = await request<{ client_name: string; expires_in_hours: number }>("/api/v1/agent/device/preview",
      { method: "POST", body: JSON.stringify({ user_code: code.value }) });
    client.value = result.client_name; ttl.value = result.expires_in_hours;
  } catch (reason) { fail(reason); } finally { busy.value = false; }
}
async function decide(approved: boolean) {
  busy.value = true; error.value = "";
  try {
    await request("/api/v1/agent/device/approve", { method: "POST",
      body: JSON.stringify({ user_code: code.value, approved }) });
    message.value = approved ? "授权完成，请返回 AI 助手继续。你可以随时在此撤销。" : "已拒绝此次连接。";
    client.value = ""; code.value = ""; await load();
  } catch (reason) { fail(reason); } finally { busy.value = false; }
}
async function revoke(id: string) {
  busy.value = true; error.value = "";
  try {
    await request("/api/v1/agent/grants/" + id, { method: "DELETE" });
    message.value = "授权已撤销。"; await load();
  } catch (reason) { fail(reason); } finally { busy.value = false; }
}
onMounted(load);
</script>
<template>
  <main class="agent-connect content-panel">
    <h1>连接 AI 助手</h1>
    <p>输入你正在使用的 Codex 或 Qoder-CN 显示的 8 位授权码。只批准你本人发起的连接。</p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <form @submit.prevent="preview">
      <label for="agent-code">授权码</label>
      <input id="agent-code" v-model="code" maxlength="12" autocomplete="off" spellcheck="false"
        required :disabled="busy || !!client" placeholder="例如 ABCD2345">
      <button class="primary-button" :disabled="busy || !!client">查看连接请求</button>
    </form>
    <section v-if="client" aria-label="授权范围">
      <h2>{{ client }} 请求连接</h2>
      <p>允许查看你有权访问的 AI 成果、保存和修改你自己的私有草稿与孵化摘要。授权将在 {{ ttl }} 小时后过期。</p>
      <p>最终登记仍需你在资产页面预览并确认。共享范围也由你选择。</p>
      <button class="primary-button" :disabled="busy" @click="decide(true)">允许连接</button>
      <button class="secondary-button" :disabled="busy" @click="decide(false)">拒绝</button>
    </section>
    <h2>我的连接</h2>
    <p v-if="!grants.length">尚无已授权的连接。</p>
    <ul>
      <li v-for="grant in grants" :key="grant.id">
        {{ grant.client_name }} ·
        {{ grant.revoked_at ? "已撤销" : grant.expires_at ? "到期：" + new Date(grant.expires_at).toLocaleString() : "等待领取" }}
        <button v-if="!grant.revoked_at" class="secondary-button" :disabled="busy" @click="revoke(grant.id)">撤销</button>
      </li>
    </ul>
  </main>
</template>
<style scoped>
.agent-connect { max-width: 760px; margin: 24px auto; padding: 24px; }
form { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 24px 0; }
input { max-width: 180px; padding: 10px; font: inherit; text-transform: uppercase; }
section { margin: 24px 0; padding: 16px; background: var(--surface-muted, #f5f7f8); border-radius: 12px; }
button { margin-right: 8px; } li { margin: 12px 0; }
</style>
