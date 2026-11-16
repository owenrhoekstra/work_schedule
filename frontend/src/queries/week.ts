import { queryOptions } from "@tanstack/vue-query";
import type { Ref } from "vue";
import { useApi } from "@/composables/useApi";
import type { WeekResponse } from "@/types/week";

// /week/ carries one week of one scope. Cache per (week, scope) — back/
// forward between weeks within a scope is instant from cache; switching
// scope is a fresh fetch. 30s staleTime matches /me/ (company switches
// and deactivations should surface within half a minute without
// hammering the endpoint).
//
// `enabled` gates the fetch until /me/ has resolved — a week request
// before available_scopes is known would either 403 (wrong default
// scope) or fire with "me" for a manager unnecessarily.
export const weekQueryOptions = (
  week: Ref<string | null>,
  scope: Ref<string>,
  enabled: Ref<boolean>,
) =>
  queryOptions({
    queryKey: ["week", week, scope],
    queryFn: () => {
      const params = new URLSearchParams();
      if (week.value) params.set("week", week.value);
      params.set("scope", scope.value);
      return useApi().get<WeekResponse>(`/schedule/week/?${params}`);
    },
    staleTime: 30_000,
    enabled,
  });
