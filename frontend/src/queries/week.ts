import { queryOptions } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { useApi } from "@/composables/useApi";
import type { WeekResponse } from "@/types/week";

// queryKey is wrapped in computed() so TanStack sees plain values at
// the type boundary — passing bare Refs in the array trips its
// overload resolution under strict inference (the key becomes
// (string | Ref<...>)[] but useQuery expects (string | null)[]).
// computed unwraps to the values on each access, preserving
// reactivity for cache-key changes.
export const weekQueryOptions = (
  week: Ref<string | null>,
  scope: Ref<string>,
  enabled: Ref<boolean>,
) =>
  queryOptions({
    queryKey: computed(() => ["week", week.value, scope.value]),
    queryFn: () => {
      const params = new URLSearchParams();
      if (week.value) params.set("week", week.value);
      params.set("scope", scope.value);
      return useApi().get<WeekResponse>(`/schedule/week/?${params}`);
    },
    staleTime: 30_000,
    enabled,
  });
