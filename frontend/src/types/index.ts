// ============================================================
// TypeScript types matching backend schemas
// ============================================================

// --- Auth Types ---
export interface User {
  id: string;
  email: string;
  name: string;
  avatar_url?: string;
  role: "admin" | "analyst" | "viewer";
  created_at: string;
  updated_at: string;
}

export interface Token {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
}

// --- Dataset Types ---
export interface Dataset {
  id: string;
  name: string;
  description?: string;
  source_type: "duckdb" | "postgresql" | "csv" | "api";
  connection_string?: string;
  schema?: DatasetSchema;
  row_count: number;
  size_bytes: number;
  created_at: string;
  updated_at: string;
  last_queried_at?: string;
}

export interface DatasetSchema {
  columns: ColumnSchema[];
}

export interface ColumnSchema {
  name: string;
  data_type: string;
  nullable: boolean;
  is_primary_key?: boolean;
}

// --- Query Types ---
export interface Query {
  id: string;
  dataset_id: string;
  sql: string;
  status: QueryStatus;
  result?: QueryResult;
  error?: string;
  duration_ms: number;
  rows_affected?: number;
  created_by: string;
  created_at: string;
  completed_at?: string;
}

export type QueryStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface QueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  truncated: boolean;
}

export interface QueryRequest {
  dataset_id: string;
  sql: string;
  limit?: number;
  save?: boolean;
}

// --- Analytics Types ---
export interface AnalyticsSummary {
  total_queries: number;
  avg_duration_ms: number;
  success_rate: number;
  queries_by_day: TimeSeriesPoint[];
  top_datasets: DatasetUsage[];
  slowest_queries: Query[];
}

export interface TimeSeriesPoint {
  timestamp: string;
  value: number;
}

export interface DatasetUsage {
  dataset_id: string;
  dataset_name: string;
  query_count: number;
  avg_duration_ms: number;
}

// --- Dashboard Types ---
export interface DashboardStats {
  total_datasets: number;
  queries_today: number;
  avg_response_time_ms: number;
  active_users: number;
  trends: {
    datasets: TrendValue;
    queries: TrendValue;
    response_time: TrendValue;
    users: TrendValue;
  };
}

export interface TrendValue {
  value: number;
  direction: "up" | "down" | "stable";
  percentage: number;
}

export interface ActivityEvent {
  id: string;
  type: "query" | "dataset" | "user" | "system";
  message: string;
  timestamp: string;
  user?: string;
}

// --- API Response Wrapper ---
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
  meta?: ApiMeta;
}

export interface ApiErrorResponse {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface ApiMeta {
  total?: number;
  page?: number;
  per_page?: number;
  total_pages?: number;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  meta: ApiMeta;
}

// --- Settings Types ---
export interface DatabaseConnection {
  id: string;
  name: string;
  type: "duckdb" | "postgresql";
  host?: string;
  port?: number;
  database: string;
  username?: string;
  password?: string;
  is_active: boolean;
  last_tested_at?: string;
  status: "connected" | "disconnected" | "error";
}

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  permissions: string[];
  created_at: string;
  last_used_at?: string;
  expires_at?: string;
}

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  avatar_url?: string;
  timezone: string;
  notification_preferences: NotificationPreferences;
}

export interface NotificationPreferences {
  email: boolean;
  query_completed: boolean;
  query_failed: boolean;
  system_alerts: boolean;
}

// --- WebSocket Message Types ---
export type WebSocketMessageType =
  | "query_progress"
  | "query_result"
  | "notification"
  | "connection_established"
  | "ping"
  | "pong";

export interface WebSocketMessage {
  type: WebSocketMessageType;
  payload: unknown;
  timestamp: string;
  id: string;
}

export interface QueryProgressPayload {
  query_id: string;
  progress: number;
  status: QueryStatus;
  message?: string;
}

export interface QueryResultPayload {
  query_id: string;
  result: QueryResult;
  duration_ms: number;
}

export interface NotificationPayload {
  id: string;
  title: string;
  message: string;
  type: "info" | "warning" | "error" | "success";
  read: boolean;
}
