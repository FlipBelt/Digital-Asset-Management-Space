import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { afterEach, test } from "node:test";

// An isolated checkout may reuse an existing dependency installation without copying it.
const dependencies = createRequire(process.env.ASSET_FRONTEND_DEPENDENCY_ROOT
  ? pathToFileURL(resolve(process.env.ASSET_FRONTEND_DEPENDENCY_ROOT, "package.json"))
  : new URL("../package.json", import.meta.url));
const Vue = dependencies("vue");
const { createMemoryHistory, createRouter } = dependencies("vue-router");
const { compileScript, compileTemplate, parse } = dependencies("@vue/compiler-sfc");
const ts = dependencies("typescript");
class ApiError extends Error { constructor(status, message) { super(message); this.status = status; } }
const transport = {
  ApiError,
  api: { currentSession: () => globalThis.__agentOAuthTransport.session() },
  request: (path, init) => globalThis.__agentOAuthTransport.request(path, init),
};
function evaluateTypescript(source, imports = {}) {
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } });
  const module = { exports: {} };
  new Function("require", "module", "exports", output.outputText)(name => imports[name] ?? dependencies(name), module, module.exports);
  return module.exports;
}
const navigation = evaluateTypescript(await readFile("src/lib/loginNavigation.ts", "utf8"));
const filename = "src/pages/AgentOAuthPage.vue";
const { descriptor } = parse(await readFile(filename, "utf8"), { filename });
const script = compileScript(descriptor, { id: "agent-oauth-test" });
const { default: Page } = evaluateTypescript(script.content, { "../lib/api": transport, "../lib/loginNavigation": navigation });
const template = compileTemplate({
  source: descriptor.template.content, filename, id: "agent-oauth-test",
  compilerOptions: { mode: "function", bindingMetadata: script.bindings },
});
assert.deepEqual(template.errors, []);
const ClientPage = { ...Page, render: new Function("Vue", template.code)(Vue) };
const apps = [];
const originalWindow = globalThis.window;
afterEach(() => {
  for (const app of apps.splice(0)) app.unmount();
  globalThis.window = originalWindow;
  delete globalThis.__agentOAuthTransport;
});
const node = (type, text = "") => ({ type, text, props: {}, children: [], parent: null });
const detach = element => {
  if (!element.parent) return;
  const siblings = element.parent.children;
  const index = siblings.indexOf(element);
  if (index >= 0) siblings.splice(index, 1);
  element.parent = null;
};
const renderer = Vue.createRenderer({
  createElement: type => node(type), createComment: text => node("comment", text), createText: text => node("text", text),
  insert(element, parent, anchor) {
    detach(element);
    const index = anchor ? parent.children.indexOf(anchor) : -1;
    parent.children.splice(index < 0 ? parent.children.length : index, 0, element);
    element.parent = parent;
  },
  remove: detach,
  patchProp(element, key, previous, value) { element.props[key] = value; },
  setText(element, text) { element.text = text; },
  setElementText(element, text) { element.text = text; element.children = []; },
  parentNode: element => element.parent,
  nextSibling: element => element.parent?.children[element.parent.children.indexOf(element) + 1] || null,
});
const content = element => element.text + element.children.map(content).join("");
const find = (element, predicate) => predicate(element) ? element : element.children.map(child => find(child, predicate)).find(Boolean);
const button = (root, label) => find(root, element => element.type === "button" && content(element).includes(label));
const flush = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick(); };
const token = "mrq_" + "A".repeat(43);
const preview = {
  client_name: "Unverified <client>", expires_in_seconds: 300,
  scopes: ["asset:read", "asset:draft", "incubation:read", "incubation:write"],
};
async function mountPage({ query = { request_token: token }, read = preview, sessionError, approve, grants = [], revoke,
  storage = new Map(), storageBlocked = false, base = "" } = {}) {
  const calls = [];
  const redirects = [];
  let sessionRead = false;
  globalThis.window = {
    location: { assign: url => redirects.push(url) },
    sessionStorage: {
      getItem(key) { if (storageBlocked) throw new Error("Storage unavailable"); return storage.get(key) ?? null; },
      setItem(key, value) { if (storageBlocked) throw new Error("Storage unavailable"); storage.set(key, value); },
      removeItem(key) { if (storageBlocked) throw new Error("Storage unavailable"); storage.delete(key); },
    },
  };
  globalThis.__agentOAuthTransport = {
    session: async () => { sessionRead = true; if (sessionError) throw sessionError; return { csrf_token: "fixture" }; },
    request: async (path, init) => {
      assert.equal(sessionRead, true, "session and CSRF must be loaded before the request");
      calls.push([path, init]);
      if (path.endsWith("/grants")) return grants;
      if (init.method === "DELETE") { if (revoke) await revoke(path, init); return { status: "revoked" }; }
      if (path.endsWith("/preview")) { if (read instanceof Error) throw read; return typeof read === "function" ? read(JSON.parse(init.body)) : read; }
      if (approve) return approve(path, init);
      return { redirect_url: "qwenwork-cn://mcp-oauth?code=server-receipt" };
    },
  };
  const router = createRouter({ history: createMemoryHistory(base), routes: [
    { path: "/agent/oauth", component: ClientPage }, { path: "/login", component: { render: () => null } },
  ] });
  await router.push({ path: "/agent/oauth", query });
  const root = node("root");
  const app = renderer.createApp(ClientPage);
  app.use(router);
  app.provide(Vue.ssrContextKey, { modules: new Set() });
  app.mount(root); apps.push(app);
  await flush();
  return { root, router, calls, redirects, storage };
}

test("preview explains the unverified name and private scopes without auto approving or exposing the request token", async () => {
  const { root, calls, redirects } = await mountPage();
  const previews = calls.filter(([path]) => path.endsWith("/preview"));
  assert.equal(previews.length, 1);
  assert.deepEqual(JSON.parse(previews[0][1].body), { request_token: token });
  assert.equal(previews[0][1].referrerPolicy, "no-referrer");
  assert.equal(calls.filter(([path]) => path.endsWith("/approve")).length, 0);
  assert.match(content(root), /未经平台核验/);
  assert.match(content(root), /私有/);
  assert.match(content(root), /确切的草稿版本/);
  assert.ok(button(root, "允许连接"));
  assert.ok(button(root, "拒绝"));
  assert.doesNotMatch(content(root), new RegExp(token));
  assert.deepEqual(redirects, []);
});

test("allow posts a deliberate decision once and follows only the returned redirect", async () => {
  let finish;
  const { root, calls, redirects } = await mountPage({
    query: { request_token: token, redirect: "https://untrusted.invalid/callback" },
    approve: () => new Promise(resolve => { finish = resolve; }),
  });
  const allow = button(root, "允许连接");
  const pending = allow.props.onClick();
  await allow.props.onClick();
  const decisions = calls.filter(([path]) => path.endsWith("/approve"));
  assert.equal(decisions.length, 1);
  assert.deepEqual(JSON.parse(decisions[0][1].body), { request_token: token, approved: true });
  assert.deepEqual(redirects, []);
  finish({ redirect_url: "qwenwork-cn://mcp-oauth?code=approved-receipt" });
  await pending; await flush();
  assert.deepEqual(redirects, ["qwenwork-cn://mcp-oauth?code=approved-receipt"]);
});

test("reject posts false and does not grant access", async () => {
  const { root, calls, redirects } = await mountPage();
  await button(root, "拒绝").props.onClick(); await flush();
  assert.deepEqual(JSON.parse(calls.find(([path]) => path.endsWith("/approve"))[1].body), { request_token: token, approved: false });
  assert.equal(redirects.length, 1);
  assert.match(content(root), /已拒绝连接/);
});

test("a failed decision shows a fixed error and never follows a query redirect", async () => {
  const { root, redirects } = await mountPage({
    query: { request_token: token, redirect: "https://untrusted.invalid/callback" },
    approve: async () => { throw new ApiError(410, "sensitive " + token); },
  });
  await button(root, "允许连接").props.onClick(); await flush();
  assert.match(content(root), /已失效/);
  assert.doesNotMatch(content(root), /sensitive|mrq_/);
  assert.deepEqual(redirects, []);
});

test("login URLs contain only a local recovery handle and consent resumes once in the same mount", async () => {
  const { router, calls, storage } = await mountPage({
    query: { request_token: token, redirect: "https://untrusted.invalid" }, sessionError: new ApiError(401, token),
    base: "/test/",
  });
  await flush();
  assert.equal(router.currentRoute.value.path, "/login");
  const target = new URL(router.currentRoute.value.query.redirect, "https://asset-center.invalid");
  assert.equal(target.pathname, "/agent/oauth");
  assert.match(target.searchParams.get("resume"), /^[0-9a-f-]{36}$/);
  assert.doesNotMatch(router.currentRoute.value.fullPath, /request_token|mrq_|untrusted/);
  assert.deepEqual(calls, []);
  assert.equal(storage.size, 1);
  const restored = await mountPage({ query: { resume: target.searchParams.get("resume") }, storage, base: "/test/" });
  assert.equal(restored.router.currentRoute.value.fullPath, "/agent/oauth");
  assert.equal(storage.size, 0);
  assert.deepEqual(JSON.parse(restored.calls.find(([path]) => path.endsWith("/preview"))[1].body), { request_token: token });
  assert.ok(button(restored.root, "允许连接"));
  assert.equal(restored.calls.filter(([path]) => path.endsWith("/approve")).length, 0);
  assert.doesNotMatch(content(restored.root), /mrq_/);
  const replayed = await mountPage({ query: { resume: target.searchParams.get("resume") }, storage, base: "/test/" });
  assert.match(content(replayed.root), /无法恢复/);
  assert.deepEqual(replayed.calls, []);
});

test("recovery is bound to the frontend mount and expired records cannot approve", async () => {
  const pending = await mountPage({ sessionError: new ApiError(401, "Login required") });
  const target = new URL(pending.router.currentRoute.value.query.redirect, "https://asset-center.invalid");
  const query = { resume: target.searchParams.get("resume") };
  const wrongMount = await mountPage({ query, storage: pending.storage, base: "/test/" });
  assert.match(content(wrongMount.root), /无法恢复/);
  assert.deepEqual(wrongMount.calls, []);
  assert.equal(button(wrongMount.root, "允许连接"), undefined);
  const [key, value] = [...pending.storage][0];
  pending.storage.set(key, JSON.stringify({ ...JSON.parse(value), expires_at: Date.now() - 1 }));
  const expired = await mountPage({ query, storage: pending.storage });
  assert.match(content(expired.root), /无法恢复/);
  assert.equal(pending.storage.size, 0);
  assert.deepEqual(expired.calls, []);
  assert.equal(expired.router.currentRoute.value.fullPath, "/agent/oauth");
});

test("blocked session storage fails safely and offers a login URL without the pending request", async () => {
  const { root, router, calls } = await mountPage({ sessionError: new ApiError(401, token), storageBlocked: true });
  assert.match(content(root), /无法暂存/);
  assert.doesNotMatch(content(root), /mrq_/);
  assert.deepEqual(calls, []);
  assert.equal(button(root, "允许连接"), undefined);
  await button(root, "前往登录").props.onClick(); await flush();
  assert.equal(router.currentRoute.value.path, "/login");
  assert.equal(router.currentRoute.value.query.redirect, "/agent/oauth?restart=1");
  assert.doesNotMatch(router.currentRoute.value.fullPath, /request_token|mrq_/);
});

test("expired or failed previews show a fixed error without leaking server details and can be reread", async () => {
  const { root, calls, redirects } = await mountPage({ read: new ApiError(410, "sensitive " + token) });
  assert.match(content(root), /已失效/);
  assert.doesNotMatch(content(root), /sensitive|mrq_/);
  assert.equal(button(root, "允许连接"), undefined);
  await button(root, "重新读取请求").props.onClick(); await flush();
  assert.equal(calls.filter(([path]) => path.endsWith("/preview")).length, 2);
  assert.deepEqual(redirects, []);
});

test("unknown scopes cannot be approved but can be refused", async () => {
  const { root, calls } = await mountPage({ read: { ...preview, scopes: ["asset:publish"] } });
  assert.equal(button(root, "允许连接").props.disabled, true);
  await button(root, "允许连接").props.onClick();
  assert.equal(calls.filter(([path]) => path.endsWith("/approve")).length, 0);
  await button(root, "拒绝").props.onClick();
  assert.equal(calls.filter(([path]) => path.endsWith("/approve")).length, 1);
});

test("an absent request opens grant management while duplicate tokens do not offer approval", async () => {
  const managed = await mountPage({ query: {} });
  assert.match(content(managed.root), /查看你已授权的应用/);
  assert.equal(button(managed.root, "允许连接"), undefined);
  assert.deepEqual(managed.calls.map(([path]) => path), ["/api/v1/agent/oauth/grants"]);
  for (const query of [{ request_token: [token, "another-request"] }, { request_token: "" }]) {
    const { root, calls } = await mountPage({ query });
    assert.match(content(root), /缺失或无效/);
    assert.equal(button(root, "允许连接"), undefined);
    assert.deepEqual(calls, []);
  }
});

test("a safe restart marker asks for a new request while keeping grant management available", async () => {
  const { root, calls } = await mountPage({ query: { restart: "1" } });
  assert.match(content(root), /重新发起连接请求/);
  assert.equal(button(root, "允许连接"), undefined);
  assert.deepEqual(calls.map(([path]) => path), ["/api/v1/agent/oauth/grants"]);
});

test("revocation requires a click, targets only the selected grant, and reads the result back", async () => {
  const grants = [{ id: "owned-grant", client_name: "My AI client", scopes: ["asset:draft"], expires_at: null, revoked_at: null }];
  let finish;
  const { root, calls } = await mountPage({ query: {}, grants,
    revoke: async path => {
      assert.equal(path, "/api/v1/agent/oauth/grants/owned-grant");
      await new Promise(resolve => { finish = resolve; });
      grants[0].revoked_at = "2026-10-16T00:00:00Z";
    },
  });
  assert.equal(calls.filter(([, init]) => init.method === "DELETE").length, 0);
  const control = button(root, "撤销授权");
  const pending = control.props.onClick();
  await control.props.onClick();
  assert.equal(calls.filter(([, init]) => init.method === "DELETE").length, 1);
  finish(); await pending; await flush();
  assert.match(content(root), /已撤销/);
  assert.match(content(root), /私有草稿会保留/);
  assert.equal(button(root, "撤销授权"), undefined);
  assert.equal(calls.filter(([path]) => path.endsWith("/grants")).length, 2);
});

test("changing the request ignores an older preview response and binds the decision to the displayed client", async () => {
  let finishOld;
  const replacement = "mrq_" + "B".repeat(43);
  const { root, router, calls } = await mountPage({ read: body => body.request_token === token
    ? new Promise(resolve => { finishOld = resolve; }) : { ...preview, client_name: "Current client" } });
  await router.replace({ path: "/agent/oauth", query: { request_token: replacement } }); await flush();
  finishOld({ ...preview, client_name: "Previous client" }); await flush();
  assert.match(content(root), /Current client/);
  assert.doesNotMatch(content(root), /Previous client/);
  await button(root, "允许连接").props.onClick();
  const decision = calls.find(([path]) => path.endsWith("/approve"));
  assert.equal(JSON.parse(decision[1].body).request_token, replacement);
});
