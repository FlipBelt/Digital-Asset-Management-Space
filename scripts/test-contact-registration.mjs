import assert from "node:assert/strict";
import { contactIdentifier, parseContactRows } from "../frontend/src/lib/contactRegistration.ts";

const people = [{ id: "p1", display_name: "惜君-测试员工", employment_status: "active", legal_entity_id: "c1", department_id: "d1" },
  { id: "p2", display_name: "离职-测试员工", employment_status: "departed", legal_entity_id: "c1", department_id: "d1" }];
const departments = [{ id: "d1", name: "信息技术部", legal_entity_id: "c1" }];
const identities = [{ identifier: "18958354558", version: 6 }];
const parse = (text, rows = people) => parseContactRows(text, rows, departments, identities, "c1");
assert.equal(contactIdentifier("+86 189-5835-4558"), "18958354558");
assert.equal(contactIdentifier("Test@Example.COM"), "test@example.com");
assert.equal(contactIdentifier("not-a-phone"), null);
const source = parse("18958354558\t惜君\t技术部\t宁波");
assert.equal(source.errors.length, 0);
assert.equal(source.rows[0].custodian_person_id, "p1");
assert.equal(source.rows[0].expected_version, 6);
assert.equal(source.rows[0].owner_department_id, "d1");
const shared = parse("17365822471\t转发器\t技术部\t共用转发");
assert.equal(shared.rows[0].custodian_person_id, null);
assert.equal(shared.rows[0].owner_department_id, "d1");
assert.equal(parse("17365822471\t前台手机\t不存在的部门").errors.length, 1);
assert.equal(parse("18958354558\t离职\t技术部").errors.length, 1);
assert.equal(parse("18958354558\t惜君\t技术部", [...people, { ...people[0], id: "ambiguous" }]).errors.length, 1);
assert.equal(parse("18958354558\t惜君\t技术部\t法人手机号（勿用）").rows[0].registration_blocked, true);
assert.equal(parse("18958354558\t惜君\t技术部\n+8618958354558\t惜君\t技术部").errors.length, 1);
console.log("Contact registration: 14 assertions passed for normalization, real holder matching, shared resources, restrictions and updates.");
