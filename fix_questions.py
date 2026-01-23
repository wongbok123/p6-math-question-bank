#!/usr/bin/env python3
"""
fix_questions.py - Fix specific extraction issues

Usage:
    # Re-extract specific pages for a school
    python fix_questions.py --school "Ai Tong" --pages 14,15,29

    # Delete and re-extract a specific question
    python fix_questions.py --school "Ai Tong" --delete-question P2_0

    # Fix question number (e.g., Q0 should be Q8)
    python fix_questions.py --school "Ai Tong" --renumber P2_0 P2_8
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database import get_connection, get_questions
from config import PDF_DIR, IMAGES_DIR


def delete_question(school: str, section: str, question_num: int, part_letter: str = None):
    """Delete a specific question from database."""
    with get_connection() as conn:
        if part_letter:
            cursor = conn.execute(
                """DELETE FROM questions
                   WHERE school = ? AND paper_section = ? AND question_num = ? AND part_letter = ?""",
                (school, section, question_num, part_letter)
            )
        else:
            cursor = conn.execute(
                """DELETE FROM questions
                   WHERE school = ? AND paper_section = ? AND question_num = ?""",
                (school, section, question_num)
            )
        print(f"Deleted {cursor.rowcount} row(s)")
        return cursor.rowcount


def renumber_question(school: str, old_section: str, old_num: int, new_section: str, new_num: int):
    """Change question number (e.g., fix Q0 -> Q8)."""
    with get_connection() as conn:
        # Check if target already exists
        existing = conn.execute(
            """SELECT id FROM questions
               WHERE school = ? AND paper_section = ? AND question_num = ?""",
            (school, new_section, new_num)
        ).fetchone()

        if existing:
            print(f"Warning: {new_section} Q{new_num} already exists!")
            return 0

        cursor = conn.execute(
            """UPDATE questions
               SET paper_section = ?, question_num = ?, pdf_question_num = ?
               WHERE school = ? AND paper_section = ? AND question_num = ?""",
            (new_section, new_num, new_num, school, old_section, old_num)
        )
        print(f"Renumbered {cursor.rowcount} row(s): {old_section} Q{old_num} -> {new_section} Q{new_num}")
        return cursor.rowcount


def delete_by_page(school: str, page_nums: list):
    """Delete all questions from specific pages."""
    with get_connection() as conn:
        for page in page_nums:
            cursor = conn.execute(
                """DELETE FROM questions WHERE school = ? AND pdf_page_num = ?""",
                (school, page)
            )
            print(f"Deleted {cursor.rowcount} questions from page {page}")


def list_questions_by_page(school: str, page_num: int):
    """List questions on a specific page."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT paper_section, question_num, part_letter, substr(latex_text, 1, 50) as preview, answer
               FROM questions WHERE school = ? AND pdf_page_num = ?
               ORDER BY paper_section, question_num""",
            (school, page_num)
        ).fetchall()

        if not rows:
            print(f"No questions found on page {page_num}")
            return

        print(f"\nQuestions on page {page_num}:")
        for row in rows:
            part = f"({row['part_letter']})" if row['part_letter'] else ""
            print(f"  {row['paper_section']} Q{row['question_num']}{part}: {row['preview']}...")
            print(f"    Answer: {row['answer'][:50] if row['answer'] else 'None'}...")


def show_school_summary(school: str):
    """Show summary of questions for a school."""
    questions = get_questions(school=school)

    by_section = {}
    for q in questions:
        sec = q['paper_section']
        if sec not in by_section:
            by_section[sec] = []
        by_section[sec].append(q)

    print(f"\n{school} Summary:")
    print("-" * 40)
    for section in ['P1A', 'P1B', 'P2']:
        if section in by_section:
            nums = sorted(set(q['question_num'] for q in by_section[section]))
            print(f"{section}: {len(by_section[section])} questions (Q{min(nums)}-Q{max(nums)})")
            # Show gaps
            expected = set(range(1, max(nums) + 1))
            missing = expected - set(nums)
            if missing:
                print(f"  Missing: {sorted(missing)}")
        else:
            print(f"{section}: 0 questions")


def main():
    parser = argparse.ArgumentParser(description="Fix extraction issues")
    parser.add_argument("--school", type=str, required=True, help="School name")
    parser.add_argument("--list-page", type=int, help="List questions on a page")
    parser.add_argument("--delete-page", type=str, help="Delete questions from pages (comma-separated)")
    parser.add_argument("--delete-question", type=str, help="Delete question (e.g., P2_0 or P1B_11)")
    parser.add_argument("--renumber", nargs=2, help="Renumber question: OLD NEW (e.g., P2_0 P2_8)")
    parser.add_argument("--summary", action="store_true", help="Show school summary")
    args = parser.parse_args()

    if args.summary:
        show_school_summary(args.school)
        return

    if args.list_page:
        list_questions_by_page(args.school, args.list_page)
        return

    if args.delete_page:
        pages = [int(p.strip()) for p in args.delete_page.split(",")]
        delete_by_page(args.school, pages)
        return

    if args.delete_question:
        # Parse P2_0 or P1B_11a format
        match = __import__('re').match(r'(P1A|P1B|P2)_(\d+)([a-z])?', args.delete_question, __import__('re').IGNORECASE)
        if match:
            section = match.group(1).upper()
            qnum = int(match.group(2))
            part = match.group(3)
            delete_question(args.school, section, qnum, part)
        else:
            print(f"Invalid question format: {args.delete_question}")
            print("Use format like: P2_0, P1B_11, P2_6a")
        return

    if args.renumber:
        old, new = args.renumber
        old_match = __import__('re').match(r'(P1A|P1B|P2)_(\d+)', old, __import__('re').IGNORECASE)
        new_match = __import__('re').match(r'(P1A|P1B|P2)_(\d+)', new, __import__('re').IGNORECASE)
        if old_match and new_match:
            renumber_question(
                args.school,
                old_match.group(1).upper(), int(old_match.group(2)),
                new_match.group(1).upper(), int(new_match.group(2))
            )
        else:
            print("Invalid format. Use: P2_0 P2_8")
        return

    # Default: show summary
    show_school_summary(args.school)


if __name__ == "__main__":
    main()
