<!-- components/Login/SubmitButton.vue -->
<script setup lang="ts">
import { PhSpinner } from "@phosphor-icons/vue";
import { Button } from "@/components/ui/button";

defineProps<{ submitting: boolean; label: string; loadingLabel: string }>();
</script>

<template>
  <Button
    type="submit"
    class="h-11 w-full text-base aria-disabled:pointer-events-none aria-disabled:opacity-60"
    :aria-disabled="submitting"
    :aria-busy="submitting"
  >
    <PhSpinner v-if="submitting" class="animate-spin" aria-hidden="true" />
    {{ submitting ? loadingLabel : label }}
  </Button>
</template>