<!-- components/PageSkeleton.vue -->
<script setup lang="ts">
import { PhSpinner } from "@phosphor-icons/vue";
</script>

<template>
  <div class="flex min-h-screen items-center justify-center">
    <PhSpinner class="size-8 animate-spin text-muted-foreground" aria-hidden="true" />
  </div>
</template>