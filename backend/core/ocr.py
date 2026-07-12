# backend/core/ocr.py
# ─────────────────────────────────────────────────────────
# OCR fallback for scanned PDFs.
#
# Problem: PyPDFLoader can only extract text that already
# exists as real characters in a PDF. Scanned GRs (photos of
# pages, no embedded text) return empty strings — this file
# detects that and converts the page to an image, then runs
# Tesseract OCR (English + Marathi) to produce real text.
#
# Called by:
#   core/vectorstore.py → embed_all_pdfs() uses this instead
#                          of raw PyPDFLoader when pages look scanned
# ─────────────────────────────────────────────────────────

import sys
import os
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from pdf2image import convert_from_path
import pytesseract

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# Below this many real characters, a page is treated as scanned/image-only
MIN_REAL_TEXT_CHARS = 20

# Tesseract language codes: eng = English, mar = Marathi (Devanagari)
# Requires the Marathi language pack installed alongside Tesseract itself
OCR_LANGUAGES = "eng+mar"


def _page_looks_scanned(text: str) -> bool:
    """
    Heuristic: if a page's extracted text is empty or near-empty,
    it's almost certainly a scanned image with no real text layer.
    """
    return len(text.strip()) < MIN_REAL_TEXT_CHARS


def _ocr_single_page(pdf_path: str, page_number: int) -> str:
    """
    Converts one specific PDF page to an image, then runs Tesseract OCR.
    page_number is 1-indexed (matches pdf2image's first_page/last_page).

    Returns:
        Recognized text string (may contain OCR errors — this is expected)
    """
    try:
        images = convert_from_path(
            pdf_path,
            first_page=page_number,
            last_page=page_number,
            dpi=300,  # higher DPI improves OCR accuracy, especially for Devanagari
        )
        if not images:
            return ""

        text = pytesseract.image_to_string(images[0], lang=OCR_LANGUAGES)
        return text.strip()

    except Exception as e:
        print(f"  ⚠️ OCR failed on page {page_number}: {e}")
        return ""


def load_pdf_with_ocr_fallback(pdf_path: str) -> list[Document]:
    """
    Loads a PDF page by page. For each page:
        - tries normal text extraction first (fast, accurate when available)
        - if that page looks scanned (near-empty text), falls back to OCR

    This is a drop-in replacement for PyPDFLoader(pdf_path).load() —
    returns the same list[Document] shape, so nothing downstream
    (chunking, embedding, citations) needs to change.

    Returns:
        List of Document objects, one per page, each with
        page_content and metadata including "page" and "ocr_used" (bool)
    """
    loader = PyPDFLoader(pdf_path)
    pages = loader.load()

    result_pages = []
    ocr_page_count = 0

    for page in pages:
        real_text = page.page_content

        if _page_looks_scanned(real_text):
            page_number = page.metadata.get("page", 0) + 1  # PyPDFLoader is 0-indexed
            ocr_text = _ocr_single_page(pdf_path, page_number)

            if ocr_text:
                ocr_page_count += 1
                new_doc = Document(
                    page_content=ocr_text,
                    metadata={**page.metadata, "ocr_used": True},
                )
                result_pages.append(new_doc)
            else:
                # OCR itself found nothing — keep the empty page rather
                # than dropping it, so page numbering stays consistent
                page.metadata["ocr_used"] = True
                page.metadata["ocr_failed"] = True
                result_pages.append(page)
        else:
            page.metadata["ocr_used"] = False
            result_pages.append(page)

    if ocr_page_count > 0:
        print(f"  🔍 OCR applied to {ocr_page_count}/{len(pages)} page(s) in {Path(pdf_path).name}")

    return result_pages