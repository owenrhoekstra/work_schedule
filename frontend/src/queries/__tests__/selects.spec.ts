import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, nextTick } from "vue";

const { mockPost } = vi.hoisted(() => ({ mockPost: vi.fn() }));

vi.mock("@/composables/useApi", () => ({
  useApi: () => ({ post: mockPost }),
}));

import { useSelectCompanyMutation, useSelectTeamMutation } from "@/queries/selects";

const TestHarness = defineComponent({
  setup(_, { expose }) {
    expose({
      company: useSelectCompanyMutation(),
      team: useSelectTeamMutation(),
    });
    return () => null;
  },
});

let queryClient: QueryClient;

beforeEach(() => {
  mockPost.mockReset();
  queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
});

async function mountHarness() {
  const wrapper = mount(TestHarness, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  });
  await nextTick();
  return wrapper.vm as unknown as {
    company: ReturnType<typeof useSelectCompanyMutation>;
    team: ReturnType<typeof useSelectTeamMutation>;
  };
}

describe("useSelectCompanyMutation", () => {
  it("posts to /companies/select/", async () => {
    mockPost.mockResolvedValueOnce({ ok: true, error: "" });
    const h = await mountHarness();
    await h.company.mutateAsync("comp-uuid");
    expect(mockPost).toHaveBeenCalledWith("/companies/select/", {
      company_id: "comp-uuid",
    });
  });

  it("invalidates me and week queries on ok=true", async () => {
    mockPost.mockResolvedValueOnce({ ok: true, error: "" });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const h = await mountHarness();
    await h.company.mutateAsync("comp-uuid");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["me"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["week"] });
  });

  it("does not invalidate on ok=false", async () => {
    mockPost.mockResolvedValueOnce({ ok: false, error: "No access" });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const h = await mountHarness();
    await h.company.mutateAsync("comp-uuid");
    expect(invalidate).not.toHaveBeenCalled();
  });
});

describe("useSelectTeamMutation", () => {
  it("posts to /teams/select/", async () => {
    mockPost.mockResolvedValueOnce({ ok: true, error: "" });
    const h = await mountHarness();
    await h.team.mutateAsync("team-uuid");
    expect(mockPost).toHaveBeenCalledWith("/teams/select/", {
      team_id: "team-uuid",
    });
  });

  it("posts null when clearing", async () => {
    mockPost.mockResolvedValueOnce({ ok: true, error: "" });
    const h = await mountHarness();
    await h.team.mutateAsync(null);
    expect(mockPost).toHaveBeenCalledWith("/teams/select/", {
      team_id: null,
    });
  });

  it("invalidates me and week on ok=true", async () => {
    mockPost.mockResolvedValueOnce({ ok: true, error: "" });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const h = await mountHarness();
    await h.team.mutateAsync("team-uuid");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["me"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["week"] });
  });
});
