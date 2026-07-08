# backend/auth/jwt_handler.py
# ─────────────────────────────────────────────────────────
# JWT token creation and verification.
# Two functions only — create_token() and verify_token().
# Everything auth-related flows through here.
# ─────────────────────────────────────────────────────────

import sys
import os
from datetime import datetime, timedelta, timezone

# jose is the JWT library — handles encoding and decoding tokens
from jose import JWTError, jwt

# HTTPException lets us return proper HTTP error responses
from fastapi import HTTPException, status

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# ── Algorithm used to sign tokens ────────────────────────
# HS256 = HMAC with SHA-256
# Industry standard for JWT signing
ALGORITHM = "HS256"


def create_token(data: dict) -> str:
    """
    Creates a signed JWT token.

    What goes inside the token (the 'payload'):
      - username: who this token belongs to
      - role: admin or user (used to protect admin routes)
      - exp: expiry timestamp (token stops working after this)

    The token is signed with JWT_SECRET from .env
    Anyone who tampers with the token will fail verification.

    Args:
        data: dict containing at minimum {"username": "...", "role": "..."}

    Returns:
        A JWT token string like "eyJhbGciOiJIUzI1NiJ9..."
    """
    # Copy the data so we don't modify the original dict
    payload = data.copy()

    # Set expiry time — current time + hours defined in .env
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload["exp"] = expire

    # Encode everything into a signed token string
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)
    return token


def verify_token(token: str) -> dict:
    """
    Verifies a JWT token and returns its payload.

    Called on every protected route request.
    The frontend sends the token in the Authorization header:
        Authorization: Bearer eyJhbGciOiJIUzI1NiJ9...

    This function:
      1. Decodes the token using JWT_SECRET
      2. Checks the signature hasn't been tampered with
      3. Checks the token hasn't expired
      4. Returns the payload (username, role) if all checks pass

    Args:
        token: the raw JWT string from the request header

    Returns:
        dict with username and role if valid

    Raises:
        HTTPException 401 if token is invalid or expired
    """
    # This exception is what we raise if anything goes wrong
    # 401 = Unauthorized
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decode and verify the token
        # jose automatically checks expiry and signature
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])

        # Extract username from payload
        username: str = payload.get("username")
        role: str = payload.get("role")

        # If username missing from payload something is wrong
        if username is None or role is None:
            raise credentials_exception

        return {"username": username, "role": role}

    except JWTError:
        # Token is expired, tampered, or malformed
        raise credentials_exception