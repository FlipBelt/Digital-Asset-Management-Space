import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { after, afterEach, test } from "node:test";
import * as Vue from "vue";
import { renderToString } from "@vue/server-renderer";
import { compileScript, compileTemplate, parse } from "@vue/compiler-sfc";
import { createServer } from "vite";

const fixtureModule = "\0test-platform-logo-brands";
const server = await createServer({
  server: { middlewareMode: true }, appType: "custom", logLevel: "error",
  plugins: [{
    name: "test-platform-logo-local-brands", enforce: "pre",
    resolveId(source, importer) {
      if (source === "../lib/platformBrand" && importer?.replaceAll("\\", "/").includes("/PlatformLogo.vue")) return fixtureModule;
    },
    load(id) {
      if (id === fixtureModule) return `export function resolvePlatformBrand(name, website) {
        if (name === "Known A" || website === "https://brand-a.example.invalid") return { key: "a", label: "Known A", src: "/local/brand-a.svg" };
        if (name === "Known B") return { key: "b", label: "Known B", src: "/local/brand-b.svg" };
        if (name === "Known Wide") return { key: "wide", label: "Known Wide", src: "/local/brand-wide.svg", wide: true };
        return null;
      }`;
    },
  }],
});
after(() => server.close());
const { default: PlatformLogo } = await server.ssrLoadModule("/src/components/PlatformLogo.vue");
const filename = "src/components/PlatformLogo.vue";
const { descriptor } = parse(await readFile(filename, "utf8"), { filename });
const script = compileScript(descriptor, { id: "platform-logo-test" });
const template = compileTemplate({
  source: descriptor.template.content, filename, id: "platform-logo-test",
  compilerOptions: { mode: "function", bindingMetadata: script.bindings },
});
assert.deepEqual(template.errors, []);
const ClientLogo = { ...PlatformLogo, render: new Function("Vue", template.code)(Vue) };
const apps = [];
afterEach(() => { for (const app of apps.splice(0)) app.unmount(); });
const node = (type, text = "") => ({ type, text, props: {}, children: [], parent: null });
const detach = element => {
  if (element.parent) {
    const siblings = element.parent.children;
    const index = siblings.indexOf(element);
    if (index >= 0) siblings.splice(index, 1);
  }
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
const find = (element, type) => element.type === type ? element : element.children.map(child => find(child, type)).find(Boolean);
async function mountLogo(values = {}) {
  const props = Vue.reactive({ name: "Known A", ...values });
  const root = node("root");
  const app = renderer.createApp({ setup: () => () => Vue.h(ClientLogo, props) });
  app.provide(Vue.ssrContextKey, { modules: new Set() });
  app.mount(root); apps.push(app);
  await Vue.nextTick();
  return { props, root };
}

test("known brands render a local decorative image at the requested size", async () => {
  const html = await renderToString(Vue.createSSRApp(PlatformLogo, { name: "Known A", size: 48, class: "record-icon" }));
  assert.match(html, /aria-hidden="true"/);
  assert.match(html, /width:48px/);
  assert.match(html, /height:48px/);
  assert.match(html, /flex:0 0 48px/);
  assert.match(html, /background-color:#fff/);
  assert.match(html, /<img[^>]+src="\/local\/brand-a.svg"[^>]+alt=""/);
  assert.doesNotMatch(html, /https?:\/\//);
});

test("unknown brands use a neutral icon while retaining the default dimensions", async () => {
  const { root } = await mountLogo({ name: "Unknown brand" });
  assert.equal(find(root, "img"), undefined);
  assert.ok(find(root, "svg"));
  assert.equal(find(root, "span").props.style.width, "40px");
  assert.equal(find(root, "span").props["aria-hidden"], "true");
});

test("the actual image error handler falls back and a different brand restores the image", async () => {
  const { props, root } = await mountLogo();
  const image = find(root, "img");
  assert.equal(image.props.src, "/local/brand-a.svg");
  image.props.onError();
  await Vue.nextTick();
  assert.equal(find(root, "img"), undefined);
  assert.ok(find(root, "svg"));
  props.name = "Known B";
  await Vue.nextTick();
  assert.equal(find(root, "img").props.src, "/local/brand-b.svg");
  assert.equal(find(root, "svg"), undefined);
});

test("name or website changes retry an unchanged local image source", async () => {
  const { props, root } = await mountLogo();
  find(root, "img").props.onError();
  await Vue.nextTick();
  props.website = "https://brand-a.example.invalid";
  await Vue.nextTick();
  assert.equal(find(root, "img").props.src, "/local/brand-a.svg");
  find(root, "img").props.onError();
  await Vue.nextTick();
  props.name = "Known A alias";
  await Vue.nextTick();
  assert.equal(find(root, "img").props.src, "/local/brand-a.svg");
});

test("wide artwork uses a 2.4 to 1 frame and image failure returns to a square", async () => {
  const { props, root } = await mountLogo({ name: "Known Wide", size: 40, class: "record-icon" });
  const frame = find(root, "span");
  assert.equal(frame.props.style.width, "96px");
  assert.equal(frame.props.style.minWidth, "96px");
  assert.equal(frame.props.style.maxWidth, "96px");
  assert.equal(frame.props.style.height, "40px");
  assert.equal(frame.props.style.flex, "0 0 96px");
  assert.equal(Number.parseFloat(frame.props.style.width) / Number.parseFloat(frame.props.style.height), 2.4);
  assert.equal(find(root, "img").props.src, "/local/brand-wide.svg");
  find(root, "img").props.onError();
  await Vue.nextTick();
  assert.equal(find(root, "img"), undefined);
  assert.ok(find(root, "svg"));
  assert.equal(frame.props.style.width, "40px");
  assert.equal(frame.props.style.height, "40px");
  assert.equal(frame.props.style.flex, "0 0 40px");
  props.name = "Known A";
  await Vue.nextTick();
  assert.equal(find(root, "img").props.src, "/local/brand-a.svg");
  assert.equal(frame.props.style.width, "40px");
});
