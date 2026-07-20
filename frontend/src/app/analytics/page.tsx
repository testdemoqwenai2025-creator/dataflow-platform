"use client";

import React, { useState, useCallback } from "react";
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

export default function AnalyticsPage() {
  const [datasets] = useState<Dataset[]>(mockDatasets);
  const [selectedDataset, setSelectedDataset] = useState<string>(mockDatasets[0].id);
  const [sql, setSql] = useState(sampleQueries[mockDatasets[0].id]);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"table" | "chart">("table");
  const [copied, setCopied] = useState(false);

  const handleDatasetChange = (datasetId: string) => {
    setSelectedDataset(datasetId);
    if (sampleQueries[datasetId]) {
      setSql(sampleQueries[datasetId]);
    }
    setResult(null);
    setError(null);
  };

  const handleRunQuery = useCallback(async () => {
    if (!sql.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const queryResult = await apiClient.queries.execute({
        dataset_id: selectedDataset,
        sql,
        limit: 100,
      });

      if (queryResult.result) {
        setResult(queryResult.result);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to execute query. Using demo data.");
        setResult(mockResult);
      }
    } finally {
      setLoading(false);
    }
  }, [sql, selectedDataset]);

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
    a.download = "query_results.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleRunDemo = () => {
    setResult(mockResult);
    setError(null);
  };

  return (
    <div className="space-y-6 animate-fade-in">
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
                    {(datasets.find((d) => d.id === selectedDataset)?.size_bytes ?? 0 / 1024 / 1024).toFixed(1)} MB
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
                  icon={<RefreshCw className="w-3.5 h-3.5" />}
                  onClick={handleRunDemo}
                >
                  Demo
                </Button>
              </div>
            </CardBody>
          </Card>
        </div>

        {/* Results Panel */}
        <div className="xl:col-span-2">
          <Card className="h-full">
            <CardHeader
              action={
                result && (
                  <div className="flex items-center gap-2">
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
                  </div>
                )
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
                  <div className="px-4 py-3 border-t border-surface-200 bg-surface-50 text-xs text-surface-500">
                    {result.row_count} row{result.row_count !== 1 ? "s" : ""}
                    {result.truncated && " (truncated)"}
                  </div>
                </div>
              )}

              {!loading && result && activeTab === "chart" && (
                <div className="p-6">
                  {result.rows.length > 0 && result.columns.length >= 2 ? (
                    <div className="h-80">
                      {/* Chart using SVG (since recharts needs dynamic import in production) */}
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
