import type { Department, Person } from "./api";

export function findSelectablePeople(
  people: Person[], departments: Department[], query: string, departmentId = "", excludedIds: string[] = [],
): Person[] {
  const names = new Map(departments.map(item => [item.id, item.name]));
  const excluded = new Set(excludedIds);
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return people.filter(person => {
    if (person.employment_status !== "active" || excluded.has(person.id)) return false;
    if (departmentId && person.department_id !== departmentId) return false;
    const text = `${person.display_name} ${person.employee_no} ${names.get(person.department_id ?? "") ?? ""}`.toLocaleLowerCase();
    return words.every(word => text.includes(word));
  });
}

export function togglePersonSelection(selectedIds: string[], personId: string, checked: boolean): string[] {
  const next = new Set(selectedIds);
  if (checked) next.add(personId);
  else next.delete(personId);
  return [...next];
}
