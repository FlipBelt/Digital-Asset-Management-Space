import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../frontend/public/boot-recovery.js", import.meta.url), "utf8");
function fixture() {
  const listeners = new Map();
  const nodes = Object.fromEntries(["[data-boot-title]", "[data-boot-message]", "[data-boot-actions]", ".boot-progress"].map(key => [key, { textContent: "", hidden: key === "[data-boot-actions]" }]));
  const panel = { role: "status", setAttribute(key, value) { this[key] = value; }, getAttribute(key) { return this[key]; }, querySelector(key) { return nodes[key]; } };
  let mounted = false, timeout, reloads = 0;
  class Element { closest(selector) { return selector === "[data-boot-retry]"; } }
  const window = { setTimeout(callback, ms) { assert.equal(ms, 15000); timeout = callback; }, addEventListener(name, callback) { listeners.set(name, callback); }, location: { reload() { reloads++; } } };
  const document = { querySelector() { return mounted ? null : panel; }, addEventListener(name, callback) { listeners.set(name, callback); } };
  runInNewContext(source, { window, document, Element });
  return { panel, nodes, listeners, timeout: () => timeout(), mount: () => { mounted = true; }, reloads: () => reloads, Element };
}
{
  const f = fixture();
  f.timeout();
  assert.equal(f.panel.role, "status");
  assert.equal(f.nodes["[data-boot-title]"].textContent, "加载时间较长");
  assert.equal(f.nodes["[data-boot-actions]"].hidden, false);
  f.listeners.get("click")({ target: new f.Element() });
  assert.equal(f.reloads(), 1);
}
{
  const f = fixture();
  f.listeners.get("error")({ target: { tagName: "IMG" } });
  assert.equal(f.nodes["[data-boot-actions]"].hidden, true);
  f.listeners.get("error")({ target: { tagName: "SCRIPT" } });
  assert.equal(f.panel.role, "alert");
  assert.match(f.nodes["[data-boot-message]"].textContent, /应用文件加载失败/);
  f.timeout();
  assert.equal(f.panel.role, "alert", "Timeout must preserve an already reported loading failure");
}
{
  const f = fixture();
  f.mount();
  f.timeout();
  f.listeners.get("error")({ target: { tagName: "SCRIPT" } });
  assert.equal(f.nodes["[data-boot-actions]"].hidden, true, "Recovery must never replace a mounted business page");
}
{
  const f = fixture();
  f.listeners.get("asset-center-bootstrap-error")();
  assert.equal(f.panel.role, "alert");
  assert.equal(f.nodes["[data-boot-title]"].textContent, "页面加载遇到问题");
}
console.log("Boot recovery passed: timeout, script failure, reload, mounted-page isolation and runtime error.");
