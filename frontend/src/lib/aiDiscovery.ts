import type { Asset, AssetListResponse, AssetType } from "./api";

export const AI_DISCOVERY_GROUPS = [
  { value: "knowledge", label: "知识与方法", purpose: "把经验变成可复用的方法", description: "查找提示词、模板和技能，借鉴已有的判断规则与操作方法。" },
  { value: "assistants", label: "工具与助手", purpose: "让 AI 帮你处理具体任务", description: "查找插件、连接工具与智能体，了解它们能做什么、如何使用。" },
  { value: "applications", label: "应用与自动化", purpose: "把 AI 能力落到业务应用", description: "复用已登记的 AI 辅助开发应用和脚本，减少重复操作。" },
  { value: "workflows", label: "业务工作流", purpose: "把单次成果连接成工作方法", description: "了解工作步骤、关键判断和关联成果，将 AI 用到完整业务流程。" },
] as const;
const otherGroup = { value: "other", label: "其他 AI 成果", purpose: "发现新的 AI 用法", description: "查看已登记的其他 AI 成果，了解说明与共享范围。" };
const assistedCodes = new Set(["internal_system", "automation_script"]);
const assistedMethods = new Set(["vibe_coding", "mixed"]);
type CatalogType = Pick<AssetType, "id" | "code" | "name">;
type Outcome = Pick<Asset, "asset_type_id" | "development_method" | "archived_at">;

export function aiDiscoveryGroup(code: string): string {
  if (["ai_prompt", "ai_template", "ai_skill"].includes(code)) return "knowledge";
  if (["ai_plugin", "ai_mcp", "ai_agent"].includes(code)) return "assistants";
  if (code === "ai_workflow") return "workflows";
  if (assistedCodes.has(code) || code === "ai_application") return "applications";
  return "other";
}

export function isAIOutcome(asset: Outcome, type?: Pick<AssetType, "code">): boolean {
  if (!type || asset.archived_at) return false;
  return type.code.startsWith("ai_") || (assistedCodes.has(type.code) && assistedMethods.has(asset.development_method || ""));
}

export function aiDiscoveryGroups(catalog: CatalogType[]) {
  const other = catalog.some(type => type.code.startsWith("ai_") && aiDiscoveryGroup(type.code) === "other");
  return [...AI_DISCOVERY_GROUPS, ...(other ? [otherGroup] : [])];
}

export function aiTypeName(type?: CatalogType): string {
  if (!type) return "AI 成果";
  return ({
    ai_prompt: "AI 提示词", ai_template: "AI 模板", ai_skill: "AI 技能", ai_plugin: "AI 插件",
    ai_mcp: "MCP 连接工具", ai_agent: "AI 智能体", ai_workflow: "AI 工作流",
    internal_system: "AI 辅助开发应用", automation_script: "AI 辅助自动化脚本",
  } as Record<string, string>)[type.code] || type.name;
}

export function aiDiscoveryCounts(assets: Asset[], catalog: CatalogType[]): Record<string, number> {
  const counts: Record<string, number> = { all: 0 };
  const types = new Map(catalog.map(type => [type.id, type]));
  for (const asset of assets) {
    const type = types.get(asset.asset_type_id);
    if (!isAIOutcome(asset, type)) continue;
    const group = aiDiscoveryGroup(type!.code);
    counts.all! += 1;
    counts[group] = (counts[group] || 0) + 1;
  }
  return counts;
}

export function filterAIDiscoveryAssets(assets: Asset[], catalog: CatalogType[], filters: { group?: string; type?: string; keyword?: string }) {
  const types = new Map(catalog.map(type => [type.id, type]));
  const keyword = (filters.keyword || "").trim().toLocaleLowerCase();
  return assets.filter(asset => {
    const type = types.get(asset.asset_type_id);
    if (!isAIOutcome(asset, type)) return false;
    if (filters.group && filters.group !== "all" && aiDiscoveryGroup(type!.code) !== filters.group) return false;
    if (filters.type && asset.asset_type_id !== filters.type) return false;
    return !keyword || [asset.name, asset.asset_code, asset.description, aiTypeName(type)].join(" ").toLocaleLowerCase().includes(keyword);
  });
}

// The preview uses existing per-type endpoints. Never request the full company
// catalog, or count a single page as the complete collection of AI outcomes.
export async function loadAIDiscoveryAssets(
  catalog: CatalogType[],
  fetchPage: (params: Record<string, string>) => Promise<AssetListResponse>,
  params: Record<string, string>,
): Promise<Asset[]> {
  const types = [...new Map(catalog.filter(type => type.code.startsWith("ai_") || assistedCodes.has(type.code)).map(type => [type.id, type])).values()];
  const results = await Promise.all(types.map(async type => {
    const rows: Asset[] = [];
    let page = 1;
    let total = 0;
    do {
      const result = await fetchPage({ ...params, category: "all", asset_type_id: type.id, page: String(page), page_size: "100" });
      if (!Number.isSafeInteger(result.pagination.total) || result.pagination.total < 0 || result.pagination.page !== page ||
        (!result.data.length && (page - 1) * 100 < result.pagination.total)) throw new Error("AI 资产读取不完整，请重试。");
      total = result.pagination.total;
      rows.push(...result.data.filter(asset => asset.asset_type_id === type.id && isAIOutcome(asset, type)));
      page += 1;
    } while ((page - 1) * 100 < total);
    return rows;
  }));
  return [...new Map(results.flat().map(asset => [asset.id, asset])).values()]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at) || a.id.localeCompare(b.id));
}

export function isManagementSearchRoute(path: string): boolean {
  return ["/manage", "/assets", "/accounts", "/organization", "/services", "/governance", "/imports", "/intake", "/scenarios", "/admin", "/hudu"]
    .some(base => path === base || path.startsWith(base + "/"));
}
