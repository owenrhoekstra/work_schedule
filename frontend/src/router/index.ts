import { createRouter, createWebHistory } from "vue-router";
import { useUserStore } from "@/stores/user";

declare module "vue-router" {
  interface RouteMeta {
    title?: string;
    public?: boolean;
  }
}

// Prod: shell served at /accounts/login-vue/ by Django. Dev: Vite
// serves at /. The router base must match the URL the shell is
// mounted at, or history navigation breaks.
const base = import.meta.env.DEV ? "/" : "/accounts/login-vue/";

const router = createRouter({
  history: createWebHistory(base),
  routes: [
    {
      path: "/",
      name: "login",
      component: () => import("@/views/Login.vue"),
      meta: { title: "Log in", public: true },
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
  const app = import.meta.env.VITE_APP_NAME;
  document.title = to.meta.title ? `${app} - ${to.meta.title}` : app;
});

export default router;
