# backend/scripts/check_ocr.py
# Reusable sanity-check tool — prints extracted text per page so you
# can manually verify it looks correct, for ANY uploaded GR PDF.
# Usage: python scripts/check_ocr.py GR_filename.pdf

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ocr import load_pdf_with_ocr_fallback
from config import settings

if len(sys.argv) < 2:
    print("Usage: python scripts/check_ocr.py <filename.pdf>")
    sys.exit(1)

filename = sys.argv[1]
pdf_path = settings.GRDOCS_PATH / filename

if not pdf_path.exists():
    print(f"File not found: {pdf_path}")
    sys.exit(1)

pages = load_pdf_with_ocr_fallback(str(pdf_path))

for i, page in enumerate(pages):
    ocr_flag = page.metadata.get("ocr_used")
    print(f"\n--- Page {i+1} (OCR used: {ocr_flag}) ---")
    print(page.page_content[:500])