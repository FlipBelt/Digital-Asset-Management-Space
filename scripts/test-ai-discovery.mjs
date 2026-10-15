import assert from "node:assert/strict";
import { aiDiscoveryGroup, aiDiscoveryGroups, aiDiscoveryCounts, filterAIDiscoveryAssets, isAIOutcome, loadAIDiscoveryAssets, isManagementSearchRoute, aiTypeName } from "../frontend/src/lib/aiDiscovery.ts";
const types = [
  { id: "skill", code: "ai_skill", name: "AI 技能" },
  { id: "plugin", code: "ai_plugin", name: "AI 插件" },
  { id: "workflow", code: "ai_workflow", name: "AI 工作流" },
  { id: "system", code: "internal_system", name: "内部系统" },
  { id: "script", code: "automation_script", name: "脚本" },
  { id: "cloud", code: "cloud_server", name: "云服务器" },
  { id: "future", code: "ai_future", name: "新 AI 成果" },
];
const asset = (id, type, method = null, description = null) => ({
  id, asset_type_id: type, development_method: method, archived_at: null,
  name: `成果 ${id}`, asset_code: id, description, updated_at: "2026-09-29T00:00:00Z",
});
for (const code of ["ai_prompt", "ai_template", "ai_skill"]) assert.equal(aiDiscoveryGroup(code), "knowledge");
for (const code of ["ai_plugin", "ai_mcp", "ai_agent"]) assert.equal(aiDiscoveryGroup(code), "assistants");
assert.equal(aiDiscoveryGroup("ai_workflow"), "workflows");
assert.equal(aiTypeName({ id: "workflow", code: "ai_workflow", name: "AI工作流/智能体" }), "AI 工作流");
assert.equal(aiTypeName({ id: "future", code: "ai_future", name: "新 AI 成果" }), "新 AI 成果");
assert.equal(aiDiscoveryGroup("automation_script"), "applications");
assert.equal(aiDiscoveryGroup("ai_future"), "other");
for (const code of ["cloud_server", "platform_tenant", "api_service", "saas_subscription", "registration_identity"]) {
  assert.equal(isAIOutcome(asset("resource", "x", "mixed"), { code }), false);
}
for (const method of [null, "traditional", "low_code"]) {
  assert.equal(isAIOutcome(asset("old-system", "system", method), types[3]), false);
}
for (const method of ["vibe_coding", "mixed"]) assert.equal(isAIOutcome(asset("app", "system", method), types[3]), true);
assert.equal(isAIOutcome({ ...asset("archived", "skill"), archived_at: "2026-09-28" }, types[0]), false);
assert.equal(isAIOutcome(asset("unknown", "none")), false);
assert.equal(aiDiscoveryGroups(types).at(-1).value, "other");
assert.equal(aiDiscoveryGroups(types.slice(0, -1)).length, 4);
const rows = [asset("k", "skill", null, "商品评论归纳"), asset("p", "plugin"), asset("w", "workflow"), asset("a", "system", "mixed"), asset("legacy", "system", "traditional"), asset("infra", "cloud"), asset("new", "future")];
assert.deepEqual(aiDiscoveryCounts(rows, types), { all: 5, knowledge: 1, assistants: 1, workflows: 1, applications: 1, other: 1 });
assert.deepEqual(filterAIDiscoveryAssets(rows, types, { group: "knowledge", keyword: "评论" }).map(item => item.id), ["k"]);
assert.deepEqual(filterAIDiscoveryAssets(rows, types, { type: "system" }).map(item => item.id), ["a"]);
assert.equal(filterAIDiscoveryAssets(rows, types, { keyword: "不存在" }).length, 0);
const requests = [];
const loaded = await loadAIDiscoveryAssets(types, async params => {
  requests.push(params);
  assert.notEqual(params.asset_type_id, "cloud");
  if (params.asset_type_id === "skill") return { data: Number(params.page) === 1 ? Array.from({ length: 100 }, (_, n) => asset(`k${n}`, "skill")) : [asset("k100", "skill")], pagination: { page: Number(params.page), total: 101 } };
  return { data: rows.filter(item => item.asset_type_id === params.asset_type_id), pagination: { page: Number(params.page), total: rows.filter(item => item.asset_type_id === params.asset_type_id).length } };
}, { scope: "team", department_id: "dept", keyword: "comment" });
assert.equal(loaded.length, 105);
assert.equal(requests.filter(params => params.asset_type_id === "skill").length, 2);
assert.ok(requests.every(params => params.scope === "team" && params.department_id === "dept" && params.page_size === "100"));
await assert.rejects(loadAIDiscoveryAssets([types[0]], async () => ({ data: [], pagination: { page: 1, total: 2 } }), { scope: "discover" }), /读取不完整/);
await assert.rejects(loadAIDiscoveryAssets([types[0]], async () => { throw new Error("unavailable"); }, { scope: "discover" }), /unavailable/);
const duplicated = await loadAIDiscoveryAssets([types[0], types[0]], async () => ({ data: [asset("same", "skill"), asset("same", "skill")], pagination: { page: 1, total: 2 } }), { scope: "discover" });
assert.equal(duplicated.length, 1);
for (const path of ["/manage", "/assets/123", "/intake", "/organization"]) assert.equal(isManagementSearchRoute(path), true);
for (const path of ["/discover", "/team", "/my", "/workflows", "/assets-unknown"]) assert.equal(isManagementSearchRoute(path), false);
console.log("AI discovery: outcome eligibility, purpose groups, filtered counts, full pagination, failure handling and search boundaries passed.");
