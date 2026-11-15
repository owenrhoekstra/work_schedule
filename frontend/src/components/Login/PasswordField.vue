<!-- components/Login/PasswordField.vue -->
<script setup lang="ts">
import { computed, ref } from "vue";
import { PhEye, PhEyeSlash } from "@phosphor-icons/vue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const props = withDefaults(
  defineProps<{
    id?: string;
    label?: string;
    error?: string;
    formError?: string;
    autocomplete?: string;
  }>(),
  {
    id: "password",
    label: "Password",
    autocomplete: "current-password",
  },
);

const model = defineModel<string>({ required: true });
const show = ref(false);

const describedBy = computed(() =>
  props.error ? `${props.id}-error` : props.formError ? "form-error" : undefined,
);
</script>

<template>
  <div class="space-y-1.5">
    <Label :for="id">{{ label }}</Label>
    <div class="relative">
      <Input
        :id="id"
        v-model="model"
        name="password"
        :type="show ? 'text' : 'password'"
        :autocomplete="autocomplete"
        class="h-11 pr-11 text-base md:text-sm"
        :aria-invalid="Boolean(error || formError)"
        :aria-describedby="describedBy"
      />
      <Button
        type="button"
        variant="ghost"
        size="icon"
        class="absolute top-0 right-0 size-11"
        :aria-label="show ? 'Hide password' : 'Show password'"
        :aria-pressed="show"
        @click="show = !show"
      >
        <PhEyeSlash v-if="show" class="size-5" aria-hidden="true" />
        <PhEye v-else class="size-5" aria-hidden="true" />
      </Button>
    </div>
    <p v-if="error" :id="`${id}-error`" class="text-sm text-danger">{{ error }}</p>
  </div>
</template>