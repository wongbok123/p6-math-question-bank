"""
Main pipeline runner for P6 Math Question Extraction.
"""

import argparse
import gc
import sys
import time
import traceback
from pathlib import Path
from typing import List, Optional

import psutil
from tqdm import tqdm


# =============================================================================
# Memory Management Utilities
# =============================================================================

def get_memory_usage():
    """Return current memory usage percentage and available GB."""
    mem = psutil.virtual_memory()
    return mem.percent, mem.available / (1024**3)


def check_memory_safe(threshold_percent=80, min_available_gb=2.0):
    """Check if it's safe to continue processing."""
    used_percent, available_gb = get_memory_usage()
    return used_percent < threshold_percent and available_gb > min_available_gb


def cleanup_memory():
    """Force garbage collection and log memory status."""
    gc.collect()
    used, available = get_memory_usage()
    return f"Memory: {used:.1f}% used, {available:.1f}GB available"

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import PDF_DIR, IMAGES_DIR, PAPER_SECTIONS
from database import init_db, insert_question, get_statistics
from segmenter import QuestionSegmenter
from pipeline.pdf_loader import PDFLoader, parse_pdf_filename, list_pdfs
from pipeline.structural_analyzer import (
    StructuralAnalyzer,
    DocumentStructure,
    get_mark_for_question,
)
from pipeline.vision_extractor import VisionExtractor
from pipeline.answer_parser import AnswerParser
from pipeline.validator import Validator, generate_validation_report, DocumentValidation
from utils.ollama_client import check_ollama_setup, ensure_models_available


class Pipeline:
    """Main extraction pipeline."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.pdf_loader = PDFLoader()
        self.structural_analyzer = None  # Lazy load
        self.segmenter = QuestionSegmenter()
        self.vision_extractor = None  # Lazy load
        self.answer_parser = None  # Lazy load
        self.validator = Validator()

    def _log(self, message: str):
        """Print message if verbose mode."""
        if self.verbose:
            print(message)

    def _init_ocr(self):
        """Initialize OCR components."""
        if self.structural_analyzer is None:
            self._log("Initializing PaddleOCR...")
            self.structural_analyzer = StructuralAnalyzer()

    def _init_vision(self):
        """Initialize vision model components."""
        if self.vision_extractor is None:
            self._log("Initializing vision extractor...")
            self.vision_extractor = VisionExtractor()
        if self.answer_parser is None:
            self._log("Initializing answer parser...")
            self.answer_parser = AnswerParser()

    def process_pdf(self, pdf_path: Path) -> DocumentValidation:
        """
        Process a single PDF through the complete pipeline.
        Uses page-by-page processing to avoid memory overload.
        """
        self._log(f"\n{'='*60}")
        self._log(f"Processing: {pdf_path.name}")
        self._log(f"{'='*60}")

        # Check memory before starting
        self._log(cleanup_memory())
        if not check_memory_safe():
            self._log("WARNING: Low memory at start, running cleanup...")
            gc.collect()
            time.sleep(1)

        # Parse filename for metadata
        year, school = parse_pdf_filename(pdf_path.name)
        self._log(f"School: {school}, Year: {year}")

        # Load PDF
        doc = self.pdf_loader.load_pdf(pdf_path)
        page_count = self.pdf_loader.get_page_count(doc)
        self._log(f"Pages: {page_count}")

        # Helper function to get page images on demand (avoids storing all in memory)
        def get_page_image(page_num):
            """Get a single page image (regenerated each time to save memory)."""
            return self.pdf_loader.page_to_image(doc, page_num)

        # Stage 1: Structural Analysis (requires all pages, but we process and release)
        self._log("\nStage 1: Structural Analysis")
        self._init_ocr()

        # Load pages one at a time for structural analysis
        self._log("  Analyzing document structure...")
        images_for_analysis = []
        for page_num in tqdm(range(page_count), desc="Loading pages", disable=not self.verbose):
            images_for_analysis.append(get_page_image(page_num))

        structure = self.structural_analyzer.analyze_document(images_for_analysis)

        # Clear images after structural analysis
        del images_for_analysis
        gc.collect()

        self._log(f"  Section ranges: {structure.section_page_ranges}")
        self._log(f"  Answer key starts at page: {structure.answer_key_start}")
        self._log(f"  {cleanup_memory()}")

        # Stage 2: Question Segmentation (page-by-page)
        self._log("\nStage 2: Question Segmentation")
        all_questions = {}

        for section, (start_page, end_page) in structure.section_page_ranges.items():
            self._log(f"  Processing {section} (pages {start_page}-{end_page})...")

            section_questions = []
            for page_num in range(start_page, end_page + 1):
                # Load single page, process, then release
                page_image = get_page_image(page_num)
                boxes = self.segmenter.segment_page(page_image, page_num)
                regions = self.segmenter.extract_regions(page_image, boxes)
                section_questions.extend(regions)
                del page_image
                gc.collect()

            all_questions[section] = section_questions
            self._log(f"    Found {len(section_questions)} question regions")

        self._log(f"  {cleanup_memory()}")

        # Stage 3: Vision Extraction
        self._log("\nStage 3: Vision Extraction")
        self._init_vision()

        extraction_results = {}
        for section, regions in all_questions.items():
            self._log(f"  Extracting {section}...")
            extracted = []

            for i, region in enumerate(tqdm(regions, desc=f"  {section}", disable=not self.verbose)):
                result = self.vision_extractor.extract_question(region)

                question_num = i + 1
                marks = get_mark_for_question(section, question_num) or 3

                extracted.append({
                    "question_num": question_num,
                    "marks": marks,
                    "latex_text": result.latex_text,
                    "options": result.options,
                    "diagram_description": result.diagram_description,
                    "image": region,
                })

            extraction_results[section] = extracted

        # Clear segmented questions after extraction
        del all_questions
        gc.collect()
        self._log(f"  {cleanup_memory()}")

        # Stage 4: Answer Extraction (page-by-page)
        self._log("\nStage 4: Answer Extraction")
        answers = {}

        if structure.answer_key_start is not None:
            answer_page_count = page_count - structure.answer_key_start
            self._log(f"  Processing {answer_page_count} answer pages...")

            for page_idx in range(answer_page_count):
                page_num = structure.answer_key_start + page_idx
                # Load single answer page, process, then release
                page_image = get_page_image(page_num)
                # For MCQ sections, try to parse answer key directly
                mcq_answers = self.answer_parser.parse_mcq_answer_key(page_image)
                if mcq_answers:
                    answers.setdefault("P1A", {}).update(mcq_answers)
                del page_image
                gc.collect()

        # Save to database
        self._log("\nSaving to database...")
        school_dir = IMAGES_DIR / f"{school}_{year}"
        school_dir.mkdir(parents=True, exist_ok=True)

        for section, questions in extraction_results.items():
            for q in questions:
                # Save image
                image_filename = f"{section}_Q{q['question_num']:02d}.png"
                image_path = school_dir / image_filename

                import cv2
                cv2.imwrite(str(image_path), q["image"])

                # Get answer if available
                section_answers = answers.get(section, {})
                answer = section_answers.get(q["question_num"])

                # Insert into database
                insert_question(
                    school=school,
                    year=year,
                    paper_section=section,
                    question_num=q["question_num"],
                    marks=q["marks"],
                    latex_text=q["latex_text"],
                    image_path=str(image_path),
                    diagram_description=q.get("diagram_description"),
                    options=q.get("options"),
                    answer=answer,
                )

        # Validate results
        self._log("\nValidation:")
        validation = self.validator.validate_document(extraction_results)
        validation.pdf_name = pdf_path.name

        if self.verbose:
            print(generate_validation_report(validation))

        # Cleanup
        doc.close()
        del extraction_results
        gc.collect()
        self._log(f"Completed: {cleanup_memory()}")

        return validation

    def process_all(self, pdf_dir: Path = PDF_DIR) -> List[DocumentValidation]:
        """
        Process all PDFs in the specified directory with memory safety.
        """
        pdfs = list_pdfs(pdf_dir)
        total = len(pdfs)
        self._log(f"Found {total} PDFs to process")

        results = []
        for idx, pdf_path in enumerate(pdfs, 1):
            # Progress indicator
            self._log(f"\n[{idx}/{total}] Starting: {pdf_path.name}")
            self._log(cleanup_memory())

            # Memory safety check before each PDF
            if not check_memory_safe():
                self._log("WARNING: Low memory, waiting for cleanup...")
                gc.collect()
                time.sleep(2)
                if not check_memory_safe(threshold_percent=90):
                    self._log("ERROR: Memory critically low, stopping batch processing")
                    break

            try:
                validation = self.process_pdf(pdf_path)
                results.append(validation)
            except MemoryError:
                self._log(f"MEMORY ERROR: Skipping {pdf_path.name}")
                gc.collect()
            except Exception as e:
                self._log(f"ERROR processing {pdf_path.name}: {e}")
                traceback.print_exc()
            finally:
                # Always cleanup between PDFs
                gc.collect()
                self._log(cleanup_memory())

        return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="P6 Math Question Extraction Pipeline"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all PDFs in the pdfs directory",
    )
    parser.add_argument(
        "--pdf",
        type=str,
        help="Process a specific PDF file",
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Initialize/reset the database",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check Ollama setup without processing",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output",
    )

    args = parser.parse_args()

    # Check Ollama setup
    if args.check:
        print("Checking Ollama setup...")
        status = check_ollama_setup()
        for key, value in status.items():
            icon = "OK" if value else "MISSING"
            print(f"  {key}: {icon}")
        return 0 if all(status.values()) else 1

    # Initialize database
    if args.init_db:
        init_db()
        print("Database initialized")
        return 0

    # Ensure Ollama is ready
    if not ensure_models_available():
        print("ERROR: Ollama setup incomplete. Run with --check for details.")
        return 1

    # Initialize database
    init_db()

    # Create pipeline
    pipeline = Pipeline(verbose=not args.quiet)

    if args.pdf:
        pdf_path = Path(args.pdf)
        if not pdf_path.exists():
            print(f"ERROR: PDF not found: {pdf_path}")
            return 1
        pipeline.process_pdf(pdf_path)

    elif args.all:
        results = pipeline.process_all()

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        success = sum(1 for r in results if r.is_valid)
        print(f"Processed: {len(results)} PDFs")
        print(f"Successful: {success}")
        print(f"With issues: {len(results) - success}")

        stats = get_statistics()
        print(f"\nTotal questions in database: {stats['total_questions']}")

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
