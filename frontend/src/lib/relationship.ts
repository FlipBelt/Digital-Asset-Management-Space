import type { RelationshipChoice, RelationshipEdge, RelationshipNode } from "./api";

export const relationshipGroups = [
  { key: "ownership", label: "归属与管理" }, { key: "deployment", label: "部署与挂载" },
  { key: "usage", label: "调用与使用" }, { key: "other", label: "其他关联" },
] as const;

const forwardLabels: Record<string, string> = {
  OWNED_BY: "归属", ON_PLATFORM: "所属平台", DEPLOYED_ON: "部署在", MOUNTED_ON: "挂载到",
  CALLS: "调用", USES: "使用", MANAGES: "管理", DEPENDS_ON: "依赖", RELATED_TO: "关联协作",
};
export function relationshipPreview(current: string, choice?: RelationshipChoice, target?: string) {
  if (!choice) return "请选择一种关系";
  const other = target || "待选择的对象";
  const [source, destination] = choice.direction === "downstream" ? [other, current] : [current, other];
  if (choice.direction === "peer") return `${source} ↔ ${destination}（关联协作）`;
  return `${source} → ${forwardLabels[choice.relation_type] || choice.label} → ${destination}`;
}
export function relationshipSentence(current: RelationshipNode, edge: RelationshipEdge, nodes: RelationshipNode[]) {
  const source = nodes.find(row => row.id === edge.source)?.label || "关联对象";
  const target = nodes.find(row => row.id === edge.target)?.label || "关联对象";
  const other = edge.source === current.id ? target : source;
  if (edge.source_model === "Asset.legal_entity_id") return `${current.label} → 归属公司 → ${other}`;
  if (edge.source_model === "Asset.owner_department_id") return `${current.label} → 归属部门 → ${other}`;
  if (edge.source_model === "PlatformTenant.platform_id") return `${current.label} → 所属平台 → ${other}`;
  if (edge.source_model === "PlatformAccountRegistrationIdentity") return `${current.label} → 注册时使用 → ${other}`;
  if (edge.section === "responsibility") return `${current.label} → ${edge.label} → ${other}`;
  return `${source} → ${edge.label} → ${target}`;
}

/**
 * Resolve a relationship node to the detail page that represents its model.
 * The backend href remains authoritative when present, while asset_id/kind
 * provide a stable fallback for older or partially populated relationship rows.
 */
export function relationshipNodeHref(node?: RelationshipNode | null): string {
  if (!node) return "/assets";
  if (node.href && node.href !== "/assets") return node.href;
  if (node.asset_id) return `/assets/${node.asset_id}`;

  const nodeId = node.id.replace(/^(entity|platform|grant):/, "");
  if (node.kind === "entity" || node.id.startsWith("entity:"))
    return `/directory/entity/${nodeId}`;
  if (node.kind === "platform" || node.id.startsWith("platform:"))
    return `/directory/platform/${nodeId}`;
  if (node.kind === "grant" || node.id.startsWith("grant:"))
    return `/directory/grant/${nodeId}`;
  if (node.kind === "person" || node.kind === "department") return "/organization";
  return node.href ?? "/assets";
}
