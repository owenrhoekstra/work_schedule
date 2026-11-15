// composables/Login/usePasswordLogin.ts
import { ref } from "vue";
import { ApiError, useApi } from "@/composables/useApi";
import { messageFor } from "./useFormErrors";

interface LoginResponse {
  ok: boolean;
  redirect_url: string;
  error: string;
}

/**
 * Read a `next` param from the current URL. Django's login redirect
 * appends ?next=/target/ when a session expires mid-action. This is
 * passthrough — the server re-validates against ALLOWED_HOSTS.
 */
function currentNextParam(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("next") ?? "";
}

export function usePasswordLogin() {
  const api = useApi();

  const username = ref("");
  const password = ref("");
  const submitting = ref(false);
  const formError = ref("");

  async function submit() {
    if (submitting.value) return;

    // No client-side field validation — the server is the sole
    // authority on what's valid (AGENTS.md: red errors must come from
    // the server). Empty fields become a 422 from the API with a
    // generic "Username and password required." message.
    formError.value = "";
    submitting.value = true;
    try {
      const resp = await api.post<LoginResponse>(
        "/accounts/login/",
        {
          username: username.value.trim(),
          password: password.value,
          next: currentNextParam(),
        },
        { skipAuthHandling: true },
      );
      if (!resp.ok) {
        formError.value = resp.error || "Incorrect username or password.";
        return;
      }
      // Full-page navigation to a Django URL. The destination is not a
      // Vue route — Django's middleware routes based on the user's
      // memberships (home / picker / waiting).
      window.location.href = resp.redirect_url;
    } catch (e) {
      // The API returns {ok: false, error} at 200 for bad credentials
      // and at 422 for missing fields. useApi throws on non-2xx, so
      // 422 lands here with the server's message inside `e.data.error`
      // — surface that instead of the generic fallback.
      if (
        e instanceof ApiError &&
        e.data &&
        typeof e.data === "object" &&
        "error" in e.data &&
        typeof (e.data as { error?: unknown }).error === "string"
      ) {
        formError.value = (e.data as { error: string }).error;
      } else {
        formError.value = messageFor(e);
      }
    } finally {
      submitting.value = false;
    }
  }

  return { username, password, submitting, formError, submit };
}
