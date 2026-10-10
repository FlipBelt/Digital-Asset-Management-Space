// Independent of the application bundle, so a failed bundle can still recover.
(() => {
  function showRecovery(title, message, role) {
    const panel = document.querySelector("#app .boot-fallback");
    if (!panel) return;
    if (role === "status" && panel.getAttribute("role") === "alert") return;
    panel.setAttribute("role", role);
    panel.querySelector("[data-boot-title]").textContent = title;
    panel.querySelector("[data-boot-message]").textContent = message;
    panel.querySelector("[data-boot-actions]").hidden = false;
    panel.querySelector(".boot-progress").hidden = true;
  }
  window.setTimeout(() => showRecovery("加载时间较长", "可以刷新重试，或返回登录页。若仍无法打开，请联系管理员。", "status"), 15000);
  window.addEventListener("error", (event) => {
    if (event.target && event.target.tagName === "SCRIPT") {
      showRecovery("页面未能加载", "应用文件加载失败，请检查网络后刷新重试。", "alert");
    }
  }, true);
  window.addEventListener("asset-center-bootstrap-error", () => {
    showRecovery("页面加载遇到问题", "请刷新重试。若仍无法打开，请联系管理员。", "alert");
  });
  document.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest("[data-boot-retry]")) window.location.reload();
  });
})();
