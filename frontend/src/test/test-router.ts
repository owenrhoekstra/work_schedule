import { createMemoryHistory, createRouter, type Router } from "vue-router";

/**
 * Minimal router for component tests. One login route with the same
 * meta.public flag the production router uses, so App.vue's ready-gate
 * and public-route detection behave correctly.
 */
export function makeTestRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: "/",
        name: "login",
        component: { template: "<div>login-stub</div>" },
        meta: { title: "Log in", public: true },
      },
    ],
  });
}