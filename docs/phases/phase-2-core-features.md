# Phase 2 — Core Features

**Duration**: Weeks 4-7  
**Goal**: Add authentication, data ingestion, SQL query execution, and interactive dashboard components.

---

## Active Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/register` | Create new user account |
| `POST` | `/api/v1/auth/login` | Login with email/password, receive JWT |
| `POST` | `/api/v1/auth/refresh` | Refresh expired access token |
| `GET` | `/api/v1/auth/me` | Get authenticated user profile |
| `POST` | `/api/v1/data/upload` | Upload CSV/Parquet file to DuckDB |
| `GET` | `/api/v1/data/datasets/{id}` | Get dataset schema and stats |
| `DELETE` | `/api/v1/data/datasets/{id}` | Delete a dataset |
| `POST` | `/api/v1/data/query` | Execute SQL query on DuckDB (returns query_id) |
| `GET` | `/api/v1/data/query/recent` | Get recent query history |
| `GET` | `/api/v1/data/query/{query_id}` | Get query status and results by ID |
| `GET` | `/api/v1/data/export/{id}` | Export dataset as CSV/Parquet/JSON |
| `GET` | `/api/v1/analytics/dashboard` | Get dashboard configuration |
| `PUT` | `/api/v1/analytics/dashboard` | Update dashboard configuration |

---

## What Was Built

### Authentication System
- **JWT tokens** with access token (30 min) + refresh token (7 days)
- **bcrypt password hashing** via passlib
- **Route protection middleware** that validates tokens on protected endpoints
- **Token refresh flow** with automatic retry in the frontend API client

### Data Ingestion Pipeline
- **File upload** supporting CSV, Parquet, JSON, and TSV formats
- **DuckDB native readers** for zero-copy ingestion (no pandas intermediate)
- **Schema detection** with automatic column type inference
- **Data validation** ensuring uploaded files meet size and format constraints

### SQL Query Engine
- **Query validation** that blocks dangerous operations (DROP, TRUNCATE, system table access)
- **DuckDB execution** with result pagination for large datasets
- **Query timeout** with configurable limits to prevent runaway queries
- **Error handling** with structured error responses and SQL syntax hints

### Dashboard UI
- **KPI cards** with sparkline trends for datasets, queries, response time, users
- **Recent queries table** with status badges (Done, Error, Running)
- **Quick query editor** with SQL syntax highlighting
- **Activity chart** showing daily query volume

### Rate Limiting
- **Fixed-window rate limiter** with configurable limits (default: 100 req/min)
- **In-memory counter** for development (no external dependencies)
- **Redis backend** for distributed deployments

---

## Key Decisions

- **DuckDB for queries, not PostgreSQL**: Analytical queries on uploaded datasets run against DuckDB's columnar engine, which is orders of magnitude faster for GROUP BY and aggregation operations than PostgreSQL's row-oriented storage.
- **SQL validation over sandboxing**: Instead of trying to sandbox SQL execution, we validate queries against a blacklist of dangerous patterns. This is simpler and sufficient for the current trust model (authenticated users).
- **JWT over session-based auth**: JWT tokens enable stateless authentication, which is essential for horizontal scaling. The tradeoff is token revocation complexity, which we mitigate with short-lived access tokens and a refresh token rotation strategy.
