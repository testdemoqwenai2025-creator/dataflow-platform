# DataFlow Platform

> A modern analytics platform built with Next.js, FastAPI middleware, and dual-database architecture (DuckDB + PostgreSQL).

![Architecture](docs/diagrams/architecture-workflow.png)

## Architecture Overview

DataFlow follows a **three-tier architecture** where the frontend communicates exclusively through a centralized API proxy, which forwards all requests to the FastAPI middleware layer. The middleware handles authentication, rate limiting, and data routing to the appropriate database engine.

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐     ┌────────────┐
│   Next.js    │────▶│  API Proxy   │────▶│   FastAPI     │────▶│   DuckDB   │
│  Frontend    │◀────│  /api/[...]  │◀────│   Middleware   │◀────│ (Analytics)│
└─────────────┘     └──────────────┘     └───────────────┘     └────────────┘
                                                  │            ┌────────────┐
                                                  └───────────▶│ PostgreSQL │
                                                               │(Transactional)│
                                                               └────────────┘
```

### Key Design Principles

1. **Frontend ↔ Middleware Communication**: The frontend never connects directly to any database. All requests flow through the API proxy (`/api/[...path]`) to the FastAPI middleware, which then routes to DuckDB (analytical queries) or PostgreSQL (transactional data).

2. **Dual Database Strategy**: DuckDB handles analytical workloads (OLAP) with columnar storage for fast aggregations, while PostgreSQL manages transactional data (OLTP) with ACID compliance for user accounts, audit logs, and metadata.

3. **Middleware as Gateway**: FastAPI serves as the single entry point, enforcing auth, rate limiting, CORS, and query validation before any data access occurs.

4. **Phase-Based Development**: The repository is organized into four development phases, each documented with active endpoints, so future developers can follow the exact progression.

---

## Build Status

| Component | Status | Details |
|-----------|--------|---------|
| **Frontend (Next.js)** | ✅ Build Pass | 7 routes compiled, 429 packages |
| **Backend (FastAPI)** | ✅ Verified | 24 API routes, all imports pass |
| **Auth Flow** | ✅ Tested | Register → Login → JWT tokens verified |
| **SQL Query Engine** | ✅ Tested | DuckDB in-memory queries execute correctly |
| **Health Check** | ✅ Tested | Returns healthy with DuckDB status |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (optional)

### Local Development

```bash
# Clone the repository
git clone https://github.com/testdemoqwenai2025-creator/dataflow-platform.git
cd dataflow-platform

# Start backend
cd backend
python3 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Start frontend (in a new terminal)
cd frontend
npm install
npm run dev
```

The application will be available at:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs

### Docker Compose

```bash
docker-compose up --build
```

This starts all services: frontend (port 3000), backend (port 8000), PostgreSQL (port 5432), and Redis (port 6379).

---

## Project Structure

```
dataflow-platform/
├── README.md                    # This file
├── SKILLS.md                    # Project capabilities & skill matrix
├── IMPROVEMENTS.md              # Evolution roadmap & market trends
├── docker-compose.yml           # Multi-container orchestration
├── Makefile                     # Development commands
├── .gitignore
│
├── backend/                     # FastAPI middleware + services
│   ├── main.py                  # App factory, WebSocket, lifespan
│   ├── requirements.txt
│   ├── app/
│   │   ├── core/                # Config, database, security
│   │   ├── api/v1/              # REST endpoints (auth, data, analytics)
│   │   ├── models/              # Pydantic schemas
│   │   ├── services/            # Business logic (query, analytics)
│   │   └── middleware/          # CORS, auth, rate limiting
│   ├── migrations/              # SQL schema
│   └── tests/                   # pytest test suite
│
├── frontend/                    # Next.js application
│   ├── package.json
│   ├── next.config.js           # API proxy rewrites
│   ├── src/
│   │   ├── app/                 # App Router pages
│   │   │   ├── dashboard/       # Main dashboard
│   │   │   ├── analytics/       # Query editor + results
│   │   │   ├── settings/        # DB connections, API keys
│   │   │   └── api/[...path]/   # ⭐ API proxy to backend
│   │   ├── components/          # React components
│   │   │   ├── layout/          # Sidebar, Header, MainLayout
│   │   │   ├── dashboard/       # KPICard, RecentQueries
│   │   │   └── ui/              # Button, Card (reusable)
│   │   ├── lib/                 # api-client, websocket
│   │   ├── hooks/               # useApi, useQuery, useMutation
│   │   └── types/               # TypeScript interfaces
│   └── public/
│
├── docs/
│   ├── diagrams/                # Architecture & mockup PNGs
│   └── phases/                  # Phase-by-phase documentation
│       ├── phase-1-foundation.md
│       ├── phase-2-core-features.md
│       ├── phase-3-integration.md
│       └── phase-4-production.md
│
├── scripts/                     # Setup & seeding utilities
│   ├── setup.sh
│   └── seed_db.py
│
└── .github/workflows/           # CI/CD pipeline
    └── ci.yml
```

---

## API Endpoints by Phase

### Phase 1 — Foundation

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/api/v1/info` | API version & capabilities |
| `GET` | `/api/v1/data/datasets` | List all datasets |
| `ALL` | `/api/[...path]` | Frontend proxy to backend |

### Phase 2 — Core Features

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/register` | Create account |
| `POST` | `/api/v1/auth/login` | Login, get JWT |
| `POST` | `/api/v1/auth/refresh` | Refresh access token |
| `GET` | `/api/v1/auth/me` | Get current user |
| `POST` | `/api/v1/data/upload` | Upload CSV/Parquet to DuckDB |
| `POST` | `/api/v1/data/query` | Execute SQL on DuckDB |
| `GET` | `/api/v1/analytics/dashboard` | Dashboard stats |
| `DELETE` | `/api/v1/data/datasets/{id}` | Delete dataset |

### Phase 3 — Integration

| Method | Endpoint | Description |
|--------|----------|-------------|
| `WS` | `/ws` | WebSocket real-time updates |
| `POST` | `/api/v1/analytics/aggregate` | Aggregate data |
| `POST` | `/api/v1/analytics/pivot` | Generate pivot table |
| `GET` | `/api/v1/analytics/stats/{id}` | Statistical summary |
| `GET` | `/api/v1/data/export/{id}` | Export dataset |

### Phase 4 — Production

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Full health (DB + Redis + deps) |
| — | CI/CD Pipeline | GitHub Actions automated testing |

---

## Frontend Mockup

![Frontend Mockup](docs/diagrams/frontend-mockup.png)

The dashboard features:
- **KPI Cards** with sparklines showing dataset count, queries, response time, and active users
- **Quick Query Editor** with SQL syntax highlighting, connected to DuckDB via the API proxy
- **Query Activity Chart** showing daily usage patterns
- **Recent Queries Table** with status badges (Done, Error, Running)
- **Quick Actions** for uploading data, creating dashboards, and managing API keys

---

## Frontend ↔ Backend Communication

All frontend communication goes through a single centralized path:

```
React Component
    → useApi() hook
        → api-client.ts (adds auth token, handles errors)
            → /api/[...path] proxy route (Next.js)
                → FastAPI middleware (auth + rate limit + CORS)
                    → DuckDB (analytical queries) or PostgreSQL (transactional)
```

### API Client (`src/lib/api-client.ts`)

The central API client handles:
- **Authentication**: Automatically attaches JWT tokens to all requests
- **Token Refresh**: Transparently refreshes expired tokens with mutex locking
- **Error Handling**: Typed `ApiError` class with status codes and messages
- **Request Logging**: Development-mode request/response logging
- **WebSocket Management**: Real-time query progress via `/ws`

### API Proxy Route (`src/app/api/[...path]/route.ts`)

The catch-all proxy route forwards every HTTP method (GET, POST, PUT, PATCH, DELETE) to the FastAPI backend. This ensures the frontend never makes direct database connections — all data flows through the middleware layer.

---

## Development Phases

Each phase builds on the previous one. See [docs/phases/](docs/phases/) for detailed documentation.

| Phase | Focus | Duration | Key Deliverable |
|-------|-------|----------|-----------------|
| **1 — Foundation** | Project setup, DB connections, basic API | 3 weeks | Working backend + frontend shell |
| **2 — Core Features** | Auth, data ingestion, query engine | 4 weeks | Full CRUD + SQL execution |
| **3 — Integration** | WebSocket, analytics, charts, PostgreSQL | 4 weeks | Real-time analytics platform |
| **4 — Production** | CI/CD, Docker, testing, monitoring | 3 weeks | Production-ready deployment |

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Next.js 14 + React 18 + TypeScript | UI framework with App Router |
| **Styling** | Tailwind CSS | Utility-first design system |
| **Charts** | Recharts | Data visualization |
| **API Proxy** | Next.js Route Handlers | Frontend-to-backend bridge |
| **Middleware** | FastAPI (Python) | API gateway + business logic |
| **Auth** | JWT + bcrypt | Secure token-based authentication |
| **Analytics DB** | DuckDB | Embedded columnar database for OLAP |
| **Transactional DB** | PostgreSQL | ACID-compliant relational database |
| **ORM** | SQLAlchemy | PostgreSQL model management |
| **Caching** | Redis | Query cache + session store + rate limiting |
| **Real-time** | WebSocket | Live query progress notifications |
| **Containerization** | Docker Compose | Multi-service orchestration |
| **CI/CD** | GitHub Actions | Automated testing and deployment |
| **Testing** | pytest + vitest + Playwright | Unit, integration, E2E tests |

---

## Environment Variables

### Backend

```env
# Database
DATABASE_URL=duckdb:///data/analytics.duckdb
POSTGRES_URL=postgresql://dataflow:secret@localhost:5432/dataflow

# Auth
SECRET_KEY=your-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Redis
REDIS_URL=redis://localhost:6379/0

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:8000

# Environment
ENVIRONMENT=development
```

### Frontend

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
```

---

## Contributing

1. Follow the phase-based development approach documented in `docs/phases/`
2. All frontend changes must communicate through the API proxy — never direct DB access
3. Backend endpoints must include proper auth, validation, and rate limiting
4. Write tests for new features before submitting PRs
5. See [SKILLS.md](SKILLS.md) for the project's capability matrix

---

## License

MIT License — see [LICENSE](LICENSE) for details.
