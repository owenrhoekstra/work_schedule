import { createRouter, createWebHistory } from "vue-router";
import Login from "@/views/Login.vue";

// The login shell is served at /accounts/login/ in prod (and / in dev
// via Vite SPA fallback). The base must exactly match the URL Django
// rendered, or history-based navigation and router.resolve append
// relative paths (e.g. /accounts/login/accounts/login/).
//
// PROD_LEGACY_BASE: /accounts/login-vue/ was an earlier dev alias; no
// longer served by any template, but harmless to keep in the list in
// case a bookmark to that path is still in the wild. Safe to remove
// once we confirm no live references.
const LOGIN_BASES = ["/accounts/login/", "/accounts/login-vue/"];

function baseForLogin(): string {
  if (import.meta.env.DEV) return "/";
  const pathname = window.location.pathname;
  return LOGIN_BASES.find((b) => pathname.startsWith(b)) ?? "/";
}

export function createLoginRouter() {
  return createRouter({
    history: createWebHistory(baseForLogin()),
    routes: [
      {
        path: "/",
        name: "login",
        component: Login,
        meta: { title: "Log in", public: true },
      },
      {
        path: "/:pathMatch(.*)*",
        redirect: { name: "login" },
      },
    ],
  });
}
