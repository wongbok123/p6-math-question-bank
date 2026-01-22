#!/usr/bin/env python3
"""
safe_test.py - Memory-safe PDF test script

This script tests basic PDF text extraction without loading heavy models
(no PaddleOCR, no Ollama). Used to verify PDF handling works before
adding model dependencies.

Usage:
    python safe_test.py [pdf_path] [max_pages]

Example:
    python safe_test.py pdfs/2025-P6-Maths-Prelim\ Exam-St\ Nicholas.pdf 3
"""

import gc
import sys
import psutil
import pdfplumber
from pathlib import Path

# Safety threshold - abort if memory exceeds this percentage
MEMORY_THRESHOLD = 70.0


def get_memory_info():
    """Get current memory usage stats."""
    mem = psutil.virtual_memory()
    return {
        "percent": mem.percent,
        "available_gb": mem.available / (1024 ** 3),
        "used_gb": mem.used / (1024 ** 3),
        "total_gb": mem.total / (1024 ** 3),
    }


def format_memory(info):
    """Format memory info for display."""
    return f"{info['percent']:.1f}% used, {info['available_gb']:.2f}GB free"


def check_memory_safe():
    """Check if memory usage is below threshold. Returns True if safe."""
    info = get_memory_info()
    if info["percent"] > MEMORY_THRESHOLD:
        print(f"\n[WARNING] Memory at {info['percent']:.1f}% - exceeds {MEMORY_THRESHOLD}% threshold!")
        return False
    return True


def safe_test(pdf_path: str, max_pages: int = 3):
    """
    Safely test PDF text extraction with memory monitoring.

    Args:
        pdf_path: Path to PDF file
        max_pages: Maximum pages to process (default: 3)
    """
    print("=" * 60)
    print("SAFE PDF TEST - Memory-Safe Mode")
    print("=" * 60)

    # Initial memory check
    mem_info = get_memory_info()
    print(f"\n[START] Memory: {format_memory(mem_info)}")

    if not check_memory_safe():
        print("[ABORT] Memory too high before starting. Close some apps and retry.")
        return False

    # Verify file exists
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"[ERROR] File not found: {pdf_path}")
        return False

    print(f"\n[INFO] File: {pdf_file.name}")
    print(f"[INFO] Size: {pdf_file.stat().st_size / 1024:.1f} KB")
    print(f"[INFO] Processing up to {max_pages} page(s)")

    try:
        # Open PDF with pdfplumber (lightweight)
        with pdfplumber.open(pdf_path) as pdf:
            print(f"\n[LOADED] Memory: {format_memory(get_memory_info())}")
            print(f"[INFO] Total pages in PDF: {len(pdf.pages)}")

            if not check_memory_safe():
                print("[ABORT] Memory spike after loading PDF.")
                return False

            pages_to_process = min(max_pages, len(pdf.pages))

            for i in range(pages_to_process):
                print(f"\n{'─' * 50}")
                print(f"Processing Page {i + 1}/{pages_to_process}")
                print(f"{'─' * 50}")

                # Memory check before each page
                if not check_memory_safe():
                    print(f"[ABORT] Memory exceeded at page {i + 1}")
                    return False

                page = pdf.pages[i]

                # Extract text
                text = page.extract_text() or ""
                char_count = len(text)
                line_count = text.count('\n') + 1 if text else 0

                print(f"[EXTRACTED] {char_count} chars, {line_count} lines")

                # Show preview (first 500 chars)
                if text:
                    preview = text[:500]
                    if len(text) > 500:
                        preview += "\n... [truncated]"
                    print(f"\n--- Text Preview ---\n{preview}")
                else:
                    print("[NOTE] No text extracted (page may be image-only)")

                # Extract tables if any
                tables = page.extract_tables()
                if tables:
                    print(f"\n[TABLES] Found {len(tables)} table(s)")
                    for j, table in enumerate(tables[:2]):  # Show max 2 tables
                        print(f"  Table {j + 1}: {len(table)} rows")

                # Explicit cleanup after each page
                del text
                if tables:
                    del tables
                gc.collect()

                print(f"\n[PAGE {i + 1} DONE] Memory: {format_memory(get_memory_info())}")

        # Final cleanup
        gc.collect()

        print(f"\n{'=' * 60}")
        print("[SUCCESS] PDF test completed!")
        print(f"[FINAL] Memory: {format_memory(get_memory_info())}")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        gc.collect()
        return False


def main():
    """Main entry point with CLI argument handling."""
    # Default test file
    default_pdf = "pdfs/2025-P6-Maths-Prelim Exam-St Nicholas.pdf"

    # Parse arguments
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else default_pdf
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    # Run test
    success = safe_test(pdf_path, max_pages)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
