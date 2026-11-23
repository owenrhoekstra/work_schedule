import { keepPreviousData, QueryClient } from "@tanstack/vue-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("@/composables/useApi", () => ({
  useApi: () => ({ get: mockGet }),
}));

import { prefetchAdjacentWeeks, weekQueryOptions } from "@/queries/week";
import type { WeekRef } from "@/types/week";

const sampleWeekRef: WeekRef = {
  start: "2026-11-16",
  title: "Week of November 16th",
  prev: "2026-11-09",
  next: "2026-11-23",
  is_current: true,
  can_go_back: true,
};

let queryClient: QueryClient;

beforeEach(() => {
  mockGet.mockReset();
  mockGet.mockResolvedValue({});
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
});

describe("weekQueryOptions", () => {
  it("sets placeholderData to keepPreviousData", () => {
    const opts = weekQueryOptions(ref("comp-abc"), ref(null), ref("company"), ref(true));
    expect(opts.placeholderData).toBe(keepPreviousData);
  });

  it("includes companyId, week, and scope in queryKey via computed", () => {
    const opts = weekQueryOptions(ref("comp-abc"), ref("2026-11-16"), ref("team"), ref(true));
    const key = (opts.queryKey as unknown as { value: unknown }).value;
    expect(key).toEqual(["week", "comp-abc", "2026-11-16", "team"]);
  });

  it("preserves null week in queryKey for the current-week sentinel", () => {
    const opts = weekQueryOptions(ref("comp-abc"), ref(null), ref("company"), ref(true));
    const key = (opts.queryKey as unknown as { value: unknown }).value;
    expect(key).toEqual(["week", "comp-abc", null, "company"]);
  });

  it("preserves null companyId in queryKey before /me/ resolves", () => {
    const opts = weekQueryOptions(ref(null), ref(null), ref("company"), ref(false));
    const key = (opts.queryKey as unknown as { value: unknown }).value;
    expect(key).toEqual(["week", null, null, "company"]);
  });
});

describe("prefetchAdjacentWeeks", () => {
  it("fetches prev and next into cache with the right URLs", async () => {
    await prefetchAdjacentWeeks(queryClient, "comp-abc", sampleWeekRef, "company");
    expect(mockGet).toHaveBeenCalledWith("/schedule/week/?week=2026-11-09&scope=company");
    expect(mockGet).toHaveBeenCalledWith("/schedule/week/?week=2026-11-23&scope=company");
  });

  it("populates cache under keys containing companyId", async () => {
    mockGet.mockImplementation(() => Promise.resolve({ marker: "cached" }));
    await prefetchAdjacentWeeks(queryClient, "comp-abc", sampleWeekRef, "company");
    expect(queryClient.getQueryData(["week", "comp-abc", "2026-11-09", "company"])).toEqual({
      marker: "cached",
    });
    expect(queryClient.getQueryData(["week", "comp-abc", "2026-11-23", "company"])).toEqual({
      marker: "cached",
    });
  });

  it("respects staleTime on repeat calls", async () => {
    await prefetchAdjacentWeeks(queryClient, "comp-abc", sampleWeekRef, "company");
    const callsAfterFirst = mockGet.mock.calls.length;
    await prefetchAdjacentWeeks(queryClient, "comp-abc", sampleWeekRef, "company");
    // Second call should NOT refetch — data is fresh within 30s.
    expect(mockGet.mock.calls.length).toBe(callsAfterFirst);
  });
});
