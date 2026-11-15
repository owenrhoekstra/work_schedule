// composables/Login/usePasswordLogin.ts
import { ref } from "vue";
import { useApi } from "@/composables/useApi";
import { messageFor, useFormErrors } from "./useFormErrors";

interface LoginResponse {
  ok: boolean;
  redirect_url: string;
  error: string;
}

export function usePasswordLogin() {
  const api = useApi();

  const username = ref("");
  const password = ref("");
  const submitting = ref(false);
  const { formError, fieldErrors, clearAll, setFieldError, invalid, describedBy, focusField } =
    useFormErrors(["username", "password"] as const);

  async function submit() {
    if (submitting.value) return;

    clearAll();
    const trimmed = username.value.trim();
    if (!trimmed) setFieldError("username", "Enter your username.");
    if (!password.value) setFieldError("password", "Enter your password.");
    if (fieldErrors.username) return focusField("username");
    if (fieldErrors.password) return focusField("password");

    submitting.value = true;
    try {
      const resp = await api.post<LoginResponse>(
        "/accounts/login/",
        { username: trimmed, password: password.value },
        { skipAuthHandling: true },
      );
      if (!resp.ok) {
        formError.value = resp.error || "Incorrect username or password.";
        focusField("password");
        return;
      }
      // Full-page navigation to a Django URL. The destination is not a
      // Vue route — Django's middleware chain handles picker/waiting/
      // home routing based on the user's memberships.
      window.location.href = resp.redirect_url;
    } catch (e) {
      formError.value = messageFor(e);
      focusField("password");
    } finally {
      submitting.value = false;
    }
  }

  return {
    username,
    password,
    submitting,
    formError,
    fieldErrors,
    invalid,
    describedBy,
    submit,
  };
}
