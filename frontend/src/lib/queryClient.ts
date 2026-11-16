import { QueryClient } from "@tanstack/vue-query";
import { ApiError } from "@/composables/useApi";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 4xx won't become true on retry. Network/5xx get 2 retries.
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
          return false;
        }
        return failureCount < 2;
      },
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
    },
  },
});
