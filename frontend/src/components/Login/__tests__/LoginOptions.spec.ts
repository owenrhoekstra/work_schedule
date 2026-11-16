import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import LoginOptions from "../LoginOptions.vue";

describe("LoginOptions", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("hides the SSO card when VITE_OIDC_ENABLED is unset", () => {
    vi.stubEnv("VITE_OIDC_ENABLED", "");
    const wrapper = mount(LoginOptions);

    expect(wrapper.text()).not.toMatch(/single sign-on/i);
    expect(wrapper.text()).toMatch(/password/i);
  });

  it("hides the SSO card when VITE_OIDC_ENABLED is 'false'", () => {
    vi.stubEnv("VITE_OIDC_ENABLED", "false");
    const wrapper = mount(LoginOptions);

    expect(wrapper.text()).not.toMatch(/single sign-on/i);
  });

  it("shows the SSO card when VITE_OIDC_ENABLED is 'true'", () => {
    vi.stubEnv("VITE_OIDC_ENABLED", "true");
    const wrapper = mount(LoginOptions);

    expect(wrapper.text()).toMatch(/single sign-on/i);
    expect(wrapper.text()).toMatch(/password/i);
  });

  it("renders the create-account link", () => {
    const wrapper = mount(LoginOptions);

    const link = wrapper.find('a[href="/accounts/signup/"]');
    expect(link.exists()).toBe(true);
    expect(link.text()).toMatch(/create an account/i);
  });
});