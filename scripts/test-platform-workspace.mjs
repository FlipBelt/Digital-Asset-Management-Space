import assert from "node:assert/strict";
import { platformAccountGroups, legacyServiceTarget } from "../frontend/src/lib/platformWorkspace.ts";
import { managementItems, managementSection } from "../frontend/src/lib/managementWorkspace.ts";

const directory = [
  { id: "zero", name: "空平台", provider_name: "Empty" },
  { id: "one", name: "一个账号", provider_name: "First" },
  { id: "three", name: "三个账号", provider_name: "Third" },
  { id: "tie", name: "两个账号", provider_name: "Second" },
  { id: "two", name: "两个账号", provider_name: "Second" },
  { id: "missing", name: "无账号层级", provider_name: null },
];
const platforms = [
  { id: "one", company_accounts: [{ children: [1, 2, 3] }], personal_accounts: [] },
  { id: "three", company_accounts: [{}, {}], personal_accounts: [{}] },
  { id: "two", company_accounts: [{}], personal_accounts: [{}] },
  { id: "tie", company_accounts: [], personal_accounts: [{}, {}] },
];
const original = structuredClone({ directory, platforms });
const groups = platformAccountGroups(directory, platforms);
assert.deepEqual(groups.map(group => group.label), ["已有账号", "暂无账号"]);
assert.deepEqual(groups[0].entries.map(row => row.id), ["three", "tie", "two", "one"]);
assert.deepEqual(groups[0].entries.map(row => row.accountCount), [3, 2, 2, 1]);
assert.equal(groups[1].entries.length, 2);
assert.ok(groups[1].entries.every(row => row.accountCount === 0));
assert.deepEqual({ directory, platforms }, original);
assert.deepEqual(platformAccountGroups(directory, platforms, " SECOND ")[0].entries.map(row => row.id), ["tie", "two"]);
assert.equal(platformAccountGroups(directory, platforms, "空平台")[1].entries[0].id, "zero");
assert.ok(platformAccountGroups(directory, platforms, "不存在").every(group => group.entries.length === 0));
assert.ok(platformAccountGroups([], []).every(group => group.entries.length === 0));

for (const suffix of ["alerts", "deepseek", "minimax", "aliyun"]) {
  assert.deepEqual(legacyServiceTarget(`/services/${suffix}`, { q: "保留", tag: ["a", "b"] }, "#record"),
    { path: `/accounts/usage/${suffix}`, query: { q: "保留", tag: ["a", "b"] }, hash: "#record" });
  assert.equal(managementSection(`/accounts/usage/${suffix}`), "accounts");
  assert.equal(managementSection(`/services/${suffix}`), "accounts");
}
assert.deepEqual(legacyServiceTarget("/services", { section: "old", platform: "one" }, "#usage"),
  { path: "/accounts", query: { section: "usage", platform: "one" }, hash: "#usage" });
assert.equal(legacyServiceTarget("/services/unrecognized"), null);
assert.equal(legacyServiceTarget("/accounts"), null);
assert.deepEqual(legacyServiceTarget("/services/", { q: "keep" }, "#kept"), { path: "/accounts", query: { q: "keep", section: "usage" }, hash: "#kept" });
assert.deepEqual(legacyServiceTarget("/services/deepseek/", { q: "keep" }, "#kept"), { path: "/accounts/usage/deepseek", query: { q: "keep" }, hash: "#kept" });
assert.equal(managementSection("/accounts", { section: "usage" }), "accounts");
const adminItems = managementItems({ roles: ["system_admin"], permissions: [] });
assert.equal(adminItems.filter(item => item.key === "accounts").length, 1);
assert.ok(!adminItems.some(item => item.key === "services"));
assert.deepEqual(managementItems({ roles: ["employee"], permissions: [] }), []);
console.log("Platform workspace: 31 assertions passed (groups, counts, stable ordering, search, legacy links and navigation).");
