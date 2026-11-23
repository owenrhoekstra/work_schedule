import { keepPreviousData, type QueryClient, queryOptions } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { useApi } from "@/composables/useApi";
import type { WeekRef, WeekResponse } from "@/types/week";

// queryKey now includes companyId so a company switch produces a fresh
// cache entry (not a refetch-in-place of stale cross-company data).
// keepPreviousData + isPlaceholderData then does the right thing on all
// three transition types:
//   week nav   → new key, prefetched → instant; cold → skeleton
//   scope nav  → new key → skeleton (or prefetched if we ever add it)
//   company nav → new key → skeleton (cross-company never reuses cache)
export const weekQueryOptions = (
  companyId: Ref<string | null>,
  week: Ref<string | null>,
  scope: Ref<string>,
  enabled: Ref<boolean>,
) =>
  queryOptions({
    queryKey: computed(() => ["week", companyId.value, week.value, scope.value]),
    queryFn: () => {
      const params = new URLSearchParams();
      if (week.value) params.set("week", week.value);
      params.set("scope", scope.value);
      return useApi().get<WeekResponse>(`/schedule/week/?${params}`);
    },
    staleTime: 30_000,
    enabled,
    placeholderData: keepPreviousData,
  });

export async function prefetchAdjacentWeeks(
  queryClient: QueryClient,
  companyId: string | null,
  currentWeek: WeekRef,
  scope: string,
): Promise<void> {
  const fetchWeek = (weekIso: string) => {
    const params = new URLSearchParams({ week: weekIso, scope });
    return useApi().get<WeekResponse>(`/schedule/week/?${params}`);
  };
  await Promise.all([
    queryClient.prefetchQuery({
      queryKey: ["week", companyId, currentWeek.prev, scope],
      queryFn: () => fetchWeek(currentWeek.prev),
      staleTime: 30_000,
    }),
    queryClient.prefetchQuery({
      queryKey: ["week", companyId, currentWeek.next, scope],
      queryFn: () => fetchWeek(currentWeek.next),
      staleTime: 30_000,
    }),
  ]);
}
