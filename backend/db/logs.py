# backend/db/logs.py
# ─────────────────────────────────────────────────────────
# All MongoDB operations related to query logs.
# Every time a user asks a question, it gets saved here.
# Admin uses this for analytics. Users see their own history.
# ─────────────────────────────────────────────────────────

import sys
import os
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.mongo import get_db


async def save_query_log(
    username: str,
    query: str,
    answer: str,
    citations: list,
    language: str,
    elapsed_sec: float,
    was_successful: bool = True,
) -> None:
    """
    Saves a single query and its response to MongoDB.
    Called automatically after every chat query — user never sees this.

    Args:
        username    : who asked the question
        query       : the exact question asked
        answer      : the AI's response
        citations   : list of {file, page, preview} dicts
        language    : 'english' or 'marathi'
        elapsed_sec : how long the response took in seconds
        was_successful : False if vector store was missing or error occurred
    """
    database = get_db()

    log_entry = {
        "username":      username,
        "query":         query,
        "answer":        answer,
        "citations":     citations,
        "language":      language,
        "elapsed_sec":   elapsed_sec,
        "was_successful": was_successful,
        # Timestamp stored in UTC — consistent across timezones
        "created_at":    datetime.now(timezone.utc),
    }

    await database.query_logs.insert_one(log_entry)


async def get_logs_by_user(username: str, limit: int = 50) -> list:
    """
    Returns the most recent query logs for a specific user.
    Used on the My History page — users only see their own queries.

    Args:
        username : filter logs by this username
        limit    : max number of logs to return (default 50)

    Returns:
        List of log dicts, newest first
    """
    database = get_db()

    cursor = database.query_logs.find(
        {"username": username},
        {"_id": 0}                          # exclude MongoDB internal _id field
    ).sort(
        "created_at", -1                    # -1 = descending = newest first
    ).limit(limit)

    logs = await cursor.to_list(length=limit)
    return logs


async def get_all_logs(limit: int = 200) -> list:
    """
    Returns all query logs across all users.
    Admin only — used on the All Logs page.

    Args:
        limit : max number of logs to return (default 200)

    Returns:
        List of log dicts, newest first
    """
    database = get_db()

    cursor = database.query_logs.find(
        {},                                 # empty filter = all documents
        {"_id": 0}
    ).sort(
        "created_at", -1
    ).limit(limit)

    logs = await cursor.to_list(length=limit)
    return logs


async def get_log_stats() -> dict:
    """
    Computes summary statistics across all query logs.
    Used on the Admin Dashboard stat cards.

    Returns dict:
        total_queries  : total number of queries ever made
        unique_users   : how many distinct users have queried
        avg_elapsed    : average response time in seconds
        languages      : breakdown by language {"english": 45, "marathi": 12}
        success_rate   : percentage of successful queries
    """
    database = get_db()

    # Count total documents in the collection
    total = await database.query_logs.count_documents({})

    if total == 0:
        return {
            "total_queries": 0,
            "unique_users":  0,
            "avg_elapsed":   0,
            "languages":     {},
            "success_rate":  100,
        }

    # MongoDB aggregation pipeline
    # Think of this as a series of operations run on the collection
    pipeline = [
        {
            # $group groups all documents and computes values
            "$group": {
                "_id": None,                            # null = group everything together
                "avg_elapsed": {"$avg": "$elapsed_sec"},
                "successful":  {"$sum": {"$cond": ["$was_successful", 1, 0]}},
            }
        }
    ]

    agg_result = await database.query_logs.aggregate(pipeline).to_list(length=1)
    avg_elapsed   = round(agg_result[0]["avg_elapsed"], 2) if agg_result else 0
    successful    = agg_result[0]["successful"] if agg_result else 0
    success_rate  = round((successful / total) * 100) if total > 0 else 100

    # Get unique users using distinct()
    unique_users = await database.query_logs.distinct("username")

    # Count by language
    lang_pipeline = [
        {"$group": {"_id": "$language", "count": {"$sum": 1}}}
    ]
    lang_result = await database.query_logs.aggregate(lang_pipeline).to_list(length=10)
    languages = {item["_id"]: item["count"] for item in lang_result}

    return {
        "total_queries": total,
        "unique_users":  len(unique_users),
        "avg_elapsed":   avg_elapsed,
        "languages":     languages,
        "success_rate":  success_rate,
    }