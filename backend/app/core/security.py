"""
Security utilities for authentication and authorisation.

This module provides:
    - JWT token creation and verification (python-jose)
    - Password hashing and validation (passlib bcrypt)
    - FastAPI dependency for extracting the current user from a token

Architecture Decision:
    We use stateless JWT tokens rather than server-side sessions. This keeps
    the backend horizontally scalable — any instance can verify a token
    without shared state. The trade-off is that token revocation requires
    a short expiry + a blocklist (not implemented here but straightforward
    to add via Redis).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Password hashing ──────────────────────────────────────────────────────
# We use bcrypt which is the gold standard for password hashing.
# The deprecated="auto" setting transparently handles verification of
# hashes produced by older algorithms during migration.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Bearer token extractor ────────────────────────────────────────────────
# HTTPBearer automatically extracts the token from the Authorization header
# and returns a 403 if missing (vs. 401 for other auth failures).
security = HTTPBearer()


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt.

    Args:
        password: The plaintext password to hash.

    Returns:
        The bcrypt hash string (includes salt and cost factor).
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.

    Args:
        plain_password: The password provided by the user.
        hashed_password: The stored bcrypt hash.

    Returns:
        True if the password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.

    The token payload includes:
        - sub: The subject (typically user ID or email)
        - exp: Expiration timestamp
        - iat: Issued-at timestamp
        - type: Token type ("access" or "refresh")

    Args:
        data: Dictionary of claims to encode in the token.
        expires_delta: Optional custom expiration duration.
            Defaults to settings.ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()

    # Determine expiration
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    logger.debug("Access token created for subject: %s", data.get("sub"))
    return encoded_jwt


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT refresh token with a longer lifetime.

    Refresh tokens are used to obtain new access tokens without requiring
    the user to re-authenticate. They should be stored securely (httpOnly
    cookie or secure storage) and have a longer expiry than access tokens.

    Args:
        data: Dictionary of claims to encode.
        expires_delta: Optional custom expiration. Defaults to 7 days.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()

    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=7)

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    })

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def verify_token(token: str, token_type: str = "access") -> dict[str, Any]:
    """
    Decode and verify a JWT token.

    Args:
        token: The encoded JWT string.
        token_type: Expected token type ("access" or "refresh").

    Returns:
        The decoded token payload as a dictionary.

    Raises:
        HTTPException: If the token is invalid, expired, or wrong type.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )

        # Verify token type matches expectation
        if payload.get("type") != token_type:
            logger.warning(
                "Token type mismatch: expected %s, got %s",
                token_type,
                payload.get("type"),
            )
            raise credentials_exception

        return payload

    except JWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise credentials_exception


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    """
    FastAPI dependency that extracts and validates the current user from
    the Authorization Bearer token.

    Usage in endpoint:
        @router.get("/me")
        def read_users_me(current_user: dict = Depends(get_current_user)):
            return current_user

    Returns:
        Dictionary with at minimum 'sub' (user identifier) from the token,
        plus any additional claims stored at creation time.

    Raises:
        HTTPException 401: If the token is missing, invalid, or expired.
    """
    token = credentials.credentials
    payload = verify_token(token, token_type="access")

    # 'sub' is the standard JWT claim for the subject (user ID / email)
    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token: missing subject",
        )

    return payload
