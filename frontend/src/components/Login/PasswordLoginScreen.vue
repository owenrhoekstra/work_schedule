<!-- components/Login/PasswordLoginScreen.vue -->
<script setup lang="ts">
import { Input } from "@/components/ui/input";
import { usePasswordLogin } from "@/composables/Login/usePasswordLogin";
import BackToOptionsButton from "./BackToOptionsButton.vue";
import FormErrorAlert from "./FormErrorAlert.vue";
import PasswordField from "./PasswordField.vue";
import SubmitButton from "./SubmitButton.vue";

const emit = defineEmits<{ back: [] }>();
const { username, password, submitting, formError, submit } = usePasswordLogin();
</script>

<template>
  <div>
    <BackToOptionsButton @click="emit('back')" />

    <h1 class="mb-1 font-display text-2xl font-bold">Log in with password</h1>
    <p class="mb-8 text-sm text-muted-foreground">Enter your details to continue.</p>

    <FormErrorAlert v-if="formError" id="form-error" :message="formError" />

    <form novalidate class="space-y-5" @submit.prevent="submit">
      <div class="space-y-1.5">
        <label for="username" class="text-sm font-medium leading-none"> Username </label>
        <Input
          id="username"
          v-model="username"
          name="username"
          type="text"
          autocomplete="username"
          autocapitalize="none"
          spellcheck="false"
          class="h-11 text-base md:text-sm"
          :aria-describedby="formError ? 'form-error' : undefined"
        />
      </div>

      <PasswordField id="password" v-model="password" :form-error="formError" />

      <SubmitButton :submitting="submitting" label="Log in" loading-label="Logging in…" />
    </form>
  </div>
</template>
