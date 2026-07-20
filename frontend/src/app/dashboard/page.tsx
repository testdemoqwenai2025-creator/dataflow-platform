"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Database,
  Activity,
  Clock,
  Users,
  Play,
  ArrowRight,
  AlertCircle,
  Check,
  Info,
  X,
  Loader2,
} from "lucide-react";
import { KPICard } from "@/components/dashboard/KPICard";
import { RecentQueries } from "@/components/dashboard/RecentQueries";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardTitle, CardBody } from "@/components/ui/Card";
import { apiClient, ApiError } from "@/lib/api-client";
import type { DashboardStats, Query, QueryResult } from "@/types";

// ---- Mock data for demo when backend is unavailable ----
const mockStats: DashboardStats = {
  total_datasets: 24,
  queries_today: 156,
  avg_response_time_ms: 245,
  active_users: 12,
  trends: {
    datasets: { value: 24, direction: "up" as const, percentage: 8.3 },
    queries: { value: 156, direction: "up" as const, percentage: 12.5 },
    response_time: { value: 245, direction: "down" as const, percentage: 5.2 },
    users: { value: 12, direction: "up" as const, percentage: 3.1 },
  },
};

const mockQueries: Query[] = [
  {
    id: "1",
    dataset_id: "ds-1",
    sql: "SELECT * FROM sales WHERE revenue > 10000 ORDER BY date DESC",
    status: "completed",
    duration_ms: 234,
    created_by: "admin",
    created_at: new Date(Date.now() - 120000).toISOString(),
  },
  {
    id: "2",
    dataset_id: "ds-2",
    sql: "SELECT category, SUM(revenue) as total FROM orders GROUP BY category",
    status: "completed",
    duration_ms: 156,
    created_by: "analyst",
    created_at: new Date(Date.now() - 300000).toISOString(),
  },
  {
    id: "3",
    dataset_id: "ds-1",
    sql: "SELECT COUNT(*) FROM users WHERE created_at > '2024-01-01'",
    status: "running",
    duration_ms: 0,
    created_by: "admin",
    created_at: new Date(Date.now() - 30000).toISOString(),
  },
  {
    id: "4",
    dataset_id: "ds-3",
    sql: "SELECT region, AVG(sales) FROM metrics GROUP BY region HAVING AVG(sales) > 500",
    status: "failed",
    duration_ms: 89,
    error: "Column 'sales' not found",
    created_by: "viewer",
    created_at: new Date(Date.now() - 600000).toISOString(),
  },
  {
    id: "5",
    dataset_id: "ds-1",
    sql: "INSERT INTO audit_log (action, user_id, timestamp) VALUES ('query', 1, NOW())",
    status: "completed",
    duration_ms: 45,
    created_by: "admin",
    created_at: new Date(Date.now() - 900000).toISOString(),
  },
];

const sparklineData = {
  datasets: [18, 20, 19, 21, 22, 21, 24],
  queries: [120, 135, 128, 142, 138, 149, 156],
  responseTime: [280, 265, 270, 258, 252, 248, 245],
  users: [8, 9, 10, 9, 11, 10, 12],
};

// ---- Toast notification ----
interface Toast {
  id: string;
  message: string;
  type: "success" | "error" | "info";
}

// ---- KPI Skeleton ----
function KPISkeleton() {
  return (
    <div className="rounded-xl bg-white border border-surface-200 p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="skeleton w-10 h-10 rounded-lg" />
        <div className="skeleton w-16 h-6 rounded-full" />
      </div>
      <div className="mt-3">
        <div className="skeleton h-8 w-24 rounded" />
        <div className="skeleton h-4 w-20 rounded mt-2" />
      </div>
      <div className="mt-3 h-8">
        <div className="skeleton w-full h-full rounded" />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [queries, setQueries] = useState<Query[]>([]);
  const [loading, setLoading] = useState(true);
  const [quickQuery, setQuickQuery] = useState("");
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [queryExecutionTime, setQueryExecutionTime] = useState<number | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Toast helpers
  const addToast = useCallback((message: string, type: Toast["type"] = "info") => {
    const id = `toast-${Date.now()}`;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  // Fetch dashboard data
  const fetchDashboardData = useCallback(async () => {
    setLoading(true);
    try {
      const [dashStats, recentQueries] = await Promise.all([
        apiClient.analytics.dashboard(),
        apiClient.queries.recent(5),
      ]);
      setStats(dashStats);
      setQueries(recentQueries);
    } catch (error) {
      // Use mock data if backend is unavailable
      console.warn("Backend unavailable, using mock data:", error);
      setStats(mockStats);
      setQueries(mockQueries);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  // Quick query execution
  const handleQuickQuery = async () => {
    if (!quickQuery.trim()) return;

    setQueryLoading(true);
    setQueryError(null);
    setQueryResult(null);
    setQueryExecutionTime(null);

    const startTime = performance.now();

    try {
      const queryResult = await apiClient.queries.execute({
        dataset_id: "default",
        sql: quickQuery,
      });

      const elapsed = Math.round(performance.now() - startTime);
      setQueryExecutionTime(queryResult.duration_ms || elapsed);

      if (queryResult.result) {
        setQueryResult(queryResult.result);
        addToast(`Query executed successfully (${queryResult.result.row_count} rows)`, "success");
      } else {
        addToast("Query executed successfully", "success");
      }

      // Refresh queries list
      try {
        const recentQueries = await apiClient.queries.recent(5);
        setQueries(recentQueries);
      } catch {
        // Keep existing queries if refresh fails
      }
    } catch (error) {
      const elapsed = Math.round(performance.now() - startTime);
      setQueryExecutionTime(elapsed);

      let userMessage = "Failed to execute query";
      if (error instanceof ApiError) {
        if (error.code === "NETWORK_ERROR") {
          userMessage = "Unable to connect to the server. The backend may be offline.";
        } else if (error.status === 400) {
          userMessage = `Invalid query: ${error.message}`;
        } else if (error.status === 404) {
          userMessage = "No default dataset available. Try the Analytics page for full query support.";
        } else {
          userMessage = error.message;
        }
      }
      setQueryError(userMessage);
      addToast(userMessage, "error");
    } finally {
      setQueryLoading(false);
    }
  };

  const dismissQueryResult = () => {
    setQueryResult(null);
    setQueryError(null);
    setQueryExecutionTime(null);
  };

  const displayStats = stats || mockStats;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Toast notifications */}
      <div className="fixed top-4 right-4 z-50 space-y-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium animate-fade-in ${
              toast.type === "success"
                ? "bg-green-600 text-white"
                : toast.type === "error"
                ? "bg-red-600 text-white"
                : "bg-surface-800 text-white"
            }`}
          >
            {toast.type === "success" && <Check className="w-4 h-4" />}
            {toast.type === "error" && <AlertCircle className="w-4 h-4" />}
            {toast.type === "info" && <Info className="w-4 h-4" />}
            {toast.message}
          </div>
        ))}
      </div>

      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-surface-900">Dashboard</h1>
          <p className="mt-1 text-sm text-surface-500">
            Overview of your data platform activity
          </p>
        </div>
        <Button
          variant="secondary"
          icon={<Activity className="w-4 h-4" />}
          onClick={fetchDashboardData}
        >
          Refresh
        </Button>
      </div>

      {/* KPI Cards */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPISkeleton />
          <KPISkeleton />
          <KPISkeleton />
          <KPISkeleton />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard
            label="Total Datasets"
            value={displayStats.total_datasets}
            icon={<Database className="w-5 h-5" />}
            trend={displayStats.trends.datasets}
            sparklineData={sparklineData.datasets}
          />
          <KPICard
            label="Queries Today"
            value={displayStats.queries_today}
            icon={<Activity className="w-5 h-5" />}
            trend={displayStats.trends.queries}
            sparklineData={sparklineData.queries}
          />
          <KPICard
            label="Avg Response Time"
            value={`${displayStats.avg_response_time_ms}ms`}
            icon={<Clock className="w-5 h-5" />}
            trend={displayStats.trends.response_time}
            sparklineData={sparklineData.responseTime}
          />
          <KPICard
            label="Active Users"
            value={displayStats.active_users}
            icon={<Users className="w-5 h-5" />}
            trend={displayStats.trends.users}
            sparklineData={sparklineData.users}
          />
        </div>
      )}

      {/* Quick Query + Activity Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Quick Query */}
        <div className="lg:col-span-1 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Quick Query</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="space-y-3">
                <textarea
                  value={quickQuery}
                  onChange={(e) => setQuickQuery(e.target.value)}
                  placeholder="SELECT * FROM ..."
                  className="sql-editor w-full h-32 px-3 py-2 text-sm rounded-lg border border-surface-200 bg-surface-50 text-surface-900 placeholder:text-surface-400 resize-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition-all"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      handleQuickQuery();
                    }
                  }}
                />
                {queryError && (
                  <div className="flex items-start gap-2 p-2 rounded-md bg-red-50 border border-red-100">
                    <AlertCircle className="w-3.5 h-3.5 text-red-500 shrink-0 mt-0.5" />
                    <p className="text-xs text-red-600">{queryError}</p>
                  </div>
                )}
                <div className="flex items-center justify-between">
                  <span className="text-xs text-surface-400">
                    Press ⌘+Enter to run
                  </span>
                  <Button
                    size="sm"
                    icon={<Play className="w-3.5 h-3.5" />}
                    loading={queryLoading}
                    onClick={handleQuickQuery}
                    disabled={!quickQuery.trim()}
                  >
                    Run Query
                  </Button>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* Inline Query Results */}
          {queryResult && (
            <Card>
              <CardHeader
                action={
                  <div className="flex items-center gap-2">
                    {queryExecutionTime !== null && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-surface-100 text-surface-600">
                        <Clock className="w-3 h-3" />
                        {queryExecutionTime < 1000
                          ? `${queryExecutionTime}ms`
                          : `${(queryExecutionTime / 1000).toFixed(2)}s`}
                      </span>
                    )}
                    <button
                      onClick={dismissQueryResult}
                      className="p-1 rounded text-surface-400 hover:text-surface-600 hover:bg-surface-100 transition-colors"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                }
              >
                <CardTitle>Query Results</CardTitle>
              </CardHeader>
              <CardBody noPadding>
                <div className="overflow-x-auto max-h-64 overflow-y-auto">
                  <table className="w-full data-table">
                    <thead>
                      <tr className="border-b border-surface-200 bg-surface-50 sticky top-0">
                        {queryResult.columns.map((col) => (
                          <th
                            key={col}
                            className="px-3 py-2 text-left whitespace-nowrap text-xs font-medium text-surface-600"
                          >
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-100">
                      {queryResult.rows.slice(0, 20).map((row, i) => (
                        <tr
                          key={i}
                          className="hover:bg-surface-50 transition-colors"
                        >
                          {queryResult.columns.map((col) => (
                            <td
                              key={col}
                              className="px-3 py-2 whitespace-nowrap text-xs text-surface-700"
                            >
                              {typeof row[col] === "number"
                                ? (row[col] as number).toLocaleString()
                                : String(row[col] ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="px-3 py-2 border-t border-surface-200 bg-surface-50 text-xs text-surface-500 flex items-center justify-between">
                  <span>
                    {queryResult.row_count} row{queryResult.row_count !== 1 ? "s" : ""}
                    {queryResult.truncated && " (truncated)"}
                    {queryResult.rows.length > 20 && ` · showing first 20`}
                  </span>
                </div>
              </CardBody>
            </Card>
          )}

          {/* Loading state for query */}
          {queryLoading && (
            <Card>
              <CardBody>
                <div className="flex flex-col items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 text-brand-500 animate-spin" />
                  <p className="mt-2 text-sm text-surface-500">
                    Executing query...
                  </p>
                </div>
              </CardBody>
            </Card>
          )}
        </div>

        {/* Activity Chart Placeholder */}
        <Card className="lg:col-span-2">
          <CardHeader
            action={
              <div className="flex items-center gap-2">
                <button className="px-3 py-1 text-xs font-medium text-brand-600 bg-brand-50 rounded-md">
                  7D
                </button>
                <button className="px-3 py-1 text-xs font-medium text-surface-500 hover:text-surface-700 rounded-md hover:bg-surface-100 transition-colors">
                  30D
                </button>
                <button className="px-3 py-1 text-xs font-medium text-surface-500 hover:text-surface-700 rounded-md hover:bg-surface-100 transition-colors">
                  90D
                </button>
              </div>
            }
          >
            <CardTitle>Query Activity</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="h-64 flex items-end gap-1.5 pt-4">
              {sparklineData.queries.map((val, i) => {
                const max = Math.max(...sparklineData.queries);
                const height = (val / max) * 100;
                const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
                return (
                  <div
                    key={i}
                    className="flex-1 flex flex-col items-center gap-1"
                  >
                    <div
                      className="w-full rounded-t-md bg-gradient-to-t from-brand-500 to-accent-400 transition-all duration-300 hover:from-brand-600 hover:to-accent-500"
                      style={{ height: `${height}%` }}
                    />
                    <span className="text-[10px] text-surface-400">
                      {days[i]}
                    </span>
                  </div>
                );
              })}
            </div>
          </CardBody>
        </Card>
      </div>

      {/* Recent Queries Table */}
      <RecentQueries queries={queries} loading={loading} />

      {/* Quick links */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card hover>
          <CardBody className="flex items-center gap-4">
            <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-accent-50 text-accent-600">
              <Database className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-surface-900">
                Browse Datasets
              </h3>
              <p className="text-xs text-surface-500 mt-0.5">
                Explore available data sources
              </p>
            </div>
            <ArrowRight className="w-4 h-4 text-surface-400" />
          </CardBody>
        </Card>
        <Card hover>
          <CardBody className="flex items-center gap-4">
            <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-brand-50 text-brand-600">
              <Activity className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-surface-900">
                View Analytics
              </h3>
              <p className="text-xs text-surface-500 mt-0.5">
                Detailed performance insights
              </p>
            </div>
            <ArrowRight className="w-4 h-4 text-surface-400" />
          </CardBody>
        </Card>
        <Card hover>
          <CardBody className="flex items-center gap-4">
            <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-purple-50 text-purple-600">
              <Users className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-surface-900">
                Manage Team
              </h3>
              <p className="text-xs text-surface-500 mt-0.5">
                Users and permissions
              </p>
            </div>
            <ArrowRight className="w-4 h-4 text-surface-400" />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
