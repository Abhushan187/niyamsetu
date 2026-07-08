# backend/api/summary.py
# ─────────────────────────────────────────────────────────
# GR Summary generation endpoints.
#
# Endpoints:
#   POST /api/summary/generate      → generate summary for one GR
#   GET  /api/summary/list          → list all past summaries
#   GET  /api/summary/download/{filename} → download summary TXT file
#
# Admin only — summary generation is a heavy LLM operation.
# Uses BackgroundTasks like embed.py — returns immediately,
# runs in background, frontend polls for completion.
# ─────────────────────────────────────────────────────────

import sys
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.router import get_admin_user, get_current_user
from core.summarizer import process_gr, list_summaries
from config import settings

router = APIRouter(prefix="/api/summary", tags=["Summary"])


# ── Summary job state tracker ─────────────────────────────
# Same pattern as embed.py — track background job state in memory
_summary_state = {
    "running":      False,
    "last_status":  "idle",       # idle | running | done | failed
    "last_message": "Not started",
    "current_step": "",
    "filename":     "",
    "result":       None,         # stores the result when done
}


class GenerateRequest(BaseModel):
    """What the frontend sends to trigger summary generation."""
    filename: str   # e.g. "GR_2024_transfer.pdf"


async def _run_summary_job(pdf_path: str, filename: str):
    """
    Background job — runs process_gr() and updates state.
    Called via BackgroundTasks so endpoint returns immediately.
    """
    global _summary_state

    def on_progress(step: str):
        """Called by process_gr() at each step."""
        _summary_state["current_step"] = step
        _summary_state["last_message"] = step

    result = await process_gr(
        pdf_path=pdf_path,
        progress_callback=on_progress,
    )

    if result["success"]:
        _summary_state["running"]      = False
        _summary_state["last_status"]  = "done"
        _summary_state["last_message"] = "Summary generated successfully."
        _summary_state["result"]       = {
            "metadata": result["metadata"],
            "summary":  result["summary"],
            "txt_path": result.get("txt_path", ""),
        }
    else:
        _summary_state["running"]      = False
        _summary_state["last_status"]  = "failed"
        _summary_state["last_message"] = result["message"]
        _summary_state["result"]       = None


@router.post("/generate")
async def generate_summary(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    admin: dict = Depends(get_admin_user),
):
    """
    Starts summary generation for a specific GR PDF.
    Admin only.

    Returns immediately — frontend polls /status for completion.
    Result is stored in _summary_state["result"] when done.
    """
    global _summary_state

    # Don't start if already running
    if _summary_state["running"]:
        return {
            "success": False,
            "message": "Summary generation already running.",
            "state":   _summary_state,
        }

    # Validate the file exists
    pdf_path = settings.GRDOCS_PATH / request.filename
    if not pdf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{request.filename}' not found in grdocs folder.",
        )

    # Reset state
    _summary_state.update({
        "running":      True,
        "last_status":  "running",
        "last_message": f"Starting summary for {request.filename}...",
        "current_step": "Initializing",
        "filename":     request.filename,
        "result":       None,
    })

    # Run in background
    background_tasks.add_task(_run_summary_job, str(pdf_path), request.filename)

    return {
        "success": True,
        "message": f"Summary generation started for '{request.filename}'. Poll /api/summary/status.",
        "state":   _summary_state,
    }


@router.get("/status")
async def get_summary_status(
    admin: dict = Depends(get_admin_user),
):
    """
    Returns current summary generation status.
    Frontend polls this every 3 seconds while job runs.
    When last_status is "done", result contains metadata + summary.
    """
    return {
        "success": True,
        "state":   _summary_state,
    }


@router.get("/list")
async def get_summaries_list(
    admin: dict = Depends(get_admin_user),
):
    """
    Returns list of all previously generated summaries.
    Used to populate the past summaries tab on the Summary page.
    """
    summaries = list_summaries()
    return {
        "success":   True,
        "summaries": summaries,
        "total":     len(summaries),
    }


@router.get("/download/{filename}")
async def download_summary(
    filename: str,
    admin: dict = Depends(get_admin_user),
):
    """
    Downloads a summary TXT file.
    Frontend triggers this when admin clicks Download button.

    Args:
        filename : the TXT filename e.g. "GR_2024_transfer_summary.txt"
    """
    file_path = settings.SUMMARIES_PATH / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Summary file '{filename}' not found.",
        )

    # FileResponse streams the file directly to the browser
    # media_type forces browser to download rather than display
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="text/plain",
    )