#!/usr/bin/env python3
"""
parse_answers.py - Extract and link answers from answer key pages

Processes answer key pages from PDFs and links extracted answers
to questions already in the database.

Usage:
    export GEMINI_API_KEY="your-key"
    python parse_answers.py --pdf "2025-P6-Maths-Prelim Exam-St Nicholas.pdf"
"""

import gc
import os
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import pdfplumber
from PIL import Image
import psutil

sys.path.insert(0, str(Path(__file__).parent))

from utils.gemini_client import GeminiClient
from database import get_questions, get_question, update_answer, get_connection
from config import PDF_DIR, IMAGES_DIR

DPI = 200

# Specialized prompt for answer extraction
ANSWER_KEY_PROMPT = """This is an ANSWER KEY page from a P6 Math exam.

Extract ALL answers shown. For each question number, provide:
1. Question number (just the number)
2. The FINAL ANSWER (look for boxed values, "Ans:", or the last result)
3. Working steps if shown

IMPORTANT:
- For MCQ questions, the answer is a single letter (A, B, C, or D)
- For calculation questions, extract the final numerical answer
- Include units if shown ($, %, cm, etc.)

Format EXACTLY like this:
Q1: A
Q2: B
Q3: $45.60
Q4: 3:5
Q5: 25%
Q6:
Working: 100 ÷ 4 = 25, 25 × 3 = 75
Answer: 75

Extract EVERY answer visible on this page. Be thorough and precise."""


@dataclass
class ParsedAnswer:
    """Parsed answer from Gemini response."""
    question_num: int
    answer: str
    working: Optional[str] = None


def get_memory():
    mem = psutil.virtual_memory()
    return f"{mem.percent:.1f}%"


def parse_school_from_filename(filename: str) -> Tuple[str, int]:
    """Extract school name and year from PDF filename."""
    name = Path(filename).stem
    year_match = re.search(r"(\d{4})", name)
    year = int(year_match.group(1)) if year_match else 2025
    parts = name.split("-")
    school = parts[-1].strip() if parts else "Unknown"
    return school, year


def is_valid_mcq_answer(answer: str) -> bool:
    """Check if answer is a valid MCQ response (A, B, C, or D)."""
    if not answer:
        return False
    clean = answer.strip().upper()
    # Allow single letter or with parentheses like "(A)" or "A)"
    if clean in ['A', 'B', 'C', 'D']:
        return True
    if clean in ['(A)', '(B)', '(C)', '(D)', 'A)', 'B)', 'C)', 'D)']:
        return True
    # Also allow numbered options (1, 2, 3, 4) for some papers
    if clean in ['1', '2', '3', '4']:
        return True
    return False


def normalize_mcq_answer(answer: str) -> str:
    """Normalize MCQ answer to single uppercase letter (convert 1→A, 2→B, etc.)."""
    clean = answer.strip().upper()
    # Extract just the letter or number
    match = re.match(r'[\(\[]?([A-D1-4])[\)\]]?', clean)
    if match:
        char = match.group(1)
        # Convert numeric to letter: 1→A, 2→B, 3→C, 4→D
        num_to_letter = {'1': 'A', '2': 'B', '3': 'C', '4': 'D'}
        return num_to_letter.get(char, char)
    return answer


def parse_answer_response(response: str, section_hint: str = "") -> List[ParsedAnswer]:
    """Parse Gemini's answer extraction response.

    Args:
        response: Raw response from Gemini
        section_hint: Optional section hint (P1A, P1B, P2) for validation
    """
    answers = []

    # Split by lines and process
    lines = response.strip().split('\n')
    current_q = None
    current_answer = None
    current_working = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for question number pattern: Q1:, Q2:, etc.
        q_match = re.match(r'^Q(\d+)\s*[:\-]?\s*(.*)$', line, re.IGNORECASE)

        if q_match:
            # Save previous question if exists
            if current_q is not None and current_answer:
                answers.append(ParsedAnswer(
                    question_num=current_q,
                    answer=current_answer.strip(),
                    working='\n'.join(current_working) if current_working else None
                ))

            current_q = int(q_match.group(1))
            rest = q_match.group(2).strip()

            # Check if answer is on same line
            if rest and not rest.lower().startswith('working'):
                current_answer = rest
            else:
                current_answer = None
            current_working = []

        elif line.lower().startswith('answer:'):
            current_answer = line.split(':', 1)[1].strip()

        elif line.lower().startswith('working:'):
            current_working.append(line.split(':', 1)[1].strip())

        elif current_q is not None and not current_answer:
            # Might be a continuation of answer
            if line and not line.startswith('-'):
                current_answer = line

    # Save last question
    if current_q is not None and current_answer:
        answers.append(ParsedAnswer(
            question_num=current_q,
            answer=current_answer.strip(),
            working='\n'.join(current_working) if current_working else None
        ))

    return answers


def determine_section_for_answer(question_num: int, answer: str, page_text: str = "") -> Optional[str]:
    """Determine which section an answer belongs to based on question number and answer format.

    Paper structure:
    - P1A (MCQ): Q1-10 (1 mark), Q11-18 (2 marks) - answers are A/B/C/D
    - P1B: Q1-5 (2 marks), Q6-15 (3-5 marks) - numeric/text answers
    - P2: Q1-5 (2 marks), Q6-17 (3-5 marks) - numeric/text answers

    Returns the most likely section or None if unclear.
    """
    is_mcq = is_valid_mcq_answer(answer)

    # Check page text for section markers
    page_lower = page_text.lower()
    if "booklet a" in page_lower or "paper 1a" in page_lower:
        return "P1A" if is_mcq else None
    if "booklet b" in page_lower or "paper 1b" in page_lower:
        return "P1B"
    if "paper 2" in page_lower:
        return "P2"

    # Infer from answer format and question number
    if is_mcq:
        # MCQ answers (A/B/C/D) belong to P1A
        if question_num <= 18:
            return "P1A"
    else:
        # Non-MCQ could be P1B or P2
        # P1B typically has Q1-15, P2 has Q1-17
        # Without more context, we can't distinguish
        # Return None to let caller try both
        return None

    return None


def detect_answer_key_pages(pdf_path: Path) -> List[int]:
    """Detect which pages are likely answer key pages."""
    answer_pages = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = (page.extract_text() or "").lower()

            # Check for strong answer key indicators (explicit headers)
            strong_markers = [
                "answer key", "marking scheme", "suggested answers",
                "model answer", "mark scheme"
            ]
            if any(marker in text for marker in strong_markers):
                answer_pages.append(i + 1)
                continue

            # Check for dense Q1, Q2, Q3 patterns (typical of answer sheets)
            # But NOT if page has blank answer lines (which indicates question page)
            has_blank_answers = bool(re.search(r'ans\s*:\s*_+', text))
            if has_blank_answers:
                continue  # This is a question page, not answer key

            # Check for tabular answer format: multiple Q#: answer patterns
            answer_pattern_count = len(re.findall(r'q\s*\d+\s*[:\s]+(?:[abcd]|\$?\d)', text))
            if answer_pattern_count >= 5:
                answer_pages.append(i + 1)
                continue

            # Check for dense MCQ answers (A B C D patterns close together)
            if text.count("q1") + text.count("q2") + text.count("q3") >= 2:
                mcq_pattern = re.search(r'\b[abcd]\b.*\b[abcd]\b.*\b[abcd]\b', text)
                if mcq_pattern:
                    answer_pages.append(i + 1)

    # If no pages detected, assume last 10% of PDF (conservative)
    if not answer_pages:
        total = len(pdf.pages)
        start = int(total * 0.9)
        answer_pages = list(range(start + 1, total + 1))

    return answer_pages


def process_answer_pages(
    pdf_path: Path,
    client: GeminiClient,
    school: str,
    year: int,
    page_numbers: Optional[List[int]] = None
) -> Dict[str, int]:
    """Process answer key pages and update database."""

    stats = {"pages": 0, "answers_found": 0, "answers_linked": 0, "errors": []}

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

        # Detect or use provided page numbers
        if page_numbers is None:
            page_numbers = detect_answer_key_pages(pdf_path)

        print(f"[INFO] Processing answer key pages: {page_numbers}")

        for page_num in page_numbers:
            if page_num < 1 or page_num > total_pages:
                continue

            print(f"\n[PAGE {page_num}] ", end="")

            page = pdf.pages[page_num - 1]
            page_text = page.extract_text() or ""
            img = page.to_image(resolution=DPI)
            image = img.original

            # Send to Gemini
            result = client.extract_from_image(image, ANSWER_KEY_PROMPT, page_num)

            if result.success:
                print(f"[OK] ", end="")

                # Parse answers
                answers = parse_answer_response(result.question_text)
                print(f"Found {len(answers)} answers")

                stats["answers_found"] += len(answers)

                # Detect section from page text for better matching
                page_lower = page_text.lower()
                page_section_hint = None
                if "paper 2" in page_lower:
                    page_section_hint = "P2"
                elif "booklet b" in page_lower or "paper 1b" in page_lower:
                    page_section_hint = "P1B"
                elif "booklet a" in page_lower or "paper 1a" in page_lower:
                    page_section_hint = "P1A"

                # Link to database with section-aware matching
                for ans in answers:
                    answer_value = ans.answer
                    linked = False

                    # Determine likely section based on answer format
                    inferred_section = determine_section_for_answer(
                        ans.question_num, ans.answer, page_text
                    )

                    # If it's an MCQ answer, normalize it
                    if is_valid_mcq_answer(answer_value):
                        answer_value = normalize_mcq_answer(answer_value)
                        # MCQ answers should only go to P1A
                        sections_to_try = ["P1A"]
                    elif page_section_hint == "P2":
                        # On Paper 2 answer page - only try P2 for Q1-17
                        # Don't fall back to P1B to avoid cross-contamination
                        sections_to_try = ["P2"]
                    elif ans.question_num >= 16 and ans.question_num <= 30:
                        # Q16-30 without Paper 2 marker = P1B (Q16→Q1, Q17→Q2, etc.)
                        # Don't fall back to P2 to avoid cross-contamination
                        sections_to_try = ["P1B"]
                    elif page_section_hint:
                        # Use page section hint as priority
                        sections_to_try = [page_section_hint]
                        # Add fallbacks for non-MCQ
                        for fallback in ["P1B", "P2"]:
                            if fallback != page_section_hint:
                                sections_to_try.append(fallback)
                    elif inferred_section:
                        # Use inferred section first
                        sections_to_try = [inferred_section]
                        # Add fallbacks for non-MCQ
                        if inferred_section not in ["P1B", "P2"]:
                            sections_to_try.extend(["P1B", "P2"])
                    else:
                        # Try P1B and P2 for non-MCQ answers
                        # (Don't try P1A for non-MCQ - that would be a mismatch)
                        sections_to_try = ["P1B", "P2"]

                    for section in sections_to_try:
                        # For P1B answers, the answer key shows Q16-30 but DB stores Q1-15
                        actual_question_num = ans.question_num
                        if section == "P1B" and ans.question_num > 15:
                            actual_question_num = ans.question_num - 15

                        # Look up question ID first
                        q = get_question(school, year, section, actual_question_num)
                        if not q:
                            continue

                        success = update_answer(
                            question_id=q['id'],
                            answer=answer_value,
                            worked_solution=ans.working,
                            overwrite=False,
                        )
                        if success:
                            # Show the PDF question number for P1B for clarity
                            if section == "P1B" and ans.question_num > 15:
                                display_str = f"Q{ans.question_num}->Q{actual_question_num} ({section})"
                            else:
                                display_str = f"Q{actual_question_num} ({section})"
                            answer_preview = answer_value[:30] if len(answer_value) > 30 else answer_value
                            print(f"    {display_str}: {answer_preview}")
                            stats["answers_linked"] += 1
                            linked = True
                            break

                    if not linked:
                        # Debug: show what sections we tried
                        print(f"    Q{ans.question_num}: [NO MATCH in {sections_to_try}] {answer_value[:20]}...")

            else:
                print(f"[ERROR] {result.error}")
                stats["errors"].append(f"Page {page_num}: {result.error}")

            stats["pages"] += 1

            del image
            gc.collect()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Parse answer keys and link to questions")
    parser.add_argument("--pdf", type=str, required=True, help="PDF file to process")
    parser.add_argument("--pages", type=str, help="Specific pages (e.g., 39-48)")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY not set!")
        sys.exit(1)

    print("=" * 60)
    print("ANSWER KEY PARSER")
    print("=" * 60)

    # Find PDF
    pdf_path = PDF_DIR / args.pdf
    if not pdf_path.exists():
        pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"[ERROR] PDF not found: {args.pdf}")
        sys.exit(1)

    school, year = parse_school_from_filename(pdf_path.name)
    print(f"[INFO] School: {school}, Year: {year}")
    print(f"[INFO] Memory: {get_memory()}")

    # Parse page range
    page_numbers = None
    if args.pages:
        try:
            start, end = map(int, args.pages.split("-"))
            page_numbers = list(range(start, end + 1))
        except:
            print(f"[ERROR] Invalid page range: {args.pages}")
            sys.exit(1)

    # Init Gemini
    print("\n[INIT] Connecting to Gemini...")
    client = GeminiClient(api_key=api_key)

    # Process
    stats = process_answer_pages(pdf_path, client, school, year, page_numbers)

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"Pages processed: {stats['pages']}")
    print(f"Answers found: {stats['answers_found']}")
    print(f"Answers linked to DB: {stats['answers_linked']}")
    print(f"Errors: {len(stats['errors'])}")

    # Show sample linked answers
    print("\n[SAMPLE] Questions with answers:")
    questions = get_questions(school=school, year=year)
    with_answers = [q for q in questions if q.get('answer')]
    for q in with_answers[:5]:
        print(f"  {q['paper_section']} Q{q['question_num']}: {q['answer']}")


if __name__ == "__main__":
    main()
