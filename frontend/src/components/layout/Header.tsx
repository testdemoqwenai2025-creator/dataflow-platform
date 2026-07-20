"use client";

import React, { useState, useRef, useEffect } from "react";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  Search,
  Bell,
  ChevronRight,
  User,
  LogOut,
  Settings,
  HelpCircle,
} from "lucide-react";

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

// ---- Breadcrumb helper ----
function getBreadcrumbs(pathname: string): { label: string; href: string }[] {
  const crumbs = [{ label: "Home", href: "/dashboard" }];

  if (pathname === "/") return crumbs;

  const segments = pathname.split("/").filter(Boolean);
  let currentPath = "";

  for (const segment of segments) {
    currentPath += `/${segment}`;
    crumbs.push({
      label: segment.charAt(0).toUpperCase() + segment.slice(1),
      href: currentPath,
    });
  }

  return crumbs;
}

export function Header() {
  const pathname = usePathname();
  const breadcrumbs = getBreadcrumbs(pathname || "");
  const [searchFocused, setSearchFocused] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  // Close menus on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        userMenuRef.current &&
        !userMenuRef.current.contains(e.target as Node)
      ) {
        setShowUserMenu(false);
      }
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifications(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const notifications = [
    { id: 1, title: "Query completed", message: "Your long-running query has finished", time: "2m ago", read: false },
    { id: 2, title: "Dataset updated", message: "Sales data has been refreshed", time: "1h ago", read: false },
    { id: 3, title: "System update", message: "Platform maintenance scheduled", time: "3h ago", read: true },
  ];

  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <header className="flex items-center justify-between h-16 px-6 bg-white border-b border-surface-200">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm" aria-label="Breadcrumb">
        {breadcrumbs.map((crumb, index) => (
          <React.Fragment key={crumb.href}>
            {index > 0 && (
              <ChevronRight className="w-3.5 h-3.5 text-surface-400" />
            )}
            <span
              className={cn(
                "transition-colors",
                index === breadcrumbs.length - 1
                  ? "text-surface-900 font-medium"
                  : "text-surface-500 hover:text-surface-700"
              )}
            >
              {crumb.label}
            </span>
          </React.Fragment>
        ))}
      </nav>

      {/* Search bar */}
      <div className="flex-1 max-w-md mx-8">
        <div
          className={cn(
            "flex items-center gap-2 px-3 py-2 rounded-lg border transition-all duration-200",
            searchFocused
              ? "border-brand-400 ring-2 ring-brand-100 bg-white"
              : "border-surface-200 bg-surface-50"
          )}
        >
          <Search className="w-4 h-4 text-surface-400 shrink-0" />
          <input
            type="text"
            placeholder="Search queries, datasets..."
            className="flex-1 bg-transparent text-sm text-surface-900 placeholder:text-surface-400 outline-none"
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
          />
          <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono text-surface-400 bg-surface-100 rounded border border-surface-200">
            ⌘K
          </kbd>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {/* Notification bell */}
        <div ref={notifRef} className="relative">
          <button
            onClick={() => {
              setShowNotifications(!showNotifications);
              setShowUserMenu(false);
            }}
            className="relative flex items-center justify-center w-10 h-10 rounded-lg text-surface-500 hover:bg-surface-100 hover:text-surface-700 transition-colors"
            aria-label="Notifications"
          >
            <Bell className="w-5 h-5" />
            {unreadCount > 0 && (
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full" />
            )}
          </button>

          {/* Notification dropdown */}
          {showNotifications && (
            <div className="absolute right-0 top-12 w-80 bg-white rounded-xl shadow-lg border border-surface-200 z-50 animate-fade-in">
              <div className="px-4 py-3 border-b border-surface-200">
                <h3 className="text-sm font-semibold text-surface-900">
                  Notifications
                </h3>
              </div>
              <div className="max-h-80 overflow-y-auto scrollbar-thin">
                {notifications.map((notif) => (
                  <div
                    key={notif.id}
                    className={cn(
                      "px-4 py-3 border-b border-surface-100 hover:bg-surface-50 transition-colors cursor-pointer",
                      !notif.read && "bg-accent-50/30"
                    )}
                  >
                    <div className="flex items-start gap-2">
                      {!notif.read && (
                        <div className="w-2 h-2 mt-1.5 rounded-full bg-accent-500 shrink-0" />
                      )}
                      <div className={!notif.read ? "" : "ml-4"}>
                        <p className="text-sm font-medium text-surface-900">
                          {notif.title}
                        </p>
                        <p className="text-xs text-surface-500 mt-0.5">
                          {notif.message}
                        </p>
                        <p className="text-xs text-surface-400 mt-1">
                          {notif.time}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="px-4 py-2 border-t border-surface-200">
                <button className="text-xs text-brand-600 hover:text-brand-700 font-medium">
                  View all notifications
                </button>
              </div>
            </div>
          )}
        </div>

        {/* User menu */}
        <div ref={userMenuRef} className="relative">
          <button
            onClick={() => {
              setShowUserMenu(!showUserMenu);
              setShowNotifications(false);
            }}
            className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-surface-100 transition-colors"
          >
            <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center">
              <User className="w-4 h-4 text-white" />
            </div>
            <span className="hidden sm:block text-sm font-medium text-surface-700">
              Admin
            </span>
          </button>

          {/* User dropdown */}
          {showUserMenu && (
            <div className="absolute right-0 top-12 w-56 bg-white rounded-xl shadow-lg border border-surface-200 z-50 animate-fade-in">
              <div className="px-4 py-3 border-b border-surface-200">
                <p className="text-sm font-medium text-surface-900">
                  Admin User
                </p>
                <p className="text-xs text-surface-500">admin@dataflow.io</p>
              </div>
              <div className="py-1">
                <button className="flex items-center gap-3 w-full px-4 py-2 text-sm text-surface-700 hover:bg-surface-50 transition-colors">
                  <User className="w-4 h-4" />
                  Profile
                </button>
                <button className="flex items-center gap-3 w-full px-4 py-2 text-sm text-surface-700 hover:bg-surface-50 transition-colors">
                  <Settings className="w-4 h-4" />
                  Settings
                </button>
                <button className="flex items-center gap-3 w-full px-4 py-2 text-sm text-surface-700 hover:bg-surface-50 transition-colors">
                  <HelpCircle className="w-4 h-4" />
                  Help
                </button>
              </div>
              <div className="border-t border-surface-200 py-1">
                <button className="flex items-center gap-3 w-full px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors">
                  <LogOut className="w-4 h-4" />
                  Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
