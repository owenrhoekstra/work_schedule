<!-- components/Login/LoginOptions.vue -->
<script setup lang="ts">
import { PhPassword, PhShieldCheck } from "@phosphor-icons/vue";
import LoginOptionCard from "./LoginOptionCard.vue";

const emit = defineEmits<{ select: [mode: "sso" | "password"] }>();

// Prod: Django login shell template injects window.__LOGIN_CONFIG__
// with oidcEnabled reflecting settings.OIDC_ENABLED.
//
// Dev: Vite serves frontend/index.html directly (no Django render),
// so __LOGIN_CONFIG__ is absent. Read VITE_OIDC_ENABLED from the env
// instead — set it to "true" in .env to mirror your backend's OIDC
// state during local development. Prod ignores this env var; only
// the shell injection is trusted there.
const config = (
  window as unknown as {
    __LOGIN_CONFIG__?: { oidcEnabled?: boolean };
  }
).__LOGIN_CONFIG__;

const oidcEnabled = import.meta.env.DEV
  ? import.meta.env.VITE_OIDC_ENABLED === "true"
  : config?.oidcEnabled === true;
</script>

<template>
  <div>
    <h1 class="mb-1 font-display text-2xl font-bold">Log in</h1>
    <p class="mb-8 text-sm text-muted-foreground">Choose how you'd like to sign in.</p>

    <div class="space-y-3">
      <LoginOptionCard
        v-if="oidcEnabled"
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
        :recommended="!oidcEnabled"
        @click="emit('select', 'password')"
      >
        <template #icon><PhPassword class="size-5" /></template>
      </LoginOptionCard>
    </div>

    <p class="mt-8 text-center text-sm text-muted-foreground">
      New here?
      <a href="/accounts/signup/" class="font-medium text-primary hover:underline">
        Create an account
      </a>
    </p>
  </div>
</template>
