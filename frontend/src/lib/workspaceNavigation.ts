// Historical workspaces remain available in production, but are absent from the test experience.
export function legacyWorkspaceEnabled(baseUrl: string, hostname: string): boolean {
  return !baseUrl.startsWith("/test") && !["localhost", "127.0.0.1"].includes(hostname);
}

const categoryLabels: Record<string, string> = {
  platform_account: "账号与身份", internal_system: "系统与 AI 成果",
  saas_software: "软件与订阅", api_service: "API 服务", cloud_network: "云资源与网络",
  data_storage: "数据与存储", domain_ip: "域名与资质", hardware_license: "设备与许可",
};
export function assetCategoryLabel(category: { code: string; name: string }): string {
  return categoryLabels[category.code] || category.name;
}
