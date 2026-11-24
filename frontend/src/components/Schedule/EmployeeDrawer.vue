<script setup lang="ts">
import { PhArrowSquareOut, PhEnvelopeSimple, PhSpinner } from "@phosphor-icons/vue";
import { useQuery } from "@tanstack/vue-query";
import { computed, ref, watch } from "vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { format12, formatDateMedium } from "@/lib/format";
import {
  employeeQueryOptions,
  useEmployeeFlagMutation,
  useSendWelcomeMutation,
} from "@/queries/employee";
import { meQueryOptions } from "@/queries/me";
import type { WeekEmployee } from "@/types/week";

const showDialog = ref(false);

const props = defineProps<{ employee: WeekEmployee | null }>();
const open = defineModel<boolean>("open", { required: true });

const { data: me } = useQuery(meQueryOptions());
const canViewEmployee = computed(
  () => me.value?.permissions.includes("schedule.view_employee") ?? false,
);

const id = computed(() => props.employee?.id ?? null);
const { data: detail, isPending, isError } = useQuery(employeeQueryOptions(id));

const flagMutation = useEmployeeFlagMutation(id);
const welcomeMutation = useSendWelcomeMutation(id);

const activeWeek = ref("");
watch(
  detail,
  (d) => {
    if (d?.pattern)
      activeWeek.value = d.pattern.current_cycle_label ?? d.pattern.weeks[0]?.label ?? "";
  },
  { immediate: true },
);
const shownWeek = computed(() =>
  detail.value?.pattern?.weeks.find((w) => w.label === activeWeek.value),
);

const savingKey = computed(() =>
  flagMutation.isPending.value ? flagMutation.variables.value?.key : null,
);
const profileUrl = computed(() => `/schedule/employees/${id.value}/defaults/`);
</script>

<template>
  <Sheet v-model:open="open">
    <SheetContent class="flex w-full flex-col gap-0 overflow-y-auto sm:max-w-md">
      <SheetHeader class="border-b pb-4">
        <SheetTitle class="font-display text-xl">{{ employee?.display_name }}</SheetTitle>
        <SheetDescription>{{ employee?.role_name }}</SheetDescription>
        <div class="flex flex-wrap gap-1 pt-1">
          <Badge v-if="employee?.cycle" variant="secondary">Week {{ employee.cycle.label }}</Badge>
          <Badge v-if="employee?.last_day" variant="destructive">
            Last day: {{ formatDateMedium(employee.last_day) }}
          </Badge>
        </div>
      </SheetHeader>

      <div v-if="isPending" class="flex justify-center p-8">
        <PhSpinner class="size-5 animate-spin text-muted-foreground" aria-label="Loading" />
      </div>
      <p v-else-if="isError || !detail" class="p-6 text-sm text-destructive">
        Couldn’t load this employee. Close the drawer and try again.
      </p>

      <div v-else class="space-y-6 p-4">
        <section v-if="detail.flags.length">
          <h3
            class="mb-2 font-display text-xs font-semibold tracking-wide text-muted-foreground uppercase"
          >
            Quick settings
          </h3>
          <ul class="divide-y rounded-lg border">
            <li
              v-for="flag in detail.flags"
              :key="flag.key"
              class="flex items-center justify-between gap-3 p-3"
            >
              <label :for="`flag-${flag.key}`" class="min-w-0 flex-1 text-sm">
                <span class="font-medium">{{ flag.label }}</span>
                <span v-if="flag.description" class="block text-xs text-muted-foreground">
                  {{ flag.description }}
                </span>
              </label>
              <PhSpinner
                v-if="savingKey === flag.key"
                class="size-4 animate-spin text-muted-foreground"
                aria-hidden="true"
              />
              <Switch
                :id="`flag-${flag.key}`"
                :model-value="flag.value"
                :disabled="!flag.can_edit || savingKey === flag.key"
                @update:model-value="
                  (v: boolean) => flagMutation.mutate({ key: flag.key, value: v })
                "
              />
            </li>
          </ul>
        </section>

        <section>
          <h3
            class="mb-2 font-display text-xs font-semibold tracking-wide text-muted-foreground uppercase"
          >
            Current schedule
          </h3>
          <template v-if="detail.pattern">
            <div v-if="detail.pattern.cycle_weeks > 1" class="mb-2 flex flex-wrap gap-1">
              <Button
                v-for="w in detail.pattern.weeks"
                :key="w.label"
                size="sm"
                :variant="w.label === activeWeek ? 'default' : 'outline'"
                @click="activeWeek = w.label"
              >
                Week {{ w.label }}
              </Button>
            </div>
            <table class="w-full text-sm">
              <tbody>
                <tr v-for="d in shownWeek?.days" :key="d.label" class="border-t first:border-t-0">
                  <td class="py-1.5 pr-4 text-left text-muted-foreground">{{ d.label }}</td>
                  <td class="py-1.5 text-right tabular-nums">
                    <span v-if="d.start && d.end"
                      >{{ format12(d.start) }} – {{ format12(d.end) }}</span
                    >
                    <span v-else class="text-subtle-foreground">OFF</span>
                  </td>
                </tr>
              </tbody>
            </table>
            <p class="mt-2 text-xs text-muted-foreground">
              Effective {{ formatDateMedium(detail.pattern.effective_from) }}
              {{
                detail.pattern.through
                  ? `· through ${formatDateMedium(detail.pattern.through)}`
                  : "· ongoing"
              }}
            </p>
          </template>
          <p v-else class="text-sm text-muted-foreground">No schedule set up yet.</p>
        </section>

        <section v-if="detail.can.send_welcome && !detail.last_day">
          <Button
            variant="outline"
            size="sm"
            :disabled="welcomeMutation.isPending.value"
            @click="showDialog = true"
          >
            <PhEnvelopeSimple class="size-4" aria-hidden="true" />
            Send welcome email
          </Button>
        </section>
        <ConfirmDialog
          v-model:open="showDialog"
          title="Send Welcome Email?"
          :description="`This will send ${employee?.display_name} a welcome email to ${detail.email} `"
          @approved="welcomeMutation.mutate()"
          @cancelled="showDialog = false"
        />
      </div>

      <SheetFooter class="mt-auto border-t p-4" v-if="canViewEmployee">
        <Button as-child class="w-full">
          <a :href="profileUrl">
            Open full profile
            <PhArrowSquareOut class="size-4" aria-hidden="true" />
          </a>
        </Button>
      </SheetFooter>
    </SheetContent>
  </Sheet>
</template>
