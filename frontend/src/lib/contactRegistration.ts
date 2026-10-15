import type { Department, Person, RegistrationIdentity } from "./api";

export interface ContactRow {
  identifier: string; legal_entity_id: string | null; custodian_person_id: string | null;
  owner_department_id: string | null; source_nature: string; verification_status: "documented";
  registration_blocked: boolean; expected_version: number | null; note: string;
}

export function contactIdentifier(value: string): string | null {
  const compact = value.trim().replace(/[\s-]/g, "").replace(/^\+86/, "");
  if (/^1\d{10}$/.test(compact)) return compact;
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value.trim()) ? value.trim().toLocaleLowerCase() : null;
}

export function contactCustodians(people: Person[], companyId: string | null, allowCrossCompany = false) {
  return people.filter(person => person.employment_status === "active" &&
    (allowCrossCompany || !companyId || person.legal_entity_id === companyId));
}

export function contactDepartments(departments: Department[], companyId: string | null, allowCrossCompany = false) {
  return departments.filter(department => allowCrossCompany || !companyId || department.legal_entity_id === companyId);
}

export function parseContactRows(text: string, people: Person[], departments: Department[], identities: RegistrationIdentity[], companyId: string, allowCrossCompany = false) {
  const rows: ContactRow[] = [], errors: string[] = [], seen = new Set<string>();
  const departmentAlias = (name: string) => ({ "技术部": "信息技术部", "行政人事部": "人事行政部" }[name] || name);
  for (const [index, line] of text.trim().split(/\r?\n/).entries()) {
    if (!line.trim()) continue;
    const [raw = "", holder = "", sourceDepartment = "", note = ""] = line.split("\t").map(value => value.trim());
    const identifier = contactIdentifier(raw);
    if (!identifier) { errors.push(`第 ${index + 1} 行：手机号或邮箱格式无效`); continue; }
    if (seen.has(identifier)) { errors.push(`第 ${index + 1} 行：号码或邮箱重复`); continue; }
    seen.add(identifier);
    const shared = ["转发器", "前台手机", "共用"].includes(holder);
    const candidates = shared ? [] : contactCustodians(people, companyId, allowCrossCompany).filter(person =>
      (person.display_name.toLocaleLowerCase() === holder.toLocaleLowerCase() || person.display_name.split(/[-－]/)[0]?.toLocaleLowerCase() === holder.toLocaleLowerCase()));
    const companyPeople = candidates.filter(person => person.legal_entity_id === companyId);
    const matches = companyPeople.length ? companyPeople : candidates;
    if (!shared && matches.length !== 1) { errors.push(`第 ${index + 1} 行：请核对“${holder}”的唯一在职人员`); continue; }
    const person = matches[0], entityId = companyId || person?.legal_entity_id || "";
    const departmentCandidates = contactDepartments(departments, entityId, allowCrossCompany).filter(team => team.name === departmentAlias(sourceDepartment));
    const companyTeams = departmentCandidates.filter(team => team.legal_entity_id === entityId);
    const teams = companyTeams.length ? companyTeams : departmentCandidates;
    if (teams.length > 1) { errors.push(`第 ${index + 1} 行：请核对“${sourceDepartment}”的唯一使用部门`); continue; }
    const departmentId = teams.length === 1 ? teams[0]!.id : person?.department_id || null;
    if (!person && !departmentId) { errors.push(`第 ${index + 1} 行：共用号码需要明确使用部门`); continue; }
    const previous = identities.find(item => contactIdentifier(item.identifier) === identifier);
    rows.push({ identifier, legal_entity_id: entityId || null, custodian_person_id: person?.id || null,
      owner_department_id: departmentId, source_nature: "company_owned", verification_status: "documented",
      registration_blocked: /勿用|禁止.*注册/.test(note), expected_version: previous?.version || null,
      note: `来源使用人：${holder}；来源使用部门：${sourceDepartment}。${note}` });
  }
  return { rows, errors };
}
