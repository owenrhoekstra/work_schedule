export interface LoginConfig {
  oidcEnabled?: boolean;
}

/**
 * Decide whether to show the SSO card.
 *
 * Prod (isDev=false): the Django login shell injects
 * window.__LOGIN_CONFIG__.oidcEnabled from settings.OIDC_ENABLED.
 * That's authoritative — VITE_OIDC_ENABLED is ignored even if set.
 *
 * Dev (isDev=true): Vite serves the shell without a Django render, so
 * __LOGIN_CONFIG__ is absent. VITE_OIDC_ENABLED from .env is the only
 * signal. Any value other than the literal string "true" is treated
 * as disabled.
 */
export function resolveOidcEnabled(
  config: LoginConfig | undefined,
  opts: { isDev: boolean; devFlag: string | undefined },
): boolean {
  if (opts.isDev) {
    return opts.devFlag === "true";
  }
  return config?.oidcEnabled === true;
}