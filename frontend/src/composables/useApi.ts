export type ApiErrorKind = "http" | "network" | "timeout" | "aborted";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public kind: ApiErrorKind = "http",
    public data?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isUnauthorized() {
    return this.status === 401;
  }
  get isForbidden() {
    return this.status === 403;
  }
}

interface ApiConfig {
  baseUrl: string;
  timeoutMs: number;
  getToken?: () => string | null;
  refreshSession?: () => Promise<boolean>;
  onUnauthorized?: () => void;
  onForbidden?: (error: ApiError) => void;
}

let config: ApiConfig = { baseUrl: "", timeoutMs: 15_000 };

export const configureApi = (next: Partial<ApiConfig>) => {
  config = { ...config, ...next };
};

const readCsrfToken = (): string | null => {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  if (!match || !match[1]) return null;
  return decodeURIComponent(match[1]);
};

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  timeoutMs?: number;
  skipAuthHandling?: boolean;
}

let recovery: Promise<boolean> | null = null;
const recoverSession = (): Promise<boolean> => {
  recovery ??= (async () => {
    const ok = config.refreshSession ? await config.refreshSession().catch(() => false) : false;
    if (!ok) config.onUnauthorized?.();
    return ok;
  })().finally(() => {
    recovery = null;
  });
  return recovery;
};

const buildUrl = (path: string, query?: RequestOptions["query"]) => {
  const url = /^https?:\/\//.test(path) ? path : config.baseUrl + path;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}${url.includes("?") ? "&" : "?"}${qs}` : url;
};

const parseBody = async (res: Response): Promise<unknown> => {
  if (res.status === 204 || res.headers.get("content-length") === "0") return undefined;
  const type = res.headers.get("content-type") ?? "";
  if (type.includes("json")) return res.json().catch(() => undefined);
  const text = await res.text().catch(() => "");
  return text || undefined;
};

const messageFrom = (data: unknown, fallback: string) => {
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    if (typeof d.message === "string") return d.message;
    if (typeof d.error === "string") return d.error;
  }
  return typeof data === "string" && data ? data : fallback;
};

export async function request<T = unknown>(
  path: string,
  options: RequestOptions = {},
  isRetry = false,
): Promise<T> {
  const {
    body,
    query,
    timeoutMs = config.timeoutMs,
    skipAuthHandling,
    signal,
    headers,
    ...init
  } = options;

  const finalHeaders = new Headers(headers);
  if (!finalHeaders.has("Accept")) finalHeaders.set("Accept", "application/json");

  let payload: BodyInit | undefined;
  if (body instanceof FormData || typeof body === "string" || body instanceof Blob) {
    payload = body;
  } else if (body !== undefined) {
    payload = JSON.stringify(body);
    if (!finalHeaders.has("Content-Type")) finalHeaders.set("Content-Type", "application/json");
  }

  const token = config.getToken?.();
  if (token && !finalHeaders.has("Authorization"))
    finalHeaders.set("Authorization", `Bearer ${token}`);

  // CSRF: Django requires X-CSRFToken on unsafe methods. Attach from
  // the cookie on every non-safe verb.
  const method = ((init.method as string | undefined) ?? "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method) && !finalHeaders.has("X-CSRFToken")) {
    const csrf = readCsrfToken();
    if (csrf) finalHeaders.set("X-CSRFToken", csrf);
  }

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  signal?.addEventListener("abort", () => controller.abort(), { once: true });

  let res: Response;
  let data: unknown;
  try {
    res = await fetch(buildUrl(path, query), {
      credentials: "include",
      ...init,
      headers: finalHeaders,
      body: payload,
      signal: controller.signal,
    });
    data = await parseBody(res);
  } catch (err) {
    if (timedOut) throw new ApiError(0, "The request timed out", "timeout");
    if (signal?.aborted || (err instanceof DOMException && err.name === "AbortError")) {
      throw new ApiError(0, "Request cancelled", "aborted");
    }
    throw new ApiError(0, "Network error. Check your connection.", "network");
  } finally {
    clearTimeout(timer);
  }

  if (res.ok) return data as T;

  const error = new ApiError(
    res.status,
    messageFrom(data, res.statusText || "Request failed"),
    "http",
    data,
  );

  if (!skipAuthHandling) {
    if (res.status === 401) {
      if (isRetry) {
        config.onUnauthorized?.();
      } else if (await recoverSession()) {
        return request<T>(path, options, true);
      }
    } else if (res.status === 403) {
      config.onForbidden?.(error);
    }
  }

  throw error;
}

export const useApi = () => ({
  request,
  get: <T = unknown>(path: string, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "GET" }),
  post: <T = unknown>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "POST", body }),
  put: <T = unknown>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "PUT", body }),
  patch: <T = unknown>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "PATCH", body }),
  del: <T = unknown>(path: string, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "DELETE" }),
});
