import { VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia } from "pinia";
import { createApp } from "vue";

import App from "./App.vue";
import { queryClient } from "./lib/queryClient";
import { createAppRouter } from "./router/app";
import { createLoginRouter } from "./router/login";
import "./assets/theme.css";
import { configureApi } from "@/composables/useApi";

configureApi({
  baseUrl: "/api/v1",
  // Full reload discards stale SPA state (and the query cache) when
  // the session is dead. router.push would leave a logged-out shell
  // alive. 401 is the one global logout trigger.
  onUnauthorized: () => window.location.assign("/accounts/login/"),
});

// Prime the CSRF cookie before any POST. Prod: shell template sets it
// via {{ csrf_token }}. Dev: Vite serves the page so no Django render
// has happened — hit the dedicated endpoint to seed it.
void (async () => {
  const has = document.cookie.split(";").some((c) => c.trim().startsWith("csrftoken="));
  if (has) return;
  try {
    await fetch("/api/v1/csrf/", { credentials: "include" });
  } catch {
    /* login POST will 403 if this fails; nothing else to do */
  }
})();

// Login and app are two routers, two base URLs, two shells' worth of
// intent — but one bundle and one App.vue. Dispatch on pathname so a
// /schedule/ page load constructs the guarded app router and a
// /accounts/login/ load constructs the unguarded login router. The
// two trees never coexist; this is a one-time decision per page load.
//
// DEV: Vite serves both paths from the same SPA fallback (base = "/"),
// so /schedule* is the only distinguishing prefix.
// PROD: Django serves login_spa.html at /accounts/login/ and
// schedule_spa.html at /schedule/. Anything else under those prefixes
// (e.g. /accounts/login/foo) matches the login shell's base list.
function isLoginPath(pathname: string): boolean {
  if (import.meta.env.DEV) {
    return !pathname.startsWith("/schedule");
  }
  return pathname.startsWith("/accounts/login/") || pathname.startsWith("/accounts/login-vue/");
}

const router = isLoginPath(window.location.pathname) ? createLoginRouter() : createAppRouter();

// One title hook for both routers — the two trees share the app name.
router.afterEach((to) => {
  const app = import.meta.env.VITE_APP_NAME || "Docket";
  document.title = to.meta.title ? `${app} - ${to.meta.title}` : app;
});

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.use(VueQueryPlugin, { queryClient });
app.mount("#app");
