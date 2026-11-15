// composables/Login/useSsoLogin.ts
import { ref } from "vue";

/**
 * Kick off the SSO redirect. Django's OIDC view drives the dance:
 * /oidc/authenticate/?next=/accounts/company-picker/ → Zitadel →
 * /oidc/callback/ → Django session established → picker → home.
 *
 * The shell template in prod injects window.__LOGIN_CONFIG__.oidcUrl;
 * in dev we fall back to the hardcoded path (Vite proxies /oidc to
 * Django at :8000).
 */
export function useSsoLogin() {
  const status = ref<"redirecting" | "error">("redirecting");
  const error = ref("");

  function start() {
    status.value = "redirecting";
    error.value = "";
    try {
      const config = (window as unknown as { __LOGIN_CONFIG__?: { oidcUrl?: string } })
        .__LOGIN_CONFIG__;
      const url = config?.oidcUrl ?? "/oidc/authenticate/?next=/accounts/company-picker/";
      window.location.assign(url);
    } catch {
      status.value = "error";
      error.value = "Couldn't start single sign-on. Please try again.";
    }
  }

  return { status, error, start };
}
