# backend/core/ocr.py
# ─────────────────────────────────────────────────────────
# OCR fallback for scanned PDFs — AND for PDFs with corrupted
# text layers (legacy non-Unicode Marathi fonts like Kruti Dev /
# Shivaji / DV-TT that visually render correctly but extract as
# scrambled Devanagari via PyPDFLoader).
#
# Problem 1: PyPDFLoader can only extract text that already
# exists as real characters in a PDF. Scanned GRs (photos of
# pages, no embedded text) return empty strings.
#
# Problem 2 (NEW): Some GRs use legacy non-Unicode Marathi fonts.
# The PDF's internal font encoding maps glyphs to the WRONG
# Unicode codepoints. The extracted text still LOOKS like
# Devanagari (has matras, consonants, sentence structure) but is
# semantically scrambled — e.g. "विभागीय" comes out as "शवभागीय".
# This is invisible to length-only checks and gets silently fed
# to the LLM, which then hallucinates plausible-sounding but
# completely wrong content.
#
# Both problems are handled the same way: fall back to
# rendering the page as an image and running Tesseract OCR on it,
# which sidesteps the broken font mapping entirely.
#
# Called by:
#   core/vectorstore.py → embed_all_pdfs() uses this instead
#                          of raw PyPDFLoader when pages look scanned
#   core/summarizer.py  → _load_pdf_text() uses this for summaries
# ─────────────────────────────────────────────────────────

import sys
import os
import re
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

# ── Garbled-font detection ────────────────────────────────
# Real Maharashtra GRs almost always contain at least one of these
# common, high-frequency words UNMANGLED — they appear in nearly
# every GR's letterhead, boilerplate, or closing lines. If a page
# has plenty of Devanagari-looking characters but NONE of these
# recognizable words appear, the font encoding is almost certainly
# corrupted (legacy non-Unicode font), even though PyPDFLoader
# successfully extracted "text".
#
# These are deliberately common/boilerplate words, not content
# words — so this check works regardless of what the GR is about.
EXPECTED_MARATHI_ANCHORS = [
    "महाराष्ट्र",       # Maharashtra
    "शासन",             # Government
    "शासन आदेश",        # Government Order
    "विभाग",            # Department
    "दिनांक",           # Date
    "यांच्या",          # (possessive - very common grammatical word)
    "करण्यात",          # "being done/carried out" - extremely common verb form in GRs
]

# Minimum Devanagari character count before we even bother checking
# for anchor words — avoids false positives on near-empty pages
MIN_CHARS_FOR_ANCHOR_CHECK = 40

DEVANAGARI_PATTERN = re.compile(r'[\u0900-\u097F]')


def _page_looks_scanned(text: str) -> bool:
    """
    Heuristic: decides whether a page needs OCR instead of the
    PyPDFLoader-extracted text.

    Two independent checks, either one triggers OCR fallback:

    1. LENGTH CHECK (original): if extracted text is empty or
       near-empty, it's almost certainly a scanned image with no
       real text layer.

    2. ANCHOR-WORD CHECK (new): if the page has a substantial
       amount of Devanagari-looking text but NONE of the common,
       near-universal GR boilerplate words appear anywhere, the
       font encoding is very likely corrupted (legacy non-Unicode
       font). The text LOOKS like Marathi character-by-character
       but is semantically scrambled, which a naive length check
       cannot catch.
    """
    stripped = text.strip()

    # Check 1: too short to be real content
    if len(stripped) < MIN_REAL_TEXT_CHARS:
        return True

    # Check 2: garbled font encoding — plenty of Devanagari-looking
    # characters, but none of the expected common words show up
    devanagari_char_count = len(DEVANAGARI_PATTERN.findall(stripped))
    if devanagari_char_count >= MIN_CHARS_FOR_ANCHOR_CHECK:
        if not any(anchor in stripped for anchor in EXPECTED_MARATHI_ANCHORS):
            return True

    return False


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
        - if that page looks scanned OR has a corrupted font encoding
          (near-empty text, or garbled/unrecognizable Devanagari),
          falls back to OCR

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
