import tailwindcss from "@tailwindcss/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    base: env.VITE_BASE_PATH || "/",
    plugins: [vue(), tailwindcss()],
    preview: { host: "127.0.0.1", proxy: { "/api": { target: env.LOCAL_API_TARGET || "http://127.0.0.1:8100", changeOrigin: false } } },
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": {
          target: env.LOCAL_API_TARGET || "http://127.0.0.1:8100",
          changeOrigin: false,
        },
      },
    },
  };
});
