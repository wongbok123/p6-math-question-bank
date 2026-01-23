#!/usr/bin/env python3
"""
batch_process.py - Batch process multiple PDF exam papers

Usage:
    export GEMINI_API_KEY="your-key"
    python3 batch_process.py                    # Process all unprocessed PDFs
    python3 batch_process.py --year 2025        # Process only 2025 papers
    python3 batch_process.py --pdf "file.pdf"   # Process specific PDF
"""

import argparse
import os
import sys
import time
import subprocess
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).parent))

from database import get_all_schools
from config import PDF_DIR


def get_pdf_info(pdf_path: Path) -> dict:
    """Get PDF info and estimate question/answer page ranges."""
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

    # Parse filename for year and school
    name = pdf_path.stem
    import re
    year_match = re.search(r"(\d{4})", name)
    year = int(year_match.group(1)) if year_match else 2025

    # Extract school name (last part after last hyphen)
    parts = name.split("-")
    school = parts[-1].strip() if len(parts) >= 4 else "Unknown"

    # Estimate answer key pages (usually last 4-8 pages)
    # Heuristic: ~15% of pages are answer keys
    answer_pages = max(4, min(8, total_pages // 6))
    question_end = total_pages - answer_pages

    return {
        "path": pdf_path,
        "name": name,
        "school": school,
        "year": year,
        "total_pages": total_pages,
        "question_pages": f"1-{question_end}",
        "answer_pages": f"{question_end + 1}-{total_pages}",
    }


def process_pdf(pdf_info: dict, dry_run: bool = False) -> bool:
    """Process a single PDF through extraction and verification."""
    print(f"\n{'=' * 70}")
    print(f"Processing: {pdf_info['name']}")
    print(f"School: {pdf_info['school']}, Year: {pdf_info['year']}")
    print(f"Pages: {pdf_info['total_pages']} (Q: {pdf_info['question_pages']}, A: {pdf_info['answer_pages']})")
    print("=" * 70)

    if dry_run:
        print("[DRY RUN] Would process this PDF")
        return True

    pdf_name = pdf_info["path"].name

    # Step 1: Extract questions
    print("\n[STEP 1] Extracting questions...")
    cmd1 = [
        "python3", "gemini_pipeline.py",
        "--pdf", pdf_name,
        "--pages", pdf_info["question_pages"],
    ]
    result1 = subprocess.run(cmd1, capture_output=False)
    if result1.returncode != 0:
        print(f"[ERROR] Question extraction failed")
        return False

    # Brief pause between steps
    time.sleep(2)

    # Step 2: Verify and solve answers
    print("\n[STEP 2] Verifying answers...")
    cmd2 = [
        "python3", "verify_and_solve.py",
        "--pdf", pdf_name,
        "--answer-pages", pdf_info["answer_pages"],
        "--school", pdf_info["school"],
    ]
    result2 = subprocess.run(cmd2, capture_output=False)
    if result2.returncode != 0:
        print(f"[WARNING] Answer verification had issues")

    print(f"\n[DONE] {pdf_info['school']} {pdf_info['year']} processed")
    return True


def main():
    parser = argparse.ArgumentParser(description="Batch process PDF exam papers")
    parser.add_argument("--year", type=int, help="Process only papers from this year")
    parser.add_argument("--pdf", type=str, help="Process specific PDF file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    parser.add_argument("--skip-processed", action="store_true", default=True,
                        help="Skip already processed schools (default: True)")
    args = parser.parse_args()

    # Check API key
    if not os.environ.get("GEMINI_API_KEY"):
        print("[ERROR] GEMINI_API_KEY not set!")
        print("Run: export GEMINI_API_KEY='your-key'")
        sys.exit(1)

    # Get list of PDFs to process
    if args.pdf:
        pdf_path = PDF_DIR / args.pdf
        if not pdf_path.exists():
            pdf_path = Path(args.pdf)
        if not pdf_path.exists():
            print(f"[ERROR] PDF not found: {args.pdf}")
            sys.exit(1)
        pdfs = [pdf_path]
    else:
        pdfs = sorted(PDF_DIR.glob("*.pdf"))

    # Filter by year if specified
    if args.year:
        pdfs = [p for p in pdfs if str(args.year) in p.name]

    # Get already processed schools
    processed_schools = get_all_schools() if args.skip_processed else []

    # Build processing queue
    queue = []
    for pdf_path in pdfs:
        info = get_pdf_info(pdf_path)

        # Check if already processed
        if args.skip_processed and info["school"] in processed_schools:
            print(f"[SKIP] {info['school']} {info['year']} - already processed")
            continue

        queue.append(info)

    if not queue:
        print("No PDFs to process!")
        return

    # Show processing plan
    print("\n" + "=" * 70)
    print("BATCH PROCESSING PLAN")
    print("=" * 70)
    print(f"PDFs to process: {len(queue)}")
    total_pages = sum(p["total_pages"] for p in queue)
    print(f"Total pages: {total_pages}")
    print(f"Estimated time: {total_pages * 3 // 60} - {total_pages * 5 // 60} minutes")
    print("=" * 70)

    for i, info in enumerate(queue, 1):
        print(f"{i:2d}. {info['school']} {info['year']} ({info['total_pages']} pages)")

    if args.dry_run:
        print("\n[DRY RUN] No files processed")
        return

    # Process each PDF
    successful = 0
    failed = 0

    for i, info in enumerate(queue, 1):
        print(f"\n[{i}/{len(queue)}] ", end="")
        try:
            if process_pdf(info):
                successful += 1
            else:
                failed += 1
        except KeyboardInterrupt:
            print("\n[INTERRUPTED] Stopping...")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            failed += 1

        # Pause between PDFs to avoid rate limits
        if i < len(queue):
            print("\nWaiting 5 seconds before next PDF...")
            time.sleep(5)

    # Summary
    print("\n" + "=" * 70)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 70)
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Remaining: {len(queue) - successful - failed}")


if __name__ == "__main__":
    main()
