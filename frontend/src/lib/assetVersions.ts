/** Published outcome identity is independent of the API's optimistic lock revision. */
export function displayOutcomeVersion(asset: { outcome_version?: number; sharing_scope?: string | null; version: number }): string {
  if (asset.sharing_scope == null) return `资料修订 ${asset.version}`;
  return asset.outcome_version ? `成果 V${asset.outcome_version}` : "待首次登记";
}
