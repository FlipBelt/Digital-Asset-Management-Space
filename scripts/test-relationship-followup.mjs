import assert from "node:assert/strict";
import { relationshipPreview, relationshipSentence } from "../frontend/src/lib/relationship.ts";
import { groupFollowupItems } from "../frontend/src/lib/followup.ts";

assert.equal(relationshipPreview("企业账号", { relation_type: "DEPLOYED_ON", direction: "downstream" }, "知识门户"), "知识门户 → 部署在 → 企业账号");
assert.equal(relationshipPreview("知识门户", { relation_type: "CALLS", direction: "upstream" }, "接口"), "知识门户 → 调用 → 接口");
assert.equal(relationshipPreview("甲", { relation_type: "RELATED_TO", direction: "peer" }, "乙"), "甲 ↔ 乙（关联协作）");
const nodes = [{ id: "current", label: "知识门户" }, { id: "company", label: "公司" }];
assert.equal(relationshipSentence(nodes[0], { source: "current", target: "company", source_model: "Asset.legal_entity_id" }, nodes), "知识门户 → 归属公司 → 公司");
const items = [
  { id: "plan", group_key: "a", group_label: "企业账号", group_section: "accounts", followup_kind: "subscription", asset_code: "S", expires_at: "2026-11-01" },
  { id: "system", group_key: "business-assets", group_label: "业务资产", group_section: "assets", asset_code: "SYS" },
  { id: "account", group_key: "a", group_label: "企业账号", group_section: "accounts", followup_kind: "account", asset_code: "A" },
  { id: "unlinked", group_key: "platform:b", group_label: "其他平台", group_section: "accounts", asset_code: "U" },
];
const groups = groupFollowupItems(items);
assert.equal(groups.length, 3);
assert.deepEqual(groups.find(group => group.key === "a").items.map(row => row.id), ["account", "plan"]);
assert.equal(groups.flatMap(group => group.items).length, items.length);
assert.equal(groupFollowupItems([]).length, 0);
assert.equal(groupFollowupItems(items.filter(item => item.id === "plan"))[0].label, "企业账号");
console.log("Relationship direction and follow-up grouping: 9 assertions passed.");
