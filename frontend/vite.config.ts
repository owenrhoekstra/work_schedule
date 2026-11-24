import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import vueDevTools from "vite-plugin-vue-devtools";

export default defineConfig(({ command }) => ({
  envDir: "..",
  base: command === "build" ? "/static/vue/" : "/",
  plugins: [vue(), vueDevTools(), tailwindcss()],
  server: {
    allowedHosts: ["owens-macbook-pro.tailac3f56.ts.net"],
    proxy: {
      // All API + auth + OIDC traffic goes to Django
      "/api": "http://localhost:8000",
      "/accounts": "http://localhost:8000",
      "/oidc": "http://localhost:8000",
      "/admin": "http://localhost:8000",
      "/healthz": "http://localhost:8000",
      // Django pages that are still full-page (settings, print, employee
      // details) — proxy them so links from the Vue toolbar don't bounce
      // to :8000
      "/schedule/print": "http://localhost:8000",
      "/schedule/settings": "http://localhost:8000",
      "/schedule/employees": "http://localhost:8000",
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    // Django serves the shell (login_spa.html) and django-vite reads
    // manifest.json to emit the hashed entry + CSS tags. Vite's default
    // content hashing handles cache-busting; Django must NOT rehash
    // vue/ files (see ViteAwareStorage).
    outDir: "../static/vue",
    emptyOutDir: true,
    manifest: "manifest.json",
    rollupOptions: {
      input: "src/main.ts",
    },
  },
}));
