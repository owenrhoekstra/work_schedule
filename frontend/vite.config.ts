import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import vueDevTools from "vite-plugin-vue-devtools";

export default defineConfig({
  envDir: "..",
  plugins: [vue(), vueDevTools(), tailwindcss()],
  server: {
    allowedHosts: ["localhost: 5173", "owens-macbook-pro.tailac3f56.ts.net"],
    proxy: {
      // Dev-only. Routes Django endpoints through Vite so the login
      // form's POST and the SSO redirect both reach Django at :8000.
      // Full post-login flow (redirect to /schedule/home/) is tested
      // against Django directly at localhost:8000 after building —
      // Vite dev server doesn't proxy app pages, only APIs.
      "/api": "http://localhost:8000",
      "/oidc": "http://localhost:8000",
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "../static/vue",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: "index-[hash].js",
        chunkFileNames: "[name]-[hash].js",
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith(".css")) return "index-[hash][extname]";
          return "[name]-[hash][extname]";
        },
      },
    },
  },
  base: "/static/vue/",
});
