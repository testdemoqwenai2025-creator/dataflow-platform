"""
Authentication endpoints: register, login, refresh, and current user.

This module implements a complete JWT-based authentication flow:

    1. Register — Create a new user account with hashed password.
    2. Login    — Verify credentials and return access + refresh tokens.
    3. Refresh  — Exchange a valid refresh token for new access token.
    4. Me       — Return the authenticated user's profile.

Architecture Decision:
    User data is stored in PostgreSQL for ACID compliance. We use an
    in-memory user store as a fallback when PostgreSQL is unavailable,
    enabling development without external infrastructure. In production,
    the PostgreSQL store must be used for durability and concurrency.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db, get_postgres_engine
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    verify_password,
    verify_token,
)
from app.models.schemas import (
    APIResponse,
    Token,
    TokenRefresh,
    UserCreate,
    UserLogin,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ── In-memory user store (development fallback) ───────────────────────────
# When PostgreSQL is unavailable, we store users in memory so that the
# auth flow can be tested end-to-end. This is NOT suitable for production.
_memory_users: Dict[str, dict] = {}
_user_id_counter: int = 0


def _is_postgres_available() -> bool:
    """Check if PostgreSQL is reachable."""
    try:
        engine = get_postgres_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _create_user_postgres(user_data: UserCreate, db: Session) -> dict:
    """
    Persist a new user to PostgreSQL.

    This uses raw SQL via SQLAlchemy's text() to avoid requiring
    ORM models that may not have been migrated yet. In a mature
    codebase, you'd use SQLAlchemy ORM models instead.
    """
    hashed = hash_password(user_data.password)

    try:
        result = db.execute(
            text("""
                INSERT INTO users (email, username, password_hash, is_active, is_superuser, created_at)
                VALUES (:email, :username, :hash, true, false, NOW())
                RETURNING id, email, username, is_active, is_superuser, created_at
            """),
            {"email": user_data.email, "username": user_data.username, "hash": hashed},
        )
        db.commit()
        row = result.mappings().first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user",
            )
        return dict(row)
    except Exception as exc:
        db.rollback()
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email or username already exists",
            )
        logger.error("User creation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        )


async def _create_user_memory(user_data: UserCreate) -> dict:
    """Create user in the in-memory fallback store."""
    global _user_id_counter

    # Check for duplicates
    for existing in _memory_users.values():
        if existing["email"] == user_data.email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            )
        if existing["username"] == user_data.username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this username already exists",
            )

    _user_id_counter += 1
    now = datetime.now(timezone.utc)
    user_record = {
        "id": _user_id_counter,
        "email": user_data.email,
        "username": user_data.username,
        "password_hash": hash_password(user_data.password),
        "is_active": True,
        "is_superuser": False,
        "created_at": now,
        "updated_at": None,
    }
    _memory_users[user_data.email] = user_record
    return user_record


async def _authenticate_user_postgres(email: str, password: str, db: Session) -> Optional[dict]:
    """Look up and verify a user in PostgreSQL."""
    try:
        result = db.execute(
            text("""
                SELECT id, email, username, password_hash, is_active, is_superuser, created_at
                FROM users WHERE email = :email
            """),
            {"email": email},
        )
        row = result.mappings().first()
        if row is None:
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        if not row["is_active"]:
            return None
        return dict(row)
    except Exception as exc:
        logger.error("Authentication query error: %s", exc)
        return None


async def _authenticate_user_memory(email: str, password: str) -> Optional[dict]:
    """Look up and verify a user in the in-memory store."""
    user = _memory_users.get(email)
    if user is None:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    if not user["is_active"]:
        return None
    return user


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create a new user account with email, username, and password.",
)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
) -> APIResponse[UserResponse]:
    """
    Register a new user.

    The password is hashed with bcrypt before storage. Never stored in plaintext.
    """
    logger.info("Registration attempt: email=%s, username=%s", user_data.email, user_data.username)

    try:
        if _is_postgres_available():
            user_record = await _create_user_postgres(user_data, db)
        else:
            user_record = await _create_user_memory(user_data)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected registration error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed",
        )

    # Build response — exclude password_hash
    user_response = UserResponse(
        id=user_record["id"],
        email=user_record["email"],
        username=user_record["username"],
        is_active=user_record.get("is_active", True),
        is_superuser=user_record.get("is_superuser", False),
        created_at=user_record["created_at"],
        updated_at=user_record.get("updated_at"),
    )

    return APIResponse(
        success=True,
        data=user_response,
        message="User registered successfully",
    )


@router.post(
    "/login",
    response_model=APIResponse[Token],
    summary="Login",
    description="Authenticate with email/username and password to receive JWT tokens.",
)
async def login(
    credentials: UserLogin,
    db: Session = Depends(get_db),
) -> APIResponse[Token]:
    """
    Authenticate a user and return JWT tokens.

    Accepts either email or username as the login identifier.
    Returns both an access token (short-lived) and a refresh token (long-lived).
    """
    # Determine the identifier
    identifier = credentials.email or credentials.username
    if not identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username is required",
        )

    logger.info("Login attempt: %s", identifier)

    # Authenticate
    user_record = None
    if credentials.email and _is_postgres_available():
        user_record = await _authenticate_user_postgres(credentials.email, credentials.password, db)
    elif credentials.email:
        user_record = await _authenticate_user_memory(credentials.email, credentials.password)

    # Also try username lookup in memory store
    if user_record is None and credentials.username and not _is_postgres_available():
        for user in _memory_users.values():
            if user["username"] == credentials.username:
                if verify_password(credentials.password, user["password_hash"]):
                    user_record = user
                break

    if user_record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Create tokens
    token_data = {
        "sub": str(user_record["id"]),
        "email": user_record["email"],
        "username": user_record["username"],
    }

    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data={"sub": str(user_record["id"])})

    token_response = Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return APIResponse(
        success=True,
        data=token_response,
        message="Login successful",
    )


@router.post(
    "/refresh",
    response_model=APIResponse[Token],
    summary="Refresh access token",
    description="Exchange a valid refresh token for a new access token.",
)
async def refresh_token(
    request: TokenRefresh,
) -> APIResponse[Token]:
    """
    Refresh an access token using a valid refresh token.

    The refresh token is verified for type and expiry. A new access
    token is issued with a fresh expiry.
    """
    payload = verify_token(request.refresh_token, token_type="refresh")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Issue new access token
    access_token = create_access_token(data={"sub": user_id})
    new_refresh = create_refresh_token(data={"sub": user_id})

    token_response = Token(
        access_token=access_token,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return APIResponse(
        success=True,
        data=token_response,
        message="Token refreshed successfully",
    )


@router.get(
    "/me",
    response_model=APIResponse[UserResponse],
    summary="Get current user",
    description="Return the authenticated user's profile.",
)
async def get_me(
    current_user: dict = Depends(get_current_user),
) -> APIResponse[UserResponse]:
    """
    Return the profile of the currently authenticated user.

    The user identity is extracted from the JWT token via the
    get_current_user dependency.
    """
    user_id = int(current_user["sub"])

    # Try memory store first
    for user in _memory_users.values():
        if user["id"] == user_id:
            user_response = UserResponse(
                id=user["id"],
                email=user["email"],
                username=user["username"],
                is_active=user.get("is_active", True),
                is_superuser=user.get("is_superuser", False),
                created_at=user["created_at"],
                updated_at=user.get("updated_at"),
            )
            return APIResponse(success=True, data=user_response, message="User profile retrieved")

    # If not in memory, return from token claims
    user_response = UserResponse(
        id=user_id,
        email=current_user.get("email", ""),
        username=current_user.get("username", ""),
        is_active=True,
        is_superuser=False,
        created_at=datetime.now(timezone.utc),
    )

    return APIResponse(
        success=True,
        data=user_response,
        message="User profile retrieved from token",
    )
