import { createRouter, createWebHistory } from "vue-router";
import { ApiError } from "@/composables/useApi";
import { queryClient } from "@/lib/queryClient";
import { type CurrentUser, meQueryOptions } from "@/queries/me";

declare module "vue-router" {
  interface RouteMeta {
    title?: string;
    public?: boolean;
  }
}

const getBase = (): string => {
  if (import.meta.env.DEV) return "/";
  const pathname = window.location.pathname;
  const candidates = ["/accounts/login-vue/", "/accounts/login/"];
  return candidates.find((b) => pathname.startsWith(b)) ?? "/";
};

const router = createRouter({
  history: createWebHistory(getBase()),
  routes: [
    {
      path: "/",
      name: "login",
      component: () => import("@/views/Login.vue"),
      meta: { title: "Log in", public: true },
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: { name: "login" },
    },
  ],
});

router.beforeEach(async (to) => {
  if (to.meta.public) return true;

  try {
    await queryClient.ensureQueryData(meQueryOptions());
  } catch (error) {
    // 401 → configureApi.onUnauthorized already hard-navigated; block
    // this navigation so we don't race it.
    if (error instanceof ApiError && error.isUnauthorized) return false;

    // Transient (network/timeout/5xx): keep the cached user so a blip
    // does not log an active session out. No cache → login.
    const cached = queryClient.getQueryData<CurrentUser>(meQueryOptions().queryKey);
    if (!cached) return { name: "login" };
  }

  const me = queryClient.getQueryData<CurrentUser>(meQueryOptions().queryKey);
  if (!me) return { name: "login" };

  // Waiting only when the server says there is nothing to work with.
  // Platform admins can have current_company_id set with an empty
  // companies[] (their memberships don't cover every reachable company).
  if (!me.current_company_id && me.companies.length === 0) {
    window.location.assign("/accounts/waiting/");
    return false;
  }
  return true;
});

router.afterEach((to) => {
  const app = import.meta.env.VITE_APP_NAME || "Docket";
  document.title = to.meta.title ? `${app} - ${to.meta.title}` : app;
});

export default router;
