import { queryOptions } from "@tanstack/vue-query";
import { useApi } from "@/composables/useApi";

export interface CompanyMembership {
  id: string;
  name: string;
  slug: string;
  role: string;
}

export interface TeamMembership {
  id: string;
  name: string;
  company_id: string;
  role: string;
}

export interface CurrentUser {
  id: string;
  first_name: string;
  last_name: string;
  is_platform_admin: boolean;
  permissions: string[];
  current_company_id: string | null;
  current_team_id: string | null;
  companies: CompanyMembership[];
  teams: TeamMembership[];
  available_scopes: string[];
}

// /me carries permissions + company context. 30s staleness means a
// company switch or deactivation surfaces within half a minute without
// hammering the endpoint on every navigation.
export const meQueryOptions = () =>
  queryOptions({
    queryKey: ["me"],
    queryFn: () => useApi().get<CurrentUser>("/me/"),
    staleTime: 30_000,
  });
