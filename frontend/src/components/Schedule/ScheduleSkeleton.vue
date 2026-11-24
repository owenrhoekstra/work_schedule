<script setup lang="ts">
import { Skeleton } from "@/components/ui/skeleton";

// Shape-matching skeleton for the schedule table. Renders 6 rows and
// the 6-day + total column grid so the layout doesn't jump when real
// data arrives. Header skeletons use light tones because the header
// row is the brand-indigo (dark) surface in both light and dark modes.
</script>

<template>
  <div
    class="overflow-hidden rounded-xl border border-border bg-card shadow-sm"
    role="status"
    aria-label="Loading schedule"
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
            v-for="i in 6"
            :key="`h-${i}`"
            class="p-2 text-center font-display text-sm font-medium whitespace-nowrap"
          >
            <Skeleton class="mx-auto h-3.5 w-16 bg-white/25" />
            <Skeleton class="mx-auto mt-1 h-3 w-10 bg-white/15" />
          </th>
          <th class="p-2 text-center font-display text-sm font-medium whitespace-nowrap">Total</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="i in 6" :key="`r-${i}`" class="border-t border-border">
          <td class="p-2">
            <Skeleton class="h-4 w-32" />
            <Skeleton class="mt-2 h-3 w-20" />
          </td>
          <td v-for="j in 6" :key="`c-${i}-${j}`" class="p-2">
            <Skeleton class="mx-auto h-4 w-20" />
          </td>
          <td class="p-2">
            <Skeleton class="mx-auto h-4 w-12" />
          </td>
        </tr>
      </tbody>
    </table>
    <span class="sr-only">Loading schedule…</span>
  </div>
</template>
