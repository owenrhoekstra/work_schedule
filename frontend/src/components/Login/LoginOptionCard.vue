<!-- components/Login/LoginOptionCard.vue -->
<script setup lang="ts">
defineProps<{
  title: string;
  description: string;
  recommended?: boolean;
}>();
</script>

<template>
  <button
    type="button"
    class="group flex w-full items-center gap-4 rounded-xl border border-border bg-card px-4 py-4 text-left transition focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [@media(hover:hover)]:hover:border-primary/40 [@media(hover:hover)]:hover:bg-accent active:bg-accent"
  >
    <span
      class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground transition group-active:bg-background [@media(hover:hover)]:group-hover:bg-background"
    >
      <slot name="icon" />
    </span>
    <span class="min-w-0 flex-1">
      <span class="flex flex-wrap items-center gap-2">
        <span class="font-medium">{{ title }}</span>
        <span
          v-if="recommended"
          class="rounded-full bg-primary/10 px-2 py-0.5 text-[0.65rem] font-semibold tracking-wide text-primary uppercase"
        >
          Recommended
        </span>
      </span>
      <span class="mt-0.5 block text-sm text-muted-foreground">{{ description }}</span>
    </span>
  </button>
</template>