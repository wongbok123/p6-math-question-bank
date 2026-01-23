#!/usr/bin/env python3
"""
reextract_pages.py - Re-extract specific pages that had extraction issues

Usage:
    export GEMINI_API_KEY="your-key"
    python3 reextract_pages.py --pdf "2025-P6-Maths-Prelim Exam-Ai Tong.pdf" --pages 14,19
"""

import argparse
import os
import sys
import time
import gc
from pathlib import Path

import pdfplumber
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from utils.gemini_client import GeminiClient
from database import insert_question, get_connection
from config import PDF_DIR, IMAGES_DIR

DPI = 200


# Focused extraction prompt for re-extraction
REEXTRACT_PROMPT = """Look at this exam page image carefully.

TASK: Extract ALL math questions visible on this page.

For EACH question found, provide:
1. question_number: The Q# shown (e.g., 17, 18, 19)
2. marks: Number of marks (look for [X marks] or (X marks))
3. question_text: The full question text
4. has_parts: true if question has (a), (b), (c) parts
5. parts: If has_parts, list each part separately

OUTPUT FORMAT (JSON):
{
  "questions": [
    {
      "question_number": 17,
      "marks": 2,
      "question_text": "Find the value of...",
      "has_parts": false
    },
    {
      "question_number": 18,
      "marks": 3,
      "question_text": "The figure shows...",
      "has_parts": true,
      "parts": [
        {"part": "a", "text": "(a) Find the area..."},
        {"part": "b", "text": "(b) Find the perimeter..."}
      ]
    }
  ]
}

IMPORTANT:
- Extract EVERY question visible, even partially visible ones
- Look carefully for question numbers (Q17, Q18, 17., 18., etc.)
- Include the marks for each question
- If a question has parts (a), (b), extract each part

Return ONLY valid JSON.
"""


def extract_page(client: GeminiClient, pdf_path: Path, page_num: int, school: str, year: int):
    """Re-extract a single page."""
    print(f"\n[PAGE {page_num}] Extracting...")

    with pdfplumber.open(pdf_path) as pdf:
        if page_num < 1 or page_num > len(pdf.pages):
            print(f"  Invalid page number")
            return []

        page = pdf.pages[page_num - 1]
        img = page.to_image(resolution=DPI)
        image = img.original

        # Save image
        image_path = IMAGES_DIR / f"{school}_{year}_p{page_num:02d}.png"
        image.save(image_path)

        # Extract with Gemini
        result = client.extract_from_image(image, REEXTRACT_PROMPT, page_num)

        if not result.success:
            print(f"  [ERROR] {result.error}")
            return []

        # Parse JSON response
        import json
        import re

        response = result.question_text

        # Find JSON in response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            print(f"  [ERROR] No JSON found in response")
            print(f"  Response: {response[:200]}...")
            return []

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            print(f"  [ERROR] JSON parse error: {e}")
            return []

        questions = data.get("questions", [])
        print(f"  Found {len(questions)} questions")

        extracted = []
        for q in questions:
            qnum = q.get("question_number", 0)
            marks = q.get("marks") or 2  # Default to 2 marks if not specified
            text = q.get("question_text", "")
            has_parts = q.get("has_parts", False)

            # Determine section based on question number
            if qnum <= 15:
                section = "P1A"
                stored_num = qnum
            elif qnum <= 30:
                section = "P1B"
                stored_num = qnum - 15  # Q16->1, Q17->2, etc.
            else:
                section = "P2"
                stored_num = qnum

            if has_parts and q.get("parts"):
                for part in q["parts"]:
                    part_letter = part.get("part", "a")
                    part_text = part.get("text", text)

                    extracted.append({
                        "school": school,
                        "year": year,
                        "section": section,
                        "question_num": stored_num,
                        "pdf_question_num": qnum,
                        "part_letter": part_letter,
                        "marks": marks,
                        "text": part_text,
                        "main_context": text,
                        "image_path": str(image_path),
                        "pdf_page_num": page_num,
                    })
                    print(f"    Q{qnum}({part_letter}): {part_text[:50]}...")
            else:
                extracted.append({
                    "school": school,
                    "year": year,
                    "section": section,
                    "question_num": stored_num,
                    "pdf_question_num": qnum,
                    "part_letter": None,
                    "marks": marks,
                    "text": text,
                    "main_context": None,
                    "image_path": str(image_path),
                    "pdf_page_num": page_num,
                })
                print(f"    Q{qnum}: {text[:50]}...")

        del image
        gc.collect()

        return extracted


def save_questions(questions: list):
    """Save extracted questions to database."""
    for q in questions:
        try:
            insert_question(
                school=q["school"],
                year=q["year"],
                paper_section=q["section"],
                question_num=q["question_num"],
                marks=q["marks"],
                latex_text=q["text"],
                image_path=q["image_path"],
                pdf_question_num=q["pdf_question_num"],
                pdf_page_num=q["pdf_page_num"],
                part_letter=q["part_letter"],
                main_context=q["main_context"],
            )
            print(f"  Saved: {q['section']} Q{q['question_num']}")
        except Exception as e:
            print(f"  [ERROR] Failed to save Q{q['question_num']}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Re-extract specific pages")
    parser.add_argument("--pdf", type=str, required=True, help="PDF filename")
    parser.add_argument("--pages", type=str, required=True, help="Pages to re-extract (comma-separated)")
    parser.add_argument("--save", action="store_true", help="Save to database (default: dry run)")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY not set!")
        sys.exit(1)

    # Find PDF
    pdf_path = PDF_DIR / args.pdf
    if not pdf_path.exists():
        pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"[ERROR] PDF not found: {args.pdf}")
        sys.exit(1)

    # Parse school/year from filename
    import re
    name = pdf_path.stem
    year_match = re.search(r"(\d{4})", name)
    year = int(year_match.group(1)) if year_match else 2025

    # Extract school name (last part after last hyphen)
    parts = name.split("-")
    school = parts[-1].strip() if len(parts) >= 5 else "Unknown"

    print("=" * 60)
    print("RE-EXTRACT SPECIFIC PAGES")
    print("=" * 60)
    print(f"PDF: {pdf_path.name}")
    print(f"School: {school}, Year: {year}")
    print(f"Pages: {args.pages}")
    print(f"Mode: {'SAVE' if args.save else 'DRY RUN'}")
    print("=" * 60)

    client = GeminiClient(api_key=api_key)

    pages = [int(p.strip()) for p in args.pages.split(",")]

    all_questions = []
    for page_num in pages:
        questions = extract_page(client, pdf_path, page_num, school, year)
        all_questions.extend(questions)
        time.sleep(1)  # Rate limit

    print(f"\n{'=' * 60}")
    print(f"SUMMARY: Extracted {len(all_questions)} questions from {len(pages)} pages")
    print("=" * 60)

    if args.save and all_questions:
        print("\nSaving to database...")
        save_questions(all_questions)
        print("Done!")
    elif all_questions:
        print("\n[DRY RUN] Use --save to save to database")


if __name__ == "__main__":
    main()
