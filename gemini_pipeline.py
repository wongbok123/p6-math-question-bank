#!/usr/bin/env python3
"""
gemini_pipeline.py - Full PDF extraction pipeline using Gemini API

Processes all PDFs in pdfs/ folder:
1. Converts pages to images (200 DPI)
2. Sends to Gemini for vision-based extraction
3. Parses questions and answers
4. Saves to SQLite database

Usage:
    export GEMINI_API_KEY="your-key"
    python gemini_pipeline.py                    # Process all PDFs
    python gemini_pipeline.py --pdf "file.pdf"   # Process single PDF
    python gemini_pipeline.py --pages 2-10       # Specific page range
"""

import gc
import os
import re
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

import pdfplumber
from PIL import Image
import psutil

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.gemini_client import GeminiClient, MCQ_EXTRACTION_PROMPT, ANSWER_EXTRACTION_PROMPT, MULTI_PART_EXTRACTION_PROMPT
from database import init_db, insert_question, get_statistics
from config import PDF_DIR, IMAGES_DIR

# Settings
DPI = 200  # Higher quality for better extraction
SAVE_IMAGES = True  # Save page images for reference


@dataclass
class ParsedQuestion:
    """Parsed question from Gemini response."""
    number: int
    text: str
    question_type: str  # MCQ, Short Answer, Long Answer
    options: Optional[Dict[str, str]] = None
    diagram: Optional[str] = None
    marks: int = 1
    part_letter: Optional[str] = None    # 'a', 'b', 'c', or None for non-multi-part
    main_context: Optional[str] = None   # Shared problem context for multi-part questions


def get_memory():
    """Get current memory usage."""
    mem = psutil.virtual_memory()
    return f"{mem.percent:.1f}%"


def parse_school_from_filename(filename: str) -> Tuple[str, int]:
    """Extract school name and year from PDF filename."""
    # Pattern: 2025-P6-Maths-Prelim Exam-St Nicholas.pdf
    name = Path(filename).stem

    # Extract year
    year_match = re.search(r"(\d{4})", name)
    year = int(year_match.group(1)) if year_match else 2025

    # Extract school name (after last hyphen usually)
    parts = name.split("-")
    if len(parts) >= 5:
        school = parts[-1].strip()
    else:
        school = parts[-1].strip() if parts else "Unknown"

    return school, year


def detect_section_type(page_num: int, total_pages: int, text_hint: str = "") -> str:
    """Detect section type from page content with strong marker priority."""
    text_lower = text_hint.lower()

    # Check if this looks like a question page (has blank answer lines)
    # Question pages have "Ans: _____" or "Ans: (a) _____" patterns
    has_blank_answer_lines = bool(re.search(r'ans\s*:\s*\(?[a-z]?\)?\s*_+', text_lower))

    # Check for question number patterns typical of question pages
    has_question_numbers = bool(re.search(r'^\s*(\d+)\s*[\.\)]\s*\w', text_hint, re.MULTILINE))

    # PRIORITY 1: Strong answer key markers (explicit headers)
    strong_answer_markers = [
        "answer key", "marking scheme", "suggested answers",
        "model answer", "mark scheme"
    ]
    if any(marker in text_lower for marker in strong_answer_markers):
        return "answer_key"

    # Check for dense MCQ answer patterns (Q1: A, Q2: B style) - definite answer key
    if re.search(r'Q\s*1[:\s]+[ABCD]\s+Q\s*2[:\s]+[ABCD]', text_hint, re.IGNORECASE):
        return "answer_key"

    # Check for tabular answer format: multiple "Q#: answer" patterns in quick succession
    answer_pattern_count = len(re.findall(r'Q\s*\d+\s*[:\s]+(?:[ABCD]|\$?\d)', text_hint, re.IGNORECASE))
    if answer_pattern_count >= 5:  # Likely an answer key page
        return "answer_key"

    # Check for dense working/solution patterns (multiple equations on one page = answer key)
    # Answer key pages typically have many calculations like "= 45", "÷ 3 = 15", etc.
    equation_count = len(re.findall(r'\d+\s*[+\-×÷x]\s*\d+\s*=\s*\d+', text_hint))
    if equation_count >= 6:  # Many calculations = likely answer key
        return "answer_key"

    # Check for multiple Q# patterns with sub-parts and answers (answer key format)
    # Pattern like "Q7 (b) 229°" or "Q13 (a) 60 - 48 = 12"
    qnum_with_parts = len(re.findall(r'Q\s*\d+\s*\([a-z]\)', text_hint, re.IGNORECASE))
    if qnum_with_parts >= 4:  # Multiple Q# (a)/(b) patterns = answer key
        return "answer_key"

    # If page has blank answer lines, it's a question page, not answer key
    if has_blank_answer_lines:
        # Determine question type based on section markers first
        if "paper 2" in text_lower:
            return "long_answer"
        if "booklet b" in text_lower:
            return "short_answer"
        if "booklet a" in text_lower:
            return "mcq"
        # Fall back to position-based
        ratio = page_num / total_pages
        if ratio < 0.25:
            return "mcq"
        elif ratio < 0.50:
            return "short_answer"
        else:
            return "long_answer"

    # PRIORITY 2: Strong section markers from page headers
    if "booklet a" in text_lower or "questions 1 to 10" in text_lower:
        return "mcq"
    if "booklet b" in text_lower or "questions 16 to" in text_lower or "questions 11 to" in text_lower:
        return "short_answer"
    if "paper 2" in text_lower and "answer" not in text_lower:
        return "long_answer"

    # PRIORITY 3: Detect by question number ranges mentioned
    q1_10_pattern = re.search(r'\b(Q|Question)\s*([1-9]|10)\b', text_hint, re.IGNORECASE)
    mcq_options = re.findall(r'\([A-D]\)|^[A-D]\s*[:\.]', text_hint, re.MULTILINE)

    if q1_10_pattern and len(mcq_options) >= 4:
        return "mcq"

    # PRIORITY 4: Content-based detection for P2 pages
    # If page has question numbers and long text content, likely a question page
    if has_question_numbers and len(text_hint) > 500:
        ratio = page_num / total_pages
        if ratio >= 0.50:  # Later half of PDF
            return "long_answer"

    # PRIORITY 5: Position-based heuristic (last resort only)
    # Be very conservative - only classify as answer_key if we're very sure
    ratio = page_num / total_pages
    if ratio >= 0.90:  # Only last 10% as answer key (more conservative)
        # Double-check: if page has significant text content, might be question page
        if len(text_hint) > 800 and has_question_numbers:
            return "long_answer"
        return "answer_key"
    elif ratio < 0.25:
        return "mcq"
    elif ratio < 0.50:
        return "short_answer"
    else:
        return "long_answer"


def clean_extracted_text(text: str, has_subparts: bool = None) -> str:
    """Clean up common extraction artifacts from question text.

    Args:
        text: Raw extracted text
        has_subparts: If True, keep (a) markers. If False, remove spurious (a).
                      If None, auto-detect based on presence of (b), (c), etc.
    """
    if not text:
        return text

    # Remove "(a) None" or "(a): None" patterns (spurious sub-part markers)
    text = re.sub(r'\n?\s*\([a-z]\)\s*:?\s*None\s*', '', text, flags=re.IGNORECASE)

    # Remove standalone "None" on its own line
    text = re.sub(r'^\s*None\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE)

    # Fix missing spaces after periods (e.g., "word.Another" -> "word. Another")
    text = re.sub(r'\.([A-Z])', r'. \1', text)

    # Fix garbled OCR: missing spaces before capital letters in run-together words
    # e.g., "TheamountofmoneycollectedonMonday" -> "The amount of money collected on Monday"
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    # Fix garbled OCR: missing spaces after currency/numbers
    # e.g., "$3.10morethanapen" -> "$3.10 more than a pen"
    text = re.sub(r'(\$\d+\.?\d*)([a-zA-Z])', r'\1 \2', text)

    # Fix garbled OCR: missing spaces after numbers with symbols before words
    # e.g., "20¢coins" -> "20¢ coins", "25%more" -> "25% more"
    text = re.sub(r'(\d+[¢%])([a-zA-Z])', r'\1 \2', text)

    # Fix missing space after numbers before words
    # e.g., "1coinsthan" -> "1 coins than"
    text = re.sub(r'(\d)([a-zA-Z]{2,})', r'\1 \2', text)

    # Auto-detect if this is a multi-part question
    if has_subparts is None:
        # Check if text has (b), (c), etc. - indicates genuine multi-part question
        has_subparts = bool(re.search(r'\([b-z]\)', text, re.IGNORECASE))

    # Remove spurious standalone "(a)" at start of text when not multi-part
    if not has_subparts:
        text = re.sub(r'^\s*\(a\)\s*', '', text, flags=re.IGNORECASE)

    # Remove excessive whitespace but preserve paragraph breaks
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces to single space
    text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 newlines

    # Clean up leading/trailing whitespace on each line
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)

    return text.strip()


def parse_gemini_response(response: str, section_type: str) -> List[ParsedQuestion]:
    """Parse Gemini's structured response into question objects.

    Handles both MCQ format and multi-part question format:
    - MCQ: Q1: Text + A/B/C/D options
    - Multi-part: Q6: Main + (a)/(b)/(c) sub-parts
    """
    questions = []

    # Split by question markers
    blocks = re.split(r"(?:^|\n)---+\s*\n?", response)

    for block in blocks:
        if not block.strip():
            continue

        # Try to extract question number
        num_match = re.search(r"(?:QUESTION|Q)\s*(\d+)", block, re.IGNORECASE)
        if not num_match:
            continue

        q_num = int(num_match.group(1))

        # Initialize variables
        text = ""
        options = None
        diagram = None
        marks = 1
        q_type = section_type

        # Extract diagram description (common to all formats)
        diag_match = re.search(r"Diagram:\s*(.+?)(?=\n---|$)", block, re.DOTALL | re.IGNORECASE)
        if diag_match:
            diagram = diag_match.group(1).strip()
            if diagram.lower() in ["none", "n/a", ""]:
                diagram = None

        # Check if this is a multi-part question (has Main: or (a):)
        has_main = re.search(r"Main:\s*(.+?)(?=\n\([a-z]\):|Diagram:|$)", block, re.DOTALL | re.IGNORECASE)
        has_parts = re.search(r"\([a-z]\):", block, re.IGNORECASE)

        if has_main or has_parts:
            # MULTI-PART QUESTION FORMAT
            # Create SEPARATE entries for each part
            parsed_parts = []

            # Extract main question text (shared context)
            main_text = ""
            if has_main:
                main_text = has_main.group(1).strip()
                if main_text.lower() == "none":
                    main_text = ""

            # Extract sub-parts (a), (b), (c), etc.
            for letter in ['a', 'b', 'c', 'd', 'e']:
                part_pattern = rf"\({letter}\):\s*(.+?)(?=\n\([a-z]\):|\nDiagram:|\n---|$)"
                part_match = re.search(part_pattern, block, re.DOTALL | re.IGNORECASE)
                if part_match:
                    part_text = part_match.group(1).strip()
                    # Skip if part text is just "None" or empty
                    if part_text.lower() in ["none", "n/a", ""]:
                        continue
                    # Extract marks from part if present
                    mark_match = re.search(r'\((\d+)\s*marks?\)', part_text, re.IGNORECASE)
                    part_marks = int(mark_match.group(1)) if mark_match else 2
                    # Clean marks from text
                    part_text = re.sub(r'\s*\(\d+\s*marks?\)', '', part_text, flags=re.IGNORECASE).strip()
                    if part_text:  # Only add non-empty parts
                        parsed_parts.append((letter, part_text, part_marks))

            # Also check for Text: field (single question with no parts)
            if not parsed_parts:
                text_match = re.search(r"Text:\s*(.+?)(?=\nDiagram:|\n---|$)", block, re.DOTALL | re.IGNORECASE)
                if text_match:
                    text = text_match.group(1).strip()
                    # Check for marks in text
                    mark_match = re.search(r'\((\d+)\s*marks?\)', text, re.IGNORECASE)
                    part_marks = int(mark_match.group(1)) if mark_match else 2
                    text = re.sub(r'\s*\(\d+\s*marks?\)', '', text, flags=re.IGNORECASE).strip()
                    if main_text:
                        text = main_text + "\n\n" + text
                    # Single question, no parts
                    text = clean_extracted_text(text)
                    if text:
                        questions.append(ParsedQuestion(
                            number=q_num,
                            text=text,
                            question_type=section_type,
                            options=None,
                            diagram=diagram,
                            marks=part_marks,
                            part_letter=None,
                            main_context=None
                        ))
                    continue

            # Create separate entries for each part
            if parsed_parts:
                for letter, part_text, part_marks in parsed_parts:
                    # Clean up the part-specific text
                    cleaned_part = clean_extracted_text(part_text, has_subparts=True)
                    cleaned_main = clean_extracted_text(main_text) if main_text else None

                    if cleaned_part:
                        questions.append(ParsedQuestion(
                            number=q_num,
                            text=f"({letter}) {cleaned_part}",  # Part-specific text
                            question_type=section_type,
                            options=None,
                            diagram=diagram,
                            marks=part_marks,
                            part_letter=letter,
                            main_context=cleaned_main  # Shared context
                        ))
                continue  # Skip the rest of processing for this block

        else:
            # MCQ or simple question format
            # Extract text
            text_match = re.search(r"Text:\s*(.+?)(?=\n(?:Type|Options|Diagram|A:)|$)", block, re.DOTALL | re.IGNORECASE)
            text = text_match.group(1).strip() if text_match else ""

            # Extract type
            type_match = re.search(r"Type:\s*(\w+)", block, re.IGNORECASE)
            q_type = type_match.group(1) if type_match else section_type

            # Extract options for MCQ
            if "mcq" in q_type.lower() or section_type == "mcq":
                options = {}
                for letter in ["A", "B", "C", "D"]:
                    opt_match = re.search(rf"^{letter}:\s*(.+?)(?=\n[A-D]:|Diagram:|$)", block, re.DOTALL | re.MULTILINE)
                    if opt_match:
                        options[letter] = opt_match.group(1).strip()
                if not options:
                    options = None

            # Determine marks based on section
            if section_type == "mcq":
                marks = 1 if q_num <= 10 else 2
            elif section_type == "short_answer":
                marks = 2
            else:
                marks = 3  # Default for long answer

        # Clean up the extracted text
        text = clean_extracted_text(text)

        if text:  # Only add if we have text
            questions.append(ParsedQuestion(
                number=q_num,
                text=text,
                question_type=q_type,
                options=options,
                diagram=diagram,
                marks=marks,
                part_letter=None,
                main_context=None
            ))

    return questions


def process_pdf(
    pdf_path: Path,
    client: GeminiClient,
    page_range: Optional[Tuple[int, int]] = None,
    save_to_db: bool = True
) -> Dict:
    """
    Process a single PDF file.

    Returns dict with stats about processing.
    """
    print(f"\n{'=' * 60}")
    print(f"Processing: {pdf_path.name}")
    print(f"{'=' * 60}")

    school, year = parse_school_from_filename(pdf_path.name)
    print(f"[INFO] School: {school}, Year: {year}")

    stats = {
        "pdf": pdf_path.name,
        "school": school,
        "year": year,
        "pages_processed": 0,
        "questions_found": 0,
        "errors": []
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            print(f"[INFO] Total pages: {total_pages}")

            # Determine page range
            if page_range:
                start_page, end_page = page_range
            else:
                start_page, end_page = 1, total_pages

            start_idx = max(0, start_page - 1)
            end_idx = min(end_page, total_pages)

            print(f"[INFO] Processing pages {start_page} to {end_idx}")
            print(f"[INFO] Memory: {get_memory()}")

            current_section = "mcq"

            for page_idx in range(start_idx, end_idx):
                page_num = page_idx + 1
                print(f"\n[PAGE {page_num}/{total_pages}] ", end="")

                # Convert page to image
                page = pdf.pages[page_idx]
                img = page.to_image(resolution=DPI)
                image = img.original

                # Get text hint for section detection
                text_hint = page.extract_text() or ""
                section_type = detect_section_type(page_num, total_pages, text_hint)

                # Skip if likely blank/cover page
                if len(text_hint) < 50 and page_num <= 2:
                    print(f"[SKIP] Cover/blank page")
                    del image
                    gc.collect()
                    continue

                print(f"[{section_type.upper()}] ", end="")

                # Skip answer key pages entirely - process separately with parse_answers.py
                if section_type == "answer_key":
                    print(f"[SKIP] Answer key page - use parse_answers.py")
                    del image
                    gc.collect()
                    continue

                # Save image if enabled
                if SAVE_IMAGES:
                    img_path = IMAGES_DIR / f"{school}_{year}_p{page_num:02d}.png"
                    image.save(img_path)

                # Send to Gemini with appropriate prompt
                if section_type == "mcq":
                    prompt = MCQ_EXTRACTION_PROMPT
                else:
                    prompt = MULTI_PART_EXTRACTION_PROMPT

                result = client.extract_from_image(image, prompt, page_num)

                if result.success:
                    print(f"[OK] ", end="")

                    # Parse response
                    questions = parse_gemini_response(result.question_text, section_type)
                    print(f"Found {len(questions)} questions")

                    # Save to database
                    if save_to_db and section_type != "answer_key":
                        for q in questions:
                            try:
                                # Determine paper section code
                                if section_type == "mcq":
                                    paper_section = "P1A"
                                elif section_type == "short_answer":
                                    paper_section = "P1B"
                                else:
                                    paper_section = "P2"

                                # Store original PDF question number for display purposes
                                pdf_q_num = q.number

                                # VALIDATION: P1A (MCQ) should only have Q1-Q15
                                # If detected as MCQ but Q# > 15, it's actually P1B
                                if paper_section == "P1A" and q.number > 15:
                                    paper_section = "P1B"
                                    print(f"    [AUTO-FIX] Q{q.number} moved from P1A to P1B (Q# > 15)")

                                # Adjust question numbers for P1B storage
                                # PDF shows Q16-30 (continuing from P1A), but P1B should be stored as Q1-15
                                actual_q_num = q.number
                                if paper_section == "P1B" and q.number > 15:
                                    actual_q_num = q.number - 15

                                img_path = IMAGES_DIR / f"{school}_{year}_p{page_num:02d}.png"

                                insert_question(
                                    school=school,
                                    year=year,
                                    paper_section=paper_section,
                                    question_num=actual_q_num,
                                    marks=q.marks,
                                    latex_text=q.text,
                                    image_path=str(img_path),
                                    diagram_description=q.diagram,
                                    options=q.options,
                                    pdf_question_num=pdf_q_num,
                                    pdf_page_num=page_num,
                                    part_letter=q.part_letter,
                                    main_context=q.main_context,
                                )
                                stats["questions_found"] += 1
                            except Exception as e:
                                stats["errors"].append(f"Q{q.number}: {e}")

                    elif section_type == "answer_key":
                        # TODO: Parse and link answers to questions
                        print(f"    [Answer key - linking TODO]")

                else:
                    print(f"[ERROR] {result.error}")
                    stats["errors"].append(f"Page {page_num}: {result.error}")

                stats["pages_processed"] += 1

                # Cleanup
                del image
                gc.collect()

    except Exception as e:
        print(f"\n[ERROR] {e}")
        stats["errors"].append(str(e))

    return stats


def main():
    parser = argparse.ArgumentParser(description="Process P6 Math PDFs with Gemini")
    parser.add_argument("--pdf", type=str, help="Specific PDF to process")
    parser.add_argument("--pages", type=str, help="Page range (e.g., 2-10)")
    parser.add_argument("--no-db", action="store_true", help="Don't save to database")
    args = parser.parse_args()

    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY not set!")
        print("Get a free key at: https://aistudio.google.com/app/apikey")
        print("Then: export GEMINI_API_KEY='your-key'")
        sys.exit(1)

    # Initialize
    print("=" * 60)
    print("P6 MATH QUESTION EXTRACTION PIPELINE")
    print("Using Gemini API (cloud-based, memory-safe)")
    print("=" * 60)

    print(f"\n[INIT] Memory: {get_memory()}")

    # Init database
    init_db()

    # Init Gemini client
    print("[INIT] Connecting to Gemini...")
    client = GeminiClient(api_key=api_key)
    if not client.test_connection():
        print("[ERROR] Gemini connection failed!")
        sys.exit(1)
    print("[OK] Gemini connected")

    # Parse page range
    page_range = None
    if args.pages:
        try:
            start, end = map(int, args.pages.split("-"))
            page_range = (start, end)
        except:
            print(f"[ERROR] Invalid page range: {args.pages}")
            sys.exit(1)

    # Get PDFs to process
    if args.pdf:
        pdfs = [PDF_DIR / args.pdf]
        if not pdfs[0].exists():
            # Try without path
            pdfs = [Path(args.pdf)]
    else:
        pdfs = sorted(PDF_DIR.glob("*.pdf"))

    if not pdfs:
        print("[ERROR] No PDFs found!")
        sys.exit(1)

    print(f"\n[INFO] Found {len(pdfs)} PDF(s) to process")

    # Process each PDF
    all_stats = []
    for pdf_path in pdfs:
        if not pdf_path.exists():
            print(f"[SKIP] Not found: {pdf_path}")
            continue

        stats = process_pdf(
            pdf_path,
            client,
            page_range=page_range,
            save_to_db=not args.no_db
        )
        all_stats.append(stats)

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)

    total_pages = sum(s["pages_processed"] for s in all_stats)
    total_questions = sum(s["questions_found"] for s in all_stats)
    total_errors = sum(len(s["errors"]) for s in all_stats)

    print(f"PDFs processed: {len(all_stats)}")
    print(f"Pages processed: {total_pages}")
    print(f"Questions extracted: {total_questions}")
    print(f"Errors: {total_errors}")

    if not args.no_db:
        db_stats = get_statistics()
        print(f"\nDatabase now contains: {db_stats['total_questions']} questions")

    print(f"\n[DONE] Memory: {get_memory()}")


if __name__ == "__main__":
    main()
