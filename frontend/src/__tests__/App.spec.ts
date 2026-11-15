import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import App from "@/App.vue";

/**
 * Mount App with a minimal test router. The production router installs
 * a before-guard that calls useUserStore().load(); we skip that by not
 * replicating it — the guard returns early for public routes anyway,
 * and this test only covers the public login route.
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
