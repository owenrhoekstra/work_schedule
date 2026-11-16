import { beforeEach, vi } from "vitest";

// jsdom doesn't implement matchMedia. Any component that reads
// prefers-color-scheme or viewport queries would throw.
if (typeof window !== "undefined" && !window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

// Reset window.__LOGIN_CONFIG__ before each test. Individual tests that
// need a specific value override it after mount or via vi.stubEnv.
beforeEach(() => {
  (window as unknown as Record<string, unknown>).__LOGIN_CONFIG__ = {
    oidcEnabled: false,
    oidcUrl: "/oidc/authenticate/?next=/accounts/company-picker/",
    loginUrl: "/api/v1/accounts/login/",
    csrfToken: "test-csrf",
  };

  // Replace window.location with a plain object so tests can assert
  // on .href without jsdom throwing "Not implemented: navigation".
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: { search: "", href: "http://localhost/" },
  });
});