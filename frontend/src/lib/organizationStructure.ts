import type { Department, DepartmentMembership, DingTalkProfile, LegalEntity, Person } from "./api";

export interface OrganizationCompany {
  id: string;
  name: string;
  legalEntityId: string | null;
  source: "registered" | "directory" | "member_field";
}

interface OrganizationScope {
  departments: Department[];
  people: Person[];
  memberships: DepartmentMembership[];
}

export function organizationStructure(
  entity: LegalEntity | undefined,
  entities: LegalEntity[],
  scoped: OrganizationScope,
  profiles: DingTalkProfile[],
  directoryCodes?: string[] | null,
) {
  const empty = {
    companies: [] as OrganizationCompany[],
    departments: [] as Department[],
    staleNodes: [] as Department[],
    companyPeople: new Map<string, Person[]>(),
    pendingCompanyPeople: [] as Person[],
    unavailablePeople: [] as Person[],
  };
  if (!entity) return empty;
  const visibleCodes = directoryCodes?.length ? new Set(directoryCodes) : null;
  const visibleNodes = scoped.departments.filter((item) =>
    item.status === "active" && (!visibleCodes || !item.code.startsWith("DT-") || visibleCodes.has(item.code)));
  const staleNodes = scoped.departments.filter((item) => !visibleNodes.includes(item));
  const names = new Map<string, OrganizationCompany["source"]>([[entity.name, "registered"]]);
  const profileByPerson = new Map(profiles.map((profile) => [profile.person_id, profile]));
  const companyPeople = new Map<string, Person[]>();
  const pendingCompanyPeople: Person[] = [];
  const unavailablePeople: Person[] = [];
  for (const person of scoped.people) {
    const affiliation = profileByPerson.get(person.id)?.company_affiliation;
    if (affiliation?.status === "unavailable") unavailablePeople.push(person);
    if (affiliation?.status !== "available" || !affiliation.name ||
        affiliation.source_field !== "主体（社保公司）") {
      pendingCompanyPeople.push(person);
      continue;
    }
    if (!names.has(affiliation.name)) names.set(affiliation.name, "member_field");
    const members = companyPeople.get(affiliation.name) ?? [];
    members.push(person);
    companyPeople.set(affiliation.name, members);
  }
  const registeredNames = new Set(entities.map((item) => item.name));
  const isCompany = (item: Department) =>
    names.has(item.name) || registeredNames.has(item.name) || /(?:公司|合伙企业|个体工商户)$/.test(item.name);
  for (const item of visibleNodes) {
    if (isCompany(item) && !names.has(item.name)) names.set(item.name, "directory");
  }
  const companies = [...names].map(([name, source]) => {
    const registered = entities.filter((item) => item.name === name);
    return {
      id: `company:${name}`,
      name,
      legalEntityId: registered.length === 1 ? registered[0]!.id : null,
      source: registered.length === 1 ? "registered" as const : source,
    };
  }).sort((a, b) => Number(b.name === entity.name) - Number(a.name === entity.name) ||
    a.name.localeCompare(b.name, "zh-CN"));
  const byId = new Map(visibleNodes.map((item) => [item.id, item]));
  const departments = visibleNodes.filter((item) => !isCompany(item)).map((item) => {
    let parentId = item.parent_id;
    let nearestDepartment: string | null = null;
    const visited = new Set([item.id]);
    while (parentId) {
      if (visited.has(parentId)) { nearestDepartment = null; break; }
      visited.add(parentId);
      const parent = byId.get(parentId);
      if (!parent) break;
      if (!isCompany(parent) && !nearestDepartment) nearestDepartment = parent.id;
      parentId = parent.parent_id;
    }
    return { ...item, parent_id: nearestDepartment };
  });
  return { companies, departments, staleNodes, companyPeople, pendingCompanyPeople, unavailablePeople };
}

export function companyVerificationLabel(profile?: DingTalkProfile) {
  switch (profile?.company_affiliation?.status) {
    case "available": return "已核对";
    case "missing": return "公司字段未填写";
    case "invalid": return "公司字段格式待核对";
    case "conflict": return "公司字段内容冲突";
    case "unavailable": return "源资料不可查询";
    default: return "尚未核对公司字段";
  }
}
