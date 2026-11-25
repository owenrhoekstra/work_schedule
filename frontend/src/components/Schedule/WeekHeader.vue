<script setup lang="ts">
import { PhArrowLeft, PhArrowRight, PhCalendarBlank } from "@phosphor-icons/vue";
import type { WeekRef } from "@/types/Schedule/week.ts";
import WeekSelector from "./WeekSelector.vue";

// Week nav only. Back-to-current lives in ScheduleToolbar above this,
// on its own line.
defineProps<{ week: WeekRef }>();
defineEmits<{ navigate: [week: string] }>();
</script>

<template>
  <div class="flex items-center gap-3">
    <button
      type="button"
      aria-label="Previous week"
      :disabled="!week.can_go_back"
      class="text-foreground transition-colors hover:text-link disabled:cursor-not-allowed disabled:text-subtle-foreground disabled:hover:text-subtle-foreground"
      @click="$emit('navigate', week.prev)"
    >
      <PhArrowLeft class="size-6" aria-hidden="true" />
    </button>

    <h1 class="font-display text-2xl font-bold whitespace-nowrap text-foreground">
      <WeekSelector :week="week" @navigate="$emit('navigate', $event)">
        <span class="leading-none">
          {{ week.is_current ? "This Week's Schedule" : week.title }}
        </span>
        <PhCalendarBlank class="size-6 shrink-0" aria-hidden="true" />
      </WeekSelector>
    </h1>

    <button
      type="button"
      aria-label="Next week"
      class="text-foreground transition-colors hover:text-link"
      @click="$emit('navigate', week.next)"
    >
      <PhArrowRight class="size-6" aria-hidden="true" />
    </button>
  </div>
</template>
