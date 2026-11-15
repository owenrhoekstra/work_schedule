<!-- BackToOptionsButton.vue -->
<script setup lang="ts">
import { PhArrowLeft } from "@phosphor-icons/vue";
import { Button } from "@/components/ui/button";
</script>

<template>
  <Button
    type="button"
    variant="ghost"
    class="mb-4 -ml-3 h-11 gap-1.5 px-3 text-muted-foreground"
  >
    <PhArrowLeft class="size-4" aria-hidden="true" />
    All sign-in options
  </Button>
</template>