/** Restrict post-login navigation to a route within the current frontend mount. */
export function safeLoginRedirect(value: unknown): string {
  if (typeof value !== "string" || !value || value.length > 2000) return "/my";
  try {
    const decoded = decodeURIComponent(value);
    if (/[\\\u0000-\u001f\u007f]/.test(decoded)) return "/my";
    // Validate before URL parsing: URL would normalize dot segments across /test/.
    const rawPath = decodeURIComponent(value.split(/[?#]/, 1)[0] || "");
    if (!/^\/[A-Za-z0-9/_-]*$/.test(rawPath) || rawPath.startsWith("//")) return "/my";
    if (rawPath === "/login" || rawPath.startsWith("/api/") || rawPath === "/test" || rawPath.startsWith("/test/")) return "/my";
    const parsed = new URL(value, "https://asset-center.invalid");
    if (parsed.origin !== "https://asset-center.invalid") return "/my";
    return rawPath + parsed.search;
  } catch {
    return "/my";
  }
}

export function dingTalkWebLoginError(value: unknown): string {
  const messages: Record<string, string> = {
    unavailable: "扫码登录暂未配置，请联系管理员，或使用已授权的系统账号。",
    invalid_state: "登录请求已过期或无法验证，请重新发起扫码登录。",
    cancelled: "你已取消钉钉授权，可以重新扫码登录。",
    access_denied: "当前钉钉账号未获本系统访问权限，请联系管理员确认所属企业和账号状态。",
    exchange_failed: "扫码登录未完成，请重试；如仍失败，请联系管理员检查钉钉应用配置。",
  };
  return typeof value === "string" ? messages[value] || "扫码登录未完成，请重新发起登录。" : "";
}
