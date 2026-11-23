<script setup lang="ts">
import { PhSpinner, PhWarningCircle } from "@phosphor-icons/vue";
import { computed, ref, watch } from "vue";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { format12 } from "@/lib/format";
import { useOverrideMutation } from "@/queries/overrides";
import type { Cell } from "@/types/week";

// Anchored editor for a single cell. One instance per cell in
// ScheduleDesktop — reka-ui lazily portals PopoverContent, so 120
// closed popovers cost nothing beyond the trigger binding.
//
// Optimistic updates live in useOverrideMutation. This component's
// only job is form state, gating the mutation on viewer_can, and
// surfacing the server's 422 detail inline (popover stays open so the
// user can fix and retry). Notification failures surface as a toast
// from the mutation, not here — the cell change succeeded.

const props = defineProps<{
  employeeId: string;
  employeeName: string;
  cell: Cell;
  dayLabel: string; // "Monday"
  dateLabel: string; // "Nov 16"
  canAddShift: boolean;
  canDeleteShift: boolean;
  editable: boolean; // canAddShift || canDeleteShift
}>();

const open = ref(false);
const startTime = ref("");
const endTime = ref("");
const notify = ref(false);

const mutation = useOverrideMutation();

// Re-seed form fields every time the popover opens on a new cell.
// The watcher fires on open, not on prop change, so an open popover
// stays open through an underlying cell update (e.g. background
// refetch) without clobbering mid-edit values.
watch(open, (isOpen) => {
  if (!isOpen) return;
  startTime.value = format12(props.cell.start ?? props.cell.default_start ?? "");
  endTime.value = format12(props.cell.end ?? props.cell.default_end ?? "");
  notify.value = false;
  mutation.reset();
});

// Cancel discards any typed values and closes. Same as click-outside
// for users who prefer an explicit affordance.
function cancel() {
  open.value = false;
}

function save() {
  mutation.mutate(
    {
      employeeId: props.employeeId,
      date: props.cell.date,
      action: "save",
      start: startTime.value.trim(),
      end: endTime.value.trim(),
      notify: notify.value,
    },
    { onSuccess: () => (open.value = false) },
  );
}

function markOff() {
  mutation.mutate(
    {
      employeeId: props.employeeId,
      date: props.cell.date,
      action: "off",
      notify: notify.value,
    },
    { onSuccess: () => (open.value = false) },
  );
}

function reset() {
  mutation.mutate(
    {
      employeeId: props.employeeId,
      date: props.cell.date,
      action: "reset",
    },
    { onSuccess: () => (open.value = false) },
  );
}

const submitting = computed(() => mutation.isPending.value);
const serverError = computed(() => (mutation.error.value ? mutation.error.value.message : ""));

// Save is enabled only when both fields are present and add_shift is
// held. Client-side validity (end>start) is NOT checked here — the
// server owns that rule; the popover stays open with the server's
// error inline. Matches AGENTS.md: red errors come from the server.
const canSave = computed(
  () =>
    props.canAddShift &&
    !submitting.value &&
    startTime.value.trim() !== "" &&
    endTime.value.trim() !== "",
);
const canMarkOff = computed(() => props.canDeleteShift && !submitting.value);
const canReset = computed(
  () => props.canDeleteShift && props.cell.has_override && !submitting.value,
);
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child :disabled="!editable">
      <button
        v-if="editable"
        type="button"
        class="block w-full cursor-pointer px-2 py-2 text-center text-sm whitespace-nowrap transition-colors hover:bg-muted/50"
      >
        <slot />
      </button>
      <span v-else class="block px-2 py-2 text-center text-sm whitespace-nowrap">
        <slot />
      </span>
    </PopoverTrigger>

    <PopoverContent
      class="w-80 border-2 border-foreground/25 shadow-xl"
      align="center"
      :side-offset="4"
    >
      <div class="space-y-3">
        <div>
          <p class="text-sm font-medium">{{ employeeName }} — {{ dayLabel }}</p>
          <p class="text-xs text-muted-foreground">{{ dateLabel }}</p>
        </div>

        <div
          v-if="serverError"
          class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive"
        >
          <PhWarningCircle class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>{{ serverError }}</span>
        </div>

        <form class="space-y-3" novalidate @submit.prevent="save">
          <div class="grid grid-cols-2 gap-3">
            <div class="space-y-1.5">
              <Label for="ov-start">Start</Label>
              <Input
                id="ov-start"
                v-model="startTime"
                type="text"
                placeholder="HH:MM"
                autocomplete="off"
              />
            </div>
            <div class="space-y-1.5">
              <Label for="ov-end">End</Label>
              <Input
                id="ov-end"
                v-model="endTime"
                type="text"
                placeholder="HH:MM"
                autocomplete="off"
              />
            </div>
          </div>

          <label class="flex items-center gap-2 text-sm">
            <Checkbox v-model="notify" />
            <span>Notify employee</span>
          </label>

          <div class="flex items-center justify-between gap-2 border-t pt-3">
            <div class="flex gap-1">
              <Button
                v-if="canMarkOff"
                type="button"
                variant="ghost"
                size="sm"
                :disabled="submitting"
                @click="markOff"
              >
                <PhSpinner v-if="submitting" class="size-3.5 animate-spin" aria-hidden="true" />
                Mark off
              </Button>
              <Button
                v-if="canReset"
                type="button"
                variant="ghost"
                size="sm"
                :disabled="submitting"
                @click="reset"
              >
                Reset
              </Button>
            </div>
            <div class="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                :disabled="submitting"
                @click="cancel"
              >
                Cancel
              </Button>
              <Button v-if="canAddShift" type="submit" size="sm" :disabled="!canSave">
                <PhSpinner v-if="submitting" class="size-3.5 animate-spin" aria-hidden="true" />
                Save
              </Button>
            </div>
          </div>
        </form>
      </div>
    </PopoverContent>
  </Popover>
</template>
