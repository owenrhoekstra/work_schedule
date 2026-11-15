<!-- components/Login/SsoRedirectScreen.vue -->
<script setup lang="ts">
import { onMounted } from "vue";
import { PhSpinner, PhWarningCircle } from "@phosphor-icons/vue";
import { Button } from "@/components/ui/button";
import { useSsoLogin } from "@/composables/Login/useSsoLogin";
import BackToOptionsButton from "./BackToOptionsButton.vue";

const emit = defineEmits<{ back: [] }>();
const { status, error, start } = useSsoLogin();

onMounted(start);
</script>

<template>
  <div>
    <BackToOptionsButton @click="emit('back')" />

    <div class="flex flex-col items-center py-10 text-center">
      <template v-if="status === 'redirecting'">
        <PhSpinner class="size-8 animate-spin text-muted-foreground" aria-hidden="true" />
        <h1 class="mt-4 font-display text-xl font-bold">Redirecting to your SSO provider…</h1>
        <p class="mt-2 max-w-xs text-sm text-muted-foreground">
          You'll be taken to your organisation's sign-in page.
        </p>
      </template>

      <template v-else>
        <PhWarningCircle class="size-8 text-danger" aria-hidden="true" />
        <h1 class="mt-4 font-display text-xl font-bold">Couldn't start single sign-on</h1>
        <p class="mt-2 max-w-xs text-sm text-muted-foreground">{{ error }}</p>
        <Button type="button" variant="outline" class="mt-6" @click="start">Try again</Button>
      </template>
    </div>
  </div>
</template>