# backend/api/upload.py
# ─────────────────────────────────────────────────────────
# GR Document Upload endpoints.
#
# Endpoints:
#   POST /api/upload        → upload a GR PDF file (admin only)
#   GET  /api/upload/list   → list all uploaded GR files
#   DELETE /api/upload/{filename} → delete a GR file (admin only)
#
# Files are saved to backend/data/grdocs/
# Metadata is saved to MongoDB gr_metadata collection
# ─────────────────────────────────────────────────────────

import sys
import os
import shutil
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import JSONResponse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth.router import get_admin_user, get_current_user
from db.gr_meta import save_gr_metadata, get_all_gr_metadata, delete_gr_metadata, get_gr_stats
from config import settings

router = APIRouter(prefix="/api/upload", tags=["Upload"])

# Only these file types are accepted
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}
# Max file size — 50MB
MAX_FILE_SIZE_MB = 50


@router.post("/")
async def upload_gr_file(
    file: UploadFile = File(...),
    admin: dict = Depends(get_admin_user),
):
    """
    Upload a GR document (PDF/DOC/DOCX).
    Admin only.

    The frontend sends this as multipart/form-data.
    FastAPI handles the parsing automatically via UploadFile.

    Steps:
        1. Validate file extension
        2. Validate file size
        3. Save file to grdocs/ folder
        4. Save metadata to MongoDB
        5. Return confirmation
    """
    # ── Step 1: Validate extension ────────────────────────
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{suffix}' not allowed. Only PDF, DOC, DOCX accepted.",
        )

    # ── Step 2: Read file and check size ──────────────────
    contents = await file.read()
    size_mb   = len(contents) / (1024 * 1024)

    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large ({size_mb:.1f}MB). Maximum allowed is {MAX_FILE_SIZE_MB}MB.",
        )

    size_kb = round(len(contents) / 1024, 1)

    # ── Step 3: Save to disk ──────────────────────────────
    settings.GRDOCS_PATH.mkdir(parents=True, exist_ok=True)
    destination = settings.GRDOCS_PATH / file.filename

    # If file already exists add timestamp suffix to avoid overwrite
    if destination.exists():
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem      = Path(file.filename).stem
        dest_name = f"{stem}_{ts}{suffix}"
        destination = settings.GRDOCS_PATH / dest_name
    else:
        dest_name = file.filename

    with open(destination, "wb") as f:
        f.write(contents)

    # ── Step 4: Count pages (PDF only) ───────────────────
    page_count = 0
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader     = PdfReader(str(destination))
            page_count = len(reader.pages)
        except Exception:
            page_count = 0     # not critical if page count fails

    # ── Step 5: Save metadata to MongoDB ─────────────────
    await save_gr_metadata(
        filename=dest_name,
        uploaded_by=admin["username"],
        file_size_kb=size_kb,
        page_count=page_count,
    )

    return {
        "success":    True,
        "message":    f"File '{dest_name}' uploaded successfully.",
        "filename":   dest_name,
        "size_kb":    size_kb,
        "page_count": page_count,
    }


@router.get("/list")
async def list_uploaded_files(
    current_user: dict = Depends(get_current_user),
):
    """
    Returns list of all uploaded GR files with metadata.
    Available to all logged-in users (not admin only)
    so the embed page and chat page can show available GRs.
    """
    records = await get_all_gr_metadata()

    # Also check which files actually exist on disk
    # MongoDB record might exist but file could have been deleted
    verified = []
    for record in records:
        file_path = settings.GRDOCS_PATH / record["filename"]
        record["exists_on_disk"] = file_path.exists()
        verified.append(record)

    return {
        "success": True,
        "files":   verified,
        "total":   len(verified),
    }


@router.get("/stats")
async def get_upload_stats(
    admin: dict = Depends(get_admin_user),
):
    """
    Returns summary stats for admin dashboard.
    Admin only.
    """
    stats = await get_gr_stats()
    return {"success": True, **stats}


@router.delete("/{filename}")
async def delete_uploaded_file(
    filename: str,
    admin: dict = Depends(get_admin_user),
):
    file_path = settings.GRDOCS_PATH / filename

    if file_path.exists():
        file_path.unlink()

    result = await delete_gr_metadata(filename)

    # Also remove any generated summary files for this GR —
    # otherwise Summaries page keeps showing a summary for a GR that no longer exists
    base_name = Path(filename).stem
    for ext in ("_summary.json", "_summary.txt"):
        summary_file = settings.SUMMARIES_PATH / f"{base_name}{ext}"
        if summary_file.exists():
            summary_file.unlink()

    return {
        "success": True,
        "message": f"File '{filename}' deleted.",
    }