<!-- components/Login/FormErrorAlert.vue -->
<script setup lang="ts">
import { PhWarningCircle } from "@phosphor-icons/vue";

defineProps<{ message: string; id?: string }>();
</script>

<template>
  <div
    :id="id"
    role="alert"
    class="mb-6 flex items-start gap-2 rounded-lg border border-danger/30 bg-danger-subtle px-4 py-3 text-sm font-medium text-danger"
  >
    <PhWarningCircle class="mt-0.5 size-5 shrink-0" aria-hidden="true" />
    <p>{{ message }}</p>
  </div>
</template>