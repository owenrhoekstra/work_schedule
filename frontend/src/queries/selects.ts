import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { useApi } from "@/composables/useApi";

interface SelectResponse {
  ok: boolean;
  error: string;
}

// Company switch invalidates /me/ (current_company_id, teams[],
// available_scopes all change) and marks every cached /week/ entry
// stale WITHOUT refetching (refetchType: "none"). A normal
// invalidation would refetch active week queries and race the session
// switch; marking stale only is safe because nothing fires until the
// new company's week keys mount after /me/ updates. In-flight week
// requests are still cancelled up front for the same reason.
// The backend clears session team_id on company switch, so the next
// /me/ returns current_team_id: null and teams: [] for the new
// company until the user picks one. Week keys omit current_team_id,
// so without the stale mark, switching back to a company within
// staleTime would reuse a roster fetched under a previously selected
// team instead of showing all viewable teams.
export function useSelectCompanyMutation() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (companyId: string) =>
      api.post<SelectResponse>("/companies/select/", { company_id: companyId }),
    // A week request in flight when the session flips could store
    // company B's roster under company A's key. Stop them first.
    onMutate: () => queryClient.cancelQueries({ queryKey: ["week"] }),
    onSuccess: async (data) => {
      if (!data.ok) return;
      // Stale only, no refetch: cached weeks were fetched under a team
      // selection the backend has now cleared, so they must not be
      // treated as fresh when their key next mounts.
      queryClient.invalidateQueries({
        queryKey: ["week"],
        refetchType: "none",
      });
      // Week keys embed current_company_id, so the new company's
      // weeks only fetch once /me/ has updated.
      await queryClient.invalidateQueries({ queryKey: ["me"] });
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
