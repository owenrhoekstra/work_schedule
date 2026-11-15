// composables/Login/useLoginMode.ts
import { ref } from "vue";

export type LoginMode = "options" | "sso" | "password";

export function useLoginMode(initial: LoginMode = "options") {
  const mode = ref<LoginMode>(initial);

  function select(next: LoginMode) {
    mode.value = next;
  }

  function backToOptions() {
    mode.value = "options";
  }

  return { mode, select, backToOptions };
}
