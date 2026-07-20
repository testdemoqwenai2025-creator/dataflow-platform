"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { apiClient, ApiError } from "@/lib/api-client";
import type { ApiResponse } from "@/types";

// ============================================================
// React hooks for API calls
// ============================================================

// ---- useApi: Generic API helper ----
interface UseApiReturn {
  get: <T>(endpoint: string, params?: Record<string, string>) => Promise<T>;
  post: <T>(endpoint: string, body?: unknown) => Promise<T>;
  put: <T>(endpoint: string, body?: unknown) => Promise<T>;
  del: <T>(endpoint: string) => Promise<T>;
  loading: boolean;
  error: ApiError | null;
}

export function useApi(): UseApiReturn {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const execute = useCallback(
    async <T>(fn: () => Promise<T>): Promise<T> => {
      setLoading(true);
      setError(null);
      try {
        const result = await fn();
        return result;
      } catch (err) {
        const apiError =
          err instanceof ApiError
            ? err
            : new ApiError(
                err instanceof Error ? err.message : "Unknown error",
                "UNKNOWN",
                0
              );
        setError(apiError);
        throw apiError;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const get = useCallback(
    <T>(endpoint: string, params?: Record<string, string>) =>
      execute<T>(() => request<T>(endpoint, { params })),
    [execute]
  );

  const post = useCallback(
    <T>(endpoint: string, body?: unknown) =>
      execute<T>(() => request<T>(endpoint, { method: "POST", body })),
    [execute]
  );

  const put = useCallback(
    <T>(endpoint: string, body?: unknown) =>
      execute<T>(() => request<T>(endpoint, { method: "PUT", body })),
    [execute]
  );

  const del = useCallback(
    <T>(endpoint: string) =>
      execute<T>(() => request<T>(endpoint, { method: "DELETE" })),
    [execute]
  );

  return { get, post, put, del, loading, error };
}

// ---- useQuery: Fetch + cache ----
interface UseQueryResult<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
  refetch: () => Promise<void>;
}

const queryCache = new Map<string, { data: unknown; timestamp: number }>();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

export function useQuery<T>(
  endpoint: string,
  options?: {
    params?: Record<string, string>;
    enabled?: boolean;
    cache?: boolean;
    cacheTTL?: number;
    retry?: number;
    retryDelay?: number;
  }
): UseQueryResult<T> {
  const {
    params,
    enabled = true,
    cache = true,
    cacheTTL = CACHE_TTL,
    retry = 2,
    retryDelay = 1000,
  } = options || {};

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<ApiError | null>(null);
  const retryCountRef = useRef(0);

  const cacheKey = `${endpoint}?${new URLSearchParams(params || {}).toString()}`;

  const fetchData = useCallback(async () => {
    // Check cache
    if (cache) {
      const cached = queryCache.get(cacheKey);
      if (cached && Date.now() - cached.timestamp < cacheTTL) {
        setData(cached.data as T);
        setLoading(false);
        return;
      }
    }

    setLoading(true);
    setError(null);

    try {
      const result = await request<T>(endpoint, { params });

      // Update cache
      if (cache) {
        queryCache.set(cacheKey, { data: result, timestamp: Date.now() });
      }

      setData(result);
      retryCountRef.current = 0;
    } catch (err) {
      const apiError =
        err instanceof ApiError
          ? err
          : new ApiError(
              err instanceof Error ? err.message : "Unknown error",
              "UNKNOWN",
              0
            );

      // Retry logic
      if (retryCountRef.current < retry && apiError.status >= 500) {
        retryCountRef.current++;
        setTimeout(() => fetchData(), retryDelay * retryCountRef.current);
        return;
      }

      setError(apiError);
    } finally {
      setLoading(false);
    }
  }, [endpoint, cacheKey, cache, cacheTTL, params, retry, retryDelay]);

  useEffect(() => {
    if (enabled) {
      fetchData();
    }
  }, [enabled, fetchData]);

  return { data, loading, error, refetch: fetchData };
}

// ---- useMutation: Post/Put with loading state ----
interface UseMutationResult<TData, TVariables> {
  mutate: (variables: TVariables) => Promise<TData>;
  data: TData | null;
  loading: boolean;
  error: ApiError | null;
  reset: () => void;
}

export function useMutation<TData, TVariables = unknown>(
  endpoint: string,
  options?: {
    method?: "POST" | "PUT" | "PATCH";
    onSuccess?: (data: TData) => void;
    onError?: (error: ApiError) => void;
  }
): UseMutationResult<TData, TVariables> {
  const { method = "POST", onSuccess, onError } = options || {};

  const [data, setData] = useState<TData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const mutate = useCallback(
    async (variables: TVariables): Promise<TData> => {
      setLoading(true);
      setError(null);

      try {
        const result = await request<TData>(endpoint, {
          method,
          body: variables,
        });

        setData(result);
        onSuccess?.(result);
        return result;
      } catch (err) {
        const apiError =
          err instanceof ApiError
            ? err
            : new ApiError(
                err instanceof Error ? err.message : "Unknown error",
                "UNKNOWN",
                0
              );

        setError(apiError);
        onError?.(apiError);
        throw apiError;
      } finally {
        setLoading(false);
      }
    },
    [endpoint, method, onSuccess, onError]
  );

  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  return { mutate, data, loading, error, reset };
}

// ============================================================
// Internal request helper (mirrors api-client logic for hooks)
// ============================================================

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

async function request<T>(
  endpoint: string,
  options: {
    method?: string;
    body?: unknown;
    params?: Record<string, string>;
  } = {}
): Promise<T> {
  const { method = "GET", body, params } = options;

  let url = `${BASE_URL}${endpoint}`;
  if (params) {
    const searchParams = new URLSearchParams(params);
    url += `?${searchParams.toString()}`;
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (typeof window !== "undefined") {
    const token = localStorage.getItem("dataflow_access_token");
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  const response = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({
      error: { code: "UNKNOWN", message: response.statusText },
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
}

// ---- Cache invalidation helper ----
export function invalidateCache(pattern?: string): void {
  if (!pattern) {
    queryCache.clear();
    return;
  }

  const keys = Array.from(queryCache.keys());
  for (const key of keys) {
    if (key.includes(pattern)) {
      queryCache.delete(key);
    }
  }
}
