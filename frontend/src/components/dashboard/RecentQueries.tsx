"use client";

import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { Clock, CheckCircle2, XCircle, Loader2, Ban } from "lucide-react";
import type { Query, QueryStatus } from "@/types";

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

interface RecentQueriesProps {
  queries: Query[];
  loading?: boolean;
}

const statusConfig: Record<
  QueryStatus,
  { label: string; icon: React.ElementType; className: string }
> = {
  completed: {
    label: "Completed",
    icon: CheckCircle2,
    className: "text-green-600 bg-green-50",
  },
  running: {
    label: "Running",
    icon: Loader2,
    className: "text-blue-600 bg-blue-50",
  },
  pending: {
    label: "Pending",
    icon: Clock,
    className: "text-yellow-600 bg-yellow-50",
  },
  failed: {
    label: "Failed",
    icon: XCircle,
    className: "text-red-600 bg-red-50",
  },
  cancelled: {
    label: "Cancelled",
    icon: Ban,
    className: "text-surface-500 bg-surface-100",
  },
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function formatTimeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${diffDay}d ago`;
}

function truncateSQL(sql: string, maxLength: number = 80): string {
  if (sql.length <= maxLength) return sql;
  return sql.substring(0, maxLength) + "...";
}

export function RecentQueries({ queries, loading = false }: RecentQueriesProps) {
  if (loading) {
    return (
      <div className="rounded-xl bg-white border border-surface-200 shadow-sm">
        <div className="px-6 py-4 border-b border-surface-200">
          <h3 className="text-base font-semibold text-surface-900">
            Recent Queries
          </h3>
        </div>
        <div className="divide-y divide-surface-100">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="px-6 py-3">
              <div className="flex items-center gap-4">
                <div className="skeleton h-5 w-20 rounded" />
                <div className="skeleton h-5 flex-1 rounded" />
                <div className="skeleton h-5 w-16 rounded" />
                <div className="skeleton h-5 w-20 rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-white border border-surface-200 shadow-sm">
      <div className="flex items-center justify-between px-6 py-4 border-b border-surface-200">
        <h3 className="text-base font-semibold text-surface-900">
          Recent Queries
        </h3>
        <button className="text-sm text-brand-600 hover:text-brand-700 font-medium transition-colors">
          View all
        </button>
      </div>

      {queries.length === 0 ? (
        <div className="px-6 py-12 text-center">
          <Clock className="w-10 h-10 text-surface-300 mx-auto mb-3" />
          <p className="text-sm text-surface-500">No queries yet</p>
          <p className="text-xs text-surface-400 mt-1">
            Run your first query to see results here
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full data-table">
            <thead>
              <tr className="border-b border-surface-200">
                <th className="px-6 py-3 text-left">Status</th>
                <th className="px-6 py-3 text-left">Query</th>
                <th className="px-6 py-3 text-right">Duration</th>
                <th className="px-6 py-3 text-right">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-100">
              {queries.map((query) => {
                const status = statusConfig[query.status];
                const StatusIcon = status.icon;

                return (
                  <tr
                    key={query.id}
                    className="hover:bg-surface-50 transition-colors cursor-pointer"
                  >
                    <td className="px-6 py-3">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium",
                          status.className
                        )}
                      >
                        <StatusIcon
                          className={cn(
                            "w-3 h-3",
                            query.status === "running" && "animate-spin"
                          )}
                        />
                        {status.label}
                      </span>
                    </td>
                    <td className="px-6 py-3">
                      <code className="text-sm text-surface-700 font-mono">
                        {truncateSQL(query.sql)}
                      </code>
                    </td>
                    <td className="px-6 py-3 text-right">
                      <span className="text-sm text-surface-600">
                        {query.duration_ms
                          ? formatDuration(query.duration_ms)
                          : "—"}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-right">
                      <span className="text-sm text-surface-500">
                        {query.created_at
                          ? formatTimeAgo(query.created_at)
                          : "—"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
