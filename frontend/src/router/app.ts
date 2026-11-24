import { createRouter, createWebHistory } from "vue-router";
import { ApiError } from "@/composables/useApi";
import { queryClient } from "@/lib/queryClient";
import { type CurrentUser, meQueryOptions } from "@/queries/me";
import Schedule from "@/views/Schedule.vue";

// The app router owns /schedule/*. Login (a separate router at
// /accounts/login/) is a different shell with no guard; it never
// reaches this module. main.ts dispatches on pathname.
export function createAppRouter() {
  const router = createRouter({
    history: createWebHistory("/schedule/"),
    routes: [
      {
        path: "/",
        name: "schedule",
        component: Schedule,
        meta: { title: "Schedule" },
      },
      {
        path: "/:pathMatch(.*)*",
        redirect: { name: "schedule" },
      },
    ],
  });

  // One guard for the whole app router. Fetch /me/ on the first
  // navigation of a session (and again on every subsequent nav when
  // staleTime expires). Handles three failure modes:
  //
  //   401 → configureApi.onUnauthorized already hard-navigated to
  //         /accounts/login/. Block this nav so we don't race it.
  //   transient (network / timeout / 5xx) with cached user → proceed
  //         with the cache; a blip shouldn't log an active session out.
  //   transient with no cache → refuse nav; login is the only safe
  //         destination (main.ts will already have dispatched to the
  //         login shell if we're coming from a fresh page load, so
  //         this mostly catches mid-session failures).
  //
  // Scope-gating beyond this (which scopes the user can view) lives
  // server-side. The SPA trusts available_scopes from /me/ and lets
  // the /week/ endpoint 403 on any mismatch — a single source of truth.
  router.beforeEach(async () => {
    try {
      await queryClient.ensureQueryData(meQueryOptions());
    } catch (error) {
      if (error instanceof ApiError && error.isUnauthorized) {
        return false;
      }
      const cached = queryClient.getQueryData<CurrentUser>(meQueryOptions().queryKey);
      if (!cached) return false;
    }

    const me = queryClient.getQueryData<CurrentUser>(meQueryOptions().queryKey);
    if (!me) return false;

    // Zero viable companies: Django's waiting page owns this state.
    // Full-page nav (not router.push) because /accounts/waiting/ is a
    // Django template, not a Vue route.
    if (!me.current_company_id && me.companies.length === 0) {
      window.location.assign("/accounts/waiting/");
      return false;
    }

    return true;
  });

  return router;
}
