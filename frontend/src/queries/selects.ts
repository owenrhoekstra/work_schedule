import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { useApi } from "@/composables/useApi";

interface SelectResponse {
  ok: boolean;
  error: string;
}

// Company switch invalidates BOTH /me/ (current_company_id, teams[],
// available_scopes all change) and /week/ (roster entirely different).
// The backend clears session team_id on company switch, so the next
// /me/ returns current_team_id: null and teams: [] for the new
// company until the user picks one.
export function useSelectCompanyMutation() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (companyId: string) =>
      api.post<SelectResponse>("/companies/select/", {
        company_id: companyId,
      }),
    onSuccess: (data) => {
      if (!data.ok) return;
      queryClient.invalidateQueries({ queryKey: ["me"] });
      queryClient.invalidateQueries({ queryKey: ["week"] });
    },
  });
}

// Team switch: current_company_id unchanged, available_scopes same,
// but the team-scoped roster changes. Invalidate both anyway — /me/
// updates current_team_id so the picker reflects the new selection;
// /week/ refetches with the new team narrowing.
export function useSelectTeamMutation() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (teamId: string | null) =>
      api.post<SelectResponse>("/teams/select/", {
        team_id: teamId,
      }),
    onSuccess: (data) => {
      if (!data.ok) return;
      queryClient.invalidateQueries({ queryKey: ["me"] });
      queryClient.invalidateQueries({ queryKey: ["week"] });
    },
  });
}
