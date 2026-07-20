import type {
  ApiResponse,
  ApiErrorResponse,
  ApiMeta,
  LoginRequest,
  RegisterRequest,
  Token,
  User,
  Dataset,
  Query,
  QueryRequest,
  QueryResult,
  DashboardStats,
  AnalyticsSummary,
  ActivityEvent,
  DatabaseConnection,
  ApiKey,
  UserProfile,
  NotificationPreferences,
  PaginatedResponse,
} from "@/types";

// ============================================================
// Central API Client
// ============================================================

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api/v1";
const REFRESH_TOKEN_KEY = "dataflow_refresh_token";
const ACCESS_TOKEN_KEY = "dataflow_access_token";

// ---- Token helpers ----
function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

function setTokens(access: string, refresh: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS_TOKEN_KEY, access);
  localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}

function clearTokens(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

// ---- Request logging ----
interface RequestLog {
  method: string;
  url: string;
  status: number;
  duration: number;
  timestamp: string;
}

const requestLogs: RequestLog[] = [];
const MAX_LOGS = 100;

function logRequest(log: RequestLog): void {
  requestLogs.unshift(log);
  if (requestLogs.length > MAX_LOGS) {
    requestLogs.pop();
  }
  if (process.env.NODE_ENV === "development") {
    console.log(
      `[API] ${log.method} ${log.url} → ${log.status} (${log.duration}ms)`
    );
  }
}

export function getRequestLogs(): RequestLog[] {
  return [...requestLogs];
}

// ---- Custom error class ----
export class ApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown>;

  constructor(
    message: string,
    code: string,
    status: number,
    details?: Record<string, unknown>
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

// ---- Token refresh logic ----
let isRefreshing = false;
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (isRefreshing && refreshPromise) {
    return refreshPromise;
  }

  isRefreshing = true;
  refreshPromise = (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      clearTokens();
      return null;
    }

    try {
      const response = await fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        clearTokens();
        return null;
      }

      const data: ApiResponse<Token> = await response.json();
      if (data.success && data.data) {
        setTokens(data.data.access_token, data.data.refresh_token);
        return data.data.access_token;
      }

      clearTokens();
      return null;
    } catch {
      clearTokens();
      return null;
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

// ---- Core request function ----
interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  params?: Record<string, string>;
  signal?: AbortSignal;
  skipAuth?: boolean;
}

async function request<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const {
    method = "GET",
    body,
    headers: customHeaders = {},
    params,
    signal,
    skipAuth = false,
  } = options;

  // Build URL with query params
  let url = `${BASE_URL}${endpoint}`;
  if (params) {
    const searchParams = new URLSearchParams(params);
    url += `?${searchParams.toString()}`;
  }

  // Build headers
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...customHeaders,
  };

  // Add auth token
  if (!skipAuth) {
    const token = getAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  const startTime = performance.now();

  try {
    const response = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });

    const duration = Math.round(performance.now() - startTime);

    // Handle 401 - attempt token refresh
    if (response.status === 401 && !skipAuth) {
      const newToken = await refreshAccessToken();
      if (newToken) {
        headers["Authorization"] = `Bearer ${newToken}`;
        const retryResponse = await fetch(url, {
          method,
          headers,
          body: body ? JSON.stringify(body) : undefined,
          signal,
        });

        const retryDuration = Math.round(performance.now() - startTime);
        logRequest({
          method,
          url: endpoint,
          status: retryResponse.status,
          duration: retryDuration,
          timestamp: new Date().toISOString(),
        });

        if (!retryResponse.ok) {
          const errorData: ApiErrorResponse = await retryResponse.json().catch(
            () => ({
              success: false,
              error: {
                code: "UNKNOWN",
                message: retryResponse.statusText,
              },
            })
          );
          throw new ApiError(
            errorData.error?.message || "Request failed",
            errorData.error?.code || "UNKNOWN",
            retryResponse.status,
            errorData.error?.details
          );
        }

        const data: ApiResponse<T> = await retryResponse.json();
        return data.data;
      }

      // Refresh failed, redirect to login
      clearTokens();
      if (typeof window !== "undefined") {
        window.location.href = "/dashboard";
      }
      throw new ApiError("Session expired", "TOKEN_EXPIRED", 401);
    }

    logRequest({
      method,
      url: endpoint,
      status: response.status,
      duration,
      timestamp: new Date().toISOString(),
    });

    // Parse response
    if (!response.ok) {
      const errorData: ApiErrorResponse = await response.json().catch(() => ({
        success: false,
        error: {
          code: "UNKNOWN",
          message: response.statusText,
        },
      }));
      throw new ApiError(
        errorData.error?.message || "Request failed",
        errorData.error?.code || "UNKNOWN",
        response.status,
        errorData.error?.details
      );
    }

    const data: ApiResponse<T> = await response.json();
    return data.data;
  } catch (error) {
    if (error instanceof ApiError) throw error;

    // Network error
    if (error instanceof TypeError && error.message.includes("fetch")) {
      throw new ApiError(
        "Network error. Please check your connection.",
        "NETWORK_ERROR",
        0
      );
    }

    throw new ApiError(
      error instanceof Error ? error.message : "Unknown error",
      "UNKNOWN",
      0
    );
  }
}

// ---- Paginated request helper ----
async function paginatedRequest<T>(
  endpoint: string,
  params?: Record<string, string>
): Promise<{ data: T[]; meta: ApiMeta }> {
  let url = `${BASE_URL}${endpoint}`;
  if (params) {
    const searchParams = new URLSearchParams(params);
    url += `?${searchParams.toString()}`;
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  const token = getAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(url, { headers });

  if (!response.ok) {
    const errorData: ApiErrorResponse = await response.json().catch(() => ({
      success: false,
      error: { code: "UNKNOWN", message: response.statusText },
    }));
    throw new ApiError(
      errorData.error?.message || "Request failed",
      errorData.error?.code || "UNKNOWN",
      response.status
    );
  }

  const data: PaginatedResponse<T> = await response.json();
  return { data: data.data, meta: data.meta };
}

// ============================================================
// API Methods
// ============================================================

export const apiClient = {
  // ---- Auth ----
  auth: {
    login: (data: LoginRequest) =>
      request<Token>("/auth/login", { method: "POST", body: data, skipAuth: true }),

    register: (data: RegisterRequest) =>
      request<Token>("/auth/register", {
        method: "POST",
        body: data,
        skipAuth: true,
      }),

    me: () => request<User>("/auth/me"),

    logout: () => {
      clearTokens();
      return Promise.resolve();
    },

    refreshToken: () => refreshAccessToken(),
  },

  // ---- Datasets ----
  datasets: {
    list: (params?: Record<string, string>) =>
      params
        ? paginatedRequest<Dataset>("/datasets", params)
        : request<Dataset[]>("/datasets"),

    get: (id: string) => request<Dataset>(`/datasets/${id}`),

    create: (data: Partial<Dataset>) =>
      request<Dataset>("/datasets", { method: "POST", body: data }),

    update: (id: string, data: Partial<Dataset>) =>
      request<Dataset>(`/datasets/${id}`, { method: "PUT", body: data }),

    delete: (id: string) =>
      request<void>(`/datasets/${id}`, { method: "DELETE" }),

    schema: (id: string) =>
      request<Dataset["schema"]>(`/datasets/${id}/schema`),

    testConnection: (id: string) =>
      request<{ status: string }>(`/datasets/${id}/test`, {
        method: "POST",
      }),
  },

  // ---- Queries ----
  queries: {
    list: (params?: Record<string, string>) =>
      params
        ? paginatedRequest<Query>("/queries", params)
        : request<Query[]>("/queries"),

    get: (id: string) => request<Query>(`/queries/${id}`),

    execute: (data: QueryRequest) =>
      request<Query>("/queries/execute", { method: "POST", body: data }),

    cancel: (id: string) =>
      request<void>(`/queries/${id}/cancel`, { method: "POST" }),

    result: (id: string) =>
      request<QueryResult>(`/queries/${id}/result`),

    recent: (limit: number = 10) =>
      request<Query[]>("/queries/recent", { params: { limit: String(limit) } }),
  },

  // ---- Analytics ----
  analytics: {
    summary: (params?: Record<string, string>) =>
      request<AnalyticsSummary>("/analytics/summary", { params }),

    dashboard: () => request<DashboardStats>("/analytics/dashboard"),

    activity: (limit: number = 20) =>
      request<ActivityEvent[]>("/analytics/activity", {
        params: { limit: String(limit) },
      }),

    timeseries: (metric: string, params?: Record<string, string>) =>
      request<{ points: { timestamp: string; value: number }[] }>(
        `/analytics/timeseries/${metric}`,
        { params }
      ),
  },

  // ---- Settings ----
  settings: {
    getConnections: () =>
      request<DatabaseConnection[]>("/settings/connections"),

    createConnection: (data: Partial<DatabaseConnection>) =>
      request<DatabaseConnection>("/settings/connections", {
        method: "POST",
        body: data,
      }),

    updateConnection: (id: string, data: Partial<DatabaseConnection>) =>
      request<DatabaseConnection>(`/settings/connections/${id}`, {
        method: "PUT",
        body: data,
      }),

    deleteConnection: (id: string) =>
      request<void>(`/settings/connections/${id}`, { method: "DELETE" }),

    testConnection: (data: Partial<DatabaseConnection>) =>
      request<{ status: string }>("/settings/connections/test", {
        method: "POST",
        body: data,
      }),

    getApiKeys: () => request<ApiKey[]>("/settings/api-keys"),

    createApiKey: (data: Partial<ApiKey>) =>
      request<ApiKey & { key: string }>("/settings/api-keys", {
        method: "POST",
        body: data,
      }),

    deleteApiKey: (id: string) =>
      request<void>(`/settings/api-keys/${id}`, { method: "DELETE" }),

    getProfile: () => request<UserProfile>("/settings/profile"),

    updateProfile: (data: Partial<UserProfile>) =>
      request<UserProfile>("/settings/profile", {
        method: "PUT",
        body: data,
      }),

    updateNotifications: (data: Partial<NotificationPreferences>) =>
      request<NotificationPreferences>("/settings/notifications", {
        method: "PUT",
        body: data,
      }),
  },

  // ---- Health ----
  health: {
    check: () =>
      request<{ status: string; version: string }>("/health", {
        skipAuth: true,
      }),
  },
};

// Export token helpers for use in other modules
export { getAccessToken, getRefreshToken, setTokens, clearTokens, BASE_URL };
