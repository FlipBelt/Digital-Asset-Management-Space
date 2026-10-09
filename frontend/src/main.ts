import { createApp } from "vue";

import App from "./App.vue";
import router from "./router";
import "./styles.css";

const root = document.getElementById("app");
const bootFallback = root?.querySelector(".boot-fallback")?.cloneNode(true);

function showRuntimeError() {
  if (!root || !bootFallback) return;
  root.replaceChildren(bootFallback.cloneNode(true));
  window.dispatchEvent(new Event("asset-center-bootstrap-error"));
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

import "./styles/tokens.css";
import "./styles/login.css";
