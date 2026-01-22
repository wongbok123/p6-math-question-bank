"""
MiniCPM-V based vision extraction for math questions.
"""

import base64
import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import cv2

from config import (
    OLLAMA_BASE_URL,
    VISION_MODEL,
    QUESTION_EXTRACTION_PROMPT,
)


@dataclass
class ExtractedQuestion:
    """Extracted question data."""
    latex_text: str
    options: Optional[Dict[str, str]] = None
    diagram_description: Optional[str] = None
    raw_response: str = ""


class VisionExtractor:
    """Extracts question content using vision language model."""

    def __init__(self, model: str = VISION_MODEL, base_url: str = OLLAMA_BASE_URL):
        self.model = model
        self.base_url = base_url

    def _image_to_base64(self, image: np.ndarray) -> str:
        """Convert numpy image to base64 string."""
        # Ensure RGB format
        if len(image.shape) == 3 and image.shape[2] == 3:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            image_rgb = image

        # Encode as PNG
        success, buffer = cv2.imencode(".png", cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR))
        if not success:
            raise ValueError("Failed to encode image")

        return base64.b64encode(buffer).decode("utf-8")

    def _call_ollama(self, prompt: str, image_b64: str) -> str:
        """Call Ollama API with image."""
        import requests

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.RequestException as e:
            print(f"Ollama API error: {e}")
            return ""

    def extract_question(self, image: np.ndarray) -> ExtractedQuestion:
        """
        Extract question content from an image.
        """
        image_b64 = self._image_to_base64(image)
        response = self._call_ollama(QUESTION_EXTRACTION_PROMPT, image_b64)

        return self._parse_question_response(response)

    def extract_from_file(self, image_path: Path) -> ExtractedQuestion:
        """
        Extract question from an image file.
        """
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")
        return self.extract_question(image)

    def _parse_question_response(self, response: str) -> ExtractedQuestion:
        """
        Parse the model response into structured data.
        """
        result = ExtractedQuestion(latex_text="", raw_response=response)

        # Extract text content
        text_match = re.search(r"<text>(.*?)</text>", response, re.DOTALL)
        if text_match:
            result.latex_text = text_match.group(1).strip()
        else:
            # Fallback: use entire response as text
            result.latex_text = self._clean_response(response)

        # Extract MCQ options
        options_match = re.search(r"<options>(.*?)</options>", response, re.DOTALL)
        if options_match:
            try:
                options_str = options_match.group(1).strip()
                result.options = json.loads(options_str)
            except json.JSONDecodeError:
                # Try to parse as key-value pairs
                result.options = self._parse_options_fallback(options_str)

        # Extract diagram description
        diagram_match = re.search(r"<diagram>(.*?)</diagram>", response, re.DOTALL)
        if diagram_match:
            desc = diagram_match.group(1).strip()
            if desc.lower() != "none":
                result.diagram_description = desc

        return result

    def _clean_response(self, response: str) -> str:
        """Clean up response text."""
        # Remove XML-like tags
        cleaned = re.sub(r"<[^>]+>", "", response)
        # Remove extra whitespace
        cleaned = " ".join(cleaned.split())
        return cleaned

    def _parse_options_fallback(self, options_str: str) -> Optional[Dict[str, str]]:
        """
        Fallback parser for MCQ options.
        Handles formats like "A: option1, B: option2" or "A) option1 B) option2"
        """
        options = {}

        # Try pattern: A: text or A) text or (A) text
        patterns = [
            r"([A-D])\s*[:\)]\s*([^A-D]+?)(?=[A-D]\s*[:\)]|$)",
            r"\(([A-D])\)\s*([^(]+?)(?=\([A-D]\)|$)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, options_str, re.IGNORECASE)
            if matches:
                for letter, text in matches:
                    options[letter.upper()] = text.strip()
                break

        return options if options else None

    def batch_extract(
        self, images: list, progress_callback=None
    ) -> list:
        """
        Extract questions from multiple images.
        """
        results = []
        total = len(images)

        for i, image in enumerate(images):
            if progress_callback:
                progress_callback(i, total)

            result = self.extract_question(image)
            results.append(result)

        return results


def create_extraction_prompt(question_type: str = "general") -> str:
    """
    Create a specialized extraction prompt based on question type.
    """
    base_prompt = """Analyze this math question image and extract the content.

Instructions:
1. Transcribe all text exactly as shown
2. Use LaTeX notation for mathematical expressions (e.g., $\\frac{1}{2}$, $x^2$)
3. For diagrams, provide a detailed description

"""

    if question_type == "mcq":
        return base_prompt + """
This is a Multiple Choice Question. Extract:
- The question text
- All options (A, B, C, D) with their content
- Any diagram description

Format:
<text>Question text with LaTeX math</text>
<options>{"A": "...", "B": "...", "C": "...", "D": "..."}</options>
<diagram>Description or "None"</diagram>
"""

    elif question_type == "short_answer":
        return base_prompt + """
This is a Short Answer Question. Extract:
- The complete question text
- Any given values or conditions
- Any diagram description

Format:
<text>Question text with LaTeX math</text>
<options>None</options>
<diagram>Description or "None"</diagram>
"""

    else:
        return QUESTION_EXTRACTION_PROMPT


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        image_path = Path(sys.argv[1])
        if not image_path.exists():
            print(f"File not found: {image_path}")
            sys.exit(1)

        extractor = VisionExtractor()
        print(f"Extracting from: {image_path}")

        result = extractor.extract_from_file(image_path)

        print(f"\nExtracted Content:")
        print(f"  Text: {result.latex_text[:200]}...")
        print(f"  Options: {result.options}")
        print(f"  Diagram: {result.diagram_description}")
    else:
        print("Usage: python vision_extractor.py <image_path>")
