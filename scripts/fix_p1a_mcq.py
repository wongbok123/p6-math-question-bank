#!/usr/bin/env python3
"""
fix_p1a_mcq.py - Fix P1A MCQ answers by extracting from BOOKLET A table

This script specifically targets the BOOKLET A grid/table format in answer keys
to extract Q1-Q15 MCQ answers and convert digits (1-4) to letters (A-D).

Usage:
    # Fix all schools
    python3 fix_p1a_mcq.py

    # Fix specific school
    python3 fix_p1a_mcq.py --school "ACS Junior"

    # Dry run (show changes without applying)
    python3 fix_p1a_mcq.py --dry-run
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image

# Load .env file if present
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from utils.gemini_client import GeminiClient
from database import get_connection, get_questions, get_question, update_answer, get_all_schools
from config import IMAGES_DIR

# Directory for answer key images
ANSWER_KEY_DIR = IMAGES_DIR / "answer_keys"


# P1A-specific extraction prompt targeting BOOKLET A table
P1A_EXTRACTION_PROMPT = """This is an ANSWER KEY page from a P6 Math exam.

TASK: Find and extract Paper 1 Booklet A (MCQ) answers.

LOOK FOR these patterns:
1. "Paper 1 Booklet A" header with a table showing Q1-Q15 (or Q1-Q18)
2. A grid/table with question numbers (Q1, Q2...) and single digit answers (1, 2, 3, or 4)
3. Table formats vary:
   - Horizontal: Q1 | Q2 | Q3... in one row, answers 4 | 2 | 1... below
   - Vertical: Q1 | 2 | Q6 | 4 | Q11 | 4 (3 columns of Q/answer pairs)
   - Two rows: Q1-Q10 then Q11-Q15

WHAT TO EXTRACT:
- Question number (1-15 or 1-18)
- The SINGLE DIGIT answer (1, 2, 3, or 4) which represents MCQ option A, B, C, D

OUTPUT FORMAT - Return ONLY valid JSON:
{
  "1": "2",
  "2": "1",
  "3": "3",
  "4": "3",
  "5": "2",
  "6": "4",
  "7": "2",
  "8": "1",
  "9": "1",
  "10": "4",
  "11": "4",
  "12": "3",
  "13": "3",
  "14": "1",
  "15": "3"
}

CRITICAL RULES:
1. Extract ONLY the single digit (1, 2, 3, or 4) for each question
2. Question numbers should be 1-15 (or up to 18)
3. If the page has "Paper 1 Booklet B" but NOT "Booklet A", return error
4. Return ONLY valid JSON, no other text

If you cannot find Paper 1 Booklet A answers on this page, return:
{"error": "No Booklet A table found"}
"""


def normalize_mcq_answer(answer: str) -> str:
    """Convert digit (1-4) to letter (A-D)."""
    answer = str(answer).strip()

    # If already a letter, return uppercase
    if answer.upper() in ['A', 'B', 'C', 'D']:
        return answer.upper()

    # Convert digit to letter
    mapping = {'1': 'A', '2': 'B', '3': 'C', '4': 'D'}

    # Handle formats like "(3)", "[2]", "Option 1"
    match = re.search(r'[(\[]?([1-4])[)\]]?', answer)
    if match:
        digit = match.group(1)
        return mapping.get(digit, answer)

    return mapping.get(answer, answer)


def extract_p1a_from_answer_key(
    client: GeminiClient,
    image_paths: List[Path]
) -> Dict[int, str]:
    """
    Extract Q1-Q15 answers from answer key images.

    Looks for BOOKLET A table and extracts MCQ answers.

    Args:
        client: GeminiClient instance
        image_paths: List of answer key image paths

    Returns:
        Dict mapping question number to letter answer (e.g., {1: "A", 2: "B", ...})
    """
    all_answers: Dict[int, str] = {}

    for img_path in image_paths:
        if not img_path.exists():
            print(f"  [SKIP] Image not found: {img_path}")
            continue

        print(f"  Processing {img_path.name}... ", end="")

        try:
            image = Image.open(img_path)
        except Exception as e:
            print(f"[ERROR] {e}")
            continue

        # Send to Gemini with P1A-specific prompt
        result = client.extract_from_image(image, P1A_EXTRACTION_PROMPT)

        if not result.success:
            print(f"[ERROR] {result.error}")
            continue

        response_text = result.question_text

        # Parse JSON response
        try:
            # Find JSON in response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                answers_dict = json.loads(json_str)

                # Check for error response
                if "error" in answers_dict:
                    print(f"[{answers_dict['error']}]")
                    continue

                # Extract and normalize answers
                found_count = 0
                for q_str, ans in answers_dict.items():
                    try:
                        q_num = int(q_str)
                        if 1 <= q_num <= 18:  # Allow up to Q18
                            normalized = normalize_mcq_answer(ans)
                            if normalized in ['A', 'B', 'C', 'D']:
                                all_answers[q_num] = normalized
                                found_count += 1
                    except (ValueError, TypeError):
                        continue

                print(f"[found {found_count} answers]")

                # If we found answers, we can stop
                if found_count >= 10:  # Reasonable threshold
                    break
            else:
                print("[no JSON found]")

        except json.JSONDecodeError as e:
            print(f"[JSON error: {e}]")
            continue

    return all_answers


def get_answer_key_images(school: str, year: int = 2025) -> List[Path]:
    """Find answer key images for a school."""
    # Handle variations in school name
    school_normalized = school.replace(" ", "_")

    # Look for matching files
    pattern = f"{school}_{year}_answer_*.png"
    images = list(ANSWER_KEY_DIR.glob(pattern))

    # Also try with underscores
    if not images:
        pattern = f"{school_normalized}_{year}_answer_*.png"
        images = list(ANSWER_KEY_DIR.glob(pattern))

    # Sort by page number
    images.sort(key=lambda p: int(re.search(r'p(\d+)', p.name).group(1)) if re.search(r'p(\d+)', p.name) else 0)

    return images


def fix_school_p1a(
    client: GeminiClient,
    school: str,
    year: int = 2025,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Fix P1A answers for a specific school.

    Returns stats dict with counts of updated/skipped/errors.
    """
    stats = {"updated": 0, "skipped": 0, "errors": 0}

    print(f"\n{'='*50}")
    print(f"Processing {school} ({year})")
    print(f"{'='*50}")

    # Find answer key images
    images = get_answer_key_images(school, year)

    if not images:
        print(f"  [WARNING] No answer key images found for {school}")
        print(f"  Expected pattern: {school}_{year}_answer_p*.png")
        stats["errors"] = 15
        return stats

    print(f"  Found {len(images)} answer key images")

    # Extract P1A answers from images
    p1a_answers = extract_p1a_from_answer_key(client, images)

    if not p1a_answers:
        print(f"  [WARNING] Could not extract P1A answers from existing images")
        print(f"  This may mean the Paper 1 Booklet A table is on a page not yet extracted.")
        print(f"  To fix: Re-run verify_and_solve.py with --answer-pages including the MCQ page")
        stats["errors"] = 15
        return stats

    print(f"  Extracted answers: {p1a_answers}")

    # Get current P1A questions from database
    questions = get_questions(school=school, year=year, paper_section='P1A')

    if not questions:
        print(f"  [WARNING] No P1A questions found in database for {school}")
        stats["errors"] = len(p1a_answers)
        return stats

    print(f"  Found {len(questions)} P1A questions in database")

    # Update each question
    for q in questions:
        q_num = q['question_num']
        current_answer = q.get('answer', '')

        if q_num in p1a_answers:
            new_answer = p1a_answers[q_num]

            # Check if update is needed
            if current_answer == new_answer:
                print(f"    Q{q_num}: '{current_answer}' -> '{new_answer}' [no change]")
                stats["skipped"] += 1
            else:
                print(f"    Q{q_num}: '{current_answer}' -> '{new_answer}'", end="")

                if dry_run:
                    print(" [dry-run]")
                    stats["updated"] += 1
                else:
                    # Look up question ID first
                    q = get_question(school, year, 'P1A', q_num)
                    if not q:
                        print(" [NOT FOUND]")
                        stats["errors"] += 1
                        continue

                    # Update database
                    success = update_answer(
                        question_id=q['id'],
                        answer=new_answer,
                        worked_solution="[fix_p1a_mcq]",
                        overwrite=True
                    )

                    if success:
                        print(" [updated]")
                        stats["updated"] += 1
                    else:
                        print(" [FAILED]")
                        stats["errors"] += 1
        else:
            print(f"    Q{q_num}: No answer found in key")
            stats["errors"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Fix P1A MCQ answers by extracting from BOOKLET A table"
    )
    parser.add_argument(
        "--school",
        type=str,
        help="Fix specific school only (default: all schools)"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2025,
        help="Year (default: 2025)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without applying them"
    )
    args = parser.parse_args()

    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY not set!")
        print("Get a free key at: https://aistudio.google.com/app/apikey")
        sys.exit(1)

    print("=" * 60)
    print("FIX P1A MCQ ANSWERS")
    print("Extracts answers from BOOKLET A table in answer keys")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN MODE - no changes will be made]")

    client = GeminiClient(api_key=api_key)

    # Determine which schools to process
    if args.school:
        schools = [args.school]
    else:
        schools = get_all_schools()

    print(f"\nProcessing {len(schools)} school(s)...")

    # Process each school
    total_stats = {"updated": 0, "skipped": 0, "errors": 0}

    for school in schools:
        stats = fix_school_p1a(client, school, args.year, args.dry_run)

        for key in total_stats:
            total_stats[key] += stats[key]

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Updated:  {total_stats['updated']}")
    print(f"Skipped:  {total_stats['skipped']} (already correct)")
    print(f"Errors:   {total_stats['errors']}")

    if args.dry_run:
        print("\n[DRY RUN - no actual changes were made]")
        print("Run without --dry-run to apply changes")


if __name__ == "__main__":
    main()
