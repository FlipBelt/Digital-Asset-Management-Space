import type { Department, DepartmentMembership, Person } from "./api";

export function organizationScope(
  legalEntityId: string | null | undefined,
  departments: Department[],
  people: Person[],
  memberships: DepartmentMembership[],
) {
  const scopedDepartments = departments.filter((item) => item.legal_entity_id === legalEntityId);
  const scopedPeople = people.filter((item) => item.legal_entity_id === legalEntityId);
  const departmentIds = new Set(scopedDepartments.map((item) => item.id));
  const personIds = new Set(scopedPeople.map((item) => item.id));
  return {
    departments: scopedDepartments,
    people: scopedPeople,
    memberships: memberships.filter((item) =>
      item.is_active && departmentIds.has(item.department_id) && personIds.has(item.person_id)),
  };
}

/** Project the latest source snapshot without deleting historical memberships. */
export function currentDirectoryScope(
  scoped: ReturnType<typeof organizationScope>,
  linkedPersonIds: string[],
  currentPersonIds?: string[] | null,
) {
  if (!currentPersonIds) return scoped;
  const linked = new Set(linkedPersonIds);
  const current = new Set(currentPersonIds);
  const people = scoped.people.filter(person => !linked.has(person.id) || current.has(person.id));
  const visible = new Set(people.map(person => person.id));
  return { departments: scoped.departments, people,
    memberships: scoped.memberships.filter(membership => visible.has(membership.person_id)) };
}
