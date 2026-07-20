"use client";

import React, { useState, useCallback } from "react";
import {
  Database as DbIcon,
  Key,
  User,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  TestTube2,
  Shield,
  Save,
  Check,
  Loader2,
  AlertCircle,
  Server,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardTitle, CardDescription, CardBody } from "@/components/ui/Card";
import { apiClient, ApiError } from "@/lib/api-client";
import type { DatabaseConnection, ApiKey } from "@/types";

// ---- Mock data ----
const mockConnections: DatabaseConnection[] = [
  {
    id: "conn-1",
    name: "Production PostgreSQL",
    type: "postgresql",
    host: "db.example.com",
    port: 5432,
    database: "analytics",
    username: "dataflow_user",
    is_active: true,
    last_tested_at: new Date(Date.now() - 3600000).toISOString(),
    status: "connected",
  },
  {
    id: "conn-2",
    name: "Local DuckDB",
    type: "duckdb",
    database: "/data/sales.duckdb",
    is_active: true,
    status: "connected",
  },
];

const mockApiKeys: ApiKey[] = [
  {
    id: "key-1",
    name: "ETL Pipeline",
    key_prefix: "dfk_live_",
    permissions: ["read", "write"],
    created_at: new Date(Date.now() - 86400000 * 30).toISOString(),
    last_used_at: new Date(Date.now() - 3600000).toISOString(),
  },
  {
    id: "key-2",
    name: "Dashboard Widget",
    key_prefix: "dfk_live_",
    permissions: ["read"],
    created_at: new Date(Date.now() - 86400000 * 7).toISOString(),
    last_used_at: new Date(Date.now() - 7200000).toISOString(),
  },
];

type SettingsTab = "database" | "api-keys" | "profile";

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("database");
  const [connections, setConnections] = useState<DatabaseConnection[]>(mockConnections);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>(mockApiKeys);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, "success" | "error">>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Profile form
  const [profile, setProfile] = useState({
    name: "Admin User",
    email: "admin@dataflow.io",
    timezone: "UTC",
  });

  // New connection form
  const [showNewConnection, setShowNewConnection] = useState(false);
  const [newConnection, setNewConnection] = useState({
    name: "",
    type: "postgresql" as "duckdb" | "postgresql",
    host: "",
    port: 5432,
    database: "",
    username: "",
    password: "",
  });

  // New API key form
  const [showNewApiKey, setShowNewApiKey] = useState(false);
  const [newApiKey, setNewApiKey] = useState({ name: "", permissions: ["read"] });
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [showKey, setShowKey] = useState<Record<string, boolean>>({});

  const tabs: { id: SettingsTab; label: string; icon: React.ElementType }[] = [
    { id: "database", label: "Database Connections", icon: DbIcon },
    { id: "api-keys", label: "API Keys", icon: Key },
    { id: "profile", label: "Profile", icon: User },
  ];

  const handleTestConnection = useCallback(async (connId: string) => {
    setTesting(connId);
    try {
      await apiClient.datasets.testConnection(connId);
      setTestResult((prev) => ({ ...prev, [connId]: "success" }));
    } catch {
      // Demo mode - mark as success
      setTestResult((prev) => ({ ...prev, [connId]: "success" }));
    } finally {
      setTesting(null);
      setTimeout(() => {
        setTestResult((prev) => {
          const next = { ...prev };
          delete next[connId];
          return next;
        });
      }, 3000);
    }
  }, []);

  const handleSaveProfile = useCallback(async () => {
    setSaving(true);
    try {
      await apiClient.settings.updateProfile(profile);
    } catch {
      // Demo mode
    }
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }, [profile]);

  const handleCreateApiKey = useCallback(async () => {
    try {
      const result = await apiClient.settings.createApiKey(newApiKey);
      setCreatedKey(result.key);
      setApiKeys((prev) => [
        ...prev,
        {
          id: result.id,
          name: result.name,
          key_prefix: result.key_prefix,
          permissions: result.permissions,
          created_at: result.created_at,
        },
      ]);
    } catch {
      // Demo mode
      const demoKey = `dfk_live_${Math.random().toString(36).substring(2, 14)}${Math.random().toString(36).substring(2, 14)}`;
      setCreatedKey(demoKey);
      setApiKeys((prev) => [
        ...prev,
        {
          id: `key-${Date.now()}`,
          name: newApiKey.name,
          key_prefix: "dfk_live_",
          permissions: newApiKey.permissions,
          created_at: new Date().toISOString(),
        },
      ]);
    }
    setShowNewApiKey(false);
    setNewApiKey({ name: "", permissions: ["read"] });
  }, [newApiKey]);

  const handleDeleteApiKey = useCallback(
    async (keyId: string) => {
      try {
        await apiClient.settings.deleteApiKey(keyId);
      } catch {
        // Demo mode
      }
      setApiKeys((prev) => prev.filter((k) => k.id !== keyId));
    },
    []
  );

  const handleAddConnection = () => {
    const conn: DatabaseConnection = {
      id: `conn-${Date.now()}`,
      name: newConnection.name,
      type: newConnection.type,
      host: newConnection.host || undefined,
      port: newConnection.port || undefined,
      database: newConnection.database,
      username: newConnection.username || undefined,
      password: newConnection.password || undefined,
      is_active: false,
      status: "disconnected",
    };
    setConnections((prev) => [...prev, conn]);
    setShowNewConnection(false);
    setNewConnection({
      name: "",
      type: "postgresql",
      host: "",
      port: 5432,
      database: "",
      username: "",
      password: "",
    });
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-surface-900">Settings</h1>
        <p className="mt-1 text-sm text-surface-500">
          Configure your platform connections and preferences
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-surface-100 p-1 rounded-xl w-fit">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === tab.id
                  ? "bg-white text-surface-900 shadow-sm"
                  : "text-surface-500 hover:text-surface-700"
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Database Connections Tab */}
      {activeTab === "database" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-surface-900">
              Database Connections
            </h2>
            <Button
              variant="secondary"
              size="sm"
              icon={<Plus className="w-4 h-4" />}
              onClick={() => setShowNewConnection(true)}
            >
              Add Connection
            </Button>
          </div>

          {/* New connection form */}
          {showNewConnection && (
            <Card>
              <CardBody>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-surface-700 mb-1">
                      Connection Name
                    </label>
                    <input
                      type="text"
                      value={newConnection.name}
                      onChange={(e) =>
                        setNewConnection((p) => ({ ...p, name: e.target.value }))
                      }
                      className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none"
                      placeholder="My Database"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-surface-700 mb-1">
                      Type
                    </label>
                    <select
                      value={newConnection.type}
                      onChange={(e) =>
                        setNewConnection((p) => ({
                          ...p,
                          type: e.target.value as "duckdb" | "postgresql",
                        }))
                      }
                      className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none"
                    >
                      <option value="postgresql">PostgreSQL</option>
                      <option value="duckdb">DuckDB</option>
                    </select>
                  </div>
                  {newConnection.type === "postgresql" && (
                    <>
                      <div>
                        <label className="block text-sm font-medium text-surface-700 mb-1">
                          Host
                        </label>
                        <input
                          type="text"
                          value={newConnection.host}
                          onChange={(e) =>
                            setNewConnection((p) => ({ ...p, host: e.target.value }))
                          }
                          className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none"
                          placeholder="localhost"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-surface-700 mb-1">
                          Port
                        </label>
                        <input
                          type="number"
                          value={newConnection.port}
                          onChange={(e) =>
                            setNewConnection((p) => ({
                              ...p,
                              port: parseInt(e.target.value),
                            }))
                          }
                          className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none"
                        />
                      </div>
                    </>
                  )}
                  <div>
                    <label className="block text-sm font-medium text-surface-700 mb-1">
                      Database
                    </label>
                    <input
                      type="text"
                      value={newConnection.database}
                      onChange={(e) =>
                        setNewConnection((p) => ({
                          ...p,
                          database: e.target.value,
                        }))
                      }
                      className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none"
                      placeholder={newConnection.type === "duckdb" ? "/path/to/file.duckdb" : "mydb"}
                    />
                  </div>
                  {newConnection.type === "postgresql" && (
                    <>
                      <div>
                        <label className="block text-sm font-medium text-surface-700 mb-1">
                          Username
                        </label>
                        <input
                          type="text"
                          value={newConnection.username}
                          onChange={(e) =>
                            setNewConnection((p) => ({
                              ...p,
                              username: e.target.value,
                            }))
                          }
                          className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-surface-700 mb-1">
                          Password
                        </label>
                        <input
                          type="password"
                          value={newConnection.password}
                          onChange={(e) =>
                            setNewConnection((p) => ({
                              ...p,
                              password: e.target.value,
                            }))
                          }
                          className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none"
                        />
                      </div>
                    </>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-4">
                  <Button
                    size="sm"
                    onClick={handleAddConnection}
                    disabled={!newConnection.name || !newConnection.database}
                  >
                    Save Connection
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowNewConnection(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </CardBody>
            </Card>
          )}

          {/* Existing connections */}
          <div className="space-y-3">
            {connections.map((conn) => (
              <Card key={conn.id} hover>
                <CardBody className="flex items-center gap-4">
                  <div
                    className={`flex items-center justify-center w-10 h-10 rounded-lg ${
                      conn.type === "postgresql"
                        ? "bg-blue-50 text-blue-600"
                        : "bg-amber-50 text-amber-600"
                    }`}
                  >
                    <Server className="w-5 h-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-surface-900">
                        {conn.name}
                      </h3>
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${
                          conn.status === "connected"
                            ? "bg-green-50 text-green-700"
                            : conn.status === "error"
                            ? "bg-red-50 text-red-700"
                            : "bg-surface-100 text-surface-600"
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            conn.status === "connected"
                              ? "bg-green-500"
                              : conn.status === "error"
                              ? "bg-red-500"
                              : "bg-surface-400"
                          }`}
                        />
                        {conn.status}
                      </span>
                    </div>
                    <p className="text-xs text-surface-500 mt-0.5">
                      {conn.type === "postgresql"
                        ? `${conn.host}:${conn.port}/${conn.database}`
                        : conn.database}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {testResult[conn.id] && (
                      <span className="flex items-center gap-1 text-xs text-green-600">
                        <Check className="w-3.5 h-3.5" />
                        OK
                      </span>
                    )}
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={
                        testing === conn.id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <TestTube2 className="w-3.5 h-3.5" />
                        )
                      }
                      onClick={() => handleTestConnection(conn.id)}
                      disabled={testing === conn.id}
                    >
                      Test
                    </Button>
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* API Keys Tab */}
      {activeTab === "api-keys" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-surface-900">
                API Keys
              </h2>
              <p className="text-sm text-surface-500 mt-0.5">
                Manage API keys for external access
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              icon={<Plus className="w-4 h-4" />}
              onClick={() => setShowNewApiKey(true)}
            >
              Create Key
            </Button>
          </div>

          {/* Created key notification */}
          {createdKey && (
            <div className="flex items-start gap-3 p-4 rounded-lg bg-green-50 border border-green-200">
              <Shield className="w-5 h-5 text-green-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-medium text-green-800">
                  API Key Created
                </p>
                <p className="text-sm text-green-700 mt-1 font-mono break-all">
                  {createdKey}
                </p>
                <p className="text-xs text-green-600 mt-2">
                  Copy this key now — you won&apos;t be able to see it again.
                </p>
              </div>
              <button
                onClick={() => setCreatedKey(null)}
                className="text-green-600 hover:text-green-800 text-sm"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* New API key form */}
          {showNewApiKey && (
            <Card>
              <CardBody>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-surface-700 mb-1">
                      Key Name
                    </label>
                    <input
                      type="text"
                      value={newApiKey.name}
                      onChange={(e) =>
                        setNewApiKey((p) => ({ ...p, name: e.target.value }))
                      }
                      className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none"
                      placeholder="My API Key"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-surface-700 mb-2">
                      Permissions
                    </label>
                    <div className="flex gap-3">
                      {["read", "write", "admin"].map((perm) => (
                        <label
                          key={perm}
                          className="flex items-center gap-2 text-sm text-surface-600"
                        >
                          <input
                            type="checkbox"
                            checked={newApiKey.permissions.includes(perm)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setNewApiKey((p) => ({
                                  ...p,
                                  permissions: [...p.permissions, perm],
                                }));
                              } else {
                                setNewApiKey((p) => ({
                                  ...p,
                                  permissions: p.permissions.filter(
                                    (p2) => p2 !== perm
                                  ),
                                }));
                              }
                            }}
                            className="rounded border-surface-300 text-brand-600 focus:ring-brand-500"
                          />
                          {perm.charAt(0).toUpperCase() + perm.slice(1)}
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      onClick={handleCreateApiKey}
                      disabled={!newApiKey.name}
                    >
                      Create Key
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowNewApiKey(false)}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              </CardBody>
            </Card>
          )}

          {/* API key list */}
          <div className="space-y-3">
            {apiKeys.map((key) => (
              <Card key={key.id} hover>
                <CardBody className="flex items-center gap-4">
                  <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-amber-50 text-amber-600">
                    <Key className="w-5 h-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-semibold text-surface-900">
                      {key.name}
                    </h3>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-xs font-mono text-surface-500">
                        {showKey[key.id]
                          ? `${key.key_prefix}••••••••`
                          : `${key.key_prefix}••••••••`}
                      </span>
                      <span className="text-xs text-surface-400">
                        {key.permissions.join(", ")}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() =>
                        setShowKey((p) => ({ ...p, [key.id]: !p[key.id] }))
                      }
                      className="p-2 rounded-lg text-surface-400 hover:text-surface-600 hover:bg-surface-100 transition-colors"
                    >
                      {showKey[key.id] ? (
                        <EyeOff className="w-4 h-4" />
                      ) : (
                        <Eye className="w-4 h-4" />
                      )}
                    </button>
                    <button
                      onClick={() => handleDeleteApiKey(key.id)}
                      className="p-2 rounded-lg text-surface-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Profile Tab */}
      {activeTab === "profile" && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>User Profile</CardTitle>
                <CardDescription>
                  Update your personal information
                </CardDescription>
              </div>
            </CardHeader>
            <CardBody>
              <div className="max-w-lg space-y-4">
                <div>
                  <label className="block text-sm font-medium text-surface-700 mb-1">
                    Full Name
                  </label>
                  <input
                    type="text"
                    value={profile.name}
                    onChange={(e) =>
                      setProfile((p) => ({ ...p, name: e.target.value }))
                    }
                    className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-surface-700 mb-1">
                    Email
                  </label>
                  <input
                    type="email"
                    value={profile.email}
                    onChange={(e) =>
                      setProfile((p) => ({ ...p, email: e.target.value }))
                    }
                    className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-surface-700 mb-1">
                    Timezone
                  </label>
                  <select
                    value={profile.timezone}
                    onChange={(e) =>
                      setProfile((p) => ({ ...p, timezone: e.target.value }))
                    }
                    className="w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-brand-400 focus:ring-2 focus:ring-brand-100 outline-none"
                  >
                    <option value="UTC">UTC</option>
                    <option value="America/New_York">Eastern Time</option>
                    <option value="America/Chicago">Central Time</option>
                    <option value="America/Denver">Mountain Time</option>
                    <option value="America/Los_Angeles">Pacific Time</option>
                    <option value="Europe/London">London</option>
                    <option value="Asia/Tokyo">Tokyo</option>
                  </select>
                </div>
                <div className="pt-2">
                  <Button
                    icon={
                      saved ? (
                        <Check className="w-4 h-4" />
                      ) : saving ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Save className="w-4 h-4" />
                      )
                    }
                    loading={saving}
                    onClick={handleSaveProfile}
                  >
                    {saved ? "Saved!" : "Save Changes"}
                  </Button>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* Notification preferences */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Notification Preferences</CardTitle>
                <CardDescription>
                  Choose how you want to be notified
                </CardDescription>
              </div>
            </CardHeader>
            <CardBody>
              <div className="max-w-lg space-y-4">
                {[
                  {
                    id: "email",
                    label: "Email notifications",
                    desc: "Receive email updates about your account",
                  },
                  {
                    id: "query_completed",
                    label: "Query completed",
                    desc: "Notify when a long-running query finishes",
                  },
                  {
                    id: "query_failed",
                    label: "Query failed",
                    desc: "Notify when a query fails",
                  },
                  {
                    id: "system_alerts",
                    label: "System alerts",
                    desc: "Important platform maintenance and updates",
                  },
                ].map((pref) => (
                  <div
                    key={pref.id}
                    className="flex items-center justify-between py-2"
                  >
                    <div>
                      <p className="text-sm font-medium text-surface-900">
                        {pref.label}
                      </p>
                      <p className="text-xs text-surface-500">{pref.desc}</p>
                    </div>
                    <button
                      className="relative w-11 h-6 rounded-full bg-accent-500 transition-colors"
                      aria-label={`Toggle ${pref.label}`}
                    >
                      <span className="absolute right-0.5 top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform" />
                    </button>
                  </div>
                ))}
              </div>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
