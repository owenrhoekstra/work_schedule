// composables/Login/useFormErrors.ts
import { nextTick, reactive, ref } from "vue";
import { ApiError } from "@/composables/useApi";

export function useFormErrors<Field extends string>(fields: readonly Field[]) {
  const formError = ref("");

  const initial: Record<Field, string> = Object.fromEntries(fields.map((f) => [f, ""])) as Record<
    Field,
    string
  >;
  // reactive() returns Reactive<T>, which TS won't let you index with a
  // specific key type. Cast the return to the unwrapped shape — the
  // runtime proxy is structurally identical.
  const fieldErrors = reactive(initial) as Record<Field, string>;

  function clearAll() {
    formError.value = "";
    for (const f of fields) fieldErrors[f] = "";
  }

  function setFieldError(field: Field, message: string) {
    fieldErrors[field] = message;
  }

  const invalid = (field: Field) => Boolean(fieldErrors[field] || formError.value);
  const describedBy = (field: Field) =>
    fieldErrors[field] ? `${field}-error` : formError.value ? "form-error" : undefined;

  function focusField(id: Field) {
    nextTick(() => document.getElementById(id)?.focus());
  }

  return { formError, fieldErrors, clearAll, setFieldError, invalid, describedBy, focusField };
}

/** Shared API-error -> human message helper. */
export function messageFor(e: unknown, invalidMessage = "Incorrect username or password."): string {
  if (e instanceof ApiError) {
    if (e.kind === "network" || e.kind === "timeout") {
      return "Can't reach the server. Check your connection and try again.";
    }
    if (e.status === 400 || e.status === 401) return invalidMessage;
    if (e.status === 429) return "Too many attempts. Wait a moment and try again.";
  }
  return "Something went wrong. Please try again.";
}
