import assert from "node:assert/strict";
import { organizationScope } from "../frontend/src/lib/organizationScope.ts";

const departments = [
  { id: "a-root", legal_entity_id: "a", parent_id: null },
  { id: "a-child", legal_entity_id: "a", parent_id: "a-root" },
  { id: "b-root", legal_entity_id: "b", parent_id: null },
];
const people = [
  { id: "a-person", legal_entity_id: "a" },
  { id: "a-manager", legal_entity_id: "a" },
  { id: "b-person", legal_entity_id: "b" },
];
const memberships = [
  { id: "a-member", person_id: "a-person", department_id: "a-root", is_active: true },
  { id: "a-manager", person_id: "a-manager", department_id: "a-child", is_active: true, is_manager: true },
  { id: "b-member", person_id: "b-person", department_id: "b-root", is_active: true, is_manager: true },
  { id: "cross-person", person_id: "b-person", department_id: "a-root", is_active: true },
  { id: "cross-dept", person_id: "a-person", department_id: "b-root", is_active: true },
  { id: "inactive", person_id: "a-person", department_id: "a-child", is_active: false },
  { id: "unknown", person_id: "unknown", department_id: "a-child", is_active: true },
];
const input = structuredClone({ departments, people, memberships });
const scoped = organizationScope("a", departments, people, memberships);
assert.deepEqual(scoped.departments.map(item => item.id), ["a-root", "a-child"]);
assert.deepEqual(scoped.people.map(item => item.id), ["a-person", "a-manager"]);
assert.deepEqual(scoped.memberships.map(item => item.id), ["a-member", "a-manager"]);
assert.equal(scoped.memberships.filter(item => item.is_manager).length, 1);
for (const id of [undefined, null, "missing"]) {
  assert.deepEqual(organizationScope(id, departments, people, memberships), { departments: [], people: [], memberships: [] });
}
assert.deepEqual(organizationScope("a", [], [], []), { departments: [], people: [], memberships: [] });
assert.deepEqual({ departments, people, memberships }, input);
console.log("Organization scoping: 9 assertions passed, including cross-company and missing-binding boundaries.");
