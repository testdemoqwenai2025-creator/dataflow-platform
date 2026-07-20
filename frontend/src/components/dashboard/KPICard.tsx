"use client";

import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

export interface KPICardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  trend?: {
    direction: "up" | "down" | "stable";
    percentage: number;
  };
  sparklineData?: number[];
  className?: string;
}

export function KPICard({
  label,
  value,
  icon,
  trend,
  sparklineData,
  className,
}: KPICardProps) {
  return (
    <div
      className={cn(
        "rounded-xl bg-white border border-surface-200 p-5 shadow-sm",
        "hover:shadow-md transition-shadow duration-200",
        className
      )}
    >
      <div className="flex items-start justify-between">
        {/* Icon */}
        <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-brand-50 text-brand-600">
          {icon}
        </div>

        {/* Trend indicator */}
        {trend && trend.direction !== "stable" && (
          <div
            className={cn(
              "flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium",
              trend.direction === "up"
                ? "bg-green-50 text-green-700"
                : "bg-red-50 text-red-700"
            )}
          >
            {trend.direction === "up" ? (
              <TrendingUp className="w-3 h-3" />
            ) : (
              <TrendingDown className="w-3 h-3" />
            )}
            <span>{Math.abs(trend.percentage)}%</span>
          </div>
        )}
        {trend && trend.direction === "stable" && (
          <div className="flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-surface-100 text-surface-600">
            <Minus className="w-3 h-3" />
            <span>0%</span>
          </div>
        )}
      </div>

      {/* Value & label */}
      <div className="mt-3">
        <p className="text-2xl font-bold text-surface-900 tracking-tight">
          {typeof value === "number" ? value.toLocaleString() : value}
        </p>
        <p className="mt-1 text-sm text-surface-500">{label}</p>
      </div>

      {/* Sparkline */}
      {sparklineData && sparklineData.length > 0 && (
        <div className="mt-3 h-8">
          <svg
            viewBox="0 0 100 30"
            className="w-full h-full"
            preserveAspectRatio="none"
          >
            <defs>
              <linearGradient id={`spark-${label}`} x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="rgb(8, 196, 179)" stopOpacity="0.3" />
                <stop offset="100%" stopColor="rgb(8, 196, 179)" stopOpacity="0" />
              </linearGradient>
            </defs>
            {(() => {
              const max = Math.max(...sparklineData);
              const min = Math.min(...sparklineData);
              const range = max - min || 1;
              const step = 100 / (sparklineData.length - 1);

              const points = sparklineData
                .map((val, i) => `${i * step},${30 - ((val - min) / range) * 28}`)
                .join(" ");

              const areaPoints = `0,30 ${points} 100,30`;

              return (
                <>
                  <polygon
                    points={areaPoints}
                    fill={`url(#spark-${label})`}
                  />
                  <polyline
                    points={points}
                    fill="none"
                    stroke="rgb(8, 196, 179)"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </>
              );
            })()}
          </svg>
        </div>
      )}
    </div>
  );
}
