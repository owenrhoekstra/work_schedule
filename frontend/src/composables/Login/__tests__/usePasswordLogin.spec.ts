import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent } from "vue";

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

import { ApiError } from "@/composables/useApi";
import { usePasswordLogin } from "../usePasswordLogin";

function mountHost() {
  // Definite-assignment assertion (`!`) tells TS the variable will be
  // assigned by the time we read it. `setup()` runs synchronously
  // during `mount()`, so the composable is guaranteed to exist before
  // we return.
  let composable!: ReturnType<typeof usePasswordLogin>;

  const Host = defineComponent({
    setup() {
      composable = usePasswordLogin();
      return composable;
    },
    template: "<div />",
  });

  mount(Host);
  return composable;
}

describe("usePasswordLogin", () => {
  beforeEach(() => {
    mockPost.mockReset();
  });

  it("sends trimmed username and passes the current next param", async () => {
    (window as unknown as { location: { search: string } }).location.search =
      "?next=/schedule/home/";
    mockPost.mockResolvedValue({
      ok: true,
      redirect_url: "/schedule/home/",
      error: "",
    });

    const c = mountHost();
    c.username.value = "  alice  ";
    c.password.value = "secret";

    await c.submit();

    expect(mockPost).toHaveBeenCalledWith(
      "/accounts/login/",
      {
        username: "alice",
        password: "secret",
        next: "/schedule/home/",
      },
      { skipAuthHandling: true },
    );
  });

  it("sets formError from response.error when ok:false", async () => {
    mockPost.mockResolvedValue({
      ok: false,
      redirect_url: "",
      error: "Invalid username or password.",
    });

    const c = mountHost();
    c.username.value = "alice";
    c.password.value = "wrong";

    await c.submit();

    expect(c.formError.value).toBe("Invalid username or password.");
    expect(c.submitting.value).toBe(false);
  });

  it("extracts e.data.error from a 422 ApiError", async () => {
    mockPost.mockRejectedValue(
      new ApiError(422, "fallback", "http", {
        error: "Username and password required.",
      }),
    );

    const c = mountHost();
    await c.submit();

    expect(c.formError.value).toBe("Username and password required.");
  });

  it("falls back to a generic message for unrecognized errors", async () => {
    mockPost.mockRejectedValue(new Error("boom"));

    const c = mountHost();
    await c.submit();

    // messageFor's generic fallback
    expect(c.formError.value).toMatch(/something went wrong/i);
  });
});
