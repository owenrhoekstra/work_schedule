import { keepPreviousData, QueryClient } from "@tanstack/vue-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("@/composables/useApi", () => ({
  useApi: () => ({ get: mockGet }),
}));

import { prefetchAdjacentWeeks, weekQueryOptions } from "@/queries/Schedule/week.ts";
import type { WeekRef } from "@/types/Schedule/week.ts";

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
    const opts = weekQueryOptions(ref("comp-abc"), ref(null), ref(null), ref("company"), ref(true));
    expect(opts.placeholderData).toBe(keepPreviousData);
  });

  it("includes companyId, teamId, week, and scope in queryKey", () => {
    const opts = weekQueryOptions(
      ref("comp-abc"),
      ref("team-xyz"),
      ref("2026-11-16"),
      ref("team"),
      ref(true),
    );
    const key = (opts.queryKey as unknown as { value: unknown }).value;
    expect(key).toEqual(["week", "comp-abc", "team-xyz", "2026-11-16", "team"]);
  });

  it("preserves null week in queryKey for the current-week sentinel", () => {
    const opts = weekQueryOptions(ref("comp-abc"), ref(null), ref(null), ref("company"), ref(true));
    const key = (opts.queryKey as unknown as { value: unknown }).value;
    expect(key).toEqual(["week", "comp-abc", null, null, "company"]);
  });

  it("preserves null companyId in queryKey before /me/ resolves", () => {
    const opts = weekQueryOptions(ref(null), ref(null), ref(null), ref("company"), ref(false));
    const key = (opts.queryKey as unknown as { value: unknown }).value;
    expect(key).toEqual(["week", null, null, null, "company"]);
  });

  it("changing teamId produces a different queryKey", () => {
    const before = weekQueryOptions(ref("c1"), ref("t1"), ref("2026-11-16"), ref("team"), ref(true))
      .queryKey as unknown as { value: unknown[] };
    const after = weekQueryOptions(ref("c1"), ref("t2"), ref("2026-11-16"), ref("team"), ref(true))
      .queryKey as unknown as { value: unknown[] };
    expect(before.value).not.toEqual(after.value);
  });
});

describe("prefetchAdjacentWeeks", () => {
  it("fetches prev and next into cache with the right URLs", async () => {
    await prefetchAdjacentWeeks(queryClient, "comp-abc", null, sampleWeekRef, "company");
    expect(mockGet).toHaveBeenCalledWith("/schedule/week/?week=2026-11-09&scope=company");
    expect(mockGet).toHaveBeenCalledWith("/schedule/week/?week=2026-11-23&scope=company");
  });

  it("populates cache under keys containing companyId + teamId", async () => {
    mockGet.mockImplementation(() => Promise.resolve({ marker: "cached" }));
    await prefetchAdjacentWeeks(queryClient, "comp-abc", "team-xyz", sampleWeekRef, "team");
    expect(
      queryClient.getQueryData(["week", "comp-abc", "team-xyz", "2026-11-09", "team"]),
    ).toEqual({ marker: "cached" });
    expect(
      queryClient.getQueryData(["week", "comp-abc", "team-xyz", "2026-11-23", "team"]),
    ).toEqual({ marker: "cached" });
  });

  it("respects staleTime on repeat calls", async () => {
    await prefetchAdjacentWeeks(queryClient, "comp-abc", null, sampleWeekRef, "company");
    const callsAfterFirst = mockGet.mock.calls.length;
    await prefetchAdjacentWeeks(queryClient, "comp-abc", null, sampleWeekRef, "company");
    expect(mockGet.mock.calls.length).toBe(callsAfterFirst);
  });
});
