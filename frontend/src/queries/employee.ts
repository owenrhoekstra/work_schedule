import { queryOptions, useMutation, useQueryClient } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";
import { toast } from "vue-sonner";
import { useApi } from "@/composables/useApi";
import type { EmployeeDetail } from "@/types/employee";

export const employeeQueryOptions = (id: Ref<string | null>) =>
  queryOptions({
    queryKey: computed(() => ["employee", id.value]),
    queryFn: () => useApi().get<EmployeeDetail>(`/schedule/employees/${id.value}/`),
    enabled: computed(() => id.value !== null),
    staleTime: 30_000,
  });

export function useEmployeeFlagMutation(employeeId: Ref<string | null>) {
  const api = useApi();
  const queryClient = useQueryClient();
  const key = computed(() => ["employee", employeeId.value]);

  return useMutation({
    mutationFn: (vars: { key: string; value: boolean }) =>
      api.post(`/schedule/employees/${employeeId.value}/flags/`, vars),
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: key.value });
      const previous = queryClient.getQueryData<EmployeeDetail>(key.value);
      queryClient.setQueryData<EmployeeDetail>(key.value, (old) =>
        old
          ? {
              ...old,
              flags: old.flags.map((f) => (f.key === vars.key ? { ...f, value: vars.value } : f)),
            }
          : old,
      );
      return { previous };
    },
    onError: (err, _vars, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(key.value, ctx.previous);
      toast.error(err.message);
    },
    // Flags can affect the schedule (e.g. visibility), so refresh both.
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: key.value });
      queryClient.invalidateQueries({ queryKey: ["week"] });
    },
  });
}

export function useSendWelcomeMutation(employeeId: Ref<string | null>) {
  const api = useApi();
  return useMutation({
    mutationFn: () => api.post(`/schedule/employees/${employeeId.value}/welcome/`, {}),
    onSuccess: () => toast.success("Welcome email sent"),
    onError: (err) => toast.error(err.message),
  });
}
