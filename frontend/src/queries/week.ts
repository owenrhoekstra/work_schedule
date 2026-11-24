import { keepPreviousData, type QueryClient, queryOptions } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { useApi } from "@/composables/useApi";
import type { WeekRef, WeekResponse } from "@/types/week";

// queryKey includes companyId AND teamId so any tenant/team switch
// produces a fresh cache entry (not a refetch-in-place of stale data
// that could belong to a different roster). keepPreviousData +
// isPlaceholderData then does the right thing on all transition types:
//   week nav   → new key, prefetched → instant; cold → skeleton
//   scope nav  → new key → skeleton
//   company nav → new key → skeleton
//   team nav   → new key → skeleton (or prefetched on return within gcTime)
export const weekQueryOptions = (
  companyId: Ref<string | null>,
  teamId: Ref<string | null>,
  week: Ref<string | null>,
  scope: Ref<string>,
  enabled: Ref<boolean>,
) =>
  queryOptions({
    queryKey: computed(() => ["week", companyId.value, teamId.value, week.value, scope.value]),
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
  teamId: string | null,
  currentWeek: WeekRef,
  scope: string,
): Promise<void> {
  const fetchWeek = (weekIso: string) => {
    const params = new URLSearchParams({ week: weekIso, scope });
    return useApi().get<WeekResponse>(`/schedule/week/?${params}`);
  };
  await Promise.all([
    queryClient.prefetchQuery({
      queryKey: ["week", companyId, teamId, currentWeek.prev, scope],
      queryFn: () => fetchWeek(currentWeek.prev),
      staleTime: 30_000,
    }),
    queryClient.prefetchQuery({
      queryKey: ["week", companyId, teamId, currentWeek.next, scope],
      queryFn: () => fetchWeek(currentWeek.next),
      staleTime: 30_000,
    }),
  ]);
}
