<script setup lang="ts">
import { Badge } from "@/components/ui/badge";
import { format12, formatDateMedium, formatDuration } from "@/lib/format";
import type { Cell, CellKind, DayHeader, WeekResponse } from "@/types/week";

defineProps<{ data: WeekResponse }>();

// Semantic tokens, not hardcoded brand colors. Mirrors the state map
// in your ScheduleCell.vue — override is coral (primary), off is
// subtle, default is foreground. off_override stays primary because
// it's a manager action, not a normal off.
const kindClasses: Record<CellKind, string> = {
  default: "text-foreground",
  override: "text-primary",
  off_override: "text-primary",
  day_override: "text-foreground font-medium",
  not_employed: "text-subtle-foreground",
  none: "text-subtle-foreground",
};

function cellText(cell: Cell, day: DayHeader | undefined): string {
  if (cell.kind === "day_override") return dayStatusLabel(day?.override_status);
  if (cell.kind === "not_employed") return "—";
  if (cell.start && cell.end) {
    return `${format12(cell.start)} – ${format12(cell.end)}`;
  }
  return "OFF";
}

function dayStatusLabel(status: string | null | undefined): string {
  if (status === "closed") return "Closed";
  if (status === "holiday") return "Holiday";
  return status ?? "";
}
</script>

<template>
  <div
    v-if="data.employees.length === 0"
    class="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground shadow-sm"
  >
    No employees scheduled for this scope and week.
  </div>

  <div
    v-else
    id="schedule-table"
    class="overflow-x-auto rounded-xl border border-border bg-card shadow-sm"
  >
    <!-- table-fixed at md (768px): proportional columns, fits the
         container, no scroll. Below md: natural width + scroll. -->
    <table class="w-full min-w-max border-collapse md:min-w-0 md:table-fixed">
      <colgroup>
        <col class="w-[18%]" />
        <col span="6" class="w-[12%]" />
        <col class="w-[10%]" />
      </colgroup>
      <thead>
        <tr class="bg-brand-indigo text-white dark:bg-secondary dark:text-foreground">
          <th class="p-2 text-left font-display text-sm font-medium whitespace-nowrap">Employee</th>
          <th
            v-for="day in data.days"
            :key="day.date"
            class="p-2 text-center font-display text-sm font-medium whitespace-nowrap"
          >
            <div>{{ day.long_label }}</div>
            <div class="text-xs font-normal opacity-80">{{ day.date_label }}</div>
            <Badge
              v-if="day.override_status"
              class="mt-1 bg-highlight text-highlight-foreground hover:bg-highlight"
            >
              {{ dayStatusLabel(day.override_status) }}
            </Badge>
          </th>
          <th class="p-2 text-center font-display whitespace-nowrap">
            <div class="text-sm font-medium">Total</div>
            <div class="text-xs font-normal opacity-80">Hours</div>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="emp in data.employees"
          :key="emp.id"
          :id="`schedule-row-${emp.id}`"
          class="border-t border-border transition-colors hover:bg-muted/50"
        >
          <td class="overflow-hidden p-2">
            <div class="truncate font-medium text-foreground" :title="emp.display_name">
              {{ emp.display_name }}
            </div>
            <div
              v-if="emp.role_name"
              class="truncate text-sm text-muted-foreground"
              :title="emp.role_name"
            >
              {{ emp.role_name }}
            </div>
            <Badge v-if="emp.cycle" variant="secondary" class="mt-1">
              Week {{ emp.cycle.label }}
            </Badge>
            <Badge v-if="emp.last_day" variant="destructive" class="mt-1">
              Last day: {{ formatDateMedium(emp.last_day) }}
            </Badge>
          </td>
          <td
            v-for="(cell, i) in emp.cells"
            :key="cell.date"
            class="overflow-hidden p-0 text-center text-sm whitespace-nowrap"
          >
            <span :class="['block px-2 py-2', kindClasses[cell.kind]]">
              <template v-if="cell.start && cell.end">
                <span>{{ format12(cell.start) }}</span>
                <span class="text-subtle-foreground"> – </span>
                <span class="text-muted-foreground">{{ format12(cell.end) }}</span>
              </template>
              <template v-else>
                {{ cellText(cell, data.days[i]) }}
              </template>
            </span>
          </td>
          <td
            class="p-2 text-center text-sm font-medium tabular-nums whitespace-nowrap text-foreground"
          >
            {{ formatDuration(emp.total_minutes) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
