import type { Asset } from "./api";

export interface AssetLink { label: string; url: string; kind: "repository" | "application" | "link" }

export function safeAssetUrl(value: string): string | null {
  const input = value.trim();
  if (/[^\S ]|[\u0000-\u001f\u007f]/.test(input)) return null;
  try {
    const url = new URL(input);
    return ["http:", "https:"].includes(url.protocol) && url.hostname && !url.username && !url.password
      ? url.href : null;
  } catch { return null; }
}

function trimUrl(value: string): string {
  let url = value.replace(/[.,;:!?。，；：！？、]+$/, "");
  while (url.endsWith(")") && (url.match(/\)/g)?.length || 0) > (url.match(/\(/g)?.length || 0)) url = url.slice(0, -1);
  return url;
}

export function assetLinks(asset: Pick<Asset, "card_links" | "description" | "source_reference" | "repository_visibility">): AssetLink[] {
  const result: AssetLink[] = [], seen = new Set<string>();
  function add(value: string, label = "") {
    const url = safeAssetUrl(trimUrl(value));
    if (!url || seen.has(url)) return;
    const hostname = new URL(url).hostname.replace(/^www\./, "");
    const repository = hostname === "github.com";
    if (repository && asset.repository_visibility !== "public") return;
    seen.add(url);
    const title = label.replace(/\u751f\u4ea7(?:环境|链接|地址|站点)?/g, "访问地址").trim();
    result.push({ url, label: repository && (!title || /^(代码仓库|GitHub(?:\s*仓库)?)$/i.test(title)) ? "GitHub" : title || hostname,
      kind: repository && (!title || /^(代码仓库|GitHub(?:\s*仓库)?)$/i.test(title)) ? "repository" : ["打开应用", "访问地址"].includes(title) ? "application" : "link" });
  }
  for (const link of asset.card_links || []) add(link.url, link.label);
  for (const text of [asset.description, asset.source_reference]) {
    if (!text) continue;
    const withoutMarkdown = text.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s<>]+?)\)/gi,
      (_, label: string, url: string) => { add(url, label); return ""; });
    for (const match of withoutMarkdown.matchAll(/https?:\/\/[^\s<>\[\]"'`，。；！？、]+/gi)) add(match[0]);
  }
  return result;
}

export function assetCardSummary(description: string | null): string {
  if (!description) return "暂无说明，待负责人补充。";
  const summary = description.replace(/\[([^\]\n]+)\]\(https?:\/\/[^\s<>]+?\)/gi, "$1")
    .replace(/https?:\/\/[^\s<>\[\]"'`，。；！？、]+/gi, "")
    .replace(/[ \t]+/g, " ").trim();
  return summary || "已登记访问链接，完整资料可在详情查看。";
}
