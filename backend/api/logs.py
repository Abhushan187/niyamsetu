# backend/api/logs.py
# ─────────────────────────────────────────────────────────
# Query log endpoints.
#
# Endpoints:
#   GET /api/logs/all      → all logs across all users (admin only)
#   GET /api/logs/mine     → current user's own query history
#   GET /api/logs/stats    → aggregate stats for admin dashboard
# ─────────────────────────────────────────────────────────

import sys
import os

from fastapi import APIRouter, Depends, Query

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.router import get_current_user, get_admin_user
from db.logs import get_all_logs, get_logs_by_user, get_log_stats

router = APIRouter(prefix="/api/logs", tags=["Logs"])


@router.get("/all")
async def fetch_all_logs(
    limit: int = Query(default=100, le=500),
    admin: dict = Depends(get_admin_user),
):
    """
    Returns all query logs across all users.
    Admin only.

    Query params:
        limit : max logs to return, default 100, max 500
    """
    logs = await get_all_logs(limit=limit)

    # Convert datetime objects to strings for JSON serialization
    for log in logs:
        if "created_at" in log:
            log["created_at"] = str(log["created_at"])

    return {
        "success": True,
        "logs":    logs,
        "total":   len(logs),
    }


@router.get("/mine")
async def fetch_my_logs(
    limit: int = Query(default=50, le=200),
    current_user: dict = Depends(get_current_user),
):
    """
    Returns query history for the currently logged-in user.
    Available to all users — they only see their own queries.

    Query params:
        limit : max logs to return, default 50, max 200
    """
    logs = await get_logs_by_user(
        username=current_user["username"],
        limit=limit,
    )

    # Convert datetime objects to strings
    for log in logs:
        if "created_at" in log:
            log["created_at"] = str(log["created_at"])

    return {
        "success":  True,
        "username": current_user["username"],
        "logs":     logs,
        "total":    len(logs),
    }


@router.get("/stats")
async def fetch_log_stats(
    admin: dict = Depends(get_admin_user),
):
    """
    Returns aggregate statistics across all query logs.
    Used to populate admin dashboard stat cards.
    Admin only.

    Response:
        total_queries  : total number of queries ever
        unique_users   : how many distinct users have queried
        avg_elapsed    : average response time in seconds
        languages      : breakdown {"english": 45, "marathi": 12}
        success_rate   : percentage of successful queries
    """
    stats = await get_log_stats()
    return {
        "success": True,
        **stats,
    }