-- ============================================================================
-- DataFlow Platform — Initial Database Schema
-- ============================================================================
-- This script creates the PostgreSQL tables for transactional data.
-- DuckDB handles analytical workloads separately (no migration needed —
-- tables are created on-the-fly when datasets are uploaded).
--
-- Tables:
--   1. users         — User accounts and authentication
--   2. datasets      — Dataset metadata and lineage
--   3. queries       — Query execution history and audit trail
--   4. dashboards    — Dashboard configurations
--   5. audit_log     — System-wide audit trail
-- ============================================================================

-- ── Extensions ────────────────────────────────────────────────────────────
-- UUID generation (if not already available)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Users Table ───────────────────────────────────────────────────────────
-- Stores user accounts with bcrypt-hashed passwords.
-- Email and username must be unique for login identification.
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    username        VARCHAR(50)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,          -- bcrypt hash
    full_name       VARCHAR(200),
    avatar_url      VARCHAR(500),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    is_superuser    BOOLEAN      NOT NULL DEFAULT FALSE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
);

-- Indexes for common lookups
CREATE INDEX IF NOT EXISTS idx_users_email    ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);
CREATE INDEX IF NOT EXISTS idx_users_active   ON users (is_active) WHERE is_active = TRUE;

-- ── Datasets Table ────────────────────────────────────────────────────────
-- Tracks metadata for datasets loaded into DuckDB.
-- The table_name field references the DuckDB table where data is stored.
CREATE TABLE IF NOT EXISTS datasets (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    table_name      VARCHAR(200) NOT NULL UNIQUE,    -- DuckDB table name
    source_file     VARCHAR(500),                      -- Original file path
    file_format     VARCHAR(20)  DEFAULT 'csv',        -- csv, parquet, json, tsv
    file_size_bytes BIGINT,
    row_count       INTEGER      DEFAULT 0,
    column_count    INTEGER      DEFAULT 0,
    columns_meta    JSONB        DEFAULT '[]'::jsonb,  -- Column names and types
    tags            JSONB        DEFAULT '[]'::jsonb,  -- Categorisation tags
    owner_id        INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    is_public       BOOLEAN      DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_datasets_owner      ON datasets (owner_id);
CREATE INDEX IF NOT EXISTS idx_datasets_table_name ON datasets (table_name);
CREATE INDEX IF NOT EXISTS idx_datasets_name       ON datasets (name);
CREATE INDEX IF NOT EXISTS idx_datasets_tags       ON datasets USING gin (tags);

-- ── Queries Table ─────────────────────────────────────────────────────────
-- Records every SQL query executed by users for audit and reproducibility.
-- Stores both the query text and result metadata (never full results —
-- those can be large).
CREATE TABLE IF NOT EXISTS queries (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    dataset_id          INTEGER      REFERENCES datasets(id) ON DELETE SET NULL,
    sql_text            TEXT         NOT NULL,
    query_type          VARCHAR(20)  DEFAULT 'select',      -- select, aggregate, pivot
    status              VARCHAR(20)  DEFAULT 'pending',      -- pending, running, completed, failed
    row_count           INTEGER,
    execution_time_ms   REAL,
    error_message       TEXT,
    result_columns      JSONB        DEFAULT '[]'::jsonb,
    truncated           BOOLEAN      DEFAULT FALSE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_queries_user    ON queries (user_id);
CREATE INDEX IF NOT EXISTS idx_queries_dataset ON queries (dataset_id);
CREATE INDEX IF NOT EXISTS idx_queries_status  ON queries (status);
CREATE INDEX IF NOT EXISTS idx_queries_created ON queries (created_at DESC);

-- ── Dashboards Table ──────────────────────────────────────────────────────
-- Stores dashboard configurations as JSON.
-- The widgets JSON contains the full layout and configuration for each
-- dashboard widget (charts, tables, metrics, text blocks).
CREATE TABLE IF NOT EXISTS dashboards (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    owner_id        INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    widgets         JSONB        NOT NULL DEFAULT '[]'::jsonb,
    layout          JSONB        DEFAULT '{}'::jsonb,
    filters         JSONB        DEFAULT '{}'::jsonb,
    is_public       BOOLEAN      DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_dashboards_owner ON dashboards (owner_id);

-- ── Audit Log Table ───────────────────────────────────────────────────────
-- Append-only log of significant system events for compliance and debugging.
-- No foreign keys — audit records must survive deletion of referenced entities.
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INTEGER,                            -- NULL if system action
    action          VARCHAR(50)  NOT NULL,               -- e.g., 'login', 'query.execute', 'dataset.upload'
    resource_type   VARCHAR(50),                         -- e.g., 'dataset', 'query', 'dashboard'
    resource_id     INTEGER,
    details         JSONB        DEFAULT '{}'::jsonb,    -- Arbitrary event details
    ip_address      VARCHAR(45),                         -- IPv4 or IPv6
    user_agent      VARCHAR(500),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user      ON audit_log (user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action    ON audit_log (action);
CREATE INDEX IF NOT EXISTS idx_audit_resource  ON audit_log (resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_created   ON audit_log (created_at DESC);

-- ── Seed Data ─────────────────────────────────────────────────────────────
-- Insert a default admin user for initial setup.
-- Password: 'admin123' (bcrypt hash — must be changed in production!)
-- Note: This hash was pre-computed for convenience. In production, generate
-- a fresh hash via: python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('admin123'))"

INSERT INTO users (email, username, password_hash, is_active, is_superuser, created_at)
VALUES (
    'admin@dataflow.local',
    'admin',
    '$2b$12$LJ3m4ys3Hz0JeVN5UxCE/.WmG/Q2qW2tKQ2D1V1e3kX5Hf6J3O9Ku',
    TRUE,
    TRUE,
    NOW()
) ON CONFLICT (email) DO NOTHING;

-- ── Helper Functions ──────────────────────────────────────────────────────

-- Automatically update the updated_at timestamp on row modification
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply the trigger to relevant tables
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_datasets_updated_at
    BEFORE UPDATE ON datasets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_dashboards_updated_at
    BEFORE UPDATE ON dashboards
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── Views ─────────────────────────────────────────────────────────────────

-- Convenient view for dataset statistics
CREATE OR REPLACE VIEW v_dataset_stats AS
SELECT
    d.id,
    d.name,
    d.table_name,
    d.row_count,
    d.column_count,
    d.file_format,
    d.file_size_bytes,
    d.is_public,
    u.username AS owner_name,
    d.created_at,
    COUNT(q.id) AS query_count,
    AVG(q.execution_time_ms) AS avg_query_time_ms
FROM datasets d
LEFT JOIN users u ON d.owner_id = u.id
LEFT JOIN queries q ON d.id = q.dataset_id AND q.status = 'completed'
GROUP BY d.id, d.name, d.table_name, d.row_count, d.column_count,
         d.file_format, d.file_size_bytes, d.is_public, u.username, d.created_at;

-- User activity summary
CREATE OR REPLACE VIEW v_user_activity AS
SELECT
    u.id,
    u.username,
    u.email,
    u.last_login_at,
    COUNT(DISTINCT d.id) AS dataset_count,
    COUNT(DISTINCT q.id) AS query_count,
    COUNT(DISTINCT db.id) AS dashboard_count
FROM users u
LEFT JOIN datasets d   ON u.id = d.owner_id
LEFT JOIN queries q     ON u.id = q.user_id
LEFT JOIN dashboards db ON u.id = db.owner_id
GROUP BY u.id, u.username, u.email, u.last_login_at;
