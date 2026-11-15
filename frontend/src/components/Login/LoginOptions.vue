<!-- components/Login/LoginOptions.vue -->
<script setup lang="ts">
import { PhPassword, PhShieldCheck } from "@phosphor-icons/vue";
import LoginOptionCard from "./LoginOptionCard.vue";

const emit = defineEmits<{ select: [mode: "sso" | "password"] }>();

// Read SSO availability from the shell template's injected config.
// When OIDC isn't configured (no Zitadel credentials in the
// environment), the SSO option is hidden — clicking it would
// redirect to the placeholder provider at oidc.invalid.example.com
// and never complete.
const config = (
  window as unknown as {
    __LOGIN_CONFIG__?: { oidcEnabled?: boolean };
  }
).__LOGIN_CONFIG__;
const oidcEnabled = config?.oidcEnabled === true;
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
