#!/usr/bin/env python3
"""
gemini_test.py - Test PDF extraction using Gemini API

This script:
1. Opens a PDF with pdfplumber
2. Converts pages to images
3. Sends to Gemini for vision-based extraction
4. Prints extracted content

No heavy local models - all processing happens in the cloud.

Usage:
    export GEMINI_API_KEY="your-api-key"
    python gemini_test.py [pdf_path] [start_page] [num_pages]

Example:
    python gemini_test.py "pdfs/2025-P6-Maths-Prelim Exam-St Nicholas.pdf" 2 3
"""

import gc
import sys
import os
from pathlib import Path

import pdfplumber
from PIL import Image
import psutil

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.gemini_client import GeminiClient, GENERAL_EXTRACTION_PROMPT


def get_memory():
    """Get current memory usage."""
    mem = psutil.virtual_memory()
    return f"{mem.percent:.1f}% ({mem.available/1024**3:.1f}GB free)"


def pdf_page_to_image(page, dpi: int = 150) -> Image.Image:
    """Convert a pdfplumber page to PIL Image."""
    # Render page to image
    img = page.to_image(resolution=dpi)
    return img.original  # Returns PIL Image


def test_gemini_extraction(
    pdf_path: str,
    start_page: int = 1,
    num_pages: int = 2,
    dpi: int = 150
):
    """
    Test Gemini extraction on PDF pages.

    Args:
        pdf_path: Path to PDF file
        start_page: First page to process (1-indexed)
        num_pages: Number of pages to process
        dpi: Resolution for PDF rendering
    """
    print("=" * 60)
    print("GEMINI PDF EXTRACTION TEST")
    print("=" * 60)

    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("\n[ERROR] GEMINI_API_KEY not set!")
        print("Get a free API key at: https://aistudio.google.com/app/apikey")
        print("Then run: export GEMINI_API_KEY='your-key-here'")
        return False

    print(f"\n[INIT] Memory: {get_memory()}")

    # Verify file exists
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"[ERROR] File not found: {pdf_path}")
        return False

    print(f"[INFO] File: {pdf_file.name}")
    print(f"[INFO] Size: {pdf_file.stat().st_size / 1024:.1f} KB")

    # Initialize Gemini client
    print("\n[INIT] Connecting to Gemini API...")
    try:
        client = GeminiClient(api_key=api_key)
        if not client.test_connection():
            print("[ERROR] Gemini connection test failed!")
            return False
        print("[OK] Gemini connected successfully")
    except Exception as e:
        print(f"[ERROR] Failed to initialize Gemini: {e}")
        return False

    print(f"[INFO] Memory after Gemini init: {get_memory()}")

    # Open PDF
    print(f"\n[PDF] Opening {pdf_file.name}...")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            print(f"[PDF] Total pages: {total_pages}")

            # Adjust page range
            start_idx = max(0, start_page - 1)
            end_idx = min(start_idx + num_pages, total_pages)
            pages_to_process = range(start_idx, end_idx)

            print(f"[INFO] Processing pages {start_page} to {start_page + len(pages_to_process) - 1}")
            print(f"[INFO] Memory: {get_memory()}")

            for page_idx in pages_to_process:
                page_num = page_idx + 1
                print(f"\n{'─' * 50}")
                print(f"PAGE {page_num}/{total_pages}")
                print(f"{'─' * 50}")

                # Convert page to image
                print(f"[RENDER] Converting page to image (DPI={dpi})...")
                page = pdf.pages[page_idx]
                image = pdf_page_to_image(page, dpi=dpi)
                print(f"[RENDER] Image size: {image.size[0]}x{image.size[1]}")
                print(f"[RENDER] Memory: {get_memory()}")

                # Send to Gemini
                print(f"[GEMINI] Sending to Gemini for extraction...")
                result = client.extract_from_image(
                    image=image,
                    prompt=GENERAL_EXTRACTION_PROMPT,
                    page_number=page_num
                )

                if result.success:
                    print(f"[GEMINI] ✓ Extraction successful!")
                    print(f"\n--- EXTRACTED CONTENT ---")
                    # Limit output for readability
                    content = result.question_text
                    if len(content) > 2000:
                        print(content[:2000])
                        print(f"\n... [truncated, {len(content)} total chars]")
                    else:
                        print(content)
                    print(f"--- END ---\n")
                else:
                    print(f"[GEMINI] ✗ Extraction failed: {result.error}")

                # Cleanup
                del image
                gc.collect()
                print(f"[CLEANUP] Memory: {get_memory()}")

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

    print(f"\n{'=' * 60}")
    print("[DONE] Test completed!")
    print(f"[FINAL] Memory: {get_memory()}")
    print("=" * 60)
    return True


def main():
    """Main entry point."""
    # Defaults
    default_pdf = "pdfs/2025-P6-Maths-Prelim Exam-St Nicholas.pdf"

    # Parse args
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else default_pdf
    start_page = int(sys.argv[2]) if len(sys.argv) > 2 else 2  # Skip cover page
    num_pages = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    success = test_gemini_extraction(pdf_path, start_page, num_pages)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
