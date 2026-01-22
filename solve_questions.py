#!/usr/bin/env python3
"""
solve_questions.py - Use Gemini to solve questions and generate working steps

Instead of matching answers from answer key (which is error-prone due to
question number mismatches), this script sends each question image to Gemini
and asks it to solve the question directly.

This ensures:
1. Answer matches the actual question
2. Working steps are relevant to the question
3. Cross-checking is possible by comparing with answer key

Usage:
    export GEMINI_API_KEY="your-key"
    python solve_questions.py                    # Solve all questions without answers
    python solve_questions.py --section P2       # Solve only P2 questions
    python solve_questions.py --force            # Re-solve all questions (overwrite)
    python solve_questions.py --verify           # Compare AI answers with existing
"""

import os
import re
import sys
import argparse
import time
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from utils.gemini_client import GeminiClient
from database import get_questions, get_connection
from config import IMAGES_DIR

# Prompt for solving questions
SOLVE_QUESTION_PROMPT = """You are a P6 Math teacher solving this exam question.

TASK: Solve this question step by step and provide the final answer.

INSTRUCTIONS:
1. Read the question carefully from the image
2. Show clear working steps
3. State the final answer clearly
4. For multi-part questions (a), (b), (c), solve each part

FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
---
WORKING:
[Show your step-by-step solution here]
[For multi-part questions, label each part]

ANSWER:
[State the final answer(s) here]
[For multi-part: (a) answer1 (b) answer2 etc.]
---

IMPORTANT:
- For money answers, include $ sign (e.g., $45.60)
- For ratios, use colon (e.g., 3:5)
- For fractions, use / (e.g., 2/3)
- For angles, include ° symbol (e.g., 45°)
- For units, include them (e.g., 24 cm², 5.5 kg)
- Be precise with numerical answers
"""

# Prompt for MCQ questions
SOLVE_MCQ_PROMPT = """You are a P6 Math teacher solving this multiple choice question.

TASK: Determine the correct answer and explain why.

INSTRUCTIONS:
1. Read the question and all options (A), (B), (C), (D)
2. Work out the solution
3. Identify the correct option

FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
---
WORKING:
[Show your calculation or reasoning]

ANSWER:
[Single letter: A, B, C, or D]
---
"""


def parse_solution_response(response: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse Gemini's solution response to extract working and answer."""
    working = None
    answer = None

    # Try to extract WORKING section
    working_match = re.search(
        r'WORKING:\s*\n(.*?)(?=\nANSWER:|\n---|\Z)',
        response,
        re.DOTALL | re.IGNORECASE
    )
    if working_match:
        working = working_match.group(1).strip()

    # Try to extract ANSWER section
    answer_match = re.search(
        r'ANSWER:\s*\n?(.*?)(?=\n---|\Z)',
        response,
        re.DOTALL | re.IGNORECASE
    )
    if answer_match:
        answer = answer_match.group(1).strip()
        # Clean up answer - take first line if multiple lines
        answer_lines = [l.strip() for l in answer.split('\n') if l.strip()]
        if answer_lines:
            answer = answer_lines[0]

    # Fallback: look for common answer patterns
    if not answer:
        # Look for "The answer is X" pattern
        ans_pattern = re.search(r'(?:answer|ans)(?:\s+is)?[:\s]+([^\n]+)', response, re.IGNORECASE)
        if ans_pattern:
            answer = ans_pattern.group(1).strip()

    return working, answer


def solve_question(
    client: GeminiClient,
    question: dict,
    force: bool = False
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Use Gemini to solve a question.

    Returns: (success, working, answer)
    """
    # Skip if already has answer and not forcing
    if question.get('answer') and not force:
        return False, None, None

    # Load the question image
    image_path = Path(question['image_path'])
    if not image_path.exists():
        print(f"[ERROR] Image not found: {image_path}")
        return False, None, None

    try:
        image = Image.open(image_path)
    except Exception as e:
        print(f"[ERROR] Failed to load image: {e}")
        return False, None, None

    # Choose prompt based on question type
    is_mcq = question.get('options') is not None
    prompt = SOLVE_MCQ_PROMPT if is_mcq else SOLVE_QUESTION_PROMPT

    # Send to Gemini
    result = client.extract_from_image(image, prompt)

    if not result.success:
        print(f"[ERROR] Gemini failed: {result.error}")
        return False, None, None

    # Parse response
    working, answer = parse_solution_response(result.question_text)

    if not answer:
        print(f"[WARN] Could not extract answer from response")
        # Try to salvage - use entire response as working
        working = result.question_text

    return True, working, answer


def update_question_solution(
    question_id: int,
    answer: str,
    working: Optional[str] = None,
    source: str = "ai_generated"
) -> bool:
    """Update question with AI-generated solution."""
    with get_connection() as conn:
        # Add source tag to working to indicate it's AI-generated
        if working:
            working = f"[{source}]\n{working}"

        cursor = conn.execute(
            """
            UPDATE questions
            SET answer = ?, worked_solution = ?
            WHERE id = ?
            """,
            (answer, working, question_id)
        )
        return cursor.rowcount > 0


def verify_answer(ai_answer: str, existing_answer: Optional[str]) -> Tuple[bool, str]:
    """
    Compare AI answer with existing answer.
    Returns (matches, explanation)
    """
    if not existing_answer:
        return True, "No existing answer to compare"

    # Normalize both answers for comparison
    def normalize(ans):
        if not ans:
            return ""
        ans = ans.lower().strip()
        # Remove common prefixes
        ans = re.sub(r'^(?:ans|answer)[:\s]*', '', ans)
        # Normalize spaces
        ans = re.sub(r'\s+', ' ', ans)
        # Remove $ for comparison
        ans = ans.replace('$', '')
        return ans

    ai_norm = normalize(ai_answer)
    existing_norm = normalize(existing_answer)

    # Check for exact match
    if ai_norm == existing_norm:
        return True, "Exact match"

    # Check if one contains the other (partial match)
    if ai_norm in existing_norm or existing_norm in ai_norm:
        return True, f"Partial match: AI='{ai_answer}' vs Existing='{existing_answer}'"

    # Try numeric comparison
    try:
        ai_num = float(re.search(r'[\d.]+', ai_norm).group())
        existing_num = float(re.search(r'[\d.]+', existing_norm).group())
        if abs(ai_num - existing_num) < 0.01:
            return True, f"Numeric match: {ai_num}"
    except:
        pass

    return False, f"MISMATCH: AI='{ai_answer}' vs Existing='{existing_answer}'"


def main():
    parser = argparse.ArgumentParser(description="Solve questions using Gemini AI")
    parser.add_argument("--section", type=str, help="Only solve questions in this section (P1A, P1B, P2)")
    parser.add_argument("--force", action="store_true", help="Re-solve questions even if they have answers")
    parser.add_argument("--verify", action="store_true", help="Verify AI answers against existing answers")
    parser.add_argument("--limit", type=int, help="Limit number of questions to process")
    parser.add_argument("--question", type=int, help="Solve specific question number")
    args = parser.parse_args()

    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY not set!")
        sys.exit(1)

    print("=" * 60)
    print("AI QUESTION SOLVER")
    print("Using Gemini to solve questions directly")
    print("=" * 60)

    # Init Gemini
    print("\n[INIT] Connecting to Gemini...")
    client = GeminiClient(api_key=api_key)

    # Get questions to solve
    query_params = {}
    if args.section:
        query_params['paper_section'] = args.section

    questions = get_questions(**query_params)

    if args.question:
        questions = [q for q in questions if q['question_num'] == args.question]

    if not args.force:
        # Filter to questions without answers
        questions = [q for q in questions if not q.get('answer')]

    if args.limit:
        questions = questions[:args.limit]

    print(f"[INFO] Found {len(questions)} questions to solve")

    if not questions:
        print("[INFO] No questions to solve")
        return

    # Process each question
    stats = {"solved": 0, "failed": 0, "verified": 0, "mismatched": 0}

    for i, q in enumerate(questions):
        section = q['paper_section']
        qnum = q['question_num']
        print(f"\n[{i+1}/{len(questions)}] {section} Q{qnum}... ", end="")

        # Store existing answer for verification
        existing_answer = q.get('answer')

        success, working, answer = solve_question(client, q, force=args.force)

        if success and answer:
            print(f"[SOLVED] {answer[:40]}{'...' if len(answer) > 40 else ''}")

            # Verify if requested
            if args.verify and existing_answer:
                matches, explanation = verify_answer(answer, existing_answer)
                if matches:
                    print(f"    [VERIFIED] {explanation}")
                    stats["verified"] += 1
                else:
                    print(f"    [WARNING] {explanation}")
                    stats["mismatched"] += 1

            # Update database
            update_question_solution(q['id'], answer, working)
            stats["solved"] += 1
        else:
            print("[FAILED]")
            stats["failed"] += 1

        # Rate limiting
        time.sleep(1)

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"Solved: {stats['solved']}")
    print(f"Failed: {stats['failed']}")
    if args.verify:
        print(f"Verified: {stats['verified']}")
        print(f"Mismatched: {stats['mismatched']}")


if __name__ == "__main__":
    main()
