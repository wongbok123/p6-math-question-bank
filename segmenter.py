"""
OpenCV-based question boundary detection and segmentation.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass

from config import SEGMENTATION, IMAGES_DIR


@dataclass
class QuestionBox:
    """Represents a detected question region."""
    y_start: int
    y_end: int
    x_start: int
    x_end: int
    page_num: int
    confidence: float = 1.0

    @property
    def height(self) -> int:
        return self.y_end - self.y_start

    @property
    def width(self) -> int:
        return self.x_end - self.x_start


class QuestionSegmenter:
    """Detects and extracts question regions from page images."""

    def __init__(self, config: dict = None):
        self.config = config or SEGMENTATION

    def detect_horizontal_lines(self, image: np.ndarray) -> List[int]:
        """
        Detect horizontal lines in an image using morphological operations.
        Returns list of y-coordinates where horizontal lines are detected.
        """
        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Apply binary threshold
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        # Create horizontal kernel for line detection
        kernel_width = self.config["morph_kernel_width"]
        kernel_height = self.config["morph_kernel_height"]
        horizontal_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (kernel_width, kernel_height)
        )

        # Detect horizontal lines
        detected_lines = cv2.morphologyEx(
            binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2
        )

        # Find contours of detected lines
        contours, _ = cv2.findContours(
            detected_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Extract y-coordinates of lines that meet minimum length
        line_positions = []
        min_length = self.config["min_line_length"]

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w >= min_length:
                line_positions.append(y + h // 2)

        # Sort and cluster nearby lines
        line_positions = sorted(set(line_positions))
        clustered = self._cluster_lines(line_positions)

        return clustered

    def _cluster_lines(self, positions: List[int]) -> List[int]:
        """Cluster nearby line positions to avoid duplicates."""
        if not positions:
            return []

        gap_threshold = self.config["line_gap_threshold"]
        clustered = []
        current_cluster = [positions[0]]

        for pos in positions[1:]:
            if pos - current_cluster[-1] <= gap_threshold:
                current_cluster.append(pos)
            else:
                clustered.append(int(np.mean(current_cluster)))
                current_cluster = [pos]

        if current_cluster:
            clustered.append(int(np.mean(current_cluster)))

        return clustered

    def detect_question_numbers(self, image: np.ndarray) -> List[Tuple[int, int]]:
        """
        Detect question number regions using template matching or OCR hints.
        Returns list of (y_position, question_number) tuples.
        """
        # This is a simplified version - can be enhanced with PaddleOCR
        # For now, relies on horizontal line detection
        return []

    def segment_page(
        self, image: np.ndarray, page_num: int = 0
    ) -> List[QuestionBox]:
        """
        Segment a page image into question boxes.
        """
        height, width = image.shape[:2]

        # Detect horizontal dividing lines
        line_positions = self.detect_horizontal_lines(image)

        # Add page boundaries if not present
        if not line_positions or line_positions[0] > 100:
            line_positions.insert(0, 0)
        if not line_positions or line_positions[-1] < height - 100:
            line_positions.append(height)

        # Create question boxes between consecutive lines
        boxes = []
        min_height = self.config["min_question_height"]
        max_height = self.config["max_question_height"]

        for i in range(len(line_positions) - 1):
            y_start = line_positions[i]
            y_end = line_positions[i + 1]
            box_height = y_end - y_start

            # Filter by height constraints
            if min_height <= box_height <= max_height:
                boxes.append(
                    QuestionBox(
                        y_start=y_start,
                        y_end=y_end,
                        x_start=0,
                        x_end=width,
                        page_num=page_num,
                    )
                )

        return boxes

    def extract_regions(
        self,
        image: np.ndarray,
        boxes: List[QuestionBox],
        margin: int = 10,
    ) -> List[np.ndarray]:
        """
        Extract image regions for each question box.
        """
        regions = []
        height, width = image.shape[:2]

        for box in boxes:
            # Apply margin with bounds checking
            y_start = max(0, box.y_start - margin)
            y_end = min(height, box.y_end + margin)
            x_start = max(0, box.x_start - margin)
            x_end = min(width, box.x_end + margin)

            region = image[y_start:y_end, x_start:x_end]
            regions.append(region)

        return regions

    def save_regions(
        self,
        regions: List[np.ndarray],
        school: str,
        year: int,
        section: str,
        start_num: int = 1,
    ) -> List[Path]:
        """
        Save extracted regions as images.
        Returns list of saved file paths.
        """
        saved_paths = []
        school_dir = IMAGES_DIR / f"{school}_{year}"
        school_dir.mkdir(parents=True, exist_ok=True)

        for i, region in enumerate(regions):
            question_num = start_num + i
            filename = f"{section}_Q{question_num:02d}.png"
            filepath = school_dir / filename

            cv2.imwrite(str(filepath), region)
            saved_paths.append(filepath)

        return saved_paths


def segment_with_canny(image: np.ndarray) -> List[int]:
    """
    Alternative segmentation using Canny edge detection.
    Useful for pages without clear horizontal lines.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

    # Apply Gaussian blur
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Canny edge detection
    edges = cv2.Canny(
        blurred,
        SEGMENTATION["canny_low"],
        SEGMENTATION["canny_high"],
    )

    # Project edges horizontally
    horizontal_projection = np.sum(edges, axis=1)

    # Find valleys (potential boundaries)
    threshold = np.mean(horizontal_projection) * 0.5
    boundaries = []

    in_valley = horizontal_projection[0] < threshold
    valley_start = 0 if in_valley else None

    for i, val in enumerate(horizontal_projection):
        if val < threshold and not in_valley:
            in_valley = True
            valley_start = i
        elif val >= threshold and in_valley:
            in_valley = False
            if valley_start is not None:
                boundaries.append((valley_start + i) // 2)

    return boundaries


def validate_segmentation(
    boxes: List[QuestionBox], expected_count: int
) -> Tuple[bool, str]:
    """
    Validate that segmentation produced expected number of questions.
    """
    actual_count = len(boxes)

    if actual_count == expected_count:
        return True, f"Segmentation valid: {actual_count} questions detected"
    elif actual_count < expected_count:
        return False, f"Under-segmentation: expected {expected_count}, got {actual_count}"
    else:
        return False, f"Over-segmentation: expected {expected_count}, got {actual_count}"


if __name__ == "__main__":
    # Test with a sample image
    import sys

    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        image = cv2.imread(image_path)
        if image is None:
            print(f"Could not load image: {image_path}")
            sys.exit(1)

        segmenter = QuestionSegmenter()
        boxes = segmenter.segment_page(image)

        print(f"Detected {len(boxes)} question regions:")
        for i, box in enumerate(boxes):
            print(f"  Q{i+1}: y={box.y_start}-{box.y_end}, height={box.height}")
    else:
        print("Usage: python segmenter.py <image_path>")
