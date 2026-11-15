<!-- views/Login.vue -->
<script setup lang="ts">
import LoginLayout from "@/components/Login/LoginLayout.vue";
import LoginOptions from "@/components/Login/LoginOptions.vue";
import PasswordLoginScreen from "@/components/Login/PasswordLoginScreen.vue";
import SsoRedirectScreen from "@/components/Login/SsoRedirectScreen.vue";
import { useLoginMode } from "@/composables/Login/useLoginMode";

const { mode, select, backToOptions } = useLoginMode();
</script>

<template>
  <LoginLayout>
    <Transition name="fade" mode="out-in">
      <LoginOptions v-if="mode === 'options'" key="options" @select="select" />
      <SsoRedirectScreen v-else-if="mode === 'sso'" key="sso" @back="backToOptions" />
      <PasswordLoginScreen v-else key="password" @back="backToOptions" />
    </Transition>
  </LoginLayout>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
