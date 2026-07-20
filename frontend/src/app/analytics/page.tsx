"use client";

import React, { useState, useCallback, useEffect } from "react";
import {
  Play,
  Download,
  Table,
  BarChart3,
  RefreshCw,
  Copy,
  Check,
  ChevronDown,
  Loader2,
  AlertCircle,
  Save,
  Clock,
  Bookmark,
  X,
  Info,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardTitle, CardBody } from "@/components/ui/Card";
import { apiClient, ApiError } from "@/lib/api-client";
import type { Dataset, QueryResult } from "@/types";

// ---- Mock datasets for demo ----
const mockDatasets: Dataset[] = [
  {
    id: "ds-1",
    name: "Sales Data",
    source_type: "postgresql",
    row_count: 150000,
    size_bytes: 45000000,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "ds-2",
    name: "User Analytics",
    source_type: "duckdb",
    row_count: 89000,
    size_bytes: 22000000,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "ds-3",
    name: "Product Catalog",
    source_type: "csv",
    row_count: 5200,
    size_bytes: 1800000,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

const sampleQueries: Record<string, string> = {
  "ds-1": "SELECT date, SUM(revenue) as total_revenue, COUNT(*) as orders FROM sales GROUP BY date ORDER BY date DESC LIMIT 100",
  "ds-2": "SELECT user_id, COUNT(*) as events, AVG(duration) as avg_duration FROM analytics GROUP BY user_id LIMIT 50",
  "ds-3": "SELECT category, COUNT(*) as products, AVG(price) as avg_price FROM products GROUP BY category",
};

const mockResult: QueryResult = {
  columns: ["date", "total_revenue", "orders"],
  rows: [
    { date: "2024-12-01", total_revenue: 45230, orders: 156 },
    { date: "2024-11-30", total_revenue: 38920, orders: 132 },
    { date: "2024-11-29", total_revenue: 52100, orders: 178 },
    { date: "2024-11-28", total_revenue: 31450, orders: 108 },
    { date: "2024-11-27", total_revenue: 42800, orders: 145 },
    { date: "2024-11-26", total_revenue: 39750, orders: 135 },
    { date: "2024-11-25", total_revenue: 48200, orders: 162 },
  ],
  row_count: 7,
  truncated: false,
};

// ---- Saved query type ----
interface SavedQuery {
  id: string;
  name: string;
  sql: string;
  dataset_id: string;
  saved_at: string;
}

// ---- Toast notification ----
interface Toast {
  id: string;
  message: string;
  type: "success" | "error" | "info";
}

export default function AnalyticsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>(mockDatasets);
  const [selectedDataset, setSelectedDataset] = useState<string>(mockDatasets[0].id);
  const [sql, setSql] = useState(sampleQueries[mockDatasets[0].id]);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"table" | "chart">("table");
  const [copied, setCopied] = useState(false);
  const [executionTimeMs, setExecutionTimeMs] = useState<number | null>(null);
  const [savedQueries, setSavedQueries] = useState<SavedQuery[]>([]);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [saveQueryName, setSaveQueryName] = useState("");
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Fetch real datasets on mount
  useEffect(() => {
    async function fetchDatasets() {
      try {
        const result = await apiClient.datasets.list();
        if (Array.isArray(result)) {
          setDatasets(result);
        }
      } catch {
        // Use mock datasets when backend is unavailable
        console.warn("Backend unavailable, using mock datasets");
      }
    }
    fetchDatasets();
  }, []);

  // Toast helpers
  const addToast = useCallback((message: string, type: Toast["type"] = "info") => {
    const id = `toast-${Date.now()}`;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const handleDatasetChange = (datasetId: string) => {
    setSelectedDataset(datasetId);
    if (sampleQueries[datasetId]) {
      setSql(sampleQueries[datasetId]);
    }
    setResult(null);
    setError(null);
    setExecutionTimeMs(null);
  };

  const handleRunQuery = useCallback(async () => {
    if (!sql.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setExecutionTimeMs(null);

    const startTime = performance.now();

    try {
      const queryResult = await apiClient.queries.execute({
        dataset_id: selectedDataset,
        sql,
        limit: 100,
      });

      const elapsed = Math.round(performance.now() - startTime);
      setExecutionTimeMs(queryResult.duration_ms || elapsed);

      if (queryResult.result) {
        setResult(queryResult.result);
        addToast(`Query executed successfully (${queryResult.rows_affected ?? queryResult.result.row_count} rows)`, "success");
      }
    } catch (err) {
      const elapsed = Math.round(performance.now() - startTime);
      setExecutionTimeMs(elapsed);

      if (err instanceof ApiError) {
        // Provide user-friendly error messages based on error codes
        let userMessage = err.message;
        if (err.code === "NETWORK_ERROR") {
          userMessage = "Unable to connect to the server. Please check your network connection and try again.";
        } else if (err.status === 400) {
          userMessage = `Invalid query: ${err.message}`;
        } else if (err.status === 401) {
          userMessage = "Your session has expired. Please sign in again.";
        } else if (err.status === 403) {
          userMessage = "You don't have permission to query this dataset.";
        } else if (err.status === 404) {
          userMessage = "The selected dataset was not found. It may have been deleted.";
        } else if (err.status === 429) {
          userMessage = "Too many requests. Please wait a moment and try again.";
        } else if (err.status && err.status >= 500) {
          userMessage = "The server encountered an error. Please try again later.";
        }
        setError(userMessage);
        addToast(userMessage, "error");
      } else {
        setError("Failed to execute query. The backend may be unavailable — try Demo mode to see sample results.");
        addToast("Query execution failed", "error");
      }
    } finally {
      setLoading(false);
    }
  }, [sql, selectedDataset, addToast]);

  const handleCopySQL = () => {
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleExport = () => {
    if (!result) return;
    const csv = [
      result.columns.join(","),
      ...result.rows.map((row) =>
        result.columns.map((col) => JSON.stringify(row[col] ?? "")).join(",")
      ),
    ].join("\n");

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `query_results_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    addToast("CSV exported successfully", "success");
  };

  const handleRunDemo = () => {
    setResult(mockResult);
    setError(null);
    setExecutionTimeMs(42);
  };

  const handleSaveQuery = () => {
    if (!sql.trim()) return;
    setShowSaveDialog(true);
    setSaveQueryName("");
  };

  const confirmSaveQuery = () => {
    const name = saveQueryName.trim() || `Query ${savedQueries.length + 1}`;
    const saved: SavedQuery = {
      id: `sq-${Date.now()}`,
      name,
      sql,
      dataset_id: selectedDataset,
      saved_at: new Date().toISOString(),
    };
    setSavedQueries((prev) => [saved, ...prev]);
    setShowSaveDialog(false);
    setSaveQueryName("");
    addToast(`Query "${name}" saved`, "success");
  };

  const loadSavedQuery = (sq: SavedQuery) => {
    setSql(sq.sql);
    setSelectedDataset(sq.dataset_id);
    setResult(null);
    setError(null);
    setExecutionTimeMs(null);
    addToast(`Loaded query "${sq.name}"`, "info");
  };

  const deleteSavedQuery = (id: string) => {
    setSavedQueries((prev) => prev.filter((q) => q.id !== id));
    addToast("Query removed from saved", "info");
  };

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
      <div>
        <h1 className="text-2xl font-bold text-surface-900">Analytics</h1>
        <p className="mt-1 text-sm text-surface-500">
          Query and analyze your datasets
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Query Editor Panel */}
        <div className="xl:col-span-1 space-y-4">
          {/* Dataset selector */}
          <Card>
            <CardHeader>
              <CardTitle>Dataset</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="relative">
                <select
                  value={selectedDataset}
                  onChange={(e) => handleDatasetChange(e.target.value)}
                  className="w-full appearance-none rounded-lg border border-surface-200 bg-white px-3 py-2.5 pr-10 text-sm text-surface-900 focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none transition-all"
                >
                  {datasets.map((ds) => (
                    <option key={ds.id} value={ds.id}>
                      {ds.name} ({ds.row_count.toLocaleString()} rows)
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400 pointer-events-none" />
              </div>
              {datasets.find((d) => d.id === selectedDataset) && (
                <div className="mt-3 flex items-center gap-2">
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-brand-50 text-brand-700">
                    {datasets.find((d) => d.id === selectedDataset)?.source_type}
                  </span>
                  <span className="text-xs text-surface-500">
                    {((datasets.find((d) => d.id === selectedDataset)?.size_bytes ?? 0) / 1024 / 1024).toFixed(1)} MB
                  </span>
                </div>
              )}
            </CardBody>
          </Card>

          {/* SQL Editor */}
          <Card>
            <CardHeader
              action={
                <button
                  onClick={handleCopySQL}
                  className="flex items-center gap-1 text-xs text-surface-500 hover:text-surface-700 transition-colors"
                >
                  {copied ? (
                    <Check className="w-3.5 h-3.5 text-green-600" />
                  ) : (
                    <Copy className="w-3.5 h-3.5" />
                  )}
                  {copied ? "Copied" : "Copy"}
                </button>
              }
            >
              <CardTitle>SQL Query</CardTitle>
            </CardHeader>
            <CardBody>
              <textarea
                value={sql}
                onChange={(e) => setSql(e.target.value)}
                placeholder="SELECT * FROM ..."
                className="sql-editor w-full h-48 px-3 py-2 text-sm rounded-lg border border-surface-200 bg-surface-50 text-surface-900 placeholder:text-surface-400 resize-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition-all"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    handleRunQuery();
                  }
                }}
              />
              <div className="flex items-center gap-2 mt-3">
                <Button
                  icon={<Play className="w-3.5 h-3.5" />}
                  loading={loading}
                  onClick={handleRunQuery}
                  disabled={!sql.trim()}
                  className="flex-1"
                >
                  Execute
                </Button>
                <Button
                  variant="secondary"
                  icon={<Bookmark className="w-3.5 h-3.5" />}
                  onClick={handleSaveQuery}
                  disabled={!sql.trim()}
                >
                  Save
                </Button>
                <Button
                  variant="secondary"
                  icon={<RefreshCw className="w-3.5 h-3.5" />}
                  onClick={handleRunDemo}
                >
                  Demo
                </Button>
              </div>

              {/* Save dialog */}
              {showSaveDialog && (
                <div className="mt-3 p-3 rounded-lg border border-surface-200 bg-surface-50 space-y-2">
                  <label className="block text-xs font-medium text-surface-700">
                    Query Name
                  </label>
                  <input
                    type="text"
                    value={saveQueryName}
                    onChange={(e) => setSaveQueryName(e.target.value)}
                    placeholder="My saved query..."
                    className="w-full rounded-md border border-surface-200 px-3 py-1.5 text-sm focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") confirmSaveQuery();
                    }}
                  />
                  <div className="flex items-center gap-2">
                    <Button size="sm" icon={<Save className="w-3 h-3" />} onClick={confirmSaveQuery}>
                      Save
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setShowSaveDialog(false)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </CardBody>
          </Card>

          {/* Saved Queries */}
          {savedQueries.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Saved Queries</CardTitle>
              </CardHeader>
              <CardBody noPadding>
                <div className="divide-y divide-surface-100">
                  {savedQueries.map((sq) => (
                    <div
                      key={sq.id}
                      className="flex items-center gap-3 px-4 py-3 hover:bg-surface-50 transition-colors group"
                    >
                      <Bookmark className="w-4 h-4 text-brand-500 shrink-0" />
                      <div className="flex-1 min-w-0 cursor-pointer" onClick={() => loadSavedQuery(sq)}>
                        <p className="text-sm font-medium text-surface-900 truncate">
                          {sq.name}
                        </p>
                        <p className="text-xs text-surface-500 truncate font-mono">
                          {sq.sql.substring(0, 60)}{sq.sql.length > 60 ? "..." : ""}
                        </p>
                      </div>
                      <button
                        onClick={() => deleteSavedQuery(sq.id)}
                        className="p-1 rounded text-surface-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </CardBody>
            </Card>
          )}
        </div>

        {/* Results Panel */}
        <div className="xl:col-span-2">
          <Card className="h-full">
            <CardHeader
              action={
                <div className="flex items-center gap-2">
                  {/* Execution time badge */}
                  {executionTimeMs !== null && !loading && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-surface-100 text-surface-600">
                      <Clock className="w-3 h-3" />
                      {executionTimeMs < 1000
                        ? `${executionTimeMs}ms`
                        : `${(executionTimeMs / 1000).toFixed(2)}s`}
                    </span>
                  )}
                  {result && (
                    <>
                      <div className="flex items-center bg-surface-100 rounded-lg p-0.5">
                        <button
                          onClick={() => setActiveTab("table")}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                            activeTab === "table"
                              ? "bg-white text-surface-900 shadow-sm"
                              : "text-surface-500 hover:text-surface-700"
                          }`}
                        >
                          <Table className="w-3.5 h-3.5" />
                          Table
                        </button>
                        <button
                          onClick={() => setActiveTab("chart")}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                            activeTab === "chart"
                              ? "bg-white text-surface-900 shadow-sm"
                              : "text-surface-500 hover:text-surface-700"
                          }`}
                        >
                          <BarChart3 className="w-3.5 h-3.5" />
                          Chart
                        </button>
                      </div>
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={<Download className="w-3.5 h-3.5" />}
                        onClick={handleExport}
                      >
                        Export CSV
                      </Button>
                    </>
                  )}
                </div>
              }
            >
              <CardTitle>Results</CardTitle>
            </CardHeader>
            <CardBody noPadding>
              {loading && (
                <div className="flex flex-col items-center justify-center py-20">
                  <Loader2 className="w-8 h-8 text-brand-500 animate-spin" />
                  <p className="mt-3 text-sm text-surface-500">
                    Executing query...
                  </p>
                  <p className="text-xs text-surface-400 mt-1">
                    This may take a moment for large datasets
                  </p>
                </div>
              )}

              {error && !loading && (
                <div className="px-6 py-8">
                  <div className="flex items-start gap-3 p-4 rounded-lg bg-red-50 border border-red-100">
                    <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-red-800">
                        Query Error
                      </p>
                      <p className="text-sm text-red-600 mt-1">{error}</p>
                      <button
                        onClick={handleRunDemo}
                        className="mt-2 text-xs font-medium text-red-700 hover:text-red-800 underline"
                      >
                        Try Demo Mode instead
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {!loading && !error && !result && (
                <div className="flex flex-col items-center justify-center py-20 text-center">
                  <Table className="w-12 h-12 text-surface-300 mb-4" />
                  <p className="text-sm text-surface-500">
                    Run a query to see results
                  </p>
                  <p className="text-xs text-surface-400 mt-1">
                    Select a dataset, write SQL, and click Execute
                  </p>
                  <p className="text-xs text-surface-400 mt-1">
                    Press <kbd className="px-1.5 py-0.5 rounded bg-surface-100 text-surface-600 font-mono text-[10px]">⌘+Enter</kbd> to run
                  </p>
                </div>
              )}

              {!loading && result && activeTab === "table" && (
                <div className="overflow-x-auto">
                  <table className="w-full data-table">
                    <thead>
                      <tr className="border-b border-surface-200 bg-surface-50">
                        {result.columns.map((col) => (
                          <th
                            key={col}
                            className="px-4 py-3 text-left whitespace-nowrap"
                          >
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-100">
                      {result.rows.map((row, i) => (
                        <tr
                          key={i}
                          className="hover:bg-surface-50 transition-colors"
                        >
                          {result.columns.map((col) => (
                            <td
                              key={col}
                              className="px-4 py-2.5 whitespace-nowrap text-surface-700"
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
                  <div className="flex items-center justify-between px-4 py-3 border-t border-surface-200 bg-surface-50 text-xs text-surface-500">
                    <span>
                      {result.row_count} row{result.row_count !== 1 ? "s" : ""}
                      {result.truncated && " (truncated)"}
                    </span>
                    {executionTimeMs !== null && (
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        Executed in {executionTimeMs < 1000 ? `${executionTimeMs}ms` : `${(executionTimeMs / 1000).toFixed(2)}s`}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {!loading && result && activeTab === "chart" && (
                <div className="p-6">
                  {result.rows.length > 0 && result.columns.length >= 2 ? (
                    <div className="h-80">
                      {(() => {
                        const labelCol = result.columns[0];
                        const valueCols = result.columns.slice(1).filter((col) =>
                          result.rows.every((row) => typeof row[col] === "number")
                        );

                        if (valueCols.length === 0) {
                          return (
                            <div className="flex items-center justify-center h-full">
                              <p className="text-sm text-surface-500">
                                No numeric columns to chart
                              </p>
                            </div>
                          );
                        }

                        const valueCol = valueCols[0];
                        const values = result.rows.map(
                          (row) => (row[valueCol] as number) || 0
                        );
                        const maxVal = Math.max(...values);
                        const minVal = Math.min(...values);
                        const range = maxVal - minVal || 1;
                        const barWidth = 100 / result.rows.length;

                        return (
                          <svg
                            viewBox="0 0 100 50"
                            className="w-full h-full"
                            preserveAspectRatio="xMidYMid meet"
                          >
                            {result.rows.map((row, i) => {
                              const val = (row[valueCol] as number) || 0;
                              const height =
                                ((val - minVal) / range) * 40 + 2;
                              const x = i * barWidth + barWidth * 0.1;
                              const w = barWidth * 0.8;
                              const y = 48 - height;

                              return (
                                <g key={i}>
                                  <rect
                                    x={x}
                                    y={y}
                                    width={w}
                                    height={height}
                                    rx="0.5"
                                    fill="url(#chartGradient)"
                                    className="hover:opacity-80 transition-opacity cursor-pointer"
                                  />
                                  <text
                                    x={x + w / 2}
                                    y={49}
                                    textAnchor="middle"
                                    fill="#94a3b8"
                                    fontSize="1.2"
                                  >
                                    {String(row[labelCol] || "").substring(0, 8)}
                                  </text>
                                </g>
                              );
                            })}
                            <defs>
                              <linearGradient
                                id="chartGradient"
                                x1="0%"
                                y1="0%"
                                x2="0%"
                                y2="100%"
                              >
                                <stop
                                  offset="0%"
                                  stopColor="#08c4b3"
                                  stopOpacity="1"
                                />
                                <stop
                                  offset="100%"
                                  stopColor="#4a6faf"
                                  stopOpacity="1"
                                />
                              </linearGradient>
                            </defs>
                          </svg>
                        );
                      })()}
                    </div>
                  ) : (
                    <div className="flex items-center justify-center h-40">
                      <p className="text-sm text-surface-500">
                        No data to chart
                      </p>
                    </div>
                  )}
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
