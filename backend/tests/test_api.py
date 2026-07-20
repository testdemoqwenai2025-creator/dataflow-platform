"""
Tests for the DataFlow Platform API.

Uses httpx AsyncClient with FastAPI's TestClient for in-process testing.
No external services (PostgreSQL, Redis) are required — tests use the
in-memory fallback stores and DuckDB's in-memory mode.

Run with:
    pytest tests/test_api.py -v

Architecture Decision:
    We use httpx.AsyncClient rather than FastAPI's sync TestClient because:
        1. Our app uses async endpoints and middleware
        2. AsyncClient properly handles ASGI lifecycle
        3. It mirrors how real HTTP clients interact with the API
"""

import pytest
import json
from httpx import AsyncClient, ASGITransport

from app.main import app


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    """
    Provide an async HTTP client for testing.

    Uses ASGITransport to call the FastAPI app directly without
    starting a real HTTP server. This is fast and deterministic.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_token(client: AsyncClient) -> str:
    """
    Register a test user and return a valid access token.

    This fixture creates a unique user for each test session and
    returns the JWT access token for authenticated requests.
    """
    # Register
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "testuser@example.com",
            "username": "testuser",
            "password": "testpassword123",
        },
    )
    assert register_response.status_code in (200, 201, 409), \
        f"Registration failed: {register_response.text}"

    # Login
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "testuser@example.com",
            "password": "testpassword123",
        },
    )
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"

    data = login_response.json()
    token = data["data"]["access_token"]
    assert token, "No access token in login response"

    return token


@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    """Return Authorization headers with a valid Bearer token."""
    return {"Authorization": f"Bearer {auth_token}"}


# ── Health & Info Tests ───────────────────────────────────────────────────


class TestHealthEndpoints:
    """Tests for health check and API info endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Health endpoint should return 200 with status information."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

        data = response.json()
        # The APIResponse wrapper is used
        assert data["success"] is True
        health = data["data"]
        assert health["status"] == "healthy"
        assert "version" in health
        assert "environment" in health
        assert "duckdb_status" in health

    @pytest.mark.asyncio
    async def test_api_info(self, client: AsyncClient):
        """Info endpoint should return API metadata and endpoint listing."""
        response = await client.get("/api/v1/info")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        info = data["data"]
        assert info["name"] == "DataFlow Platform"
        assert "endpoints" in info
        assert len(info["endpoints"]) >= 3  # auth, data, analytics

    @pytest.mark.asyncio
    async def test_version(self, client: AsyncClient):
        """Version endpoint should return current version."""
        response = await client.get("/api/v1/version")
        assert response.status_code == 200

        data = response.json()
        assert "version" in data
        assert "environment" in data


# ── Authentication Tests ──────────────────────────────────────────────────


class TestAuthEndpoints:
    """Tests for authentication endpoints."""

    @pytest.mark.asyncio
    async def test_register_new_user(self, client: AsyncClient):
        """Register endpoint should create a new user."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "username": "newuser",
                "password": "securepassword123",
            },
        )
        assert response.status_code in (200, 201)

        data = response.json()
        assert data["success"] is True
        user = data["data"]
        assert user["email"] == "newuser@example.com"
        assert user["username"] == "newuser"
        assert "password" not in user  # Password should never be returned
        assert "password_hash" not in user

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient):
        """Register should reject duplicate email addresses."""
        user_data = {
            "email": "duplicate@example.com",
            "username": "user1",
            "password": "password123",
        }

        # First registration should succeed
        response1 = await client.post("/api/v1/auth/register", json=user_data)
        assert response1.status_code in (200, 201)

        # Second registration with same email should fail
        user_data["username"] = "user2"
        response2 = await client.post("/api/v1/auth/register", json=user_data)
        assert response2.status_code in (409, 400)

    @pytest.mark.asyncio
    async def test_register_short_password(self, client: AsyncClient):
        """Register should reject passwords shorter than 8 characters."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "shortpass@example.com",
                "username": "shortpass",
                "password": "short",
            },
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient):
        """Login with valid credentials should return JWT tokens."""
        # Register first
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "logintest@example.com",
                "username": "logintest",
                "password": "testpassword123",
            },
        )

        # Login
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "logintest@example.com",
                "password": "testpassword123",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        token_data = data["data"]
        assert "access_token" in token_data
        assert "refresh_token" in token_data
        assert token_data["token_type"] == "bearer"
        assert "expires_in" in token_data

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client: AsyncClient):
        """Login with wrong password should return 401."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "wrongpassword",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token(self, client: AsyncClient):
        """Refresh endpoint should issue new tokens."""
        # Register and login
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "refresh@example.com",
                "username": "refreshuser",
                "password": "testpassword123",
            },
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "refresh@example.com", "password": "testpassword123"},
        )
        refresh_token = login_resp.json()["data"]["refresh_token"]

        # Refresh
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]

    @pytest.mark.asyncio
    async def test_get_current_user(self, client: AsyncClient, auth_token: str):
        """Me endpoint should return the authenticated user's profile."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        user = data["data"]
        assert "email" in user
        assert "username" in user

    @pytest.mark.asyncio
    async def test_me_without_token(self, client: AsyncClient):
        """Me endpoint should reject requests without a token."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code in (401, 403)


# ── Data Endpoint Tests ──────────────────────────────────────────────────


class TestDataEndpoints:
    """Tests for data management endpoints."""

    @pytest.mark.asyncio
    async def test_list_datasets_empty(self, client: AsyncClient, auth_token: str):
        """List datasets should return an empty or non-empty list."""
        response = await client.get(
            "/api/v1/data/datasets",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_upload_csv(self, client: AsyncClient, auth_token: str):
        """Upload endpoint should accept CSV files and create a DuckDB table."""
        csv_content = "name,age,city\nAlice,30,NYC\nBob,25,LA\nCarol,35,Chicago\n"
        files = {"file": ("test_data.csv", csv_content, "text/csv")}
        params = {"name": "test_upload"}

        response = await client.post(
            "/api/v1/data/upload",
            files=files,
            params=params,
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 201

        data = response.json()
        assert data["success"] is True
        dataset = data["data"]
        assert dataset["name"] == "test_upload"
        assert dataset["row_count"] == 3
        assert dataset["column_count"] == 3

    @pytest.mark.asyncio
    async def test_execute_query(self, client: AsyncClient, auth_token: str):
        """Query endpoint should execute SQL and return results."""
        # First upload a dataset
        csv_content = "category,value\nA,10\nB,20\nC,30\n"
        files = {"file": ("query_test.csv", csv_content, "text/csv")}
        await client.post(
            "/api/v1/data/upload",
            files=files,
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        # Execute a simple query
        response = await client.post(
            "/api/v1/data/query",
            json={"sql": "SELECT 1 AS value, 'test' AS label"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        result = data["data"]
        assert "columns" in result
        assert "rows" in result
        assert result["row_count"] >= 1
        assert "execution_time_ms" in result

    @pytest.mark.asyncio
    async def test_query_with_dangerous_sql(self, client: AsyncClient, auth_token: str):
        """Query endpoint should reject dangerous SQL (DROP, etc.)."""
        response = await client.post(
            "/api/v1/data/query",
            json={"sql": "DROP TABLE users"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_unsupported_format(self, client: AsyncClient, auth_token: str):
        """Upload should reject unsupported file formats."""
        files = {"file": ("test.exe", b"binary content", "application/octet-stream")}
        response = await client.post(
            "/api/v1/data/upload",
            files=files,
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 400


# ── Analytics Endpoint Tests ──────────────────────────────────────────────


class TestAnalyticsEndpoints:
    """Tests for analytics endpoints."""

    @pytest.mark.asyncio
    async def test_get_statistics(self, client: AsyncClient, auth_token: str):
        """Stats endpoint should return statistical summary for a dataset."""
        # Upload test data
        csv_content = "name,score\nAlice,85\nBob,92\nCarol,78\nDave,95\nEve,88\n"
        files = {"file": ("stats_test.csv", csv_content, "text/csv")}
        upload_resp = await client.post(
            "/api/v1/data/upload",
            files=files,
            params={"name": "stats_test"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert upload_resp.status_code == 201

        # Get dataset ID
        dataset_id = upload_resp.json()["data"]["id"]

        # Get statistics
        response = await client.get(
            f"/api/v1/analytics/stats/{dataset_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        stats = data["data"]
        assert isinstance(stats, list)
        assert len(stats) > 0

        # Check that numeric column has statistics
        score_stats = next((s for s in stats if s["column_name"] == "score"), None)
        assert score_stats is not None
        assert score_stats["mean"] is not None
        assert score_stats["min"] is not None
        assert score_stats["max"] is not None

    @pytest.mark.asyncio
    async def test_get_dashboard(self, client: AsyncClient, auth_token: str):
        """Dashboard endpoint should return a dashboard configuration."""
        response = await client.get(
            "/api/v1/analytics/dashboard",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        dashboard = data["data"]
        assert "name" in dashboard
        assert "widgets" in dashboard

    @pytest.mark.asyncio
    async def test_update_dashboard(self, client: AsyncClient, auth_token: str):
        """Dashboard update should modify the dashboard configuration."""
        response = await client.put(
            "/api/v1/analytics/dashboard",
            json={"name": "Updated Dashboard", "description": "Test update"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "Updated Dashboard"

    @pytest.mark.asyncio
    async def test_aggregation_nonexistent_table(self, client: AsyncClient, auth_token: str):
        """Aggregation on a non-existent table should return 404."""
        response = await client.post(
            "/api/v1/analytics/aggregate",
            json={
                "table_name": "nonexistent_table",
                "group_by": ["col1"],
                "metrics": {"total": "SUM(col2)"},
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 404


# ── Middleware Tests ───────────────────────────────────────────────────────


class TestMiddleware:
    """Tests for middleware behaviour."""

    @pytest.mark.asyncio
    async def test_cors_headers(self, client: AsyncClient):
        """Responses should include CORS headers."""
        response = await client.get(
            "/api/v1/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.status_code == 200
        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers

    @pytest.mark.asyncio
    async def test_rate_limit_headers(self, client: AsyncClient):
        """Responses should include rate limit headers."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers
