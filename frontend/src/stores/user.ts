import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { ApiError, useApi } from "@/composables/useApi";

export interface CurrentUser {
  firstName: string;
  lastName: string;
}

// Flip to false once /api/v1/me/ exists
const USE_STUB = false;
const stubUser: CurrentUser = { firstName: "Jane", lastName: "Doe" };

export const useUserStore = defineStore("user", () => {
  const api = useApi();

  const user = ref<CurrentUser | null>(null);
  const loading = ref(false);
  const ready = ref(false);
  const error = ref<ApiError | null>(null);
  let inflight: Promise<void> | null = null;

  const fullName = computed(() =>
    user.value ? `${user.value.firstName} ${user.value.lastName}`.trim() : "",
  );

  function load(force = false): Promise<void> {
    if (user.value && !force) return Promise.resolve();
    inflight ??= (async () => {
      loading.value = true;
      try {
        user.value = USE_STUB
          ? await new Promise<CurrentUser>((resolve) => setTimeout(() => resolve(stubUser), 300))
          : await api.get<CurrentUser>("/me");
        error.value = null;
      } catch (e) {
        error.value = e instanceof ApiError ? e : null;
      } finally {
        loading.value = false;
        ready.value = true;
        inflight = null;
      }
    })();
    return inflight;
  }

  function clear() {
    user.value = null;
    error.value = null;
    ready.value = false;
  }

  return { user, loading, ready, error, fullName, load, clear };
});
