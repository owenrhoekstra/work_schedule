<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { meQueryOptions } from "@/queries/me";
import { weekQueryOptions } from "@/queries/week";

// SMOKE-TEST version. Proves the /me/ → /week/ chain works end-to-end
// with plain markup. Replaced by the styled version (ScopeSelector,
// WeekHeader, ScheduleDesktop) once those components exist.

const route = useRoute();
const router = useRouter();

const { data: me } = useQuery(meQueryOptions());

const weekParam = computed<string | null>(() => {
  const w = route.query.week;
  return typeof w === "string" && w ? w : null;
});

// Default scope: highest available, matching the login-redirect choice.
// available_scopes from /me/ arrives pre-ordered by the server.
const scope = computed<string>(() => {
  const s = route.query.scope;
  if (typeof s === "string" && s) return s;
  const available = me.value?.available_scopes ?? [];
  if (available.includes("company")) return "company";
  if (available.includes("team")) return "team";
  return "me";
});

const enabled = computed(() => me.value !== undefined);

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
  <div v-if="isPending" class="p-6 text-gray-500">Loading schedule…</div>
  <div v-else-if="isError" class="p-6 text-brand-coral">
    Could not load schedule: {{ error?.message ?? "Unknown error" }}
  </div>
  <div v-else-if="week" class="space-y-4 p-6">
    <h1 class="font-display text-2xl font-bold text-brand-indigo">
      {{ week.week.is_current ? "This Week's Schedule" : week.week.title }}
    </h1>

    <div class="flex gap-2">
      <button
        v-if="week.week.can_go_back"
        type="button"
        class="px-3 py-1 border rounded-lg"
        @click="setWeek(week.week.prev)"
      >
        ← Previous
      </button>
      <button type="button" class="px-3 py-1 border rounded-lg" @click="setWeek(week.week.next)">
        Next →
      </button>
      <button
        v-if="!week.week.is_current"
        type="button"
        class="px-3 py-1 border rounded-lg text-brand-coral"
        @click="goCurrent"
      >
        Back to current week
      </button>
    </div>

    <div class="flex gap-2">
      <button
        v-for="s in week.available_scopes"
        :key="s"
        type="button"
        :class="[
          'px-3 py-1 border rounded-lg',
          s === scope ? 'bg-brand-coral text-white' : 'bg-white',
        ]"
        @click="setScope(s)"
      >
        {{ s }}
      </button>
    </div>

    <p class="text-sm text-gray-600">
      Scope: <strong>{{ week.scope }}</strong> · Employees:
      <strong>{{ week.employees.length }}</strong> · Viewer can:
      <code>{{ JSON.stringify(week.viewer_can) }}</code>
    </p>

    <ul class="list-disc pl-6 space-y-1">
      <li v-for="e in week.employees" :key="e.id">
        {{ e.display_name }} — {{ e.cells.length }} cells, {{ e.total_minutes }} min
      </li>
    </ul>

    <details class="text-xs">
      <summary class="cursor-pointer text-gray-500">Raw days</summary>
      <pre class="mt-2 bg-gray-50 p-3 rounded overflow-x-auto">{{
        JSON.stringify(week.days, null, 2)
      }}</pre>
    </details>
  </div>
</template>
