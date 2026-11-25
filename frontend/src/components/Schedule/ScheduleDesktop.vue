<script setup lang="ts">
import { computed, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { format12, formatDateMedium, formatDuration } from "@/lib/format";
import type { Cell, CellKind, DayHeader, WeekEmployee, WeekResponse } from "@/types/Schedule/week.ts";
import { Button } from "../ui/button";
import DayStatusMenu from "./DayStatusMenu.vue";
import EmployeeDrawer from "./EmployeeDrawer.vue";
import OverridePopover from "./OverridePopover.vue";

const props = defineProps<{ data: WeekResponse }>();

const drawerOpen = ref(false);
const selectedId = ref<string | null>(null);
// Keep the last selection after close so the sheet doesn't blank out mid-animation.
const selected = computed(
  () => props.data.employees.find((e) => e.id === selectedId.value) ?? null,
);

function openDrawer(id: string) {
  selectedId.value = id;
  drawerOpen.value = true;
}

const kindClasses: Record<CellKind, string> = {
  default: "text-foreground",
  // Empty — override times get per-piece coloring in cellPieceClass
  // so only the changed piece(s) read as coral. A cell whose override
  // equals the default (rare no-op) reads as a normal default cell.
  override: "",
  off_override: "text-primary",
  day_override: "text-foreground font-medium",
  not_employed: "text-subtle-foreground",
  none: "text-subtle-foreground",
};

// Per-piece color for cells that display a start/end range (kind =
// "default" or "override"). For override cells, a piece is coral when
// it differs from the pattern default for that day. Falls back to the
// Commit 4 styling otherwise: start inherits the outer cell class,
// end is de-emphasized to muted-foreground.
//
// Null baseline (no default shift that day) counts as "changed" —
// the override is new for this day, both pieces highlight.
function cellPieceClass(cell: Cell, piece: "start" | "end"): string {
  if (cell.kind === "override") {
    const current = piece === "start" ? cell.start : cell.end;
    const baseline = piece === "start" ? cell.default_start : cell.default_end;
    const changed = baseline === null || current !== baseline;
    if (changed) return "text-primary font-medium";
  }
  return piece === "end" ? "text-muted-foreground" : "";
}

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

// Subtext under the employee name: "Kitchen — Head Chef" when both
// are present, just "Kitchen" when the role is unset, empty when the
// employee has no team assignment. Employees without a team fall back
// to no subtext — honest reflection of the model; settings will make
// assignment easy.
function teamRoleLine(emp: WeekEmployee): string {
  if (!emp.team_name) return "";
  if (emp.team_role_name) return `${emp.team_name} — ${emp.team_role_name}`;
  return emp.team_name;
}

// Cell is editable when the viewer holds either shift perm AND the
// day isn't blocked by a company-wide override or non-employment.
// Per-action gates (Save vs Mark off) live inside the popover —
// derived from the same viewer_can flags.
function isCellEditable(cell: Cell): boolean {
  if (!cell.is_employed) return false;
  if (cell.kind === "day_override") return false;
  return props.data.viewer_can.can_add_shift || props.data.viewer_can.can_delete_shift;
}

function employeeDefaultsUrl(id: string): string {
  return `/schedule/employees/${id}/defaults/`;
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
            <DayStatusMenu
              :date="day.date"
              :label="`${day.long_label}, ${day.date_label}`"
              :status="day.override_status"
              :editable="data.viewer_can.change_day_override"
            >
              <span class="block">{{ day.long_label }}</span>
              <span class="block text-xs font-normal opacity-80">{{ day.date_label }}</span>
            </DayStatusMenu>
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
            <Button
              variant="ghost"
              class="h-auto max-w-full min-w-0 justify-start p-0 font-medium"
              :title="emp.display_name"
              @click="openDrawer(emp.id)"
            >
              <span class="truncate">{{ emp.display_name }}</span>
            </Button>
            <div
              v-if="teamRoleLine(emp)"
              class="truncate text-sm text-muted-foreground"
              :title="teamRoleLine(emp)"
            >
              {{ teamRoleLine(emp) }}
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
            <OverridePopover
              :employee-id="emp.id"
              :employee-name="emp.display_name"
              :cell="cell"
              :day-label="data.days[i]?.long_label ?? ''"
              :date-label="data.days[i]?.date_label ?? ''"
              :can-add-shift="data.viewer_can.can_add_shift"
              :can-delete-shift="data.viewer_can.can_delete_shift"
              :editable="isCellEditable(cell)"
            >
              <span :class="kindClasses[cell.kind]">
                <template v-if="cell.start && cell.end">
                  <span :class="cellPieceClass(cell, 'start')">{{ format12(cell.start) }}</span>
                  <span class="text-subtle-foreground"> – </span>
                  <span :class="cellPieceClass(cell, 'end')">{{ format12(cell.end) }}</span>
                </template>
                <template v-else>
                  {{ cellText(cell, data.days[i]) }}
                </template>
              </span>
            </OverridePopover>
          </td>
          <td
            class="p-2 text-center text-sm font-medium tabular-nums whitespace-nowrap text-foreground"
          >
            {{ formatDuration(emp.total_minutes) }}
          </td>
        </tr>
      </tbody>
    </table>
    <EmployeeDrawer v-model:open="drawerOpen" :employee="selected" />
  </div>
</template>
