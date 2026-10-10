import assert from "node:assert/strict";
import { after, test } from "node:test";
import { createRenderer, createSSRApp, nextTick, reactive, ssrContextKey } from "vue";
import { renderToString } from "@vue/server-renderer";
import { createMemoryHistory, createRouter } from "vue-router";
import { createServer } from "vite";
import { findSelectablePeople, togglePersonSelection } from "../src/lib/peopleSelection.ts";

const departments = [{ id: "design", name: "产品设计" }, { id: "supply", name: "供应链" }];
const people = [
  { id: "a", display_name: "张同事", employee_no: "FB001", department_id: "design", employment_status: "active" },
  { id: "b", display_name: "李同事", employee_no: "FB002", department_id: "supply", employment_status: "active" },
  { id: "c", display_name: "离职同事", employee_no: "FB003", department_id: "design", employment_status: "inactive" },
];
const server = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error" });
after(() => server.close());
const { default: PeoplePicker } = await server.ssrLoadModule("/src/components/PeoplePicker.vue");
const { default: AssetStructureGuide } = await server.ssrLoadModule("/src/components/AssetStructureGuide.vue");
const { default: AssetAttachments } = await server.ssrLoadModule("/src/components/AssetAttachments.vue");
const { api } = await server.ssrLoadModule("/src/lib/api.ts");
api.assetAttachments = async () => [];
const base = { id: "fixture", label: "协同人员", people, departments, multiple: true, excludedIds: [], disabled: false, personIds: [] };
// A virtual Vue host exercises reactive watchers without a browser or DOM dependency.
const renderer = createRenderer({
  createElement: type => ({ type, children: [] }), createComment: text => ({ text }), createText: text => ({ text }),
  insert(node, parent) { parent.children.push(node); }, remove() {}, patchProp() {},
  setText(node, text) { node.text = text; }, setElementText(node, text) { node.text = text; },
  parentNode: () => null, nextSibling: () => null,
});
async function setup(overrides = {}) {
  const props = reactive({ ...base, ...overrides });
  const events = [];
  let state;
  const app = renderer.createApp({ setup() {
    state = PeoplePicker.setup(props, { expose() {}, emit(name, value) {
      events.push([name, value]);
      if (name === "update:personIds") props.personIds = value;
      else props.personId = value;
    } });
    return () => null;
  } });
  app.provide(ssrContextKey, { modules: new Set() });
  app.mount({ children: [] });
  after(() => app.unmount());
  return { state, events, props };
}

test("search matches name, employee number, department and multiple words", () => {
  assert.deepEqual(findSelectablePeople(people, departments, "张 产品").map(p => p.id), ["a"]);
  assert.deepEqual(findSelectablePeople(people, departments, "fb002").map(p => p.id), ["b"]);
  assert.deepEqual(findSelectablePeople(people, departments, "  供应链  ").map(p => p.id), ["b"]);
});
test("department, active status and responsible exclusion restrict results", () => {
  assert.deepEqual(findSelectablePeople(people, departments, "", "design").map(p => p.id), ["a"]);
  assert.deepEqual(findSelectablePeople(people, departments, "", "", ["a"]).map(p => p.id), ["b"]);
  assert.deepEqual(findSelectablePeople(people.slice(0, 1), departments, "李"), []);
});
test("selection preserves off-screen members without duplicates or input mutation", () => {
  const selected = ["not-in-current-results", "a"];
  assert.deepEqual(togglePersonSelection(selected, "b", true), ["not-in-current-results", "a", "b"]);
  assert.deepEqual(togglePersonSelection(selected, "a", true), selected);
  assert.deepEqual(togglePersonSelection(selected, "a", false), ["not-in-current-results"]);
  assert.deepEqual(selected, ["not-in-current-results", "a"]);
});
test("multi selection emits complete selection after filtering and removal", async () => {
  const { state, props, events } = await setup({ personIds: ["a"] });
  state.query.value = "李";
  assert.deepEqual(state.visible.value.map(person => person.id), ["b"]);
  state.select("b", true);
  assert.deepEqual(props.personIds, ["a", "b"]);
  state.remove("a");
  assert.deepEqual(events.at(-1), ["update:personIds", ["b"]]);
});
test("changing available departments clears a stale filter and preserves selected members", async () => {
  const { state, props } = await setup({ personIds: ["a"] });
  state.department.value = "design";
  props.people = [people[1]];
  await nextTick();
  assert.equal(state.department.value, "");
  assert.deepEqual(state.visible.value.map(person => person.id), ["b"]);
  assert.deepEqual(state.selectedIds.value, ["a"]);
});

test("single selection, clearing and disabled state emit only permitted local changes", async () => {
  const { state, props, events } = await setup({ multiple: false, personId: "a" });
  state.select("b", true);
  assert.deepEqual(events.at(-1), ["update:personId", "b"]);
  state.remove("b");
  assert.equal(props.personId, null);
  props.disabled = true;
  const count = events.length;
  state.select("a", true);
  assert.equal(events.length, count);
});
test("picker renders named checkbox controls, selected chips and unavailable member safely", async () => {
  const html = await renderToString(createSSRApp(PeoplePicker, { ...base, personIds: ["a", "unavailable-id"], excludedIds: ["b"], disabled: true }));
  assert.match(html, /type="checkbox"/);
  assert.match(html, /checked/);
  assert.match(html, /fieldset[^>]*disabled/);
  assert.match(html, /移除张同事/);
  assert.match(html, /当前列表不可用/);
  assert.doesNotMatch(html, /unavailable-id|李同事|离职同事/);
});
test("no-result state keeps existing selection visible", async () => {
  const { state } = await setup({ personIds: ["a"] });
  state.query.value = "完全不匹配";
  assert.equal(state.visible.value.length, 0);
  assert.deepEqual(state.selectedIds.value, ["a"]);
  const html = await renderToString(createSSRApp(PeoplePicker, { ...base, people: [], personIds: ["a"] }));
  assert.match(html, /没有匹配的在职人员/);
  assert.match(html, /已选 1 人/);
});
test("six business categories map to intake routes without requiring a complete chain", async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/intake", component: { render: () => null } }] });
  const app = createSSRApp(AssetStructureGuide);
  app.use(router);
  await router.push("/intake");
  await router.isReady();
  const html = await renderToString(app);
  for (const mode of ["entity", "identity", "platform", "platform-account", "grant", "resource"]) assert.ok(html.includes(`mode=${mode}`));
  assert.match(html, /无需把所有类别都登记一遍/);
  assert.match(html, /仅有邮箱或用户名时选登录身份/);
  assert.match(html, /自研系统/);
});
test("attachment uploader has one visible action and read-only mode has no upload control", async () => {
  const editable = await renderToString(createSSRApp(AssetAttachments, { assetId: "synthetic", canUpload: true }));
  assert.match(editable, /input[^>]*hidden[^>]*type="file"/);
  assert.equal((editable.match(/选择并上传附件/g) ?? []).length, 1);
  const readonly = await renderToString(createSSRApp(AssetAttachments, { assetId: "synthetic" }));
  assert.doesNotMatch(readonly, /type="file"|选择并上传附件/);
});
