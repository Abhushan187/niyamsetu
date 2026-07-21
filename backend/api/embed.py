# backend/api/embed.py
# ─────────────────────────────────────────────────────────
# Embedding endpoints — triggers FAISS vector store creation.
#
# Endpoints:
#   POST /api/embed/start   → start embedding in background (admin only)
#   GET  /api/embed/status  → check if vector store is ready
#
# Why BackgroundTasks?
#   Embedding takes 2-5 minutes depending on number of PDFs.
#   If we ran it synchronously the HTTP request would timeout.
#   BackgroundTasks lets us return "started" immediately,
#   then embedding runs in the background.
#   Frontend polls /status every few seconds to check progress.
# ─────────────────────────────────────────────────────────

import sys
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.router import get_admin_user
from core.vectorstore import embed_all_pdfs, add_pdfs_to_store, is_ready
from core.gr_graph import build_graph
from db.gr_meta import get_all_gr_metadata, mark_as_embedded
from config import settings

router = APIRouter(prefix="/api/embed", tags=["Embedding"])

# ── Embedding state tracker ───────────────────────────────
# Stored in memory — tracks whether embedding is currently running.
# Simple dict instead of a database because:
#   - it only needs to survive the current server session
#   - embedding runs once, not continuously
#   - no need to persist across restarts
_embed_state = {
    "running":      False,
    "last_status":  "idle",         # idle | running | done | failed
    "last_message": "Not started",
    "total_chunks": 0,
    "started_at":   None,
    "finished_at":  None,
    "current_file": "",
    "progress":     0,              # 0-100 percentage
    "total_files":  0,
}


async def _run_embedding_job():
    """
    The actual embedding job — runs in background.
    Updates _embed_state as it progresses so frontend can poll status.

    Steps:
        1. Embed all PDFs into FAISS
        2. Mark each PDF as embedded in MongoDB
        3. Build GR relationship graph
        4. Update final state

    Wrapped in try/except/finally: if ANY step throws an unhandled
    exception, "running" must still reset to False, otherwise the
    frontend sees a permanently stuck progress bar and /start refuses
    to start a new job ("already running") forever, requiring a
    server restart to recover.
    """
    global _embed_state

    _embed_state["running"]     = True
    _embed_state["last_status"] = "running"
    _embed_state["started_at"]  = str(datetime.now(timezone.utc))
    _embed_state["progress"]    = 0

    # Count total files for progress tracking
    pdf_files = list(settings.GRDOCS_PATH.glob("*.pdf"))
    _embed_state["total_files"] = len(pdf_files)

    def on_progress(filename: str, current: int, total: int):
        """Called by embed_all_pdfs() after each PDF is processed."""
        _embed_state["current_file"] = filename
        _embed_state["progress"]     = round((current / total) * 80)  # 0-80%
        _embed_state["last_message"] = f"Embedding {filename} ({current}/{total})"

    try:
        # ── Step 1: Embed PDFs ────────────────────────────
        result = await embed_all_pdfs(progress_callback=on_progress)

        if not result["success"]:
            _embed_state["last_status"]  = "failed"
            _embed_state["last_message"] = result["message"]
            return

        _embed_state["total_chunks"] = result["total_chunks"]
        _embed_state["progress"]     = 85
        _embed_state["last_message"] = "Updating document records..."

        # ── Step 2: Mark files as embedded in MongoDB ─────
        for pdf_file in pdf_files:
            if pdf_file.name not in result.get("failed_files", []):
                await mark_as_embedded(pdf_file.name)

        _embed_state["progress"]     = 90
        _embed_state["last_message"] = "Building GR relationship graph..."

        # ── Step 3: Build GR graph ────────────────────────
        graph_result = await build_graph()

        # ── Step 4: Mark complete ─────────────────────────
        _embed_state["last_status"]  = "done"
        _embed_state["progress"]     = 100
        _embed_state["last_message"] = (
            f"Done. {result['total_chunks']} chunks embedded. "
            f"Graph: {graph_result.get('nodes', 0)} GRs, "
            f"{graph_result.get('edges', 0)} relationships."
        )

    except Exception as e:
        # Catch anything unhandled from steps 1-3 (Mongo write failure,
        # PDF read error in build_graph, etc.) so the job never hangs silently.
        _embed_state["last_status"]  = "failed"
        _embed_state["last_message"] = f"Embedding job crashed: {str(e)}"
        print(f"❌ Embedding job crashed: {e}")

    finally:
        # This ALWAYS runs, success or failure — guarantees the UI
        # never gets stuck showing "running" forever.
        _embed_state["running"]     = False
        _embed_state["finished_at"] = str(datetime.now(timezone.utc))


@router.post("/start")
async def start_embedding(
    background_tasks: BackgroundTasks,
    admin: dict = Depends(get_admin_user),
):
    """
    Starts the embedding pipeline in the background.
    Returns immediately — frontend polls /status for progress.
    Admin only.

    If embedding is already running, returns current status
    without starting a new job.
    """
    global _embed_state

    # Don't start if already running
    if _embed_state["running"]:
        return {
            "success": False,
            "message": "Embedding is already running. Check /status for progress.",
            "state":   _embed_state,
        }

    # Check there are PDFs to embed
    pdf_files = list(settings.GRDOCS_PATH.glob("*.pdf"))
    if not pdf_files:
        return {
            "success": False,
            "message": "No PDF files found. Upload some GR documents first.",
            "state":   _embed_state,
        }

    # Reset state for new run
    _embed_state.update({
        "running":      True,
        "last_status":  "running",
        "last_message": "Starting embedding pipeline...",
        "total_chunks": 0,
        "current_file": "",
        "progress":     0,
        "total_files":  len(pdf_files),
    })

    # Add to background tasks — runs after this function returns
    background_tasks.add_task(_run_embedding_job)

    return {
        "success": True,
        "message": f"Embedding started for {len(pdf_files)} PDF(s). Poll /api/embed/status for progress.",
        "state":   _embed_state,
    }


@router.get("/status")
async def get_embed_status(
    admin: dict = Depends(get_admin_user),
):
    """
    Returns current embedding status.
    Frontend polls this every 3 seconds while embedding runs.

    Response includes:
        running      : bool — is embedding currently in progress
        last_status  : "idle" | "running" | "done" | "failed"
        progress     : 0-100 percentage
        last_message : human readable status message
        vector_ready : bool — is the FAISS index ready to use
    """
    return {
        "success":      True,
        "state":        _embed_state,
        "vector_ready": is_ready(),
    }


# ── Incremental "Add Selected" job state tracker ──────────
# Separate from _embed_state so a full rebuild and a selective
# add can be told apart by the frontend, and don't collide.
_add_state = {
    "running":      False,
    "last_status":  "idle",
    "last_message": "Not started",
    "progress":     0,
    "total_files":  0,
    "current_file": "",
}


async def _run_add_job(filenames: list):
    """
    Background job for incrementally adding selected GRs to the
    existing FAISS index (does NOT rebuild the whole store).
    Wrapped in try/except/finally — same pattern as the full
    rebuild fix — so it can't hang the same way that one did.
    """
    global _add_state

    _add_state["running"]     = True
    _add_state["last_status"] = "running"
    _add_state["progress"]    = 0
    _add_state["total_files"] = len(filenames)

    def on_progress(filename: str, current: int, total: int):
        _add_state["current_file"] = filename
        _add_state["progress"]     = round((current / total) * 80)
        _add_state["last_message"] = f"Embedding {filename} ({current}/{total})"

    try:
        result = await add_pdfs_to_store(filenames, progress_callback=on_progress)

        if not result["success"]:
            _add_state["last_status"]  = "failed"
            _add_state["last_message"] = result["message"]
            return

        _add_state["progress"]     = 90
        _add_state["last_message"] = "Updating document records..."

        for filename in filenames:
            if filename not in result.get("failed_files", []):
                await mark_as_embedded(filename)

        _add_state["progress"]     = 95
        _add_state["last_message"] = "Rebuilding GR relationship graph..."

        graph_result = await build_graph()

        _add_state["last_status"]  = "done"
        _add_state["progress"]     = 100
        _add_state["last_message"] = (
            f"Done. {result['total_chunks']} new chunks added. "
            f"Graph: {graph_result.get('nodes', 0)} GRs, "
            f"{graph_result.get('edges', 0)} relationships."
        )

    except Exception as e:
        _add_state["last_status"]  = "failed"
        _add_state["last_message"] = f"Add job crashed: {str(e)}"
        print(f"❌ Add-to-index job crashed: {e}")

    finally:
        _add_state["running"] = False


class AddFilesRequest(BaseModel):
    filenames: list[str]


@router.post("/add")
async def add_selected_files(
    request: AddFilesRequest,
    background_tasks: BackgroundTasks,
    admin: dict = Depends(get_admin_user),
):
    """
    Incrementally embeds only the selected GR files into the existing
    FAISS index — does not touch or rebuild already-embedded documents.
    Admin only. Returns immediately, poll /api/embed/add-status.
    """
    global _add_state

    if _add_state["running"]:
        return {
            "success": False,
            "message": "An add-to-index job is already running.",
            "state":   _add_state,
        }

    if not request.filenames:
        return {"success": False, "message": "No files selected.", "state": _add_state}

    # Skip files already embedded — avoids silent duplicate vectors
    all_meta = await get_all_gr_metadata()
    embedded_set = {m["filename"] for m in all_meta if m.get("embedded")}
    to_add  = [f for f in request.filenames if f not in embedded_set]
    skipped = [f for f in request.filenames if f in embedded_set]

    if not to_add:
        return {
            "success": False,
            "message": "All selected files are already embedded.",
            "state":   _add_state,
        }

    _add_state.update({
        "running":      True,
        "last_status":  "running",
        "last_message": f"Starting incremental embed for {len(to_add)} file(s)...",
        "progress":     0,
        "total_files":  len(to_add),
        "current_file": "",
    })

    background_tasks.add_task(_run_add_job, to_add)

    msg = f"Adding {len(to_add)} file(s) to the vector store."
    if skipped:
        msg += f" Skipped {len(skipped)} already-embedded file(s): {', '.join(skipped)}."

    return {"success": True, "message": msg, "state": _add_state}


@router.get("/add-status")
async def get_add_status(admin: dict = Depends(get_admin_user)):
    """Frontend polls this every 3s while an incremental add job runs."""
    return {"success": True, "state": _add_state, "vector_ready": is_ready()}