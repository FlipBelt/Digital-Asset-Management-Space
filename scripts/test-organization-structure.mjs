import assert from "node:assert/strict";
import { organizationStructure } from "../frontend/src/lib/organizationStructure.ts";
import { organizationScope } from "../frontend/src/lib/organizationScope.ts";

const entity = { id: "a", name: "合成组织有限公司", code: "A", status: "active" };
const other = { id: "b", name: "合成其他有限公司", code: "B", status: "active" };
const departments = [
  { id: "company", legal_entity_id: "a", name: "合成创作有限公司", parent_id: null, code: "DT-1", status: "active" },
  { id: "team", legal_entity_id: "a", name: "设计部", parent_id: null, code: "DT-2", status: "active" },
  { id: "child", legal_entity_id: "a", name: "设计组", parent_id: "team", code: "DT-3", status: "active" },
  { id: "stale", legal_entity_id: "a", name: "旧部门", parent_id: null, code: "DT-4", status: "active" },
  { id: "other", legal_entity_id: "b", name: "其他部门", parent_id: null, code: "DT-5", status: "active" },
];
const people = [
  { id: "creator", legal_entity_id: "a", department_id: "team", display_name: "合成创作成员" },
  { id: "contact", legal_entity_id: "a", department_id: "team", display_name: "合成通讯录联系人" },
  { id: "unavailable", legal_entity_id: "a", department_id: "team", display_name: "合成待核验成员" },
  { id: "other", legal_entity_id: "b", department_id: "other", display_name: "合成外部成员" },
];
const memberships = [
  { id: "creator", person_id: "creator", department_id: "team", is_active: true, is_primary: true },
  { id: "contact", person_id: "contact", department_id: "company", is_active: true },
];
const profiles = [
  { person_id: "creator", company_affiliation: { name: "合成创作有限公司", source_field: "主体（社保公司）", status: "available" } },
  { person_id: "contact", company_affiliation: { name: entity.name, source_field: "主体（社保公司）", status: "available" } },
  { person_id: "unavailable", company_affiliation: { name: null, source_field: "主体（社保公司）", status: "unavailable" } },
  { person_id: "other", company_affiliation: { name: "合成创作有限公司", source_field: "主体（社保公司）", status: "available" } },
];
const original = structuredClone({ departments, people, memberships, profiles });
const scoped = organizationScope("a", departments, people, memberships);
const result = organizationStructure(entity, [entity, other], scoped, profiles, ["DT-1", "DT-2", "DT-3"]);
assert.deepEqual(result.departments.map(row => row.id), ["team", "child"]);
assert.equal(result.departments.find(row => row.id === "child").parent_id, "team");
assert.deepEqual(result.staleNodes.map(row => row.id), ["stale"]);
assert.deepEqual(result.companyPeople.get("合成创作有限公司").map(row => row.id), ["creator"]);
assert.deepEqual(result.companyPeople.get(entity.name).map(row => row.id), ["contact"]);
assert.deepEqual(result.pendingCompanyPeople.map(row => row.id), ["unavailable"]);
assert.deepEqual(result.unavailablePeople.map(row => row.id), ["unavailable"]);
assert.equal(result.companies.length, 2);
assert.equal(result.companies[0].legalEntityId, "a");
assert.equal(result.companies.find(row => row.name === "合成创作有限公司").legalEntityId, null);
assert.deepEqual({ departments, people, memberships, profiles }, original);
const noBinding = organizationStructure(undefined, [entity], scoped, profiles);
assert.equal(noBinding.companies.length, 0);
assert.equal(noBinding.departments.length, 0);
const cycles = [{ ...departments[1], parent_id: "child" }, { ...departments[2], parent_id: "team" }];
const cyclic = organizationStructure(entity, [entity], { ...scoped, departments: cycles }, profiles);
assert.ok(cyclic.departments.every(row => row.parent_id === null));
const nested = organizationStructure(entity, [entity], {
  ...scoped, departments: [{ ...departments[0], parent_id: "team" }, departments[1], { ...departments[2], parent_id: "company" }],
}, profiles);
assert.equal(nested.departments.find(row => row.id === "child").parent_id, "team");
const forged = organizationStructure(entity, [entity], scoped, [{
  person_id: "creator", company_affiliation: { name: "合成创作有限公司", source_field: "client-claim", status: "available" },
}]);
assert.equal(forged.companyPeople.size, 0);
console.log("Organization structure: 16 assertions passed, including distinct company/member sources, isolation, stale nodes and cycles.");
