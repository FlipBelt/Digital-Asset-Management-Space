import sources from "../assets/platform-logos/sources.json";

const images = import.meta.glob<string>("../assets/platform-logos/*.{svg,png,ico,webp}", { eager: true, query: "?url", import: "default" });
export interface PlatformBrand { key: string; label: string; src: string; names: string[]; websiteHosts: string[]; wide: boolean; requiresWebsite: boolean }
const normalize = (value: string) => value.normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase("en-US");
const pending = new Set(sources.pendingNames.map(normalize));
export const platformBrands: PlatformBrand[] = sources.brands.flatMap(item => {
  const src = images[`../assets/platform-logos/${item.asset}`];
  const dimensions = "dimensions" in item ? item.dimensions : undefined;
  const wide = Boolean(dimensions && dimensions[1] && dimensions[0]! / dimensions[1] >= 2.4);
  const requiresWebsite = Boolean("requiresWebsite" in item && item.requiresWebsite);
  return src ? [{ key: item.key, label: item.names[0]!, src, names: item.names, websiteHosts: item.websiteHosts, wide, requiresWebsite }] : [];
});

function websiteHost(website?: string | null) {
  if (!website) return null;
  try {
    const url = new URL(website);
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password || url.port) return null;
    return url.hostname.toLowerCase().replace(/^www\./, "");
  } catch { return null; }
}

export function resolvePlatformBrand(name: string, website?: string | null): PlatformBrand | null {
  const normalized = normalize(name);
  if (pending.has(normalized)) return null;
  const named = platformBrands.find(brand => brand.names.some(alias => normalize(alias) === normalized));
  const host = websiteHost(website);
  const hosted = host ? platformBrands.find(brand => brand.websiteHosts.includes(host)) : undefined;
  if (named?.requiresWebsite && !named.websiteHosts.includes(host || "")) return null;
  // A conflicting known brand is a data ambiguity, not a reason to guess a logo.
  if (named && hosted && named.key !== hosted.key) return null;
  return named || hosted || null;
}
