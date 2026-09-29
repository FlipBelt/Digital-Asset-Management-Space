export interface AssetReturnContext {
  to: string;
  path: string;
  category: "all" | "workflows";
  label: string;
}

const spaceLabels: Record<string, string> = {
  "/my": "我的首页",
  "/my/created": "我创建的",
  "/my/responsible": "我负责的",
  "/my/subscriptions": "我的订阅",
  "/my/using": "我使用的",
  "/my/ai": "我的 AI 能力",
  "/my/contributions": "我的贡献",
  "/my/drafts": "我的草稿",
  "/my/bookmarks": "我的收藏",
  "/discover": "资产发现",
  "/team": "团队空间",
};
const fallback: AssetReturnContext = { to: "/discover", path: "/discover", category: "all", label: "资产发现" };
const allowedQuery = new Set(["q", "type", "team", "page", "category", "subscription", "group"]);

// A detail link may preserve list context, but never redirect outside a known workspace.
export function assetReturnContext(value: unknown): AssetReturnContext {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return { ...fallback };
  try {
    const url = new URL(value, "http://asset-center.invalid");
    if (url.origin !== "http://asset-center.invalid" || !Object.hasOwn(spaceLabels, url.pathname)) return { ...fallback };
    for (const key of [...url.searchParams.keys()]) if (!allowedQuery.has(key)) url.searchParams.delete(key);
    const category = url.searchParams.get("category") === "workflows" ? "workflows" : "all";
    const label = url.pathname === "/discover" && category === "workflows" ? "工作流" : spaceLabels[url.pathname]!;
    return { to: url.pathname + url.search, path: url.pathname, category, label };
  } catch { return { ...fallback }; }
}

export function assetListPage(value: unknown): number {
  const page = typeof value === "string" ? Number(value) : NaN;
  return Number.isSafeInteger(page) && page >= 1 ? page : 1;
}
