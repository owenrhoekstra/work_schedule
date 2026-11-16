import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { ApiError, useApi } from "@/composables/useApi";

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
}

export const useUserStore = defineStore("user", () => {
  const api = useApi();

  const user = ref<CurrentUser | null>(null);
  const loading = ref(false);
  const ready = ref(false);
  const error = ref<ApiError | null>(null);
  let inflight: Promise<void> | null = null;

  const fullName = computed(() =>
    user.value ? `${user.value.first_name} ${user.value.last_name}`.trim() : "",
  );

  // Guards call `load(true)` for per-navigation revalidation (also acts
  // as a session probe). `load()` without `force` is a no-op once
  // populated.
  function load(force = false): Promise<void> {
    if (user.value && !force) return Promise.resolve();
    inflight ??= (async () => {
      loading.value = true;
      try {
        user.value = await api.get<CurrentUser>("/me/");
        error.value = null;
      } catch (e) {
        const apiErr = e instanceof ApiError ? e : null;
        error.value = apiErr;
        // Hardening against blips:
        // - 401 → the session is gone. Drop the cached user so the
        //   router guard redirects to login.
        // - Any other failure (network, timeout, 5xx) → transient.
        //   Keep the previously-loaded user so a blip doesn't log an
        //   active session out. The error is still surfaced via
        //   `error.value` for a toast/retry affordance.
        if (apiErr?.isUnauthorized) {
          user.value = null;
        }
      } finally {
        loading.value = false;
        ready.value = true;
        inflight = null;
      }
    })();
    return inflight;
  }

  function clear() {
    user.value = null;
    error.value = null;
    ready.value = false;
  }

  return { user, loading, ready, error, fullName, load, clear };
});
