import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { test } from "node:test";

const dependencies = createRequire(process.env.ASSET_FRONTEND_DEPENDENCY_ROOT
  ? pathToFileURL(resolve(process.env.ASSET_FRONTEND_DEPENDENCY_ROOT, "package.json"))
  : new URL("../package.json", import.meta.url));
const ts = dependencies("typescript");
const source = await readFile(new URL("../src/lib/loginNavigation.ts", import.meta.url), "utf8");
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } });
const module = { exports: {} };
new Function("module", "exports", output.outputText)(module, module.exports);
const { safeLoginRedirect } = module.exports;
const secret = "mrq_" + "A".repeat(43);

test("global OAuth login returns discard every token-bearing query including encoded and repeated keys", () => {
  for (const path of [
    "/agent/oauth?request_token=" + secret,
    "/agent/oauth/?request_token=" + secret + "&resume=untrusted",
    "/agent/oauth?%72equest%5Ftoken=" + secret,
    "/agent/oauth?request_token=first&request_token=" + secret,
    "/agent/oauth?request_token=&other=" + secret,
    "/%61gent/oauth?request_token=" + secret,
    "/agent/oauth?resume=other&request%5Ftoken=" + secret + "#section",
  ]) {
    const target = safeLoginRedirect(path);
    assert.equal(target, "/agent/oauth?restart=1");
    assert.doesNotMatch(target, /request_token|mrq_|untrusted/);
  }
});

test("normal local recovery handles and authorization management remain available", () => {
  const recovery = "/agent/oauth?resume=5a68bd70-7444-480e-8983-00f1cf55d849";
  assert.equal(safeLoginRedirect(recovery), recovery);
  assert.equal(safeLoginRedirect("/agent/oauth"), "/agent/oauth");
  assert.equal(safeLoginRedirect("/agent/oauth/"), "/agent/oauth/");
  assert.equal(safeLoginRedirect("/agent/oauth?restart=1"), "/agent/oauth?restart=1");
});

test("existing local navigation retains its query and drops URL fragments", () => {
  assert.equal(safeLoginRedirect("/assets/fixture?tab=history#section"), "/assets/fixture?tab=history");
  assert.equal(safeLoginRedirect("/my?category=drafts"), "/my?category=drafts");
  assert.equal(safeLoginRedirect("/manage?tab=settings"), "/manage?tab=settings");
});

test("external, cross-mount, API and malformed destinations continue to fail closed", () => {
  for (const value of [
    undefined, null, 42, "", "https://untrusted.invalid/path", "//untrusted.invalid/path",
    "/test/agent/oauth?request_token=" + secret, "/login?redirect=/my", "/api/v1/assets",
    "/agent/../oauth", "/my%5cother", "/my?value=%0a", "/agent/oauth?request_token=%",
  ]) assert.equal(safeLoginRedirect(value), "/my");
});
