import { createRouter, createWebHistory } from "vue-router";
import { useUserStore } from "@/stores/user";

declare module "vue-router" {
  interface RouteMeta {
    title?: string;
    public?: boolean;
  }
}

// The shell is served at /accounts/login/ in prod (and /accounts/
// login-vue/ as a dev alias). The router base must exactly match the
// URL Django rendered, or history-based navigation and router.resolve
// append relative paths (producing URLs like
// /accounts/login-vue/accounts/login/).
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

  const userStore = useUserStore();
  await userStore.load();

  if (userStore.user) return true;
  if (userStore.error?.isUnauthorized && router.hasRoute("login")) {
    return { name: "login" };
  }
  return true;
});

router.afterEach((to) => {
  const app = import.meta.env.VITE_APP_NAME || "Docket";
  document.title = to.meta.title ? `${app} - ${to.meta.title}` : app;
});

export default router;
