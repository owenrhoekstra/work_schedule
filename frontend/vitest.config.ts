import { fileURLToPath } from "node:url";
import { configDefaults, defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config.ts";

// vite.config.ts exports a UserConfigFnObject (function of ConfigEnv).
// mergeConfig wants a plain UserConfig object; resolve the function
// once for the test environment before merging.
const baseConfig =
  typeof viteConfig === "function" ? viteConfig({ command: "serve", mode: "test" }) : viteConfig;

export default mergeConfig(
  baseConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      exclude: [...configDefaults.exclude, "e2e/**"],
      root: fileURLToPath(new URL("./", import.meta.url)),
      setupFiles: ["./src/test/setup.ts"],
    },
  }),
);
