import assert from "node:assert/strict";
import { after, test } from "node:test";
import { createRenderer, createSSRApp, reactive, ssrContextKey } from "vue";
import { renderToString } from "@vue/server-renderer";
import { createMemoryHistory, createRouter } from "vue-router";
import { createServer } from "vite";
import { displayOutcomeVersion } from "../src/lib/assetVersions.ts";

const server = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error" });
after(() => server.close());
const { default: Card } = await server.ssrLoadModule("/src/components/AssetCard.vue");
const { default: Confirmation } = await server.ssrLoadModule("/src/components/AssetConfirmationPanel.vue");
const { api } = await server.ssrLoadModule("/src/lib/api.ts");
const asset = { id: "synthetic", name: "合成成果", description: "本地验证", version: 8, outcome_version: 1, status: "draft", created_by_person_id: "registrant", sharing_scope: "private" };
const renderer = createRenderer({
  createElement: type => ({ type, children: [] }), createComment: text => ({ text }), createText: text => ({ text }),
  insert(node, parent) { parent.children.push(node); }, remove() {}, patchProp() {},
  setText(node, text) { node.text = text; }, setElementText(node, text) { node.text = text; },
  parentNode: () => null, nextSibling: () => null,
});

test("published outcome display remains stable across ordinary revisions", () => {
  assert.equal(displayOutcomeVersion(asset), "成果 V1");
  assert.equal(displayOutcomeVersion({ ...asset, version: 99 }), "成果 V1");
  assert.equal(displayOutcomeVersion({ ...asset, outcome_version: 0 }), "待首次登记");
  assert.equal(displayOutcomeVersion({ ...asset, sharing_scope: null }), "资料修订 8");
});

test("real card renders outcome version without advertising lock revision as publication", async () => {
  const app = createSSRApp(Card, { asset, bookmarked: false });
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component: { render: () => null } }, { path: "/discover/:id", component: { render: () => null } }] });
  app.use(router); await router.push("/"); await router.isReady();
  const html = await renderToString(app);
  assert.match(html, /成果 V1/);
  assert.doesNotMatch(html, /版本 8|成果 V8/);
});

test("confirmation defaults to documentation update and explicitly binds requested publication", async () => {
  const preparations = [], confirmations = [], events = [];
  api.asset = async () => ({ ...asset });
  api.currentSession = async () => ({ person_id: "registrant" });
  api.prepareAssetConfirmation = async (id, body) => {
    preparations.push(body);
    return { id: "receipt", asset_version: 8, outcome_version: body.publish_new_version ? 2 : 1, content_digest: "digest", preview: {} };
  };
  api.confirmAssetDraft = async (id, body) => { confirmations.push(body); return { ...asset, status: "active" }; };
  let state;
  const app = renderer.createApp({ setup() {
    state = Confirmation.setup(reactive({ assetId: asset.id }), { expose() {}, emit: (...args) => events.push(args) });
    return () => null;
  } });
  app.provide(ssrContextKey, { modules: new Set() }); app.mount({ children: [] });
  try {
    await new Promise(setImmediate);
    assert.equal(state.publishNewVersion.value, false);
    await state.prepare();
    assert.equal(preparations[0].publish_new_version, false);
    assert.equal(state.receipt.value.outcome_version, 1);
    await state.confirm();
    assert.equal(confirmations.length, 0);
    state.publishNewVersion.value = true;
    await state.prepare();
    assert.equal(preparations[1].publish_new_version, true);
    assert.equal(state.receipt.value.outcome_version, 2);
    state.acknowledged.value = true;
    await state.confirm();
    assert.equal(confirmations[0].confirmation_id, "receipt");
    assert.equal(confirmations[0].version, 8);
    assert.equal(confirmations[0].content_digest, "digest");
    assert.equal("outcome_version" in confirmations[0], false);
    assert.deepEqual(events.at(-1), ["confirmed"]);
  } finally { app.unmount(); }
});
