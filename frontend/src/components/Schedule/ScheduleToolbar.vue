<script setup lang="ts">
import { PhPrinter } from "@phosphor-icons/vue";
import { Button } from "@/components/ui/button";
import type { ViewerCan, WeekRef } from "@/types/week";
import ScopeContextPicker from "./ScopeContextPicker.vue";
import ScopeSelector from "./ScopeSelector.vue";
import WeekHeader from "./WeekHeader.vue";

// Three-tier toolbar:
//   Row 0 (optional): Back to current week — only when off-current
//   Row 1:           [←] Week title [→]        [scopes]  [Print]
// Sits flush above the table (parent controls the gap).
//
// Print is a direct anchor to the Django print view with the current
// week pre-filled. Print options modal deferred — the page has its own
// controls; duplicating them in Vue is a follow-up.

defineProps<{
  week: WeekRef;
  scopes: string[];
  currentScope: string;
  viewerCan: ViewerCan;
}>();

defineEmits<{
  navigate: [week: string];
  goCurrent: [];
  selectScope: [scope: string];
}>();
</script>

<template>
  <div class="space-y-2">
    <button
      v-if="!week.is_current"
      type="button"
      class="text-sm font-medium text-link hover:underline"
      @click="$emit('goCurrent')"
    >
      Back to current week
    </button>

    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <WeekHeader :week="week" @navigate="$emit('navigate', $event)" />
      <div class="flex items-center gap-2">
        <ScopeContextPicker :scope="currentScope" />
        <ScopeSelector
          :scopes="scopes"
          :current="currentScope"
          @select="$emit('selectScope', $event)"
        />
        <Button v-if="viewerCan.print" variant="outline" as-child class="font-display">
          <a :href="`/schedule/print/?week=${week.start}`">
            <PhPrinter class="size-4" aria-hidden="true" />
            Print
          </a>
        </Button>
      </div>
    </div>
  </div>
</template>
