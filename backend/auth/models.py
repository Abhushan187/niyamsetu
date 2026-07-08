# backend/auth/models.py
# ─────────────────────────────────────────────────────────
# Pydantic schemas for auth-related data.
# These define the exact shape of:
#   - what the frontend sends (request body)
#   - what the backend returns (response body)
# FastAPI validates all incoming data against these automatically.
# ─────────────────────────────────────────────────────────

from pydantic import BaseModel, Field
from typing import Literal


# ── Request schemas (what frontend sends) ─────────────────

class LoginRequest(BaseModel):
    """
    Shape of the login form submission.
    Frontend sends this as JSON:
        { "username": "admin", "password": "admin123" }
    """
    username: str = Field(
        min_length=3,
        max_length=50,
        description="Username — minimum 3 characters"
    )
    password: str = Field(
        min_length=6,
        description="Password — minimum 6 characters"
    )


class CreateUserRequest(BaseModel):
    """
    Shape of the create user form (admin only).
    Frontend sends:
        { "username": "john", "password": "pass123", "name": "John Doe", "role": "user" }
    """
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)
    name: str = Field(min_length=2, max_length=100)
    # Literal means only these exact values are accepted
    # Anything else gets rejected automatically
    role: Literal["user", "admin"] = "user"


class ChangePasswordRequest(BaseModel):
    """
    Shape of the change password request.
    """
    current_password: str
    new_password: str = Field(min_length=6)


# ── Response schemas (what backend returns) ───────────────

class LoginResponse(BaseModel):
    """
    What we send back after a successful login.
    The frontend stores the token and sends it with every future request.
    """
    access_token: str
    token_type: str = "bearer"
    username: str
    name: str
    role: Literal["user", "admin"]


class UserResponse(BaseModel):
    """
    Safe representation of a user — no password included.
    Used when listing users or returning current user info.
    """
    username: str
    name: str
    role: Literal["user", "admin"]


class MessageResponse(BaseModel):
    """
    Generic success/info response.
    Used for operations that don't return data:
        { "message": "User created successfully." }
    """
    message: str