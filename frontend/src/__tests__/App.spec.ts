import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import App from "@/App.vue";

/**
 * App.vue skips the router guard on public routes, so this test (which
 * visits the login route) never triggers `ensureQueryData(meQueryOptions())`
 * in beforeEach — meaning no VueQueryPlugin is needed for this mount.
 */
function makeTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: "/",
        name: "login",
        component: () => import("@/views/Login.vue"),
        meta: { title: "Log in", public: true },
      },
    ],
  });
}

describe("App.vue", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    // Login components read window.__LOGIN_CONFIG__ (shell-injected in
    // prod). Stub it so the reads don't warn.
    (window as unknown as Record<string, unknown>).__LOGIN_CONFIG__ = {
      oidcEnabled: false,
      oidcUrl: "/oidc/authenticate/",
      loginUrl: "/api/v1/accounts/login/",
      csrfToken: "",
    };
  });

  it("renders the login shell on the public login route", async () => {
    const router = makeTestRouter();
    router.push("/");
    await router.isReady();

    const wrapper = mount(App, {
      global: { plugins: [router] },
    });
    await flushPromises();

    // Public route → MenuBar chrome is hidden.
    expect(wrapper.find("header").exists()).toBe(false);
    // App renders its main wrapper.
    expect(wrapper.find("#main-content").exists()).toBe(true);
  });
});
