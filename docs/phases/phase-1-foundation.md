# Phase 1 — Foundation

**Duration**: Weeks 1-3  
**Goal**: Establish the project skeleton, database connections, and basic communication flow between frontend and backend.

---

## Active Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check — confirms backend is running |
| `GET` | `/api/v1/info` | API version, capabilities, environment |
| `GET` | `/api/v1/data/datasets` | List all datasets in DuckDB |
| `ALL` | `/api/[...path]` | Frontend API proxy to backend |

---

## What Was Built

### Backend (FastAPI)
- **App factory** (`main.py`) with CORS middleware and lifespan events
- **DuckDB connection** (`core/database.py`) with embedded analytical database
- **Health endpoint** (`api/v1/endpoints.py`) for service monitoring
- **Dataset listing** (`api/v1/data.py`) with DuckDB table introspection
- **Configuration** (`core/config.py`) with environment-based settings

### Frontend (Next.js)
- **App Router shell** with TypeScript and Tailwind CSS
- **Layout components**: Sidebar navigation, Header with search and user menu
- **API proxy route** (`src/app/api/[...path]/route.ts`) — the critical communication bridge
- **API client** (`src/lib/api-client.ts`) with request interceptors and error handling
- **Dashboard page** with KPI cards and recent queries (mock data fallback)

### Communication Flow
```
Browser → Next.js (/api/[...path]) → FastAPI (/api/v1/*) → DuckDB
```

The frontend never connects directly to any database. All requests go through the API proxy.

---

## Developer Onboarding

1. Clone the repository
2. `cd backend && pip install -r requirements.txt && uvicorn main:app --reload`
3. `cd frontend && npm install && npm run dev`
4. Visit http://localhost:3000 — redirects to dashboard
5. Visit http://localhost:8000/docs — Swagger UI for API exploration

---

## Key Decisions

- **DuckDB over SQLite**: Columnar storage is 10-100x faster for analytical queries (aggregations, GROUP BY, window functions) while maintaining zero-config embedded simplicity.
- **API proxy pattern**: Centralizing all backend communication through a Next.js proxy route enables unified error handling, auth token injection, and future migration to edge functions without frontend changes.
- **Monolithic starting point**: The backend is modular (routes, services, middleware) but deployed as a single FastAPI process. This simplifies initial development while preserving the ability to extract microservices later.
