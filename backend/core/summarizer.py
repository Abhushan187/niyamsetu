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


def get_llm() -> OllamaLLM:
    """
    OllamaLLM (not ChatOllama) — used here because summary prompts
    work better with the completion-style interface.
    temperature=0.1 allows slight creativity for readable summaries
    while staying grounded in the document.
    """
    return OllamaLLM(
        model=settings.LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0,
        num_predict=1024,
    )


def _load_pdf_text(pdf_path: str) -> str:
    """
    Loads all text from a PDF file.
    Cleans and truncates to fit within LLM context window.

    Args:
        pdf_path : full path to the PDF file

    Returns:
        Cleaned text string, max 12000 characters
    """
    from core.ocr import load_pdf_with_ocr_fallback
    documents = load_pdf_with_ocr_fallback(pdf_path)

   # Join all pages into one text block
    full_text = "\n".join(doc.page_content for doc in documents)

    # Strip distribution list / signature footer before it reaches the LLM.
    # Every GR ends with "प्रत," (or "प्रत:") followed by a recipient list —
    # never contains answerable content, confirmed across 15 real GRs.
    cut_markers = ["प्रत,", "प्रत:", "प्रत :", "प्रत ", "\nप्रत\n"]
    for marker in cut_markers:
        idx = full_text.find(marker)
        if idx != -1:
            full_text = full_text[:idx]
            break

    # Clean whitespace and normalize line breaks
    full_text = clean_text(full_text)

    # Truncate to fit LLM context window safely
    full_text = truncate_for_context(full_text, max_chars=20000)

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
    """
    full_text = _load_pdf_text(pdf_path)
    llm       = get_llm()
    parser    = StrOutputParser()

    metadata_prompt = PromptTemplate.from_template("""
Extract the following information from this Government Resolution document.
Return ONLY valid JSON — no explanation, no markdown, no backticks.
If a field is not found, use null.
Ignore signatures, digital signature blocks, and recipient/distribution lists when extracting these fields.

Required JSON format:
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
        Summary as a formatted text string
    """
    full_text = _load_pdf_text(pdf_path)
    llm       = get_llm()
    parser    = StrOutputParser()

    summary_prompt = PromptTemplate.from_template("""
You are analyzing an official Maharashtra Government document (may be a policy resolution, circular, administrative order, or official letter — not all documents have every section below).

Instructions:
- ONLY use information present in the document text below.
- Do NOT invent, assume, or infer facts not explicitly stated.
- If a section does not apply to this document, write "Not applicable" — do not fabricate content to fill it.
- Ignore any addresses, signatures, or recipient/distribution information if present — focus only on the actual decision or content.

Include these sections (use the exact headings):

1. PURPOSE
Why was this document issued?

2. KEY CONTENT
What are the main decisions, rules, or facts stated?

3. WHO IT AFFECTS
Which people, roles, or offices does this concern, if stated?

4. FINANCIAL DETAILS
Any monetary amounts, budget codes, or allocations — if none, write "Not applicable."

5. DATES / TIMELINE
Any effective dates, deadlines, or tenures mentioned.

Keep each section concise — 1 to 3 sentences maximum.

Document:
{text}
""")
    chain   = summary_prompt | llm | parser
    summary = chain.invoke({"text": full_text})
    return summary.strip()


async def process_gr(pdf_path: str, progress_callback=None) -> dict:
    """
    Full summary pipeline for one GR document.
    Runs metadata extraction and summary generation,
    then saves both as files in the summaries/ folder.

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
            json_path  : path to saved JSON file
            txt_path   : path to saved TXT file
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