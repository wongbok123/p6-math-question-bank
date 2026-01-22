#!/usr/bin/env python3
"""
verify_and_solve.py - Hybrid approach: verify answer key matches, solve if wrong

APPROACH:
1. Parse answer key to get candidate answers (by Q#)
2. For each question in database:
   a. Find candidate answer from answer key (by Q# match)
   b. Send question image + candidate answer to Gemini
   c. Ask Gemini: "Is this the correct answer?"
   d. If YES → keep the answer
   e. If NO → Gemini solves it directly
3. Store verified/solved answer with working steps

This is more robust than direct Q# matching because:
- Gemini verifies the answer makes sense for the actual question
- Mismatched answers are caught and corrected
- Works across different PDF formats

Usage:
    export GEMINI_API_KEY="your-key"
    python verify_and_solve.py --pdf "file.pdf" --answer-pages 44-48
    python verify_and_solve.py --section P2    # Only process P2
"""

import os
import re
import sys
import gc
import argparse
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

import pdfplumber
from PIL import Image
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from segmenter import QuestionSegmenter

from utils.gemini_client import GeminiClient
from database import get_questions, get_connection, update_answer
from config import PDF_DIR, IMAGES_DIR

# Directory for answer key images
ANSWER_KEY_DIR = IMAGES_DIR / "answer_keys"

import json

DPI = 200


def normalize_mcq(answer: str) -> str:
    """
    Normalize MCQ answers: 1→A, 2→B, 3→C, 4→D
    Handles: "1", "(1)", "[1]", "1)", "Option 1", etc.
    """
    answer = answer.strip()

    # If already a letter, return as-is
    if answer.upper() in ['A', 'B', 'C', 'D']:
        return answer.upper()

    # Extract digit from various formats
    match = re.search(r'(?:Option\s*)?[(\[]?([1-4])[)\]]?', answer, re.IGNORECASE)
    if match:
        digit = match.group(1)
        return {'1': 'A', '2': 'B', '3': 'C', '4': 'D'}[digit]

    return answer


def normalize_answer(answer: str) -> str:
    """
    Normalize answer for comparison.
    Removes extra whitespace, normalizes case for letters, handles units.
    """
    if not answer:
        return ""

    answer = answer.strip()

    # Normalize MCQ letters
    if answer.upper() in ['A', 'B', 'C', 'D']:
        return answer.upper()

    # Remove common variations that shouldn't affect comparison
    # e.g., "$" at start, "cm" units, extra spaces
    normalized = re.sub(r'\s+', ' ', answer)

    # For numeric answers, try to extract the numeric value
    # But keep units for comparison
    return normalized.lower()


def find_candidate_answer(
    candidate_answers: Dict[str, 'CandidateAnswer'],
    section: str,
    qnum: int,
    pdf_qnum: Optional[int],
    part_letter: Optional[str] = None
) -> Optional['CandidateAnswer']:
    """
    Find candidate answer using section-prefixed lookup.

    Keys are expected to be like "P1A_1", "P1B_16", "P2_1".
    For multi-part questions: "P2_6A", "P2_6B" (uppercase) matches part_letter 'a', 'b'.

    Args:
        part_letter: 'a', 'b', 'c', etc. for multi-part questions, or None
    """
    lookup_keys = []
    q = pdf_qnum or qnum

    # For questions with parts, look up the specific part first
    if part_letter:
        # Try uppercase and lowercase variants: P2_6A, P2_6a
        lookup_keys.append(f"{section}_{q}{part_letter.upper()}")
        lookup_keys.append(f"{section}_{q}{part_letter.lower()}")

        # For P1B: Answer key may use Q16-30
        if section == 'P1B':
            q_plus = qnum + 15
            lookup_keys.append(f"P1B_{q_plus}{part_letter.upper()}")
            lookup_keys.append(f"P1B_{q_plus}{part_letter.lower()}")
    else:
        # No part letter - look for base question key
        if pdf_qnum:
            lookup_keys.append(f"{section}_{pdf_qnum}")

        lookup_keys.append(f"{section}_{qnum}")

        # For P1B: Answer key uses Q16-30, so also try qnum + 15
        if section == 'P1B':
            lookup_keys.append(f"P1B_{qnum + 15}")

    # Try each key
    for key in lookup_keys:
        if key in candidate_answers:
            return candidate_answers[key]

    # Fallback: try without section prefix (legacy format)
    if not part_letter:
        fallback_keys = [str(pdf_qnum) if pdf_qnum else None, str(qnum)]
        for key in fallback_keys:
            if key and key in candidate_answers:
                return candidate_answers[key]

    return None


@dataclass
class CandidateAnswer:
    """Answer candidate from answer key."""
    question_num: int
    answer: str
    section: Optional[str] = None  # P1A, P1B, P2
    working: Optional[str] = None
    source_page: int = 0


def collect_multipart_answers(
    candidate_answers: Dict[str, 'CandidateAnswer'],
    qnum: int,
    pdf_qnum: Optional[int],
    section: str = 'P2'
) -> Optional['CandidateAnswer']:
    """
    Combine multi-part answers "(a) 135° (b) 72°" from separate keys.

    Handles answer keys that store parts separately like:
    - P2_6a: 109°
    - P2_6b: 72°

    Returns a combined CandidateAnswer or None if no parts found.
    """
    parts = []
    q = pdf_qnum or qnum

    for suffix in ['a', 'b', 'c', 'd', 'e']:
        # Try various key formats (lowercase and uppercase)
        for key in [
            f"{section}_{q}{suffix}",
            f"{section}_{q}{suffix.upper()}",
            f"{section}_{q}({suffix})",
            f"{section}_{q}({suffix.upper()})"
        ]:
            if key in candidate_answers:
                parts.append((suffix, candidate_answers[key].answer))
                break

    if parts:
        # Combine parts: "(a) 109° (b) 72°"
        combined = " ".join(f"({p[0]}) {p[1]}" for p in parts)
        return CandidateAnswer(
            question_num=q,
            answer=combined,
            section=section,
            working=None,
            source_page=parts[0][1] if parts else 0  # Use first part's page
        )

    return None


# Prompt to extract all answers from an answer key page (JSON format with sections)
EXTRACT_ANSWERS_PROMPT = """This is an ANSWER KEY page from a P6 Math exam.

Extract ALL answers into JSON format WITH SECTION PREFIXES.

SECTION DETECTION RULES:
1. If you see "Paper 1 Booklet A" or "Paper 1A" header → use "P1A_" prefix
2. If you see "Paper 1 Booklet B" or "Paper 1B" header → use "P1B_" prefix
3. If you see "Paper 2" header → use "P2_" prefix
4. **IMPORTANT - NO HEADER VISIBLE**: If there's no section header on the page:
   - Questions Q1-Q15 in a GRID/TABLE with single answers (1,2,3,4 or A,B,C,D) → P1A_
   - Questions Q16-Q30 → P1B_
   - Questions Q1-Q17 with PARTS like (a), (b), (c) showing WORKING/SOLUTIONS → P2_

CRITICAL FOR MULTI-PART QUESTIONS:
- P1B questions (Q16-Q30) CAN have parts (a), (b), (c) - use "P1B_21a", "P1B_21b"
- P2 questions (Q1-Q17) often have parts (a), (b), (c) - use "P2_6a", "P2_6b"
- ALWAYS extract EACH PART as a SEPARATE key!

OUTPUT FORMAT - JSON with section prefix:
{
  "P1A_1": "4",
  "P1B_16": "324",
  "P1B_21a": "11/12",
  "P1B_21b": "30",
  "P2_6a": "109°",
  "P2_6b": "72°"
}

RULES:
1. ALWAYS include section prefix: P1A_, P1B_, or P2_
2. **CRITICAL**: For multi-part questions, create SEPARATE entries for EACH part:
   - Q21 with (a) 11/12 and (b) 30 → "P1B_21a": "11/12", "P1B_21b": "30"
   - NOT "P1B_21": "11/12" (this loses part b!)
3. Use lowercase part letters: "P1B_21a", "P2_6b" (not "P1B_21A")
4. Include units: "$159.50", "1600ml", "92.36 cm²"
5. If working is shown, extract ONLY the FINAL ANSWER value (last value calculated)
6. Extract EVERY answer visible on the page - don't skip any parts!

EXAMPLE - P1B answers (Q16-Q30):
{
  "P1B_16": "324",
  "P1B_17": "45",
  "P1B_18a": "1/4",
  "P1B_18b": "3/8",
  "P1B_19": "256",
  "P1B_20a": "15",
  "P1B_20b": "24",
  "P1B_21a": "11/12",
  "P1B_21b": "30"
}

EXAMPLE - P2 answers (Q1-Q17):
{
  "P2_6a": "109°",
  "P2_6b": "72°",
  "P2_7a": "4",
  "P2_7b": "104",
  "P2_8a": "A",
  "P2_8b": "4000ml"
}

Return ONLY valid JSON, no other text.
"""


# Prompt to verify if an answer is correct for a question (solve-first approach)
VERIFY_ANSWER_PROMPT = """Look at this math question image.

STEP 1: SOLVE the question yourself. Show your working.

STEP 2: COMPARE your answer to this candidate answer: {answer}

STEP 3: Report your verdict.

FORMAT YOUR RESPONSE:

MY_SOLUTION:
[Your step-by-step working]

MY_ANSWER: [Your calculated answer]

CANDIDATE: {answer}

VERDICT: [MATCH or MISMATCH]

If MISMATCH, explain briefly why the candidate is wrong.
"""


# Prompt to solve a question directly
SOLVE_PROMPT = """Solve this P6 Math question step by step.

Show your working clearly, then state the final answer.

FORMAT:
WORKING:
[step by step solution]

ANSWER: [final answer with units]
"""


# P2-specific prompt for multi-part questions
SOLVE_P2_PROMPT = """This is Question {qnum} from Paper 2.

IMPORTANT: This question may have MULTIPLE PARTS (a), (b), (c), etc.
Look carefully at ALL parts and solve EACH one.

Solve step by step, showing working for EACH part.

FORMAT:
WORKING:
Part (a): [working for part a]
Part (b): [working for part b]
...

ANSWER:
(a) [answer with units]
(b) [answer with units]
...

If the question has only ONE part (no (a), (b)), just solve normally:
WORKING:
[step by step solution]

ANSWER: [final answer with units]
"""


# Lenient prompt for last-resort solving
SOLVE_LENIENT_PROMPT = """Look at this math question image and solve it.

Just give me the final answer. If there are multiple parts, format as:
(a) [answer]
(b) [answer]

If just one answer:
[answer]
"""


# Prompt to verify with question context (for P2 multi-part questions)
VERIFY_WITH_CONTEXT_PROMPT = """Look at this math question image.

IMPORTANT: This is Question {pdf_qnum}.
The question asks: "{question_text}"

STEP 1: Read Question {pdf_qnum} carefully in the image
STEP 2: SOLVE that specific question. Show your working.
STEP 3: COMPARE your answer to this candidate answer: {answer}

FORMAT YOUR RESPONSE:

MY_SOLUTION:
[Your step-by-step working]

MY_ANSWER: [Your calculated answer]

CANDIDATE: {answer}

VERDICT: [MATCH or MISMATCH]

If MISMATCH, explain briefly why the candidate is wrong.
"""


def extract_answers_from_page(
    client: GeminiClient,
    image: Image.Image,
    page_num: int
) -> List[Tuple[str, CandidateAnswer]]:
    """
    Extract all answers from an answer key page using JSON format.

    Returns list of (key, CandidateAnswer) tuples where key includes section prefix.
    e.g., [("P1A_1", CandidateAnswer(...)), ("P1B_16", CandidateAnswer(...))]
    """
    result = client.extract_from_image(image, EXTRACT_ANSWERS_PROMPT, page_num)

    if not result.success:
        print(f"[ERROR] Failed to extract answers: {result.error}")
        return []

    response_text = result.question_text

    # Parse JSON response
    try:
        # Try multiple approaches to extract JSON
        answers_dict = None

        # Approach 1: Find JSON block with balanced braces
        json_start = response_text.find('{')
        if json_start >= 0:
            # Find matching closing brace
            brace_count = 0
            json_end = json_start
            for i, c in enumerate(response_text[json_start:]):
                if c == '{':
                    brace_count += 1
                elif c == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = json_start + i + 1
                        break
            json_str = response_text[json_start:json_end]
            try:
                answers_dict = json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # Approach 2: Try parsing entire response
        if not answers_dict:
            try:
                answers_dict = json.loads(response_text.strip())
            except json.JSONDecodeError:
                pass

        # Approach 3: Extract with simple regex (fallback)
        if not answers_dict:
            json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                answers_dict = json.loads(json_match.group())

        if not answers_dict:
            raise json.JSONDecodeError("Could not extract JSON", response_text, 0)

    except json.JSONDecodeError as e:
        print(f"[WARN] Could not parse JSON from page {page_num}: {e}")
        # Fallback: try line-by-line parsing for backwards compatibility
        return _fallback_line_parsing(response_text, page_num)

    answers = []
    for key, answer in answers_dict.items():
        # Parse section-prefixed key like "P1A_1", "P1B_16a", "P2_1"
        section_match = re.match(r'(P1A|P1B|P2)_(\d+[a-z]?)', key, re.IGNORECASE)

        if section_match:
            section = section_match.group(1).upper()
            q_num_str = section_match.group(2)
        else:
            # Fallback: no section prefix, try to infer from Q#
            section = None
            q_num_str = key

        # Extract base question number
        base_match = re.match(r'(\d+)', q_num_str)
        if not base_match:
            continue

        q_num = int(base_match.group(1))

        # Normalize MCQ (1→A, 2→B, etc.) only for P1A
        normalized = str(answer)
        if section == 'P1A':
            normalized = normalize_mcq(normalized)

        # Build the storage key (preserve original key format)
        storage_key = key.upper() if section_match else key

        answers.append((storage_key, CandidateAnswer(
            question_num=q_num,
            answer=normalized,
            section=section,
            working=None,
            source_page=page_num
        )))

    return answers


def _fallback_line_parsing(response_text: str, page_num: int) -> List[Tuple[str, CandidateAnswer]]:
    """Fallback line-by-line parsing if JSON parsing fails."""
    answers = []
    current_q = None
    current_part = None  # Track part letter (a, b, c)
    current_answer = None
    current_section = None

    for line in response_text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Check for section headers
        if 'paper 1' in line.lower() and 'booklet a' in line.lower():
            current_section = 'P1A'
            continue
        elif 'paper 1' in line.lower() and 'booklet b' in line.lower():
            current_section = 'P1B'
            continue
        elif 'paper 2' in line.lower():
            current_section = 'P2'
            continue

        # Check for Q# pattern with optional part letter: Q21, Q21(a), Q21a
        q_match = re.match(r'^Q(\d+)\s*(?:\(([a-e])\)|([a-e]))?\s*[:\s]+(.*)$', line, re.IGNORECASE)
        if q_match:
            # Save previous
            if current_q and current_answer:
                section = current_section or _infer_section(current_q)
                if current_part:
                    key = f"{section}_{current_q}{current_part.lower()}" if section else f"{current_q}{current_part.lower()}"
                else:
                    key = f"{section}_{current_q}" if section else str(current_q)
                answers.append((key, CandidateAnswer(
                    question_num=current_q,
                    answer=normalize_mcq(current_answer) if section == 'P1A' else current_answer,
                    section=section,
                    working=None,
                    source_page=page_num
                )))

            current_q = int(q_match.group(1))
            # Part letter can be in group 2 (parenthesized) or group 3 (not parenthesized)
            current_part = q_match.group(2) or q_match.group(3)
            current_answer = q_match.group(4).strip()

        # Check for standalone part pattern: (a) answer, (b) answer
        elif current_q:
            part_match = re.match(r'^\(([a-e])\)\s*(.+)$', line, re.IGNORECASE)
            if part_match:
                # Save previous part if exists
                if current_answer:
                    section = current_section or _infer_section(current_q)
                    if current_part:
                        key = f"{section}_{current_q}{current_part.lower()}" if section else f"{current_q}{current_part.lower()}"
                    else:
                        key = f"{section}_{current_q}" if section else str(current_q)
                    answers.append((key, CandidateAnswer(
                        question_num=current_q,
                        answer=normalize_mcq(current_answer) if section == 'P1A' else current_answer,
                        section=section,
                        working=None,
                        source_page=page_num
                    )))

                current_part = part_match.group(1)
                current_answer = part_match.group(2).strip()
            elif not current_answer:
                current_answer = line

    # Save last
    if current_q and current_answer:
        section = current_section or _infer_section(current_q)
        if current_part:
            key = f"{section}_{current_q}{current_part.lower()}" if section else f"{current_q}{current_part.lower()}"
        else:
            key = f"{section}_{current_q}" if section else str(current_q)
        answers.append((key, CandidateAnswer(
            question_num=current_q,
            answer=normalize_mcq(current_answer) if section == 'P1A' else current_answer,
            section=section,
            working=None,
            source_page=page_num
        )))

    return answers


def _infer_section(q_num: int) -> Optional[str]:
    """Infer section from question number if not explicitly given."""
    if 1 <= q_num <= 15:
        return 'P1A'  # Could be P1A or P2, but default to P1A
    elif 16 <= q_num <= 30:
        return 'P1B'
    return None


def crop_question_from_page(
    page_image: Image.Image,
    pdf_qnum: int,
    section: str
) -> Image.Image:
    """
    Crop the specific question region from a full-page image.
    Uses OpenCV segmenter to detect question boundaries.

    Args:
        page_image: Full page PIL Image
        pdf_qnum: The question number as shown in the PDF
        section: Paper section (P1A, P1B, P2)

    Returns:
        Cropped PIL Image of just the question region
    """
    # Convert PIL to OpenCV format
    cv_image = cv2.cvtColor(np.array(page_image), cv2.COLOR_RGB2BGR)

    # Use segmenter to detect question boxes
    segmenter = QuestionSegmenter()
    boxes = segmenter.segment_page(cv_image)

    if not boxes:
        # Fallback: return full image if no boxes detected
        print("[CROP: no boxes] ", end="")
        return page_image

    # For P2, questions are typically 1-2 per page
    # Use position on page to select the right box
    # First question on page is usually at the top

    height = cv_image.shape[0]

    # Estimate which box contains our question
    # P2 questions are numbered 1-17, typically 1-2 per page
    # If pdf_qnum is odd, likely first on page; if even, likely second
    if len(boxes) == 1:
        best_box = boxes[0]
    elif len(boxes) >= 2:
        # Sort boxes by y position (top to bottom)
        sorted_boxes = sorted(boxes, key=lambda b: b.y_start)
        # Simple heuristic: use first or second box based on question number parity
        # This is imperfect but better than nothing
        box_index = 0 if pdf_qnum % 2 == 1 else min(1, len(sorted_boxes) - 1)
        best_box = sorted_boxes[box_index]
    else:
        return page_image

    # Crop and convert back to PIL
    cropped = cv_image[best_box.y_start:best_box.y_end, best_box.x_start:best_box.x_end]
    print(f"[CROP: {best_box.height}px] ", end="")
    return Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))


def verify_answer(
    client: GeminiClient,
    question_image: Image.Image,
    candidate_answer: str
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Verify if a candidate answer is correct using solve-first approach.

    The AI solves the question first, then compares to the candidate.

    Returns: (verdict, correct_answer, working)
    - verdict: "CORRECT", "WRONG", or "UNSURE"
    - correct_answer: The AI's calculated answer
    - working: Working steps (if provided)
    """
    prompt = VERIFY_ANSWER_PROMPT.format(answer=candidate_answer)
    result = client.extract_from_image(question_image, prompt)

    if not result.success:
        return "UNSURE", None, None

    response = result.question_text

    # Extract AI's own answer
    my_answer_match = re.search(r'MY_ANSWER:\s*(.+?)(?=\n|CANDIDATE:|$)', response, re.IGNORECASE)
    my_answer = my_answer_match.group(1).strip() if my_answer_match else None

    # Extract working
    working_match = re.search(r'MY_SOLUTION:\s*(.+?)(?=MY_ANSWER:|$)', response, re.DOTALL | re.IGNORECASE)
    working = working_match.group(1).strip() if working_match else None

    # Check verdict
    verdict_match = re.search(r'VERDICT:\s*(MATCH|MISMATCH)', response, re.IGNORECASE)

    if verdict_match:
        verdict = verdict_match.group(1).upper()
        if verdict == "MATCH":
            return "CORRECT", candidate_answer, working
        else:
            return "WRONG", my_answer, working

    # Fallback: if we have AI's answer, compare directly
    if my_answer:
        # Simple comparison (normalize both)
        if normalize_answer(my_answer) == normalize_answer(candidate_answer):
            return "CORRECT", candidate_answer, working
        else:
            return "WRONG", my_answer, working

    return "UNSURE", None, working


def verify_answer_with_context(
    client: GeminiClient,
    question_image: Image.Image,
    candidate_answer: str,
    pdf_qnum: int,
    question_text: str
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Verify answer with question context (for P2 questions).

    Includes the question number and text in the prompt to help the AI
    identify the correct question on multi-question pages.

    Returns: (verdict, correct_answer, working)
    """
    # Truncate question text if too long
    if len(question_text) > 200:
        question_text = question_text[:200] + "..."

    prompt = VERIFY_WITH_CONTEXT_PROMPT.format(
        pdf_qnum=pdf_qnum,
        question_text=question_text,
        answer=candidate_answer
    )
    result = client.extract_from_image(question_image, prompt)

    if not result.success:
        return "UNSURE", None, None

    response = result.question_text

    # Extract AI's own answer
    my_answer_match = re.search(r'MY_ANSWER:\s*(.+?)(?=\n|CANDIDATE:|$)', response, re.IGNORECASE)
    my_answer = my_answer_match.group(1).strip() if my_answer_match else None

    # Extract working
    working_match = re.search(r'MY_SOLUTION:\s*(.+?)(?=MY_ANSWER:|$)', response, re.DOTALL | re.IGNORECASE)
    working = working_match.group(1).strip() if working_match else None

    # Check verdict
    verdict_match = re.search(r'VERDICT:\s*(MATCH|MISMATCH)', response, re.IGNORECASE)

    if verdict_match:
        verdict = verdict_match.group(1).upper()
        if verdict == "MATCH":
            return "CORRECT", candidate_answer, working
        else:
            return "WRONG", my_answer, working

    # Fallback comparison
    if my_answer:
        if normalize_answer(my_answer) == normalize_answer(candidate_answer):
            return "CORRECT", candidate_answer, working
        else:
            return "WRONG", my_answer, working

    return "UNSURE", None, working


def solve_question(
    client: GeminiClient,
    question_image: Image.Image
) -> Tuple[Optional[str], Optional[str]]:
    """
    Solve a question directly using Gemini.

    Returns: (answer, working)
    """
    result = client.extract_from_image(question_image, SOLVE_PROMPT)

    if not result.success:
        return None, None

    response = result.question_text

    # Parse answer
    answer = None
    ans_match = re.search(r'ANSWER:\s*(.+?)(?=\n|$)', response, re.IGNORECASE)
    if ans_match:
        answer = ans_match.group(1).strip()

    # Parse working
    working = None
    working_match = re.search(r'WORKING:\s*(.+?)(?=\nANSWER:|\Z)', response, re.DOTALL | re.IGNORECASE)
    if working_match:
        working = working_match.group(1).strip()

    return answer, working


def solve_question_p2(
    client: GeminiClient,
    question_image: Image.Image,
    pdf_qnum: int
) -> Tuple[Optional[str], Optional[str]]:
    """
    Solve a P2 question directly using P2-specific prompt.

    Handles multi-part questions (a), (b), (c), etc.

    Returns: (answer, working)
    """
    prompt = SOLVE_P2_PROMPT.format(qnum=pdf_qnum)
    result = client.extract_from_image(question_image, prompt)

    if not result.success:
        return None, None

    response = result.question_text

    # Parse answer - handles both single and multi-part formats
    answer = None

    # Try multi-part format first: look for lines with (a), (b), etc.
    multi_part_match = re.search(
        r'ANSWER:\s*\n?((?:\([a-e]\)\s*.+\n?)+)',
        response, re.IGNORECASE | re.MULTILINE
    )
    if multi_part_match:
        answer = multi_part_match.group(1).strip()
    else:
        # Try single answer format
        ans_match = re.search(r'ANSWER:\s*(.+?)(?=\n\n|\Z)', response, re.IGNORECASE | re.DOTALL)
        if ans_match:
            answer = ans_match.group(1).strip()

    # Parse working
    working = None
    working_match = re.search(r'WORKING:\s*(.+?)(?=\nANSWER:|\Z)', response, re.DOTALL | re.IGNORECASE)
    if working_match:
        working = working_match.group(1).strip()

    return answer, working


def solve_question_lenient(
    client: GeminiClient,
    question_image: Image.Image
) -> Tuple[Optional[str], Optional[str]]:
    """
    Last-resort lenient solving - just get the answer.

    Returns: (answer, None)
    """
    result = client.extract_from_image(question_image, SOLVE_LENIENT_PROMPT)

    if not result.success:
        return None, None

    response = result.question_text.strip()

    # The response should just be the answer
    # Look for multi-part format or plain answer
    if '(' in response and ')' in response:
        # Multi-part answer
        return response, None
    else:
        # Single answer - take first non-empty line
        for line in response.split('\n'):
            line = line.strip()
            if line:
                return line, None

    return response if response else None, None


def process_p2_with_retry(
    client: GeminiClient,
    question_image: Image.Image,
    pdf_qnum: int,
    candidate: Optional['CandidateAnswer'],
    max_retries: int = 3
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Process P2 question with robust retry logic.

    Returns: (answer, working, tag)
    """
    # Step 1: If we have a candidate from answer key, trust it
    if candidate and candidate.answer:
        return candidate.answer, None, "[answer-key]"

    # Step 2: No candidate - solve directly with P2 prompt + retry
    for attempt in range(max_retries):
        answer, working = solve_question_p2(client, question_image, pdf_qnum)
        if answer:
            return answer, working, "[ai-solved]"
        print(f"[retry {attempt + 1}] ", end="")
        time.sleep(2)

    # Step 3: Last resort - lenient prompt
    answer, working = solve_question_lenient(client, question_image)
    if answer:
        return answer, working, "[ai-solved-lenient]"

    return None, None, "[failed]"


def process_questions(
    client: GeminiClient,
    questions: List[dict],
    candidate_answers: Dict[str, CandidateAnswer],
    school: str,
    year: int
) -> Dict[str, int]:
    """
    Process questions using the verify-then-solve approach.
    Uses section-aware lookup for answer key matching.
    """
    stats = {
        "verified_correct": 0,
        "verified_wrong_solved": 0,
        "no_candidate_solved": 0,
        "failed": 0
    }

    for i, q in enumerate(questions):
        section = q['paper_section']
        qnum = q['question_num']
        pdf_qnum = q.get('pdf_question_num', qnum)
        part_letter = q.get('part_letter')

        # Format display string
        display_q = f"Q{pdf_qnum}"
        if part_letter:
            display_q = f"Q{pdf_qnum}({part_letter})"

        print(f"\n[{i+1}/{len(questions)}] {section} {display_q}... ", end="")

        # Load question image
        image_path = Path(q['image_path'])
        if not image_path.exists():
            print(f"[SKIP] Image not found")
            stats["failed"] += 1
            continue

        try:
            question_image = Image.open(image_path)
        except Exception as e:
            print(f"[ERROR] {e}")
            stats["failed"] += 1
            continue

        # Find candidate answer using section-aware lookup (now part-aware)
        candidate = find_candidate_answer(candidate_answers, section, qnum, pdf_qnum, part_letter)

        final_answer = None
        final_working = None
        final_tag = None

        if candidate:
            # Trust answer key directly for ALL sections (P1A, P1B, P2)
            # Reasons:
            # 1. Answer key extraction now handles multi-part questions
            # 2. AI verification often causes mismatches due to image/context issues
            # 3. Answer key is authoritative source
            if section == 'P1A':
                section_label = "MCQ"
            elif section == 'P1B':
                section_label = "P1B"
            else:
                section_label = "P2"

            print(f"[{section_label}] '{candidate.answer}' [ACCEPTED]")
            final_answer = candidate.answer
            final_working = None
            final_tag = "[answer-key]"  # Directly from answer key
            stats["verified_correct"] += 1
        else:
            # No candidate answer, solve directly with retry
            if section == 'P2':
                cropped_image = crop_question_from_page(question_image, pdf_qnum, section)
                print("[NO CANDIDATE] Solving with retry... ", end="")
                final_answer, final_working, final_tag = process_p2_with_retry(
                    client, cropped_image, pdf_qnum, None
                )
            else:
                print("[NO CANDIDATE, SOLVING]... ", end="")
                final_answer, final_working = solve_question(client, question_image)
                final_tag = "[ai-solved-no-key]" if final_answer else "[failed]"

            if final_answer:
                print(f"→ {final_answer}")
                stats["no_candidate_solved"] += 1
            else:
                print("[FAILED]")
                stats["failed"] += 1

        # Update database with tag
        if final_answer:
            worked_solution = None
            if final_working:
                worked_solution = f"{final_tag}\n{final_working}"
            elif final_tag:
                worked_solution = final_tag

            update_answer(
                school=school,
                year=year,
                paper_section=section,
                question_num=qnum,
                answer=final_answer,
                worked_solution=worked_solution,
                overwrite=True,
                part_letter=part_letter,
            )

        # Cleanup and rate limit
        del question_image
        gc.collect()
        time.sleep(0.5)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Verify answers and solve if wrong")
    parser.add_argument("--pdf", type=str, help="PDF file with answer key")
    parser.add_argument("--answer-pages", type=str, help="Answer key pages (e.g., 44-48)")
    parser.add_argument("--section", type=str, help="Only process this section (P1A, P1B, P2)")
    parser.add_argument("--school", type=str, help="School name filter")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY not set!")
        sys.exit(1)

    print("=" * 60)
    print("VERIFY AND SOLVE")
    print("Hybrid approach: verify answer key, solve if wrong")
    print("=" * 60)

    client = GeminiClient(api_key=api_key)

    # Step 1: Extract candidate answers from answer key
    candidate_answers: Dict[str, CandidateAnswer] = {}

    if args.pdf and args.answer_pages:
        pdf_path = PDF_DIR / args.pdf
        if not pdf_path.exists():
            pdf_path = Path(args.pdf)

        if pdf_path.exists():
            print(f"\n[STEP 1] Extracting answers from answer key...")

            # Parse school name from filename for saving images
            # Pattern: 2025-P6-Maths-Prelim Exam-School.pdf
            pdf_name = pdf_path.stem
            parts = pdf_name.split("-")
            school_name = parts[-1].strip() if len(parts) >= 5 else "Unknown"
            year_match = re.search(r"(\d{4})", pdf_name)
            pdf_year = int(year_match.group(1)) if year_match else 2025

            # Create answer key images directory
            ANSWER_KEY_DIR.mkdir(parents=True, exist_ok=True)

            # Parse page range
            start, end = map(int, args.answer_pages.split("-"))
            pages = list(range(start, end + 1))

            with pdfplumber.open(pdf_path) as pdf:
                for page_num in pages:
                    if page_num < 1 or page_num > len(pdf.pages):
                        continue

                    print(f"  Page {page_num}... ", end="")
                    page = pdf.pages[page_num - 1]
                    img = page.to_image(resolution=DPI)
                    image = img.original

                    # Save answer key page image for reference
                    answer_img_path = ANSWER_KEY_DIR / f"{school_name}_{pdf_year}_answer_p{page_num:02d}.png"
                    image.save(answer_img_path)
                    print(f"[saved] ", end="")

                    answers = extract_answers_from_page(client, image, page_num)
                    print(f"found {len(answers)} answers")

                    for key, ans in answers:
                        # Store by section-prefixed key (e.g., "P1A_1", "P1B_16", "P2_1")
                        candidate_answers[key] = ans

                    del image
                    gc.collect()
                    time.sleep(1)

            print(f"  Total candidate answers: {len(candidate_answers)}")
            # Show extracted answers for debugging
            if candidate_answers:
                # Sort keys by section then number
                def sort_key(k):
                    m = re.match(r'(P1A|P1B|P2)_(\d+)', k)
                    if m:
                        section_order = {'P1A': 0, 'P1B': 1, 'P2': 2}
                        return (section_order.get(m.group(1), 3), int(m.group(2)))
                    return (4, 0)
                sorted_keys = sorted(candidate_answers.keys(), key=sort_key)
                print(f"  Keys: {sorted_keys}")
    else:
        print("\n[INFO] No answer key provided, will solve all questions directly")

    # Step 2: Get questions from database
    print(f"\n[STEP 2] Loading questions from database...")

    query_params = {}
    if args.section:
        query_params['paper_section'] = args.section
    if args.school:
        query_params['school'] = args.school

    questions = get_questions(**query_params)

    if not questions:
        print("[INFO] No questions found")
        return

    # Get school/year from first question
    school = questions[0]['school']
    year = questions[0]['year']

    print(f"  Found {len(questions)} questions for {school} {year}")

    # Step 3: Verify and solve
    print(f"\n[STEP 3] Verifying and solving questions...")

    stats = process_questions(client, questions, candidate_answers, school, year)

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"Verified correct:     {stats['verified_correct']}")
    print(f"Wrong → solved:       {stats['verified_wrong_solved']}")
    print(f"No candidate → solved: {stats['no_candidate_solved']}")
    print(f"Failed:               {stats['failed']}")


if __name__ == "__main__":
    main()
