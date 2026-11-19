<script setup lang="ts">
import type { WeekRef } from "@/types/week";

defineProps<{ week: WeekRef }>();
defineEmits<{ navigate: [week: string]; goCurrent: [] }>();
</script>

<template>
  <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
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

    <button
      v-if="!week.is_current"
      type="button"
      class="self-start whitespace-nowrap text-sm font-medium text-link hover:underline sm:self-auto"
      @click="$emit('goCurrent')"
    >
      Back to current week
    </button>
  </div>
</template>
