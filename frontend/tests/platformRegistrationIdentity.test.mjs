import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { createRenderer, nextTick, ssrContextKey } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error" });
after(() => server.close());
const { default: Page } = await server.ssrLoadModule("/src/pages/AssetDetailPage.vue");
const { api } = await server.ssrLoadModule("/src/lib/api.ts");
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
const identity = (id, company = "company-a", blocked = false) => ({
  id: `profile-${id}`, asset_id: id, asset_code: id, legal_entity_id: company,
  identifier: `${id}@example.invalid`, name: `${id}@example.invalid`, identity_type: "email", registration_blocked: blocked,
});

async function setup(roles = ["asset_manager"]) {
  const asset = {
    id: "company-account", name: "隔离公司账号", asset_code: "隔离账号-001", asset_type_id: "tenant-type",
    legal_entity_id: "company-a", version: 7, status: "draft", archived_at: null,
    created_by_person_id: "creator", criticality: "normal", confidentiality: "internal", description: "隔离验证",
  };
  const options = [identity("local-one"), identity("local-two"), identity("foreign", "company-b"), identity("blocked", "company-a", true)];
  const context = {
    asset_id: asset.id, platform_id: "platform", platform_name: "隔离平台", tenant_identifier: null,
    verification_status: "pending", registration_identities: [],
  };
  const calls = { audits: 0, saves: [], legacy: 0, reads: 0 };
  api.asset = async id => { assert.equal(id, asset.id); calls.reads += 1; return structuredClone(asset); };
  api.currentSession = async () => ({ roles, permissions: ["asset.write"], person_id: "operator" });
  api.assetTypes = async () => [{ id: asset.asset_type_id, code: "platform_tenant", name: "平台账号", profile_kind: "generic" }];
  api.assets = async () => ({ data: [structuredClone(asset)], pagination: { total: 1 } });
  api.assetAssignment = async () => ({ ownership_scope: "company", owner_department_id: null, responsible_person_id: "operator", user_person_ids: [] });
  api.relationshipView = async () => ({ current_node: { id: asset.id, label: asset.name }, nodes: [], edges: [] });
  api.auditLogs = async () => { calls.audits += 1; return []; };
  for (const method of ["departments", "legalEntities", "people", "assetFields", "assetFieldValues", "assetIdentifiers", "platforms", "serviceInstances", "assetResponsibilities", "platformAccountChildren"]) api[method] = async () => [];
  api.relationshipChoices = async () => [{ key: "owned", group: "ownership", label: "归属", target_kind: "asset", targets: [] }];
  api.platformAccountContext = async () => structuredClone(context);
  api.registrationIdentities = async () => structuredClone(options);
  api.savePlatformRegistrationIdentity = async (id, body) => {
    assert.equal(id, asset.id); calls.saves.push(structuredClone(body));
    context.registration_identities = [options.find(item => item.asset_id === body.registration_identity_asset_id)];
    asset.version += 1;
    return structuredClone(context);
  };
  api.updateRelationshipLink = async () => { calls.legacy += 1; throw new Error("旧关系 PUT 不应调用"); };
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/assets/:id", component: { render: () => null } }] });
  await router.push(`/assets/${asset.id}?tab=relations`);
  let state;
  const app = renderer.createApp({ setup() { state = Page.setup({}, { expose() {} }); return () => null; } });
  app.use(router); app.provide(ssrContextKey, { modules: new Set() });
  app.mount({ children: [] }); apps.push(app);
  await flush();
  assert.equal(state.error.value, "", "the minimal fixture must complete the real load path");
  assert.equal(state.loading.value, false);
  return { state, router, asset, context, options, calls };
}

test("non-system administrators skip the protected audit API and managers retain the loaded editor", async () => {
  for (const roles of [["asset_manager"], ["department_manager"], ["system_admin"]]) {
    const { state, calls } = await setup(roles);
    assert.equal(calls.audits, roles.includes("system_admin") ? 1 : 0);
    assert.equal(state.canReadAuditLogs.value, roles.includes("system_admin"));
    assert.equal(state.asset.value.id, "company-account");
    assert.equal(state.canEditRegistrationIdentity.value, true);
    await state.openRegistrationIdentityEditor();
    assert.equal(state.registrationIdentityEditing.value, true);
    assert.equal(state.registrationIdentityLoading.value, false);
    assert.equal(state.registrationIdentityError.value, "");
  }
});

test("the editor excludes blocked identities and restricts non-global managers to the account company", async () => {
  const department = await setup(["department_manager"]);
  await department.state.openRegistrationIdentityEditor();
  assert.deepEqual(department.state.registrationIdentityCandidates.value.map(item => item.asset_id), ["local-one", "local-two"]);
  department.state.registrationIdentitySelection.value = "foreign";
  await department.state.saveRegistrationIdentity();
  assert.equal(department.calls.saves.length, 0);
  const manager = await setup(["asset_manager"]);
  await manager.state.openRegistrationIdentityEditor();
  assert.deepEqual(manager.state.registrationIdentityCandidates.value.map(item => item.asset_id), ["local-one", "local-two", "foreign"]);
  manager.state.registrationIdentitySelection.value = "blocked";
  await manager.state.saveRegistrationIdentity();
  assert.equal(manager.calls.saves.length, 0);
});

test("network retries reuse the exact request ID while selection and displayed version changes replace it", async () => {
  const { state, calls } = await setup();
  await state.openRegistrationIdentityEditor();
  api.savePlatformRegistrationIdentity = async (_id, body) => {
    calls.saves.push(structuredClone(body)); throw new Error("网络暂时不可用");
  };
  state.registrationIdentitySelection.value = "local-one";
  await state.saveRegistrationIdentity();
  assert.equal(state.registrationIdentityEditing.value, true);
  assert.equal(state.saving.value, false);
  assert.equal(state.registrationIdentityError.value, "网络暂时不可用");
  await state.saveRegistrationIdentity();
  assert.deepEqual(calls.saves[1], calls.saves[0]);
  assert.match(calls.saves[0].request_id, /^[0-9a-f-]{36}$/);
  state.registrationIdentitySelection.value = "local-two";
  await state.saveRegistrationIdentity();
  assert.notEqual(calls.saves[2].request_id, calls.saves[1].request_id);
  assert.equal(calls.saves[2].registration_identity_asset_id, "local-two");
  state.asset.value.version += 1;
  await state.saveRegistrationIdentity();
  assert.notEqual(calls.saves[3].request_id, calls.saves[2].request_id);
  assert.equal(calls.saves[3].version, calls.saves[2].version + 1);
});

test("a successful save reloads the account and updates its primary registration identity before closing", async () => {
  const { state, router, asset, calls } = await setup();
  await state.openRegistrationIdentityEditor();
  assert.equal(router.currentRoute.value.hash, "#registration-identity");
  state.registrationIdentitySelection.value = "local-two";
  const initialReads = calls.reads;
  await state.saveRegistrationIdentity();
  assert.equal(calls.saves.length, 1);
  assert.equal(calls.saves[0].version, 7);
  assert.ok(calls.reads > initialReads);
  assert.equal(state.asset.value.version, asset.version);
  assert.equal(state.platformAccountContext.value.registration_identities[0].asset_id, "local-two");
  assert.equal(state.linkedIdentity.value, "local-two@example.invalid");
  assert.equal(state.registrationIdentityEditing.value, false);
  assert.equal(state.registrationIdentityError.value, "");
  assert.equal(state.saving.value, false);
  assert.match(state.message.value, /概览和关联关系已更新/);
  assert.equal(router.currentRoute.value.hash, "");
});

test("editing the historical registration relationship opens the new editor and saves through its versioned API", async () => {
  const { state, router, calls } = await setup();
  state.startRelationEdit({ id: "historical-edge", edit_kind: "registration_identity", edit_target_id: "old-identity" });
  await flush();
  assert.equal(state.registrationIdentityEditing.value, true);
  assert.equal(state.editingRelationId.value, null);
  assert.equal(state.tab.value, "overview");
  assert.equal(router.currentRoute.value.query.tab, "overview");
  assert.equal(router.currentRoute.value.hash, "#registration-identity");
  assert.equal(calls.legacy, 0);
  state.registrationIdentitySelection.value = "local-one";
  await state.saveRegistrationIdentity();
  assert.equal(calls.saves.length, 1);
  assert.equal(calls.saves[0].registration_identity_asset_id, "local-one");
  assert.equal(calls.legacy, 0);
});
