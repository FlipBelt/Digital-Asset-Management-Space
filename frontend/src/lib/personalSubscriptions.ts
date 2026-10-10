import type { Asset } from "./api";
import { displayStatus } from "./labels";

export function isPersonalSubscription(asset: Pick<Asset, "is_personal_subscription">) {
  return asset.is_personal_subscription === true;
}

export function subscriptionStatus(asset: Pick<Asset, "is_personal_subscription" | "status">) {
  return isPersonalSubscription(asset) && ["active", "draft"].includes(asset.status)
    ? "已登记" : displayStatus(asset.status);
}
