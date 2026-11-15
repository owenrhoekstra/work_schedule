<!-- components/Login/PasswordInput.vue -->
<script setup lang="ts">
import { ref } from "vue";
import { PhEye, PhEyeSlash } from "@phosphor-icons/vue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

defineProps<{ id: string; invalid?: boolean; describedBy?: string }>();
const model = defineModel<string>({ required: true });
const show = ref(false);
</script>

<template>
  <div class="relative">
    <Input
      :id="id"
      v-model="model"
      name="password"
      :type="show ? 'text' : 'password'"
      autocomplete="current-password"
      class="h-11 pr-11"
      :aria-invalid="invalid"
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
</template>