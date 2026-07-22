# backend/core/summarizer.py
# ─────────────────────────────────────────────────────────
# GR Summary and Metadata Extraction.
#
# Two LLM calls per document:
#   1. Metadata extraction → returns structured JSON
#      (GR number, department, date, subject, signatory)
#   2. Summary generation  → returns readable paragraphs
#      (purpose, provisions, beneficiaries, deadlines)
#
# Output saved as both JSON and TXT files in summaries/ folder.
# Called by:
#   api/summary.py → triggers this on admin request
#
# ── FIX NOTES (garbled-font / hallucination bug) ──────────
# Previously this file had no grounding instruction telling the
# LLM what to do with unreadable/corrupted text, unlike
# core/rag.py which explicitly says "say exactly: not found".
# Combined with core/ocr.py not catching font-encoding corruption
# (only catching near-empty pages), garbled PDFs (legacy
# non-Unicode Marathi fonts) were silently summarized by the LLM
# hallucinating plausible-but-wrong GR content.
#
# Fixes applied here:
#   1. temperature=0 (was 0.1) — reduces improvisation
#   2. Explicit grounding/refusal instructions in both prompts,
#      matching the pattern already used in core/rag.py
#   3. process_gr() now checks the returned summary/metadata for
#      the refusal marker and surfaces success=False with a clear
#      message instead of silently saving a hallucinated summary
# ─────────────────────────────────────────────────────────

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone

from langchain_community.document_loaders import PyPDFLoader
from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from core.language import clean_text, truncate_for_context

# Marker the LLM is instructed to return verbatim when the source
# text is not usable. Checked in process_gr() to short-circuit
# saving a hallucinated summary/metadata file.
UNREADABLE_MARKER = "DOCUMENT_TEXT_UNREADABLE"


def get_llm() -> OllamaLLM:
    """
    OllamaLLM (not ChatOllama) — used here because summary prompts
    work better with the completion-style interface.
    temperature=0 — deterministic, and reduces the model's tendency
    to "fill in the gaps" with plausible-sounding invented content
    when the source text is garbled or incomplete. (Was 0.1.)
    """
    return OllamaLLM(
        model=settings.LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0,
    )


def _load_pdf_text(pdf_path: str) -> str:
    """
    Loads all text from a PDF file.
    Cleans and truncates to fit within LLM context window.

    Uses load_pdf_with_ocr_fallback(), which now also detects
    garbled/corrupted Devanagari (legacy font encoding issues),
    not just scanned/empty pages — see core/ocr.py.

    Args:
        pdf_path : full path to the PDF file

    Returns:
        Cleaned text string, max 12000 characters
    """
    from core.ocr import load_pdf_with_ocr_fallback
    documents = load_pdf_with_ocr_fallback(pdf_path)

    # Join all pages into one text block
    full_text = "\n".join(doc.page_content for doc in documents)

    # Clean whitespace and normalize line breaks
    full_text = clean_text(full_text)

    # Truncate to fit LLM context window safely
    full_text = truncate_for_context(full_text, max_chars=12000)

    return full_text


async def extract_metadata(pdf_path: str) -> dict:
    """
    Extracts structured metadata from a GR document using LLM.

    Asks the LLM to return valid JSON with these fields:
        gr_number         : the GR reference number
        department        : issuing department name
        issue_date        : date the GR was issued
        subject           : subject/title of the GR
        applicable_region : which region/district this applies to
        signatory         : name and designation of signing authority

    Args:
        pdf_path : path to the PDF

    Returns:
        dict of extracted metadata fields
        Falls back to {"raw_output": "..."} if JSON parsing fails
        Returns {"unreadable": True, ...} if the LLM flags the
        source text as not usable (see UNREADABLE_MARKER)
    """
    full_text = _load_pdf_text(pdf_path)
    llm       = get_llm()
    parser    = StrOutputParser()

    metadata_prompt = PromptTemplate.from_template("""
Extract the following information from this Government Resolution document.
Return ONLY valid JSON — no explanation, no markdown, no backticks.
If a field is not found, use null.

IMPORTANT — read the document text carefully before answering:
If the text below is garbled, corrupted, contains scrambled or
nonsensical Devanagari/English characters, or does not form
coherent readable sentences (this can happen with PDFs that use
broken font encoding), do NOT guess or invent field values.
Instead return exactly this JSON and nothing else:
{{"unreadable": true, "reason": "Document text could not be reliably extracted."}}

Required JSON format (when text IS readable):
{{
  "gr_number": "...",
  "department": "...",
  "issue_date": "...",
  "subject": "...",
  "applicable_region": "...",
  "signatory": "..."
}}

Document:
{text}
""")

    chain = metadata_prompt | llm | parser
    raw   = chain.invoke({"text": full_text})

    # Try to parse as JSON
    # LLMs sometimes add extra text before/after — we strip it
    try:
        # Remove any markdown code fences if present
        cleaned = raw.strip()
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        metadata = json.loads(cleaned)
        return metadata

    except json.JSONDecodeError:
        # If JSON parsing fails, return raw output
        # Frontend handles this gracefully
        return {"raw_output": raw.strip()}


async def generate_summary(pdf_path: str) -> str:
    """
    Generates a structured human-readable summary of a GR document.

    Summary includes:
        1. Purpose          — why this GR was issued
        2. Key Provisions   — what rules/changes it introduces
        3. Beneficiaries    — who is affected
        4. Financial Impact — any monetary implications
        5. Implementation   — how/when it takes effect
        6. Deadlines        — any important dates

    Args:
        pdf_path : path to the PDF

    Returns:
        Summary as a formatted text string.
        Returns the literal UNREADABLE_MARKER string (see top of
        file) if the LLM determines the source text is not usable —
        callers must check for this before treating the result as
        a real summary.
    """
    full_text = _load_pdf_text(pdf_path)
    llm       = get_llm()
    parser    = StrOutputParser()

    summary_prompt = PromptTemplate.from_template(f"""
You are an expert analyst of Maharashtra Government Resolution documents.
Provide a clear, structured summary of this Government Resolution.

IMPORTANT — before summarizing, check whether the document text
below is actually readable. GRs are sometimes extracted from PDFs
with broken font encoding, which produces text that LOOKS like
Devanagari or English but is scrambled and does not form real
words or coherent sentences. If that is the case here, do NOT
guess, do NOT invent a plausible-sounding GR topic — respond with
EXACTLY this single line and nothing else:
{UNREADABLE_MARKER}

Only if the text is genuinely readable, include these sections
(use the exact headings):

1. PURPOSE
What is the reason this resolution was issued?

2. KEY PROVISIONS
What are the main rules, decisions, or changes introduced?

3. BENEFICIARIES / TARGET GROUP
Who does this resolution apply to or benefit?

4. FINANCIAL IMPLICATIONS
Are there any monetary allocations, grants, or financial impacts?

5. IMPLEMENTATION
How and when does this resolution take effect?

6. IMPORTANT DATES / DEADLINES
List any specific dates mentioned.

Keep each section concise — 2 to 4 sentences maximum.
If information for a specific section (not the whole document) is
not available, write "Not specified." — only use {UNREADABLE_MARKER}
if the ENTIRE document text is unreadable/garbled.
Every fact you state must come directly from the document text
below — do not add outside knowledge about Maharashtra GRs in general.

Document:
{{text}}
""")

    chain   = summary_prompt | llm | parser
    summary = chain.invoke({"text": full_text})
    return summary.strip()


async def process_gr(pdf_path: str, progress_callback=None) -> dict:
    """
    Full summary pipeline for one GR document.
    Runs metadata extraction and summary generation,
    then saves both as files in the summaries/ folder.

    NOW ALSO: checks whether either the metadata or the summary
    came back flagged as unreadable (garbled/corrupted source
    text) and, if so, returns success=False with a clear message
    instead of silently saving a hallucinated result. This is the
    key fix for the "confidently wrong summary" bug — even if
    OCR fallback in core/ocr.py somehow still lets a garbled page
    through, this is a second line of defense at the LLM-output
    level.

    Args:
        pdf_path          : path to the PDF
        progress_callback : optional function called with status string
                           e.g. progress_callback("Extracting metadata...")

    Returns:
        dict with:
            success    : bool
            message    : status message
            metadata   : extracted metadata dict
            summary    : summary text string
            json_path  : path to saved JSON file (only if success)
            txt_path   : path to saved TXT file (only if success)
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        return {
            "success": False,
            "message": f"File not found: {pdf_path.name}",
            "metadata": {},
            "summary": "",
        }

    try:
        # ── Step 1: Extract metadata ──────────────────────
        if progress_callback:
            progress_callback("Extracting metadata...")

        metadata = await extract_metadata(str(pdf_path))

        # ── Step 2: Generate summary ──────────────────────
        if progress_callback:
            progress_callback("Generating summary...")

        summary = await generate_summary(str(pdf_path))

        # ── Step 2.5: Bail out if source text was unreadable ──
        # Catches garbled-font PDFs that slipped past OCR detection,
        # or pages where OCR itself produced low-quality output.
        metadata_flagged_unreadable = isinstance(metadata, dict) and metadata.get("unreadable") is True
        summary_flagged_unreadable  = UNREADABLE_MARKER in summary

        if metadata_flagged_unreadable or summary_flagged_unreadable:
            if progress_callback:
                progress_callback("Document text could not be reliably read.")
            return {
                "success": False,
                "message": (
                    f"Could not generate a reliable summary for {pdf_path.name} — "
                    "the extracted text appears garbled or corrupted (this can happen "
                    "with PDFs using legacy/non-Unicode fonts). Try re-scanning or "
                    "re-exporting the PDF, or flag it for manual review."
                ),
                "metadata": metadata,
                "summary": summary,
            }

        # ── Step 3: Save outputs ──────────────────────────
        if progress_callback:
            progress_callback("Saving report...")

        settings.SUMMARIES_PATH.mkdir(parents=True, exist_ok=True)
        base_name = pdf_path.stem

        # Save as JSON — for programmatic use
        result_data = {
            "filename":     pdf_path.name,
            "processed_at": str(datetime.now(timezone.utc)),
            "metadata":     metadata,
            "summary":      summary,
        }

        json_path = settings.SUMMARIES_PATH / f"{base_name}_summary.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=4, ensure_ascii=False)

        # Save as TXT — for human reading and download
        txt_path = settings.SUMMARIES_PATH / f"{base_name}_summary.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"GR DOCUMENT: {pdf_path.name}\n")
            f.write(f"Processed: {result_data['processed_at']}\n")
            f.write("=" * 60 + "\n\n")
            f.write("METADATA\n")
            f.write("-" * 40 + "\n")
            f.write(json.dumps(metadata, indent=2, ensure_ascii=False))
            f.write("\n\n" + "=" * 60 + "\n\n")
            f.write("SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(summary)

        return {
            "success":   True,
            "message":   "Summary generated successfully.",
            "metadata":  metadata,
            "summary":   summary,
            "json_path": str(json_path),
            "txt_path":  str(txt_path),
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Summary generation failed: {str(e)}",
            "metadata": {},
            "summary": "",
        }


def list_summaries() -> list:
    """
    Returns all previously generated summaries.
    Used on the admin Summaries page to show past reports.

    Returns:
        List of dicts with summary info, newest first
    """
    if not settings.SUMMARIES_PATH.exists():
        return []

    summaries = []

    for json_file in sorted(
        settings.SUMMARIES_PATH.glob("*_summary.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,           # newest first
    ):
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)

            meta = data.get("metadata", {})

            summaries.append({
                "filename":     data.get("filename", json_file.name),
                "processed_at": data.get("processed_at", ""),
                "subject":      meta.get("subject", "N/A"),
                "department":   meta.get("department", "N/A"),
                "gr_number":    meta.get("gr_number", "N/A"),
                "txt_path":     str(json_file).replace("_summary.json", "_summary.txt"),
                "json_path":    str(json_file),
            })

        except Exception:
            # Skip corrupted files silently
            pass

    return summaries