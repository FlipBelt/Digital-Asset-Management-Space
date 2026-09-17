import { createApp } from "vue";

import App from "./App.vue";
import router from "./router";
import "./styles.css";

const root = document.getElementById("app");

function showRuntimeError() {
  if (!root) return;
  root.innerHTML = "<div class=\"boot-fallback\" role=\"alert\"><div class=\"boot-fallback-mark\">集</div><strong>页面加载遇到问题</strong><span>请刷新页面，或从钉钉工作台重新打开当前环境。</span></div>";
}

if (!root) {
  throw new Error("application root is missing");
}

const app = createApp(App);
app.config.errorHandler = (error) => {
  console.error("account center runtime error", error);
  showRuntimeError();
};

try {
  app.use(router).mount(root);
} catch (error) {
  console.error("account center bootstrap error", error);
  showRuntimeError();
}
