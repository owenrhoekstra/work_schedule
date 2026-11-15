<!-- components/Login/LoginLayout.vue -->
<script setup lang="ts">
const appName = import.meta.env.VITE_APP_NAME;
</script>

<template>
  <div class="flex min-h-dvh flex-col md:flex-row">
    <div
      class="relative overflow-hidden bg-brand-yellow/90 px-6 py-10 md:flex md:w-1/2 md:flex-col md:justify-center md:px-16 md:py-0 dark:bg-brand-indigo"
    >
      <div
        aria-hidden="true"
        class="absolute -right-16 -bottom-16 size-48 rounded-full bg-brand-indigo opacity-90 md:-right-24 md:-bottom-24 md:size-96 dark:bg-brand-yellow"
      ></div>
      <div
        aria-hidden="true"
        class="absolute top-8 -left-10 size-24 rounded-full bg-brand-coral md:top-20 md:size-40 dark:bg-brand-coral dark:opacity-60"
      ></div>

      <div class="relative z-10">
        <p
          class="mb-1 font-display text-sm leading-tight font-semibold tracking-wide text-brand-indigo md:mb-2 md:text-lg dark:text-brand-yellow"
        >
          {{ appName }}
        </p>
        <p
          class="font-display text-2xl leading-tight font-bold text-brand-indigo md:mb-6 md:text-5xl dark:text-white"
        >
          Know your<br class="hidden md:block" />
          next shift<br class="hidden md:block" />
          at a glance.
        </p>
        <p class="hidden max-w-xs text-base text-brand-indigo/80 md:block dark:text-brand-offwhite/80">
          Sign in to see what's coming up and keep your week sorted.
        </p>
      </div>
    </div>

    <div class="flex flex-1 items-start justify-center px-6 py-8 md:w-1/2 md:items-center md:py-12">
      <div class="w-full max-w-sm">
        <slot />
      </div>
    </div>
  </div>
</template>