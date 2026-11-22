<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import ScheduleDesktop from "@/components/Schedule/ScheduleDesktop.vue";
import ScheduleToolbar from "@/components/Schedule/ScheduleToolbar.vue";
import { meQueryOptions } from "@/queries/me";
import { weekQueryOptions } from "@/queries/week";

const route = useRoute();
const router = useRouter();

const { data: me } = useQuery(meQueryOptions());

const weekParam = computed<string | null>(() => {
  const w = route.query.week;
  return typeof w === "string" && w ? w : null;
});

// Scope priority: company > team > me, matching the login-redirect
// preference. If the URL scope isn't in the user's available_scopes
// (mangled URL, stale bookmark), fall back to the preference rather
// than firing a request the server will 403. URL normalization is
// deferred — the component renders the correct scope, and clicking
// a tab rewrites the URL cleanly.
const scope = computed<string>(() => {
  const s = route.query.scope;
  const available = me.value?.available_scopes ?? [];
  if (typeof s === "string" && s && available.includes(s)) return s;
  if (available.includes("company")) return "company";
  if (available.includes("team")) return "team";
  return "me";
});

// Two guards against unnecessary /week/ calls:
// 1. me.value !== undefined: /me/ has resolved (success or cache).
// 2. available_scopes.length > 0: there's something to view. A
//    company member with no Employee row and no allow_member_view_all
//    has zero scopes — firing /week/ would 403 for no reason.
const hasScopes = computed(() => (me.value?.available_scopes.length ?? 0) > 0);
const enabled = computed(() => me.value !== undefined && hasScopes.value);

const {
  data: week,
  isPending,
  isError,
  error,
} = useQuery(weekQueryOptions(weekParam, scope, enabled));

function setWeek(newWeek: string) {
  router.push({ query: { ...route.query, week: newWeek } });
}
function setScope(newScope: string) {
  router.push({ query: { ...route.query, scope: newScope } });
}
function goCurrent() {
  const q = { ...route.query };
  delete q.week;
  router.push({ query: q });
}
</script>

<template>
  <div v-if="me && !hasScopes" class="py-12 text-center">
    <p class="text-muted-foreground">You don't have a schedule here yet.</p>
    <p class="mt-2 text-sm text-muted-foreground">Ask a manager to add you to the schedule.</p>
  </div>

  <div v-else-if="isPending" class="py-8 text-muted-foreground">Loading schedule…</div>

  <div v-else-if="isError" class="py-8 text-destructive">
    Could not load schedule: {{ error?.message ?? "Unknown error" }}
  </div>

  <div v-else-if="week" class="mx-auto space-y-5 pt-16">
    <ScheduleToolbar
      :week="week.week"
      :scopes="week.available_scopes"
      :current-scope="scope"
      :viewer-can="week.viewer_can"
      @navigate="setWeek"
      @go-current="goCurrent"
      @select-scope="setScope"
    />
    <ScheduleDesktop :data="week" />
  </div>
</template>
