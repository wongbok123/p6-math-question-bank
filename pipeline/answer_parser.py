"""
Answer key parsing with working steps extraction.
"""

import re
import base64
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import cv2

from config import (
    OLLAMA_BASE_URL,
    VISION_MODEL,
    TEXT_MODEL,
    ANSWER_EXTRACTION_PROMPT,
    ANSWER_MARKERS,
    ANSWER_TYPE_PATTERNS,
)


@dataclass
class ExtractedAnswer:
    """Extracted answer data."""
    answer: str
    worked_solution: Optional[str] = None
    diagram_description: Optional[str] = None
    question_num: Optional[int] = None
    confidence: float = 1.0
    raw_response: str = ""


class AnswerParser:
    """Parses answer keys and extracts working steps."""

    def __init__(
        self,
        vision_model: str = VISION_MODEL,
        text_model: str = TEXT_MODEL,
        base_url: str = OLLAMA_BASE_URL,
    ):
        self.vision_model = vision_model
        self.text_model = text_model
        self.base_url = base_url

    def _image_to_base64(self, image: np.ndarray) -> str:
        """Convert numpy image to base64 string."""
        if len(image.shape) == 3 and image.shape[2] == 3:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            image_rgb = image

        success, buffer = cv2.imencode(".png", cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR))
        if not success:
            raise ValueError("Failed to encode image")

        return base64.b64encode(buffer).decode("utf-8")

    def _call_vision_model(self, prompt: str, image_b64: str) -> str:
        """Call vision model with image."""
        import requests

        payload = {
            "model": self.vision_model,
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
        except Exception as e:
            print(f"Vision model error: {e}")
            return ""

    def _call_text_model(self, prompt: str) -> str:
        """Call text model for validation."""
        import requests

        payload = {
            "model": self.text_model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            print(f"Text model error: {e}")
            return ""

    def extract_answer(self, image: np.ndarray) -> ExtractedAnswer:
        """
        Extract answer and working steps from an answer image.
        """
        image_b64 = self._image_to_base64(image)
        response = self._call_vision_model(ANSWER_EXTRACTION_PROMPT, image_b64)

        return self._parse_answer_response(response)

    def extract_from_file(self, image_path: Path) -> ExtractedAnswer:
        """Extract answer from an image file."""
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")
        return self.extract_answer(image)

    def _parse_answer_response(self, response: str) -> ExtractedAnswer:
        """
        Parse the model response into structured answer data.
        """
        result = ExtractedAnswer(answer="", raw_response=response)

        # Extract working steps
        working_match = re.search(r"<working>(.*?)</working>", response, re.DOTALL)
        if working_match:
            result.worked_solution = working_match.group(1).strip()

        # Extract final answer
        answer_match = re.search(r"<answer>(.*?)</answer>", response, re.DOTALL)
        if answer_match:
            result.answer = answer_match.group(1).strip()
        else:
            # Fallback: try to extract answer using markers
            result.answer = self._extract_answer_fallback(response)

        # Extract diagram answer description
        diagram_match = re.search(r"<diagram_answer>(.*?)</diagram_answer>", response, re.DOTALL)
        if diagram_match:
            desc = diagram_match.group(1).strip()
            if desc.lower() != "none":
                result.diagram_description = desc

        return result

    def _extract_answer_fallback(self, text: str) -> str:
        """
        Fallback method to extract answer using common markers.
        """
        # Try explicit markers
        for marker in ANSWER_MARKERS["explicit"]:
            pattern = rf"{re.escape(marker)}\s*(.+?)(?:\n|$)"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Try to find the last equation result
        equals_pattern = r"=\s*([^\n=]+)\s*$"
        matches = re.findall(equals_pattern, text, re.MULTILINE)
        if matches:
            return matches[-1].strip()

        return ""

    def validate_answer_type(
        self, answer: str, expected_type: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Validate that the answer matches expected type.
        Returns (is_valid, detected_type).
        """
        detected_type = None

        for type_name, pattern in ANSWER_TYPE_PATTERNS.items():
            if re.search(pattern, answer):
                detected_type = type_name
                break

        if expected_type:
            is_valid = detected_type == expected_type
            return is_valid, detected_type or "unknown"

        return detected_type is not None, detected_type or "unknown"

    def verify_answer(self, answer: str, question_text: str) -> float:
        """
        Use text model to verify answer plausibility.
        Returns confidence score 0-1.
        """
        prompt = f"""Given this math question:
{question_text}

Is this a plausible answer: {answer}

Respond with just a number from 0 to 100 indicating confidence that this is a correct answer format.
"""
        response = self._call_text_model(prompt)

        # Extract number from response
        match = re.search(r"(\d+)", response)
        if match:
            return min(int(match.group(1)) / 100, 1.0)
        return 0.5

    def parse_mcq_answer_key(self, image: np.ndarray) -> Dict[int, str]:
        """
        Parse an MCQ answer key page.
        Returns dict mapping question number to answer letter.
        """
        image_b64 = self._image_to_base64(image)

        prompt = """This is an MCQ answer key. Extract all question numbers and their answers.

Format each answer as: Q<number>: <letter>

Example output:
Q1: B
Q2: A
Q3: D
...

List all answers you can see:"""

        response = self._call_vision_model(prompt, image_b64)

        # Parse response
        answers = {}
        pattern = r"Q?(\d+)\s*[:=]\s*([A-Da-d])"
        matches = re.findall(pattern, response)

        for num_str, letter in matches:
            answers[int(num_str)] = letter.upper()

        return answers

    def batch_extract(
        self, images: List[np.ndarray], progress_callback=None
    ) -> List[ExtractedAnswer]:
        """
        Extract answers from multiple images.
        """
        results = []
        total = len(images)

        for i, image in enumerate(images):
            if progress_callback:
                progress_callback(i, total)

            result = self.extract_answer(image)
            results.append(result)

        return results


def create_answer_prompt_for_type(answer_type: str) -> str:
    """
    Create specialized answer extraction prompt based on expected type.
    """
    type_hints = {
        "money": "The answer should be a dollar amount (e.g., $45.60)",
        "ratio": "The answer should be a ratio (e.g., 3:5)",
        "percentage": "The answer should be a percentage (e.g., 25%)",
        "fraction": "The answer should be a fraction (e.g., 3/4)",
        "time": "The answer should include time units (e.g., 2 h 30 min)",
    }

    hint = type_hints.get(answer_type, "")

    return f"""Analyze this answer/solution image and extract:

1. Transcribe the COMPLETE solution with all working steps
2. Identify the FINAL answer
   {hint}
   Look for:
   - "Ans:", "Answer:", or "Total:"
   - Double-underlined or boxed values
   - The last equals sign result

Format your response as:
<working>Step-by-step solution</working>
<answer>Final value only</answer>
<diagram_answer>Description if answer is a diagram, otherwise "None"</diagram_answer>
"""


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        image_path = Path(sys.argv[1])
        if not image_path.exists():
            print(f"File not found: {image_path}")
            sys.exit(1)

        parser = AnswerParser()
        print(f"Extracting answer from: {image_path}")

        result = parser.extract_from_file(image_path)

        print(f"\nExtracted Answer:")
        print(f"  Answer: {result.answer}")
        print(f"  Working: {result.worked_solution[:200] if result.worked_solution else 'None'}...")
        print(f"  Diagram: {result.diagram_description}")
    else:
        print("Usage: python answer_parser.py <image_path>")
