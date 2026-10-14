import type { HuduFollowupItem } from "./api";

export function groupFollowupItems(items: HuduFollowupItem[]) {
  const groups = new Map<string, { key: string; label: string; section: "accounts" | "assets";
    href: string | null; platform: string | null; items: HuduFollowupItem[] }>();
  for (const item of items) {
    const key = item.group_key || "business-assets";
    if (!groups.has(key)) groups.set(key, { key, label: item.group_label || "业务资产",
      section: item.group_section || "assets", href: item.group_href || null,
      platform: item.platform_name || null, items: [] });
    groups.get(key)!.items.push(item);
  }
  for (const group of groups.values()) group.items.sort((a, b) =>
    Number(b.followup_kind === "account") - Number(a.followup_kind === "account")
    || (a.expires_at || "9999").localeCompare(b.expires_at || "9999")
    || a.asset_code.localeCompare(b.asset_code));
  return [...groups.values()].sort((a, b) => a.label.localeCompare(b.label, "zh-CN"));
}
