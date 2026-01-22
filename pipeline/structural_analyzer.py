"""
PaddleOCR-based structural analysis for detecting section anchors.
"""

import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

from config import SECTION_ANCHORS, PAPER_SECTIONS


@dataclass
class PageInfo:
    """Information about a single page."""
    page_num: int
    section: Optional[str] = None
    is_answer_key: bool = False
    detected_anchors: List[str] = field(default_factory=list)
    question_range: Tuple[int, int] = (0, 0)


@dataclass
class DocumentStructure:
    """Complete document structure analysis."""
    pages: List[PageInfo] = field(default_factory=list)
    section_page_ranges: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    answer_key_start: Optional[int] = None

    def get_section_pages(self, section: str) -> List[int]:
        """Get list of page numbers for a section."""
        if section not in self.section_page_ranges:
            return []
        start, end = self.section_page_ranges[section]
        return list(range(start, end + 1))


class StructuralAnalyzer:
    """Analyzes document structure using PaddleOCR."""

    def __init__(self):
        self.ocr = None
        self._init_ocr()

    def _init_ocr(self):
        """Initialize PaddleOCR (lazy loading)."""
        try:
            from paddleocr import PaddleOCR
            import logging
            # Suppress PaddleOCR logs
            logging.getLogger("ppocr").setLevel(logging.WARNING)
            # New PaddleOCR API (v3.x) - simplified initialization
            self.ocr = PaddleOCR(lang="en")
        except ImportError:
            print("Warning: PaddleOCR not available. Using fallback text detection.")
            self.ocr = None
        except Exception as e:
            print(f"Warning: PaddleOCR initialization failed: {e}")
            self.ocr = None

    def extract_text(self, image: np.ndarray) -> List[Tuple[str, float]]:
        """
        Extract text from image using PaddleOCR.
        Returns list of (text, confidence) tuples.
        """
        if self.ocr is None:
            return []

        try:
            result = self.ocr.predict(image)
            if result is None:
                return []

            texts = []
            # Handle new PaddleOCR v3.x result format
            if isinstance(result, dict) and "rec_texts" in result:
                # New format: dict with rec_texts and rec_scores
                rec_texts = result.get("rec_texts", [])
                rec_scores = result.get("rec_scores", [])
                for text, score in zip(rec_texts, rec_scores):
                    if text:
                        texts.append((text, float(score) if score else 1.0))
            elif isinstance(result, list):
                # Old format or list of results
                for item in result:
                    if isinstance(item, dict) and "rec_texts" in item:
                        rec_texts = item.get("rec_texts", [])
                        rec_scores = item.get("rec_scores", [])
                        for text, score in zip(rec_texts, rec_scores):
                            if text:
                                texts.append((text, float(score) if score else 1.0))
                    elif isinstance(item, list):
                        # Legacy format
                        for line in item:
                            if line and len(line) >= 2:
                                text = line[1][0]
                                confidence = line[1][1]
                                texts.append((text, confidence))

            return texts
        except Exception as e:
            print(f"OCR extraction error: {e}")
            return []

    def detect_anchors(self, image: np.ndarray) -> List[str]:
        """
        Detect section anchors in an image.
        Returns list of detected anchor strings.
        """
        texts = self.extract_text(image)
        text_content = " ".join([t[0].lower() for t in texts])

        detected = []
        for section, anchors in SECTION_ANCHORS.items():
            for anchor in anchors:
                if anchor.lower() in text_content:
                    detected.append(anchor)

        return detected

    def classify_page(self, image: np.ndarray, page_num: int) -> PageInfo:
        """
        Classify a single page based on detected anchors.
        """
        anchors = self.detect_anchors(image)
        info = PageInfo(page_num=page_num, detected_anchors=anchors)

        # Check for answer key
        for anchor in SECTION_ANCHORS["ANSWER_KEY"]:
            if anchor in anchors:
                info.is_answer_key = True
                return info

        # Determine section
        section_scores = {"P1A": 0, "P1B": 0, "P2": 0}
        for section in ["P1A", "P1B", "P2"]:
            for anchor in SECTION_ANCHORS[section]:
                if anchor in anchors:
                    section_scores[section] += 1

        if max(section_scores.values()) > 0:
            info.section = max(section_scores, key=section_scores.get)

        return info

    def analyze_document(
        self, images: List[np.ndarray]
    ) -> DocumentStructure:
        """
        Analyze complete document structure.
        """
        structure = DocumentStructure()

        if self.ocr is None:
            # Fallback: use heuristic page ranges based on typical exam structure
            return self._fallback_structure(len(images))

        # Classify each page
        for page_num, image in enumerate(images):
            page_info = self.classify_page(image, page_num)
            structure.pages.append(page_info)

            if page_info.is_answer_key and structure.answer_key_start is None:
                structure.answer_key_start = page_num

        # Determine section ranges
        self._compute_section_ranges(structure)

        # If no sections found, use fallback
        if not structure.section_page_ranges:
            return self._fallback_structure(len(images))

        return structure

    def _fallback_structure(self, total_pages: int) -> DocumentStructure:
        """
        Create fallback document structure when OCR fails.
        Uses typical P6 exam page layout heuristics.
        """
        structure = DocumentStructure()

        # Typical exam structure:
        # - First ~30% of pages: P1A (MCQ Booklet A)
        # - Next ~30%: P1B (Booklet B)
        # - Next ~30%: P2
        # - Last ~10%: Answer key

        # Estimate section boundaries
        content_pages = int(total_pages * 0.85)  # Reserve 15% for answer key
        section_size = content_pages // 3

        structure.section_page_ranges = {
            "P1A": (0, section_size - 1),
            "P1B": (section_size, 2 * section_size - 1),
            "P2": (2 * section_size, content_pages - 1),
        }
        structure.answer_key_start = content_pages

        # Create page info for all pages
        for page_num in range(total_pages):
            section = None
            is_answer = page_num >= content_pages
            if not is_answer:
                if page_num < section_size:
                    section = "P1A"
                elif page_num < 2 * section_size:
                    section = "P1B"
                else:
                    section = "P2"
            structure.pages.append(PageInfo(
                page_num=page_num,
                section=section,
                is_answer_key=is_answer,
            ))

        return structure

    def _compute_section_ranges(self, structure: DocumentStructure):
        """
        Compute page ranges for each section based on classified pages.
        """
        current_section = None
        section_starts = {}

        for page_info in structure.pages:
            if page_info.is_answer_key:
                # End all sections at answer key
                break

            if page_info.section and page_info.section != current_section:
                # Record start of new section
                section_starts[page_info.section] = page_info.page_num
                current_section = page_info.section

        # Compute end of each section
        sections = list(section_starts.keys())
        for i, section in enumerate(sections):
            start = section_starts[section]
            if i + 1 < len(sections):
                end = section_starts[sections[i + 1]] - 1
            elif structure.answer_key_start:
                end = structure.answer_key_start - 1
            else:
                end = len(structure.pages) - 1

            structure.section_page_ranges[section] = (start, end)

    def quick_scan(self, image: np.ndarray) -> Dict[str, bool]:
        """
        Quick scan for key features without full OCR.
        Uses text extraction to check for specific patterns.
        """
        texts = self.extract_text(image)
        text_content = " ".join([t[0].lower() for t in texts])

        return {
            "has_mcq": "multiple choice" in text_content or "(a)" in text_content,
            "has_diagram": "diagram" in text_content or "figure" in text_content,
            "has_marks": "mark" in text_content or "[" in text_content,
            "is_answer": any(
                anchor.lower() in text_content
                for anchor in SECTION_ANCHORS["ANSWER_KEY"]
            ),
        }


def get_expected_questions(section: str) -> int:
    """Get expected question count for a section."""
    if section in PAPER_SECTIONS:
        return PAPER_SECTIONS[section]["total_questions"]
    return 0


def get_mark_for_question(section: str, question_num: int) -> Optional[int]:
    """
    Get marks for a specific question number in a section.
    Returns None if marks are variable (3-5).
    """
    if section not in PAPER_SECTIONS:
        return None

    for range_info in PAPER_SECTIONS[section]["question_ranges"]:
        if range_info["start"] <= question_num <= range_info["end"]:
            return range_info["marks"]

    return None


if __name__ == "__main__":
    # Test structural analysis
    import cv2
    import sys

    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        image = cv2.imread(image_path)
        if image is None:
            print(f"Could not load image: {image_path}")
            sys.exit(1)

        analyzer = StructuralAnalyzer()
        page_info = analyzer.classify_page(image, 0)

        print(f"Page Analysis:")
        print(f"  Section: {page_info.section}")
        print(f"  Is Answer Key: {page_info.is_answer_key}")
        print(f"  Detected Anchors: {page_info.detected_anchors}")
    else:
        print("Usage: python structural_analyzer.py <image_path>")
