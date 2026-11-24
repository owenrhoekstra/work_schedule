<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query";
import { computed } from "vue";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { meQueryOptions } from "@/queries/me";
import { useSelectCompanyMutation, useSelectTeamMutation } from "@/queries/selects";

// Company + team pickers that sit beside the scope selector.
//
// Visibility rules (from product spec):
// - Company picker: shown whenever the user has >1 viable company,
//   regardless of scope. Changing it switches tenant.
// - Team picker: shown only when scope ∈ {team, me} AND the user
//   has >1 viewable team in the current company. Not shown on
//   company scope — company scope IS the all-teams view.
//
// Forced selection: the team picker has no "All teams" option. If the
// user is on scope=team with no team in session, they must pick one
// (the backend supports team=None = union, but the UI intent is
// single-team on team scope). Brief union may render before first
// interaction; the picker engages on click.
//
// Caveat on scope=me: the backend ignores request.team for me-scope
// (returns the viewer's single row regardless). The team picker is
// present for context / future use; changing it updates session.team_id
// but doesn't change the visible roster.

const props = defineProps<{ scope: string }>();

const { data: me } = useQuery(meQueryOptions());
const selectCompany = useSelectCompanyMutation();
const selectTeam = useSelectTeamMutation();

const showCompany = computed(() => (me.value?.companies.length ?? 0) > 1);
const showTeam = computed(() => {
  if (props.scope === "company") return false;
  return (me.value?.teams.length ?? 0) > 1;
});

const companyValue = computed(() => me.value?.current_company_id ?? "");
const teamValue = computed(() => me.value?.current_team_id ?? "");

function onCompanyChange(v: unknown) {
  // shadcn-vue's Select emits AcceptableValue; we only act on strings.
  // Non-strings (null / number / etc.) are ignored — the "Select
  // company" placeholder should never fire this since a company is
  // always selected when the picker renders.
  if (typeof v !== "string" || !v) return;
  if (v === companyValue.value) return;
  selectCompany.mutate(v);
}

function onTeamChange(v: unknown) {
  // Team picker supports clearing (null) in theory, though the forced-
  // select UX doesn't offer an "All teams" option today. Keep the
  // branch so the plumbing matches the backend's `team_id: null`
  // clear semantics.
  const next = typeof v === "string" && v ? v : null;
  if (next === teamValue.value) return;
  selectTeam.mutate(next);
}
</script>

<template>
  <div v-if="showCompany || showTeam" class="flex items-center gap-2">
    <Select v-if="showCompany" :model-value="companyValue" @update:model-value="onCompanyChange">
      <SelectTrigger class="w-48" aria-label="Select company">
        <SelectValue placeholder="Select company" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem v-for="c in me?.companies ?? []" :key="c.id" :value="c.id">
          {{ c.name }}
        </SelectItem>
      </SelectContent>
    </Select>

    <Select v-if="showTeam" :model-value="teamValue" @update:model-value="onTeamChange">
      <SelectTrigger class="w-40" aria-label="Select team">
        <SelectValue placeholder="Select team" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem v-for="t in me?.teams ?? []" :key="t.id" :value="t.id">
          {{ t.name }}
        </SelectItem>
      </SelectContent>
    </Select>
  </div>
</template>
