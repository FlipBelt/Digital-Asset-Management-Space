import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { createRenderer, createSSRApp, nextTick, ssrContextKey } from "vue";
import { renderToString } from "@vue/server-renderer";
import { createMemoryHistory, createRouter } from "vue-router";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error" });
after(() => server.close());
const { api } = await server.ssrLoadModule("/src/lib/api.ts");
const framework = await server.ssrLoadModule("/src/lib/managementWorkspace.ts");
const { default: Assets } = await server.ssrLoadModule("/src/pages/AssetsPage.vue");
const { default: Intake } = await server.ssrLoadModule("/src/pages/IntakePage.vue");
const { default: Followup } = await server.ssrLoadModule("/src/pages/AssetFollowupPage.vue");
const { default: Nav } = await server.ssrLoadModule("/src/components/ManagementNav.vue");
const renderer = createRenderer({
  createElement: type => ({ type, children: [] }), createComment: text => ({ text }), createText: text => ({ text }),
  insert(node, parent) { parent.children.push(node); }, remove() {}, patchProp() {},
  setText(node, text) { node.text = text; }, setElementText(node, text) { node.text = text; },
  parentNode: () => null, nextSibling: () => null,
});
const apps = [];
afterEach(() => { for (const app of apps.splice(0)) app.unmount(); });
const categories = [{ id: "systems", name: "公司自研系统", sort_order: 20 }, { id: "accounts", name: "平台与账号", sort_order: 10 }];
const types = [{ id: "system", category_id: "systems", name: "自研系统" }, { id: "identity", category_id: "accounts", name: "注册身份" }];
const queries = [];
function mockReads() {
  queries.length = 0;
  api.currentSession = async () => ({ roles: ["system_admin"], permissions: ["asset.write"] });
  api.assetTypes = async () => types;
  api.assetCategories = async () => categories;
  for (const key of ["departments", "legalEntities", "people", "platforms", "registrationIdentities", "platformTenants", "accounts", "providers"]) api[key] = async () => [];
  api.assets = async query => { queries.push(query); return { data: [], pagination: { total: 0 } }; };
  api.huduExpirations = async () => ({ window_days: 30, items: [] });
}
async function setup(Page, path = "/assets") {
  mockReads();
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:pathMatch(.*)*", component: { render: () => null } }] });
  await router.push(path);
  let state;
  const app = renderer.createApp({ setup() { state = Page.setup({}, { expose() {} }); return () => null; } });
  app.use(router); app.provide(ssrContextKey, { modules: new Set() });
  app.mount({ children: [] }); apps.push(app);
  await new Promise(resolve => setImmediate(resolve));
  return { state, router };
}

test("retired workspace links retain asset identity and operational follow-up", () => {
  assert.equal(framework.retiredWorkspaceTarget("/hudu"), "/assets");
  assert.equal(framework.retiredWorkspaceTarget("/hudu/assets/kept-id"), "/assets/kept-id");
  assert.equal(framework.retiredWorkspaceTarget("/hudu/expirations"), "/manage/followup");
  assert.equal(framework.retiredWorkspaceTarget("/hudu/intake"), "/imports");
  assert.equal(framework.retiredWorkspaceTarget("/department"), "/assets");
  assert.equal(framework.retiredWorkspaceTarget("/my"), null);
});
test("employee, reviewer and global administrator keep distinct entry permissions", () => {
  const user = roles => ({ roles, permissions: [] });
  assert.deepEqual(framework.managementItems(user(["employee"])), []);
  assert.equal(framework.canRegisterBasics(user(["department_manager"])), false);
  assert.equal(framework.managementItems(user(["department_manager"])).some(item => item.key === "settings"), false);
  assert.equal(framework.managementItems(user(["auditor"])).some(item => item.key === "reviews"), false);
  assert.equal(framework.managementItems(user(["asset_manager"])).some(item => item.key === "imports"), true);
  assert.equal(framework.managementItems(user(["system_admin"])).some(item => item.key === "settings"), true);
});
test("shared management navigation identifies the active settings context", async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:pathMatch(.*)*", component: { render: () => null } }] });
  await router.push("/manage?tab=settings");
  const app = createSSRApp(Nav, { user: { roles: ["system_admin"], permissions: [] } }); app.use(router);
  const html = await renderToString(app);
  assert.match(html, /aria-current="page"[^>]*>系统设置/);
  assert.doesNotMatch(html, /原资产工作区|台账/);
});
test("category selection resets pagination and incompatible type while preserving search and department", async () => {
  const { state, router } = await setup(Assets, "/assets?type=identity");
  state.businessPage.value = 3; state.businessFilters.keyword = "报表"; state.businessFilters.department_id = "design";
  await state.selectBusinessCategory("systems");
  assert.equal(state.businessPage.value, 1);
  assert.equal(state.businessFilters.asset_type_id, "");
  assert.equal(router.currentRoute.value.query.category, "systems");
  assert.equal(router.currentRoute.value.query.type, undefined);
  assert.deepEqual(state.availableBusinessTypes.value.map(item => item.id), ["system"]);
  assert.deepEqual([queries.at(-1).category_id, queries.at(-1).keyword, queries.at(-1).department_id, queries.at(-1).page], ["systems", "报表", "design", 1]);
});
test("query-only navigation restores category, type and trash using server queries", async () => {
  const { state, router } = await setup(Assets);
  await router.push("/assets?category=accounts&type=identity&trash=1");
  await nextTick(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(state.businessCategory.value, "accounts");
  assert.equal(state.businessFilters.asset_type_id, "identity");
  assert.equal(queries.at(-1).deleted_only, true);
  assert.equal(queries.at(-1).category_id, "accounts");
  router.back(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(state.businessCategory.value, "all");
  assert.equal(state.trashOpen.value, false);
  assert.equal(queries.at(-1).category_id, undefined);
});
test("trash preserves category and clear removes filters without changing selected category", async () => {
  const { state } = await setup(Assets, "/assets?category=systems");
  await state.switchTrash();
  assert.equal(queries.at(-1).category_id, "systems");
  state.businessFilters.keyword = "不存在"; state.businessFilters.department_id = "design";
  await state.clearBusinessFilters();
  assert.equal(state.businessCategory.value, "systems");
  assert.equal(queries.at(-1).keyword, ""); assert.equal(queries.at(-1).department_id, undefined);
});
test("an earlier category response cannot replace the most recently selected category", async () => {
  const { state } = await setup(Assets);
  const resolvers = [];
  api.assets = query => new Promise(resolve => resolvers.push({ query, resolve }));
  const first = state.selectBusinessCategory("systems");
  await new Promise(resolve => setImmediate(resolve));
  const second = state.selectBusinessCategory("accounts");
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(resolvers.length, 2);
  resolvers[1].resolve({ data: [{ id: "account" }], pagination: { total: 1 } }); await second;
  resolvers[0].resolve({ data: [{ id: "stale-system" }], pagination: { total: 80 } }); await first;
  assert.equal(state.businessCategory.value, "accounts");
  assert.deepEqual(state.businessAssets.value.map(item => item.id), ["account"]);
  assert.equal(state.total.value, 1);
});
test("intake selection and cancellation synchronize URL without saving a business object", async () => {
  const { state, router } = await setup(Intake, "/intake?mode=platform");
  assert.equal(state.mode.value, "platform");
  await state.choose("resource"); assert.equal(router.currentRoute.value.query.mode, "resource");
  await state.choose(""); assert.equal(router.currentRoute.value.query.mode, undefined);
  assert.equal(state.mode.value, ""); assert.equal(state.receipt.value, null);
  assert.equal(framework.registrationMode(["platform", "resource"]), "");
});
test("follow-up tab counts and search use actual response; failed load can retry", async () => {
  const { state } = await setup(Followup);
  api.huduExpirations = async () => { throw new Error("暂时离线"); };
  await state.load(); assert.equal(state.error.value, "暂时离线"); assert.equal(state.loading.value, false);
  api.huduExpirations = async () => ({ window_days: 30, items: [
    { id: "due", name: "域名", asset_code: "域名-001", has_owner: true, expires_at: "2020-10-12", owner_department_name: "设计" },
    { id: "owner", name: "文档工具", asset_code: "工具-002", has_owner: false, expires_at: null, owner_department_name: "行政" },
    { id: "future-owner", name: "远期工具", asset_code: "工具-003", has_owner: false, expires_at: "2099-12-31", owner_department_name: "行政" },
  ] });
  await state.load(); assert.equal(state.error.value, "");
  assert.deepEqual(state.tabs.value.map(tab => tab.count), [3, 1, 2]);
  state.active.value = "due"; assert.deepEqual(state.filtered.value.map(item => item.id), ["due"]);
  state.active.value = "owner"; assert.deepEqual(state.filtered.value.map(item => item.id), ["owner", "future-owner"]);
  state.query.value = "设计"; assert.equal(state.filtered.value.length, 0);
  state.active.value = "all"; assert.deepEqual(state.filtered.value.map(item => item.id), ["due"]);
});
