import type { CurrentUser } from "./api";

type Identity = Pick<CurrentUser, "roles" | "permissions"> | null;
export const managementSections = [
  { key: "overview", to: "/manage", label: "管理概览", description: "选择登记、维护和处理事项。", group: "overview" },
  { key: "assets", to: "/assets", label: "资产", description: "查询资产、维护资料与责任，归档或恢复记录。", group: "records" },
  { key: "accounts", to: "/accounts", label: "平台与账号", description: "维护平台、企业账号、登录身份和供应商。", group: "records" },
  { key: "organization", to: "/organization", label: "组织与授权", description: "核对公司、部门、人员与有效使用授权。", group: "records" },
  { key: "services", to: "/services", label: "订阅与用量", description: "查看服务、费用、余额和用量记录。", group: "records" },
  { key: "reviews", to: "/manage/reviews", label: "成果审核", description: "核对责任和资料，通过或退回当前成果版本。", group: "actions" },
  { key: "followup", to: "/manage/followup", label: "到期与责任", description: "跟进即将到期和仍缺负责人的资产。", group: "actions" },
  { key: "governance", to: "/governance", label: "申请与风险", description: "处理员工申请，跟进已发现的风险。", group: "actions" },
  { key: "imports", to: "/imports", label: "批量导入", description: "预览、校验并确认已有资料清单。", group: "records" },
  { key: "settings", to: "/manage?tab=settings", label: "系统设置", description: "维护类型、组织同步、连接器与审计。", group: "settings" },
] as const;

export function canManageWorkspace(user: Identity): boolean {
  return !!user?.roles.some(role => ["system_admin", "asset_manager", "department_manager", "group_leader", "auditor"].includes(role));
}
export function canRegisterBasics(user: Identity): boolean {
  return !!user?.roles.some(role => ["system_admin", "asset_manager"].includes(role));
}
export function managementItems(user: Identity) {
  if (!canManageWorkspace(user)) return [];
  const roles = user!.roles;
  const groupOnly = roles.includes("group_leader") && !roles.some(role => ["system_admin", "asset_manager", "department_manager", "auditor"].includes(role));
  return managementSections.filter(item => {
    if (item.key === "settings") return roles.includes("system_admin");
    if (item.key === "imports") return canRegisterBasics(user);
    if (item.key === "reviews" && !roles.some(role => ["system_admin", "asset_manager", "department_manager", "group_leader"].includes(role))) return false;
    return !groupOnly || ["overview", "assets", "organization", "reviews", "followup"].includes(item.key);
  });
}
export function managementSection(path: string, query: Record<string, unknown> = {}) {
  if (path === "/manage") return query.tab === "settings" ? "settings" : "overview";
  if (path.startsWith("/manage/reviews")) return "reviews";
  if (path.startsWith("/manage/followup")) return "followup";
  if (path === "/intake") return "register";
  if (path.startsWith("/directory/")) return path.startsWith("/directory/entity/") || path.startsWith("/directory/grant/") ? "organization" : "accounts";
  if (path === "/scenarios") return "assets";
  return managementSections.find(item => item.to !== "/manage" && (path === item.to || path.startsWith(item.to + "/")))?.key;
}

export const registrationKinds = [
  { mode: "resource", label: "系统、订阅与资源", description: "管理具体系统、服务、云资源或其他成果。" },
  { mode: "platform-account", label: "企业平台账号", description: "登记已经开通的企业账号或工作区。" },
  { mode: "platform", label: "服务平台", description: "登记提供服务的平台名称和官网。" },
  { mode: "identity", label: "登录与注册身份", description: "保管手机号、邮箱或其他登录标识。" },
  { mode: "entity", label: "公司主体", description: "登记真实公司及有来源的法人资料。" },
  { mode: "provider", label: "供应商", description: "记录服务提供方，供平台和服务引用。" },
  { mode: "grant", label: "人员使用授权", description: "分配已有批准依据的席位或使用权。" },
] as const;
export type RegistrationMode = "" | typeof registrationKinds[number]["mode"];
export function registrationMode(value: unknown): RegistrationMode {
  return typeof value === "string" && registrationKinds.some(item => item.mode === value) ? value as RegistrationMode : "";
}

// Keep existing bookmarks useful without loading a second application frame.
export function retiredWorkspaceTarget(path: string): string | null {
  if (path === "/hudu") return "/assets";
  if (path === "/hudu/intake") return "/imports";
  if (path === "/hudu/expirations") return "/manage/followup";
  const match = /^\/hudu\/assets\/([^/]+)$/.exec(path);
  if (match) return `/assets/${match[1]}`;
  if (path === "/dashboard") return "/my";
  if (path === "/department") return "/assets";
  return path.startsWith("/hudu/") ? "/assets" : null;
}
