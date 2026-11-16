import { describe, expect, it } from "vitest";

import { resolveOidcEnabled } from "../resolve-oidc-enabled";

describe("resolveOidcEnabled", () => {
  describe("dev path (isDev=true)", () => {
    it("returns true when VITE_OIDC_ENABLED is 'true'", () => {
      expect(resolveOidcEnabled(undefined, { isDev: true, devFlag: "true" })).toBe(true);
    });

    it("returns false when VITE_OIDC_ENABLED is 'false'", () => {
      expect(resolveOidcEnabled(undefined, { isDev: true, devFlag: "false" })).toBe(false);
    });

    it("returns false when VITE_OIDC_ENABLED is undefined", () => {
      expect(resolveOidcEnabled(undefined, { isDev: true, devFlag: undefined })).toBe(false);
    });

    it("ignores window.__LOGIN_CONFIG__ even when config.oidcEnabled is true", () => {
      // Conflicting case: dev flag says off, injected config says on.
      // Dev flag wins — Vite dev has no Django render, so the injected
      // value wouldn't be present in reality anyway.
      expect(resolveOidcEnabled({ oidcEnabled: true }, { isDev: true, devFlag: "false" })).toBe(
        false,
      );
    });
  });

  describe("prod path (isDev=false)", () => {
    it("returns true when config.oidcEnabled is true", () => {
      expect(resolveOidcEnabled({ oidcEnabled: true }, { isDev: false, devFlag: undefined })).toBe(
        true,
      );
    });

    it("returns false when config.oidcEnabled is false", () => {
      expect(resolveOidcEnabled({ oidcEnabled: false }, { isDev: false, devFlag: undefined })).toBe(
        false,
      );
    });

    it("returns false when config is undefined", () => {
      expect(resolveOidcEnabled(undefined, { isDev: false, devFlag: undefined })).toBe(false);
    });

    it("returns false when config.oidcEnabled is undefined", () => {
      expect(resolveOidcEnabled({}, { isDev: false, devFlag: undefined })).toBe(false);
    });

    it("ignores VITE_OIDC_ENABLED when config says false (config wins)", () => {
      // The conflicting case Greptile called out: prod has a stale or
      // developer-set VITE_OIDC_ENABLED=true in the build environment,
      // but the Django-injected config says false. Config is
      // authoritative; the SSO card stays hidden.
      expect(resolveOidcEnabled({ oidcEnabled: false }, { isDev: false, devFlag: "true" })).toBe(
        false,
      );
    });
  });
});
