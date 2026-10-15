import assert from "node:assert/strict";
import { after, test } from "node:test";
import { readFileSync, readdirSync } from "node:fs";
import { createHash } from "node:crypto";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error" });
after(() => server.close());
const { resolvePlatformBrand, platformBrands } = await server.ssrLoadModule("/src/lib/platformBrand.ts");
const folder = new URL("../src/assets/platform-logos/", import.meta.url);
const sources = JSON.parse(readFileSync(new URL("sources.json", folder), "utf8"));

test("all 27 verified brands resolve to a local asset with original source bytes", () => {
  assert.equal(platformBrands.length, 27);
  const names = new Set();
  for (const brand of sources.brands) {
    for (const name of brand.names) {
      const normalized = name.normalize("NFKC").trim().toLowerCase();
      assert.ok(!names.has(normalized), `Ambiguous alias: ${name}`); names.add(normalized);
      assert.equal(resolvePlatformBrand(name, brand.requiresWebsite ? brand.officialPage : undefined)?.key, brand.key);
    }
    const bytes = readFileSync(new URL(brand.asset, folder));
    assert.equal(createHash("sha256").update(bytes).digest("hex"), brand.sha256);
    assert.ok(brand.officialPage.startsWith("https://"));
    assert.ok(brand.assetUrl.startsWith("https://"));
    assert.ok(!/^https?:/.test(resolvePlatformBrand(brand.names[0], brand.requiresWebsite ? brand.officialPage : undefined).src));
    if (brand.asset.endsWith(".svg")) {
      const svg = bytes.toString("utf8");
      assert.doesNotMatch(svg, /<script|<foreignObject|\bon\w+\s*=|(?:href|src)\s*=\s*["'](?:https?:|\/\/|javascript:)/i);
    }
  }
  const files = readdirSync(folder).filter(file => /\.(png|svg|ico|webp)$/.test(file)).sort();
  assert.deepEqual(files, sources.brands.map(brand => brand.asset).sort());
});

test("confirmed pending names never borrow a similar brand or supplied website", () => {
  assert.equal(sources.pendingNames.length, 7);
  for (const name of sources.pendingNames) assert.equal(resolvePlatformBrand(name, "https://openai.com/"), null);
  assert.equal(resolvePlatformBrand("OpenAI合作伙伴"), null);
  assert.equal(resolvePlatformBrand("Google Ads"), null);
});

test("name matching is case and outer-whitespace tolerant without fuzzy matching", () => {
  assert.equal(resolvePlatformBrand("  openAI  ")?.key, "openai");
  assert.equal(resolvePlatformBrand("中国物品编码中心(GS1)")?.key, "gs1");
  assert.equal(resolvePlatformBrand("线性平台"), null);
  assert.equal(resolvePlatformBrand("网易企业邮箱")?.wide, true);
  assert.equal(resolvePlatformBrand("聚水潭")?.wide, true);
  assert.equal(resolvePlatformBrand("OpenAI")?.wide, false);
});

test("official-host fallback uses exact hosts and rejects spoofing, credentials and protocols", () => {
  assert.equal(resolvePlatformBrand("新目录名称", "https://platform.deepseek.com/usage?x=1")?.key, "deepseek");
  for (const url of ["https://platform.deepseek.com.evil.test", "https://evil.test/?next=https://linear.app", "https://linear.app@evil.test", "https://user@linear.app", "javascript:alert(1)", "https://linear.app:8443", "not a url"]) {
    assert.equal(resolvePlatformBrand("新目录名称", url), null, url);
  }
  assert.equal(resolvePlatformBrand("OpenAI", "https://linear.app"), null);
  assert.equal(resolvePlatformBrand("新目录名称", "https://img.alicdn.com/a.png"), null);
  assert.equal(resolvePlatformBrand("新目录名称", "https://apps.apple.com/cn/app/id1213288950"), null);
});

test("existing platform sites retain the correct corporate or platform brand", () => {
  assert.equal(resolvePlatformBrand("xAI"), null);
  assert.equal(resolvePlatformBrand("xAI", "https://x.ai/"), null);
  for (const [name, website, key] of [
    ["Google", "https://gemini.google.com", "google"], ["xAI", "https://grok.com", "xai"],
    ["京东", "https://shop.jd.com", "jd"], ["抖音", "https://ippro.bytedance.com", "douyin"],
    ["拼多多", "https://ipp.pinduoduo.com/", "pinduoduo"], ["小红书", "https://ipp.xiaohongshu.com", "xiaohongshu"],
  ]) assert.equal(resolvePlatformBrand(name, website)?.key, key);
});
