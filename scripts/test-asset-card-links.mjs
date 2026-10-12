import assert from "node:assert/strict";
import { assetLinks, safeAssetUrl, assetCardSummary } from "../frontend/src/lib/assetLinks.ts";

const card = {
  card_links: [
    { label: "代码仓库", url: "https://github.com/example/project" },
    { label: "打开应用", url: "https://app.example.test" },
  ],
  description: "用途。[GitHub 仓库](https://github.com/example/project)；[知识门户](https://wiki.example.test/)。其他入口：https://docs.example.test/start，已确认。",
  source_reference: "https://app.example.test/",
};
const links = assetLinks(card);
assert.equal(links.length, 4);
assert.deepEqual(links.map(link => link.label), ["GitHub", "打开应用", "知识门户", "docs.example.test"]);
assert.equal(links[2].url, "https://wiki.example.test/");
assert.equal(links[1].kind, "application");
for (const value of ["javascript:alert(1)", "data:text/html,test", "file:///private", "//host/path", "https://user:secret@example.test", "https://example.test\n/path", "not a url"]) assert.equal(safeAssetUrl(value), null);
assert.equal(assetLinks({ description: "(https://example.test/a_(b))。", source_reference: null })[0].url, "https://example.test/a_(b)");
assert.equal(assetLinks({ description: "HTTPS://EXAMPLE.TEST/path." })[0].url, "https://example.test/path");
assert.equal(assetLinks({ card_links: [{label: "生产链接", url: "https://app.example.test/"}] })[0].label, "访问地址");
assert.equal(assetLinks({ card_links: [{label: "bad", url: "javascript:alert(1)"}] }).length, 0);
assert.equal(assetCardSummary("说明：[GitHub](https://github.com/example/project)。"), "说明：GitHub。");
assert.equal(assetCardSummary(null), "暂无说明，待负责人补充。");
console.log("Asset card links: 17 assertions passed for filled links, deduplication, labels and URL safety.");
