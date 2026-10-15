import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { createRenderer, createSSRApp, nextTick, reactive, ssrContextKey } from "vue";
import { renderToString } from "@vue/server-renderer";
import { createMemoryHistory, createRouter } from "vue-router";
import { createServer } from "vite";

let routerHistoryReplaced = false;
const server = await createServer({
  server: { middlewareMode: true }, appType: "custom", logLevel: "error",
  plugins: [{
    name: "test-platform-router-memory-history", enforce: "pre",
    transform(source, id) {
      if (!id.replaceAll("\\", "/").endsWith("/src/router.ts")) return;
      assert.match(source, /createWebHistory\(import\.meta\.env\.BASE_URL\)/);
      routerHistoryReplaced = true;
      return source.replace("createRouter, createWebHistory", "createRouter, createMemoryHistory")
        .replace("createWebHistory(import.meta.env.BASE_URL)", "createMemoryHistory()");
    },
  }],
});
after(() => server.close());
const { api } = await server.ssrLoadModule("/src/lib/api.ts");
const { default: Services } = await server.ssrLoadModule("/src/pages/ServicesPage.vue");
const { default: Accounts } = await server.ssrLoadModule("/src/pages/AccountsPage.vue");
const { default: actualRouter } = await server.ssrLoadModule("/src/router.ts");
const originalApi = { ...api };
const apps = [];
afterEach(() => {
  for (const app of apps.splice(0)) app.unmount();
  Object.assign(api, originalApi);
});
const renderer = createRenderer({
  createElement: type => ({ type, children: [] }), createComment: text => ({ text }), createText: text => ({ text }),
  insert(node, parent) { parent.children.push(node); }, remove() {}, patchProp() {},
  setText(node, text) { node.text = text; }, setElementText(node, text) { node.text = text; },
  parentNode: () => null, nextSibling: () => null,
});
const flush = async () => { await nextTick(); await new Promise(resolve => setImmediate(resolve)); await nextTick(); };
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((accept, decline) => { resolve = accept; reject = decline; });
  return { promise, resolve, reject };
};
const products = [
  { id: "product-a", platform_id: "platform-a", provider_id: "provider-a", name: "A 服务", plan_options: ["Pro"] },
  { id: "product-b", platform_id: "platform-b", provider_id: "provider-b", name: "B 服务", plan_options: ["Pro"] },
  { id: "product-c", platform_id: "platform-c", provider_id: "provider-a", name: "C 服务", plan_options: ["Pro"] },
];
const companyInstances = [
  { id: "company-a", asset_id: "asset-a", service_product_id: "product-a", purchase_platform_id: null },
  { id: "purchase-a", asset_id: "asset-channel", service_product_id: "product-b", purchase_platform_id: "platform-a" },
  { id: "company-b", asset_id: "asset-b", service_product_id: "product-b", purchase_platform_id: null },
  { id: "company-c", asset_id: "asset-c", service_product_id: "product-c", purchase_platform_id: null },
];
const personalInstance = { id: "personal", asset_id: "personal-asset", service_product_id: "product-a" };
const accountRow = (id, children = []) => ({ asset_id: id, name: id, children, verification_status: "verified" });
const hierarchyPlatform = (id, company, personal) => ({
  id, company_accounts: company, personal_accounts: personal, pending_identities: [], registration_identities: [], service_references: [],
});
const directory = [
  { id: "empty", name: "空平台", kind: "platform", provider_id: null, review_status: "approved" },
  { id: "platform-b", name: "两个公司账号", kind: "platform", provider_id: "provider-b", review_status: "approved" },
  { id: "platform-a", name: "包含个人账号", kind: "platform", provider_id: "provider-a", review_status: "approved" },
];
const hierarchy = { platforms: [
  hierarchyPlatform("platform-b", [accountRow("b1"), accountRow("b2")], []),
  hierarchyPlatform("platform-a", [accountRow("a1", [1, 2, 3])], [accountRow("personal-1"), { ...accountRow("personal-2"), is_subscription: true }]),
], unlinked_identities: [], service_references: [] };

function mockReads() {
  const calls = { scopes: [], metrics: [] };
  api.currentSession = async () => ({ roles: ["system_admin"], permissions: ["asset.write"] });
  api.serviceProducts = async () => products;
  api.subscriptionOptions = async () => products.map(product => ({ ...product, platform_name: product.platform_id }));
  api.serviceInstances = async params => {
    calls.scopes.push(params);
    return params?.scope === "company" ? companyInstances : [...companyInstances, personalInstance];
  };
  api.assets = async () => ({ data: [{ id: "new-company-asset" }, { id: "personal-asset", is_personal_subscription: true }], pagination: { total: 2 } });
  api.metricDefinitions = async () => [{ id: "balance", display_name: "余额", unit: "CNY" }];
  api.metrics = async id => {
    calls.metrics.push(id);
    return [{ id: `metric-${id}`, service_instance_id: id, metric_definition_id: "balance", value: "15", currency: "CNY", collected_at: "2026-10-15T00:00:00Z" }];
  };
  api.accountHierarchy = async () => hierarchy;
  api.platformDirectory = async () => directory;
  return calls;
}

async function mountState(Page, values = {}, path = "/accounts?section=usage") {
  const props = reactive({ ...values });
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:pathMatch(.*)*", component: { render: () => null } }] });
  await router.push(path);
  let state;
  const app = renderer.createApp({ setup() { state = Page.setup(props, { expose() {} }); return () => null; } });
  app.use(router); app.provide(ssrContextKey, { modules: new Set() });
  app.mount({ children: [] }); apps.push(app);
  await flush();
  return { state, props, router };
}

async function renderState(Page, state, props, router) {
  const app = createSSRApp({ ...Page, setup: () => state }, props);
  app.use(router);
  return renderToString(app);
}

test("embedded services use a secondary heading while standalone services retain one page heading", async () => {
  mockReads();
  const standalone = await mountState(Services);
  const standaloneHtml = await renderState(Services, standalone.state, standalone.props, standalone.router);
  assert.equal((standaloneHtml.match(/<h1\b/g) || []).length, 1);
  assert.match(standaloneHtml, /<h1>订阅与用量<\/h1>/);
  const embedded = await mountState(Services, { embedded: true });
  const embeddedHtml = await renderState(Services, embedded.state, embedded.props, embedded.router);
  assert.equal((embeddedHtml.match(/<h1\b/g) || []).length, 0);
  assert.match(embeddedHtml, /<h2>公司订阅与用量<\/h2>/);
  assert.match(embeddedHtml, /个人订阅在/);
  assert.match(embeddedHtml, /无需录入余额或同步用量/);
});

test("services request company scope and fetch metrics only for returned company instances", async () => {
  const calls = mockReads();
  const { state } = await mountState(Services);
  assert.deepEqual(calls.scopes, [{ scope: "company" }]);
  assert.deepEqual(calls.metrics, companyInstances.map(item => item.id));
  assert.ok(!calls.metrics.includes(personalInstance.id));
  assert.deepEqual(Object.keys(state.samples.value).sort(), companyInstances.map(item => item.id).sort());
  assert.deepEqual(state.availableAssets.value.map(item => item.id), ["new-company-asset"]);
  assert.equal(state.latestMetricCount.value, companyInstances.length);
});

test("a supported platform retains its own balance entry and excludes unrelated platforms", async () => {
  mockReads();
  const { state, props, router } = await mountState(Services, { embedded: true, platformId: "platform-a", platformName: "DeepSeek" });
  assert.deepEqual(state.connectionEntries.value.map(item => item.code), ["deepseek"]);
  const html = await renderState(Services, state, props, router);
  assert.match(html, /href="\/accounts\/usage\/deepseek"/);
  assert.doesNotMatch(html, /href="\/accounts\/usage\/(minimax|aliyun)"/);
});

test("platform scope includes its products and purchases; switching to a provider resets and reloads the scope", async () => {
  const calls = mockReads();
  const { state, props } = await mountState(Services, { embedded: true, platformId: "platform-a" });
  assert.deepEqual(state.scopedProducts.value.map(item => item.id), ["product-a"]);
  assert.deepEqual(state.scopedAvailableProducts.value.map(item => item.id), ["product-a"]);
  assert.deepEqual(state.visibleInstances.value.map(item => item.id), ["company-a", "purchase-a"]);
  assert.deepEqual(calls.metrics, ["company-a", "purchase-a"]);
  state.modal.value = "metric"; state.instanceForm.asset_id = "old-selection";
  calls.metrics.length = 0;
  props.platformId = undefined; props.providerId = "provider-a";
  await flush();
  assert.equal(state.modal.value, null);
  assert.equal(state.instanceForm.asset_id, "");
  assert.deepEqual(state.scopedProducts.value.map(item => item.id), ["product-a", "product-c"]);
  assert.deepEqual(state.visibleInstances.value.map(item => item.id), ["company-a", "company-c"]);
  assert.deepEqual(calls.metrics, ["company-a", "company-c"]);
  assert.deepEqual(Object.keys(state.samples.value).sort(), ["company-a", "company-c"]);
});

test("an earlier platform response cannot replace the newly selected platform", async () => {
  mockReads();
  const pending = [];
  api.serviceInstances = () => { const result = deferred(); pending.push(result); return result.promise; };
  const { state, props } = await mountState(Services, { platformId: "platform-a" });
  assert.equal(pending.length, 1);
  props.platformId = "platform-b";
  await flush();
  assert.equal(pending.length, 2);
  pending[1].resolve(companyInstances);
  await flush();
  assert.deepEqual(state.visibleInstances.value.map(item => item.id), ["purchase-a", "company-b"]);
  assert.equal(state.loading.value, false);
  pending[0].resolve([{ id: "stale", service_product_id: "product-a", asset_id: "stale-asset" }]);
  await flush();
  assert.deepEqual(state.visibleInstances.value.map(item => item.id), ["purchase-a", "company-b"]);
  assert.deepEqual(Object.keys(state.samples.value).sort(), ["company-b", "purchase-a"]);
  assert.equal(state.error.value, "");
});

test("a failed metric load can retry, and a stale metric failure cannot overwrite a later scope", async () => {
  mockReads();
  const { state, props } = await mountState(Services, { platformId: "platform-a" });
  api.metrics = async () => { throw new Error("暂时离线"); };
  await state.load();
  assert.equal(state.error.value, "暂时离线");
  assert.equal(state.loading.value, false);
  mockReads();
  await state.load();
  assert.equal(state.error.value, "");
  assert.deepEqual(Object.keys(state.samples.value).sort(), ["company-a", "purchase-a"]);
  const oldMetric = deferred();
  api.metrics = () => oldMetric.promise;
  const oldLoad = state.load();
  await flush();
  mockReads();
  props.platformId = "platform-b";
  await flush();
  oldMetric.reject(new Error("旧范围失败"));
  await oldLoad;
  assert.equal(state.error.value, "");
  assert.equal(state.loading.value, false);
  assert.deepEqual(Object.keys(state.samples.value).sort(), ["company-b", "purchase-a"]);
});

test("AccountsPage groups and sorts by company plus personal accounts without counting child accounts", async () => {
  mockReads();
  const { state, props, router } = await mountState(Accounts, {}, "/accounts");
  assert.deepEqual(state.directoryGroups.value[0].entries.map(item => [item.id, item.accountCount]), [["platform-a", 3], ["platform-b", 2]]);
  assert.deepEqual(state.directoryGroups.value[1].entries.map(item => [item.id, item.accountCount]), [["empty", 0]]);
  const html = await renderState(Accounts, state, props, router);
  assert.match(html, /已有账号/); assert.match(html, /暂无账号/);
  assert.ok(html.indexOf("包含个人账号") < html.indexOf("两个公司账号"));
  assert.match(html, /1 个公司账号 · 2 个个人账号/);
  state.query.value = "空平台";
  assert.equal(state.directoryGroups.value[0].entries.length, 0);
  assert.deepEqual(state.directoryGroups.value[1].entries.map(item => item.id), ["empty"]);
});

test("AccountsPage usage sections embed the actual services template under a single main heading", async () => {
  mockReads();
  for (const path of ["/accounts?section=usage", "/accounts?platform=platform-a&section=usage"]) {
    const { state, props, router } = await mountState(Accounts, {}, path);
    const html = await renderState(Accounts, state, props, router);
    assert.equal((html.match(/<h1\b/g) || []).length, 1);
    assert.match(html, /<h1>平台与账号<\/h1>/);
    assert.match(html, /公司订阅与用量/);
    if (path.includes("platform=")) assert.doesNotMatch(html, /开放平台账号当前余额/);
    else assert.match(html, /href="\/accounts\/usage\/deepseek"/);
  }
});

test("the actual router preserves legacy services query and hash while retaining its existing guards", async () => {
  assert.equal(routerHistoryReplaced, true);
  await actualRouter.push("/services?platform=platform-a&section=old&q=keep&tag=a&tag=b#quota");
  assert.equal(actualRouter.currentRoute.value.path, "/accounts");
  assert.deepEqual(actualRouter.currentRoute.value.query, { platform: "platform-a", section: "usage", q: "keep", tag: ["a", "b"] });
  assert.equal(actualRouter.currentRoute.value.hash, "#quota");
  await actualRouter.push("/services/?q=kept#quota");
  assert.equal(actualRouter.currentRoute.value.path, "/accounts");
  assert.deepEqual(actualRouter.currentRoute.value.query, { q: "kept", section: "usage" });
  assert.equal(actualRouter.currentRoute.value.hash, "#quota");
  await actualRouter.push("/services/deepseek/?q=kept#quota");
  assert.equal(actualRouter.currentRoute.value.path, "/accounts/usage/deepseek");
  assert.deepEqual(actualRouter.currentRoute.value.query, { q: "kept" });
  assert.equal(actualRouter.currentRoute.value.hash, "#quota");
  for (const suffix of ["alerts", "deepseek", "minimax", "aliyun"]) {
    await actualRouter.push(`/services/${suffix}?connection=kept&tag=a&tag=b#record`);
    assert.equal(actualRouter.currentRoute.value.path, `/accounts/usage/${suffix}`);
    assert.deepEqual(actualRouter.currentRoute.value.query, { connection: "kept", tag: ["a", "b"] });
    assert.equal(actualRouter.currentRoute.value.hash, "#record");
  }
  await actualRouter.push("/accounts?section=personal&q=mine&type=saas&page=2");
  assert.equal(actualRouter.currentRoute.value.path, "/my/subscriptions");
  assert.deepEqual(actualRouter.currentRoute.value.query, { q: "mine", type: "saas", page: "2" });
  await actualRouter.push("/discover?category=workflows&group=platform&q=keep");
  assert.equal(actualRouter.currentRoute.value.path, "/workflows");
  assert.deepEqual(actualRouter.currentRoute.value.query, { q: "keep" });
});
