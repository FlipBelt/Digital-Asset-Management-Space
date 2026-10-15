import type { PlatformDirectoryEntry, PlatformHierarchy } from "./api";
import type { LocationQueryRaw } from "vue-router";

export function platformAccountGroups(directory: PlatformDirectoryEntry[], platforms: PlatformHierarchy[], query = "") {
  const counts = new Map(platforms.map(platform => [platform.id, platform.company_accounts.length + platform.personal_accounts.length]));
  const search = query.trim().toLocaleLowerCase();
  const rows = directory.filter(row => `${row.name} ${row.provider_name || ""}`.toLocaleLowerCase().includes(search))
    .map(entry => ({ ...entry, accountCount: counts.get(entry.id) || 0 }))
    .sort((a, b) => b.accountCount - a.accountCount || a.name.localeCompare(b.name, "zh-CN") || a.id.localeCompare(b.id));
  return [
    { key: "with-accounts", label: "已有账号", entries: rows.filter(row => row.accountCount > 0) },
    { key: "without-accounts", label: "暂无账号", entries: rows.filter(row => row.accountCount === 0) },
  ];
}

export function legacyServiceTarget(path: string, query: LocationQueryRaw = {}, hash = "") {
  const normalized = path.replace(/\/+$/, "");
  if (normalized === "/services") return { path: "/accounts", query: { ...query, section: "usage" }, hash };
  const match = /^\/services\/(alerts|deepseek|minimax|aliyun)$/.exec(normalized);
  return match ? { path: `/accounts/usage/${match[1]}`, query, hash } : null;
}
