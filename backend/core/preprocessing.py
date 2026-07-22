# backend/core/preprocessing.py
# ─────────────────────────────────────────────────────────
# Document preprocessing — sits between OCR and chunking.
#
# Responsibility: take the raw text/elements that come out of
# core/ocr.py (Tesseract) and clean/restructure them BEFORE they
# reach core/vectorstore.py for chunking + embedding.
#
# This module does NOT do OCR (that's ocr.py's job) and does NOT
# generate embeddings or call the LLM (that's vectorstore.py /
# rag.py / summarizer.py's job). Single responsibility: cleaning
# and structuring text.
#
# Pipeline position:
#   Upload PDF → OCR (Tesseract) → Preprocessing (HERE) →
#   Chunking → Embeddings → Vector Store → RAG
#
# Why this matters for this project specifically:
#   GRs commonly have repeated letterhead/footer boilerplate on
#   every page ("महाराष्ट्र शासन", office addresses, "प्रत माहितीसाठी"
#   distribution lists) which pollutes chunks with noise. Cleaning
#   this before chunking means the embeddings represent actual GR
#   content, not repeated boilerplate — which should improve
#   retrieval relevance and reduce hallucination downstream.
#
# Called by:
#   core/vectorstore.py → embed_all_pdfs() calls preprocess_document()
#                          on each page's text before splitting into chunks
#   core/summarizer.py   → optionally, _load_pdf_text() can also route
#                          through this for cleaner LLM input (not wired
#                          in yet — see note at bottom of file)
# ─────────────────────────────────────────────────────────

import re
from collections import Counter

from unstructured.partition.text import partition_text
from unstructured.cleaners.core import (
    clean_extra_whitespace,
    clean_non_ascii_chars,
    group_broken_paragraphs,
)

# ── Repeated header/footer detection ──────────────────────
# GRs repeat the same letterhead/footer lines on every page
# ("महाराष्ट्र शासन", office address, department name, etc).
# If a line appears on a large fraction of pages, it's almost
# certainly boilerplate, not content — strip it before chunking.
REPEATED_LINE_MIN_PAGE_FRACTION = 0.5   # appears on ≥50% of pages
REPEATED_LINE_MIN_LENGTH        = 4     # ignore very short lines (page numbers, etc — handled separately)

# Common GR boilerplate patterns worth stripping outright,
# regardless of repetition — these carry no semantic content
# for retrieval/summarization purposes.
BOILERPLATE_PATTERNS = [
    r'^\s*पृष्ठ\s*\d+\s*$',           # "Page N" (Marathi)
    r'^\s*page\s*\d+\s*(of\s*\d+)?\s*$',  # "Page N" / "Page N of M" (English)
    r'^\s*-\s*\d+\s*-\s*$',            # "- 3 -" style page numbers
    r'^\s*\d+\s*$',                    # bare page numbers on their own line
]
_BOILERPLATE_RE = [re.compile(p, re.IGNORECASE) for p in BOILERPLATE_PATTERNS]


def _split_into_lines(text: str) -> list[str]:
    """Splits page text into non-empty stripped lines for line-level analysis."""
    return [line.strip() for line in text.split("\n") if line.strip()]


def _detect_repeated_lines(pages_text: list[str]) -> set[str]:
    """
    Scans across all pages of a document and finds lines that repeat
    on a large fraction of pages — these are treated as running
    headers/footers rather than actual content.

    Args:
        pages_text : list of raw page text strings (one per PDF page)

    Returns:
        Set of line strings considered boilerplate/repeated
    """
    if len(pages_text) < 2:
        # Single-page doc — nothing to compare against, skip this step
        return set()

    line_page_counts = Counter()
    for page_text in pages_text:
        # Use a set so a line repeated twice on the SAME page only
        # counts once — we care about cross-page repetition
        unique_lines_this_page = set(_split_into_lines(page_text))
        for line in unique_lines_this_page:
            if len(line) >= REPEATED_LINE_MIN_LENGTH:
                line_page_counts[line] += 1

    threshold = max(2, round(len(pages_text) * REPEATED_LINE_MIN_PAGE_FRACTION))
    repeated = {
        line for line, count in line_page_counts.items()
        if count >= threshold
    }
    return repeated


def _strip_boilerplate_lines(text: str, repeated_lines: set[str]) -> str:
    """
    Removes lines that are either:
        - in the cross-page repeated_lines set (running headers/footers)
        - matched by BOILERPLATE_PATTERNS (page numbers etc.)

    Args:
        text           : page text to clean
        repeated_lines : set of lines identified as repeated across pages

    Returns:
        Text with boilerplate lines removed
    """
    kept_lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            kept_lines.append(line)
            continue
        if stripped in repeated_lines:
            continue
        if any(pattern.match(stripped) for pattern in _BOILERPLATE_RE):
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines)


def _normalize_whitespace(text: str) -> str:
    """
    Collapses excessive whitespace using Unstructured's cleaner,
    then applies a couple of project-specific normalizations on top.
    """
    text = clean_extra_whitespace(text)

    # Collapse 3+ blank lines down to a single paragraph break —
    # Unstructured's cleaner handles inline whitespace well but can
    # still leave multi-blank-line gaps from stripped boilerplate.
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def _rejoin_broken_paragraphs(text: str) -> str:
    """
    OCR output (and some direct-extraction PDFs) frequently breaks a
    single sentence across multiple lines because of how the PDF was
    laid out in columns/justified text. Unstructured's
    group_broken_paragraphs heuristically rejoins lines that look
    like a continuation of the previous sentence rather than a real
    paragraph break.
    """
    try:
        return group_broken_paragraphs(text)
    except Exception:
        # If this fails for any reason, don't block the pipeline —
        # just return the text unchanged and let downstream steps
        # (chunking) handle it with their own separators.
        return text


def preprocess_page(page_text: str, repeated_lines: set[str] | None = None) -> str:
    """
    Cleans a single page's text. This is the per-page entry point,
    used when repeated-line detection has already been computed
    across the whole document (see preprocess_document()).

    Steps:
        1. Strip boilerplate (repeated headers/footers, page numbers)
        2. Rejoin lines that were broken mid-sentence
        3. Normalize whitespace

    Args:
        page_text      : raw text for a single page (from OCR or direct extraction)
        repeated_lines : set of lines known to repeat across the document's
                         pages (pass None / empty set if not yet computed,
                         e.g. for single-page use)

    Returns:
        Cleaned text for this page
    """
    if not page_text or not page_text.strip():
        return ""

    text = page_text
    if repeated_lines:
        text = _strip_boilerplate_lines(text, repeated_lines)

    text = _rejoin_broken_paragraphs(text)
    text = _normalize_whitespace(text)

    return text


def preprocess_document(pages_text: list[str]) -> list[str]:
    """
    Main entry point — cleans an entire document's pages together.

    Doing this at the document level (rather than page-by-page in
    isolation) is what lets us detect and strip repeated
    headers/footers, since that requires comparing across pages.

    Args:
        pages_text : list of raw page text strings, one per PDF page,
                     in page order (typically the page_content of each
                     Document returned by
                     core.ocr.load_pdf_with_ocr_fallback())

    Returns:
        List of cleaned page text strings, same length and order as
        the input — callers should re-attach this to each page's
        existing metadata (source_file, page number, ocr_used, etc.)
        before chunking.

    Note:
        This function intentionally returns plain strings, not
        LangChain Document objects, to keep this module decoupled
        from langchain — core/vectorstore.py is responsible for
        re-wrapping cleaned text into Document objects with the
        original metadata before passing to the text splitter.
    """
    if not pages_text:
        return []

    repeated_lines = _detect_repeated_lines(pages_text)

    cleaned_pages = [
        preprocess_page(page_text, repeated_lines)
        for page_text in pages_text
    ]

    return cleaned_pages


# ── NOTE for future integration with summarizer.py ────────
# core/summarizer.py's _load_pdf_text() currently joins raw OCR
# page text directly. It could optionally call preprocess_document()
# too, for cleaner LLM input on the summary/metadata prompts.
# Left out of this initial pass on purpose — the summarizer prompt
# already got dedicated grounding/refusal instructions to handle
# garbled text, and mixing that fix with this one in the same
# change makes it harder to tell which fix helped if something
# regresses. Revisit once this preprocessing step has been
# validated on the embedding path first.
