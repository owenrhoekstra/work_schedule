import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock useApi so no real HTTP happens. post is a spy we control per
// test.
const mockPost = vi.fn();

vi.mock("@/composables/useApi", () => ({
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      message: string,
      public kind: string = "http",
      public data?: unknown,
    ) {
      super(message);
      this.name = "ApiError";
    }
  },
  useApi: () => ({
    post: mockPost,
    get: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
    request: vi.fn(),
  }),
  configureApi: vi.fn(),
}));

import PasswordLoginScreen from "../PasswordLoginScreen.vue";

describe("PasswordLoginScreen", () => {
  beforeEach(() => {
    mockPost.mockReset();
  });

  it("renders username and password fields", () => {
    const wrapper = mount(PasswordLoginScreen);

    expect(wrapper.find('input[name="username"]').exists()).toBe(true);
    expect(wrapper.find('input[name="password"]').exists()).toBe(true);
  });

  it("submits typed credentials to the API and navigates on success", async () => {
    mockPost.mockResolvedValue({
      ok: true,
      redirect_url: "/schedule/home/",
      error: "",
    });

    const wrapper = mount(PasswordLoginScreen);
    await wrapper.find('input[name="username"]').setValue("alice");
    await wrapper.find('input[name="password"]').setValue("secret");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(mockPost).toHaveBeenCalledWith(
      "/accounts/login/",
      expect.objectContaining({
        username: "alice",
        password: "secret",
      }),
      expect.objectContaining({ skipAuthHandling: true }),
    );
    expect(window.location.href).toBe("/schedule/home/");
  });

  it("shows a server error when the API returns ok:false", async () => {
    mockPost.mockResolvedValue({
      ok: false,
      redirect_url: "",
      error: "Invalid username or password.",
    });

    const wrapper = mount(PasswordLoginScreen);
    await wrapper.find('input[name="username"]').setValue("alice");
    await wrapper.find('input[name="password"]').setValue("wrong");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toMatch(/invalid username or password/i);
  });

  it("surfaces the server's 422 error message when fields are empty", async () => {
    const { ApiError } = await import("@/composables/useApi");
    mockPost.mockRejectedValue(
      new ApiError(422, "Username and password required.", "http", {
        ok: false,
        error: "Username and password required.",
      }),
    );

    const wrapper = mount(PasswordLoginScreen);
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toMatch(/username and password required/i);
  });
});