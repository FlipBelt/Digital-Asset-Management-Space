import assert from "node:assert/strict";
import { dingTalkWebLoginError, safeLoginRedirect } from "../frontend/src/lib/loginNavigation.ts";

for (const path of ["/my/bookmarks", "/my/subscriptions", "/hudu", "/discover?category=workflows&q=AI"]) {
  assert.equal(safeLoginRedirect(path), path);
}
for (const path of [undefined, ["/my"], "//evil.example", "https://evil.example/", "/\\evil.example", "/../my", "/%2e%2e/my", "/%252e%252e/my", "/%2fevil.example", "/my?x=%0d%0aLocation:evil", "/login", "/api/dingtalk/web/callback", "/test/my", "not-a-route"]) {
  assert.equal(safeLoginRedirect(path), "/my");
}
assert.match(dingTalkWebLoginError("invalid_state"), /过期/);
assert.match(dingTalkWebLoginError("cancelled"), /取消/);
assert.match(dingTalkWebLoginError("access_denied"), /访问权限/);
assert.match(dingTalkWebLoginError("upstream-secret-body"), /重新发起/);
assert.equal(dingTalkWebLoginError(undefined), "");
console.log("Login return-route and error-state assertions passed.");
