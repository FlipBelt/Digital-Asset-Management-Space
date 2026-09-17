import type { RelationshipNode } from "./api";

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
