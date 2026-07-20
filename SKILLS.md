# DataFlow Platform — Skills & Capabilities Matrix

This document catalogs every skill, capability, and technical competency embedded in the DataFlow Platform codebase. Future developers can use this as a reference to understand what the system can do, what technologies are in play, and how to extend each area.

**Last Updated**: 2026-07-20 | **Phase**: 2–3 (Core Features + Integration) | **API Routes**: 26 | **Tests**: 22/22 passing

---

## 1. Frontend Skills

### 1.1 React + Next.js Architecture
- **App Router** with file-based routing (`/dashboard`, `/analytics`, `/settings`)
- **Server Components** for data fetching, Client Components for interactivity
- **Layout System** with nested layouts (root → main layout → page)
- **API Route Handlers** as proxy layer — the critical communication bridge
- **Dynamic route** `[...path]` catch-all proxy forwarding all HTTP methods to backend

### 1.2 TypeScript Type System
- **Strict typing** across all API responses, request bodies, and UI props
- **Generic types** for API responses (`ApiResponse<T>`, `PaginatedResponse<T>`)
- **Discriminated unions** for WebSocket message types
- **Type guards** for runtime validation of external data
- **Query result types** with column/row shape inference

### 1.3 Centralized API Communication
- **api-client.ts**: Single source of truth for all backend communication
  - Request interceptor: auth token injection
  - Response interceptor: error handling, token refresh with mutex
  - Typed methods for every endpoint (auth, data, analytics, settings)
  - Request/response logging in development mode
- **WebSocket client**: Real-time connection with auto-reconnect, heartbeat, typed subscriptions
- **useApi hook**: React integration with loading state, caching, retry logic

### 1.4 UI Component Library
- **Tailwind CSS** utility-first design with custom theme tokens
- **Compound components**: Card (CardHeader, CardBody, CardFooter)
- **Variant system**: Button with primary/secondary/ghost/danger variants
- **Responsive design**: Sidebar collapse, grid breakpoints, fluid layouts
- **Loading skeletons**: Animated placeholder components for async data loading
- **Toast notifications**: Auto-dismissing success/error/info messages

### 1.5 Data Visualization
- **Recharts** integration for interactive charts
- **SVG sparklines** in KPI cards for trend visualization
- **Auto chart detection** based on data types (bar for categorical, line for time series)
- **Export to CSV/PNG** from chart components with timestamped filenames
- **Inline query results**: Scrollable data tables with column headers and execution time

### 1.6 Interactive Query Editor
- **SQL editor** with keyboard shortcuts (⌘+Enter to execute)
- **Query history**: Saved queries with click-to-load and delete functionality
- **Real-time execution feedback**: Loading states, error banners, execution time badges
- **Demo mode fallback**: Gracefully degrades when backend is unavailable

### 1.7 System Monitoring UI
- **Health check dashboard**: Visual status indicators for DuckDB and PostgreSQL
- **Test Connection button**: Manual backend connectivity verification
- **API configuration display**: Shows base URL, version, and environment info
- **Connection management**: Database connection cards with status badges

---

## 2. Backend Skills

### 2.1 FastAPI Framework
- **App factory pattern** with lifespan events for startup/shutdown
- **Dependency injection** for database sessions, current user, configuration
- **Router organization** with versioned API prefix (`/api/v1/`)
- **OpenAPI/Swagger** auto-generated documentation at `/docs`
- **WebSocket endpoint** with channel-based subscriptions
- **Structured logging** with request timing and status code tracking

### 2.2 Dual Database Management
- **DuckDB**: Embedded columnar database for analytical queries
  - Zero-configuration, file-based or in-memory
  - Native CSV/Parquet/JSON readers
  - Full SQL support with window functions, CTEs, aggregations
  - Connection pooling with thread-safe access
  - Seeded with 60,010 rows across 3 tables (sales_data, user_activity, products)
  - Real-time statistics via `information_schema` queries
- **PostgreSQL**: Relational database for transactional data
  - SQLAlchemy ORM with Alembic migrations
  - ACID-compliant user management, audit logging
  - Connection pooling via async sessionmaker
  - Graceful degradation (works without Postgres in dev)

### 2.3 Authentication & Security
- **JWT tokens** with access + refresh token flow
- **bcrypt** password hashing via passlib
- **Route protection** via middleware and dependency injection
- **SQL injection prevention** with query validation (blocks DROP, TRUNCATE, system table access)
- **CORS** with configurable origins per environment
- **In-memory user store** as development fallback when PostgreSQL is unavailable

### 2.4 Rate Limiting
- **Fixed-window algorithm** with configurable limits
- **In-memory fallback** for development (no Redis required)
- **Redis backend** for distributed rate limiting in production
- **Per-route and global** rate limit configurations
- **Rate limit headers** (X-RateLimit-Limit, X-RateLimit-Remaining) on all responses

### 2.5 Query Engine
- **SQL validation** with safety checks before execution
- **DuckDB execution** returning pandas DataFrames
- **Schema introspection** for table listing and column detection
- **Auto-pagination** for large result sets
- **Query timeout** with configurable limits
- **Query history tracking**: Thread-safe, bounded to 100 entries, records status/timing/results
- **Query ID assignment**: Each executed query receives a unique identifier for tracking

### 2.6 Analytics Engine
- **Descriptive statistics**: mean, median, std, percentiles, null counts
- **Aggregation service**: group-by with configurable metrics (sum, avg, count, min, max)
- **Pivot table generation**: dynamic index/columns/values configuration
- **Auto chart type detection**: suggests visualization based on data shape
- **Dashboard statistics**: Real-time metrics from DuckDB (table counts, row totals, memory, version)
- **Sales summary**: Dynamic revenue/customer/category aggregations from seeded data

### 2.7 Data Management
- **File upload**: CSV, Parquet, JSON, TSV with automatic schema detection
- **Data export**: Streaming responses in CSV, Parquet, or JSON format
- **Dataset CRUD**: List, inspect, and delete datasets with metadata tracking
- **Export headers**: X-Row-Count and X-Column-Count headers for streaming responses

---

## 3. Middleware Skills

### 3.1 CORS Middleware
- Environment-aware: permissive in development, restrictive in production
- Configurable allowed origins, methods, and headers
- Credentials support for authenticated cross-origin requests

### 3.2 Auth Middleware
- JWT validation on all protected routes
- Whitelist for public endpoints (health, login, register, info, version)
- User context injection into request state
- Token expiration handling with automatic refresh flow

### 3.3 Rate Limit Middleware
- Request counting with configurable time windows
- IP-based identification (extendable to user-based)
- Custom error responses with retry-after headers
- Redis integration for distributed deployments

### 3.4 Request Logging Middleware
- Structured request/response logging with timing
- Status code tracking for every endpoint
- Configurable log levels per environment

---

## 4. Infrastructure Skills

### 4.1 Docker & Containerization
- **Multi-stage builds** for optimized production images
- **Docker Compose** orchestrating: frontend, backend, PostgreSQL, Redis, Nginx
- **Health checks** in container definitions
- **Volume mounts** for data persistence and development hot-reload

### 4.2 CI/CD Pipeline
- **GitHub Actions** with test, lint, build stages
- **Matrix testing** across Python and Node.js versions
- **Service containers**: PostgreSQL and Redis for integration testing
- **Automated deployment** on main branch push
- **PR checks** with required status checks

### 4.3 Database Migrations
- **Alembic** for PostgreSQL schema migrations
- **init.sql** for initial schema setup
- **Seed scripts** for development data (10K sales, 50K activity, 10 products)

---

## 5. Testing Skills

### 5.1 Backend Testing
- **pytest** with async support for FastAPI endpoints (22 tests passing)
- **httpx AsyncClient** with ASGITransport for in-process testing
- **Test fixtures** for database sessions and auth tokens
- **Coverage reporting** with pytest-cov
- **Test categories**: Health, Auth, Data, Analytics, Middleware
- **Edge cases**: Duplicate registration, short passwords, dangerous SQL, unsupported formats

### 5.2 Frontend Testing (Planned)
- **vitest** for unit and component tests
- **Playwright** for end-to-end testing
- **Testing Library** for React component testing

---

## 6. Development Workflow Skills

### 6.1 Code Organization
- **Feature-based folder structure** in both frontend and backend
- **Clear separation of concerns**: routes, services, models, middleware
- **Consistent naming conventions**: kebab-case files, PascalCase components
- **Service layer pattern**: Business logic isolated in `app/services/`

### 6.2 Documentation
- **Phase-based docs** in `docs/phases/` for development history
- **Architecture diagrams** in `docs/diagrams/`
- **Inline code documentation** with docstrings and type hints
- **README** with quick start, structure, and endpoint reference
- **SKILLS.md** with capability matrix (this file)
- **IMPROVEMENTS.md** with evolution roadmap and market trends

### 6.3 Git Workflow
- **Conventional commits** for clear history
- **Branch strategy**: main → develop → feature branches
- **CI workflow** with GitHub Actions (repo + workflow scopes)

---

## API Endpoint Inventory

| Category | Count | Endpoints |
|----------|-------|-----------|
| **Health & Info** | 3 | `/health`, `/info`, `/version` |
| **Authentication** | 4 | `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me` |
| **Data Management** | 7 | `/data/datasets`, `/data/upload`, `/data/datasets/{id}`, `/data/query`, `/data/query/recent`, `/data/query/{id}`, `/data/export/{id}` |
| **Analytics** | 5 | `/analytics/aggregate`, `/analytics/pivot`, `/analytics/dashboard`, `/analytics/dashboard/stats`, `/analytics/stats/{id}` |
| **WebSocket** | 1 | `/ws` |
| **Documentation** | 3 | `/docs`, `/redoc`, `/openapi.json` |
| **Total** | **26** | |

---

## Skill Extension Guide

To add a new capability to the platform:

1. **Backend**: Create new router in `app/api/v1/`, add service in `app/services/`, define schemas in `app/models/schemas.py`
2. **Frontend**: Add page in `src/app/`, create components in `src/components/`, extend types in `src/types/index.ts`
3. **API Client**: Add methods to `src/lib/api-client.ts` and update `useApi` hook
4. **Documentation**: Update this SKILLS.md, add endpoint to README, create phase doc if major feature
5. **Testing**: Write tests in `backend/tests/` and frontend test files

Each skill above is self-contained and can be extended independently without affecting other parts of the system.
