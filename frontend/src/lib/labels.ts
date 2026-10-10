export const statusLabel: Record<string, string> = {
  active: "在用",
  draft: "待核验",
  pending: "待核验",
  pending_review: "待审核",
  not_required: "无需审核",
  pending_verification: "待核验",
  pending_handover: "待接管",
  verified: "已核验",
  paused: "停用",
  disabled: "停用",
  archived: "已归档",
  deleted: "已删除",
  approved: "已标准化",
  returned: "已退回",
  merged: "已合并",
};

export const criticalityLabel: Record<string, string> = {
  normal: "普通",
  important: "重要",
  critical: "关键",
};

export function displayStatus(value: string | null | undefined) {
  return value ? (statusLabel[value] ?? value) : "待核验";
}

export function displayCriticality(value: string | null | undefined) {
  return value ? (criticalityLabel[value] ?? value) : "普通";
}

export function displayReviewStatus(value: string | null | undefined) {
  const labels: Record<string, string> = { pending_review: '待审核', approved: '已通过', rejected: '已退回', not_required: '无需审核' };
  return value ? (labels[value] ?? displayStatus(value)) : '待审核';
}
