import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import vueDevTools from "vite-plugin-vue-devtools";

export default defineConfig({
  envDir: "..",
  plugins: [vue(), vueDevTools(), tailwindcss()],
  server: {
    allowedHosts: ["owens-macbook-pro.tailac3f56.ts.net"],
    proxy: {
      // Dev-only. Routes Django endpoints through Vite so the login
      // form's POST and the SSO redirect both reach Django at :8000.
      "/api": "http://localhost:8000",
      "/oidc": "http://localhost:8000",
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  base: "/static/vue/",
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
});
