import assert from "node:assert/strict";
import { after, test } from "node:test";
import { createRenderer, ssrContextKey } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error" });
after(() => server.close());
const { default: Page } = await server.ssrLoadModule("/src/pages/AssetsPage.vue");
const { api } = await server.ssrLoadModule("/src/lib/api.ts");
const renderer = createRenderer({
  createElement: type => ({ type, children: [] }), createComment: text => ({ text }), createText: text => ({ text }),
  insert(node, parent) { parent.children.push(node); }, remove() {}, patchProp() {},
  setText(node, text) { node.text = text; }, setElementText(node, text) { node.text = text; },
  parentNode: () => null, nextSibling: () => null,
});
const asset = { id: "fixture", name: "隔离成果", asset_code: "测试-001", version: 12, sharing_scope: "private" };
async function setup(roles = ["system_admin"], permissions = []) {
  api.currentSession = async () => ({ roles, permissions });
  api.assets = async () => ({ data: [asset], pagination: { total: 1 } });
  api.assetTypes = async () => [];
  api.assetCategories = async () => [];
  api.departments = async () => [];
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component: { render: () => null } }] });
  await router.push("/");
  let state;
  const app = renderer.createApp({ setup() { state = Page.setup({}, { expose() {} }); return () => null; } });
  app.use(router);
  app.provide(ssrContextKey, { modules: new Set() });
  app.mount({ children: [] });
  await state.loadBusiness();
  after(() => app.unmount());
  return state;
}
test("delete and trash controls require a global manager with write permission", async () => {
  assert.equal((await setup()).canDelete.value, true);
  assert.equal((await setup(["asset_manager"], ["asset.write"])).canDelete.value, true);
  assert.equal((await setup(["asset_manager"])).canDelete.value, false);
  assert.equal((await setup(["department_manager"], ["asset.write"])).canDelete.value, false);
});
test("cancel does not delete; confirmation sends the displayed exact version once", async () => {
  const state = await setup();
  const calls = [];
  let resolve;
  api.deleteAsset = (id, version) => { calls.push([id, version]); return new Promise(done => { resolve = done; }); };
  state.openMutation(asset, "delete");
  state.closeMutation();
  assert.equal(calls.length, 0);
  state.openMutation(asset, "delete");
  const pending = state.mutateAsset();
  state.closeMutation();
  assert.equal(state.mutationTarget.value.id, asset.id);
  await state.mutateAsset();
  assert.deepEqual(calls, [[asset.id, 12]]);
  resolve(asset);
  await pending;
  assert.equal(state.mutationTarget.value, null);
  assert.match(state.message.value, /回收站/);
});
test("conflict keeps the asset and error visible for a deliberate refresh", async () => {
  const state = await setup();
  api.deleteAsset = async () => { throw new Error("记录已被其他用户修改"); };
  state.openMutation(asset, "delete");
  await state.mutateAsset();
  assert.equal(state.mutationTarget.value.id, asset.id);
  assert.equal(state.mutationBusy.value, false);
  assert.match(state.mutationError.value, /其他用户修改/);
});
test("trash is a separate server query and restore explains AI reconfirmation", async () => {
  const state = await setup();
  let query;
  api.assets = async params => { query = params; return { data: [asset], pagination: { total: 1 } }; };
  state.businessPage.value = 3;
  await state.switchTrash();
  assert.equal(query.deleted_only, true);
  assert.equal(query.include_archived, false);
  assert.equal(query.page, 1);
  api.restoreAsset = async (id, version) => { assert.equal(id, asset.id); assert.equal(version, 12); return asset; };
  state.openMutation(asset, "restore");
  await state.mutateAsset();
  assert.match(state.message.value, /重新核对、确认并审核/);
});
