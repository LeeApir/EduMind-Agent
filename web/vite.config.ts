import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    proxy: {
      "/api": {
        target: process.env.EDUMIND_API_PROXY_TARGET ?? "http://127.0.0.1:8000",
        // The API verifies Origin against its received Host for CSRF protection.
        // Keep the browser Host when forwarding through the development proxy.
        changeOrigin: false,
      },
    },
  },
});
