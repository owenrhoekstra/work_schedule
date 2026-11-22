<script setup lang="ts">
import type { WeekRef } from "@/types/week";

// Week nav only. Back-to-current lives in ScheduleToolbar above this,
// on its own line. Kept here just so WeekHeader stays self-contained
// for the arrow/title/arrow row.
defineProps<{ week: WeekRef }>();
defineEmits<{ navigate: [week: string] }>();
</script>

<template>
  <div class="flex items-center gap-3">
    <button
      v-if="week.can_go_back"
      type="button"
      aria-label="Previous week"
      class="font-display text-2xl leading-none text-foreground transition-colors hover:text-link"
      @click="$emit('navigate', week.prev)"
    >
      ←
    </button>
    <span
      v-else
      aria-hidden="true"
      class="cursor-not-allowed font-display text-2xl leading-none text-subtle-foreground"
    >
      ←
    </span>

    <h1 class="font-display text-2xl font-bold whitespace-nowrap text-foreground">
      {{ week.is_current ? "This Week's Schedule" : week.title }}
    </h1>

    <button
      type="button"
      aria-label="Next week"
      class="font-display text-2xl leading-none text-foreground transition-colors hover:text-link"
      @click="$emit('navigate', week.next)"
    >
      →
    </button>
  </div>
</template>
