import { createRouter, createWebHistory } from "vue-router";
import { useUserStore } from "@/stores/user";

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

  const userStore = useUserStore();
  await userStore.load(true);

  if (userStore.user) {
    // Waiting only when the server gave us nothing to work with.
    // Platform admins may have current_company_id set via middleware
    // even with an empty companies[] (their memberships don't cover
    // every company they can reach). Trust current_company_id.
    if (!userStore.user.current_company_id && userStore.user.companies.length === 0) {
      window.location.assign("/accounts/waiting/");
      return false;
    }
    return true;
  }

  if (router.hasRoute("login")) return { name: "login" };
  return true;
});

router.afterEach((to) => {
  const app = import.meta.env.VITE_APP_NAME || "Docket";
  document.title = to.meta.title ? `${app} - ${to.meta.title}` : app;
});

export default router;
