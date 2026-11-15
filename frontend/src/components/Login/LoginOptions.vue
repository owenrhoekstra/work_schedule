<!-- components/Login/LoginOptions.vue -->
<script setup lang="ts">
import { PhPassword, PhShieldCheck } from "@phosphor-icons/vue";
import LoginOptionCard from "./LoginOptionCard.vue";

const emit = defineEmits<{ select: [mode: "sso" | "password"] }>();
</script>

<template>
  <div>
    <h1 class="mb-1 font-display text-2xl font-bold">Log in</h1>
    <p class="mb-8 text-sm text-muted-foreground">Choose how you'd like to sign in.</p>

    <div class="space-y-3">
      <LoginOptionCard
        title="Single sign-on"
        description="Use your organisation account."
        recommended
        @click="emit('select', 'sso')"
      >
        <template #icon><PhShieldCheck class="size-5" /></template>
      </LoginOptionCard>

      <LoginOptionCard
        title="Password"
        description="Use your username and password."
        @click="emit('select', 'password')"
      >
        <template #icon><PhPassword class="size-5" /></template>
      </LoginOptionCard>
    </div>
  </div>
</template>
