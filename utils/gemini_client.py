"""
Gemini API client for vision-based question extraction.

Uses gemini-2.0-flash-exp (free tier) instead of local Ollama models.
Updated to use the new google-genai SDK.
"""

import os
import time
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass

from google import genai
from google.genai import types
from PIL import Image


# Default model - free tier
DEFAULT_MODEL = "gemini-2.0-flash"

# Rate limiting for free tier (15 RPM, 1M TPM, 1500 RPD)
REQUESTS_PER_MINUTE = 15
REQUEST_DELAY = 60 / REQUESTS_PER_MINUTE  # ~4 seconds between requests


@dataclass
class ExtractionResult:
    """Result from Gemini extraction."""
    question_text: str
    options: Optional[Dict[str, str]] = None
    diagram_description: Optional[str] = None
    answer: Optional[str] = None
    worked_solution: Optional[str] = None
    raw_response: str = ""
    page_number: int = 0
    success: bool = True
    error: Optional[str] = None


class GeminiClient:
    """Client for extracting math questions using Gemini API."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        """
        Initialize Gemini client.

        Args:
            api_key: Gemini API key. If not provided, reads from GEMINI_API_KEY env var.
            model: Model to use (default: gemini-2.0-flash-exp)
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini API key required. Set GEMINI_API_KEY environment variable "
                "or pass api_key parameter. Get a free key at: "
                "https://aistudio.google.com/app/apikey"
            )

        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting for free tier."""
        elapsed = time.time() - self.last_request_time
        if elapsed < REQUEST_DELAY:
            sleep_time = REQUEST_DELAY - elapsed
            print(f"  [Rate limit] Waiting {sleep_time:.1f}s...")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def extract_from_image(
        self,
        image: Image.Image,
        prompt: str,
        page_number: int = 0
    ) -> ExtractionResult:
        """
        Extract content from a single image using Gemini vision.

        Args:
            image: PIL Image object
            prompt: Extraction prompt
            page_number: Page number for tracking

        Returns:
            ExtractionResult with extracted content
        """
        self._rate_limit()

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, image]
            )
            text = response.text

            return ExtractionResult(
                question_text=text,
                raw_response=text,
                page_number=page_number,
                success=True
            )

        except Exception as e:
            return ExtractionResult(
                question_text="",
                page_number=page_number,
                success=False,
                error=str(e)
            )

    def extract_questions_from_pdf_page(
        self,
        image: Image.Image,
        page_number: int,
        section_type: str = "general"
    ) -> ExtractionResult:
        """
        Extract math questions from a PDF page image.

        Args:
            image: PIL Image of the PDF page
            page_number: Page number
            section_type: Type of section (mcq, short_answer, long_answer)

        Returns:
            ExtractionResult with structured extraction
        """
        prompt = self._get_extraction_prompt(section_type)
        return self.extract_from_image(image, prompt, page_number)

    def extract_answers_from_page(
        self,
        image: Image.Image,
        page_number: int
    ) -> ExtractionResult:
        """
        Extract answers/solutions from an answer key page.

        Args:
            image: PIL Image of the answer page
            page_number: Page number

        Returns:
            ExtractionResult with answers and worked solutions
        """
        prompt = ANSWER_EXTRACTION_PROMPT
        return self.extract_from_image(image, prompt, page_number)

    def _get_extraction_prompt(self, section_type: str) -> str:
        """Get appropriate prompt based on section type."""
        if section_type == "mcq":
            return MCQ_EXTRACTION_PROMPT
        elif section_type == "short_answer":
            return SHORT_ANSWER_PROMPT
        elif section_type == "long_answer":
            return LONG_ANSWER_PROMPT
        else:
            return GENERAL_EXTRACTION_PROMPT

    def test_connection(self) -> bool:
        """Test if API connection works."""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents="Reply with just 'OK' if you can read this."
            )
            return "OK" in response.text.upper()
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False


# Extraction prompts optimized for P6 Math papers
GENERAL_EXTRACTION_PROMPT = """Analyze this P6 Math exam page and extract ALL questions visible.

For EACH question found, provide:
1. Question number
2. Full question text (use LaTeX for math: $\\frac{1}{2}$, $x^2$, etc.)
3. If MCQ: list all options (A, B, C, D)
4. If there's a diagram: describe it in detail

Format your response as:
---
QUESTION [number]:
Text: [full question text with LaTeX math]
Type: [MCQ/Short Answer/Long Answer]
Options: [A: ..., B: ..., C: ..., D: ... OR "None"]
Diagram: [description OR "None"]
---

Extract ALL questions on this page. Be thorough."""


MCQ_EXTRACTION_PROMPT = """This is a Multiple Choice Questions page from a P6 Math exam.

Extract EVERY MCQ question visible. For each question:
1. Question number
2. Complete question text (use LaTeX for math expressions)
3. All four options A, B, C, D with their full content
4. Describe any diagrams/figures

Format each question as:
---
Q[number]:
Text: [question with $LaTeX$ math]
A: [option A]
B: [option B]
C: [option C]
D: [option D]
Diagram: [description or "None"]
---

Be precise with numbers, fractions, and mathematical notation."""


SHORT_ANSWER_PROMPT = """This is a Short Answer section from a P6 Math exam.

Extract each question with:
1. Question number
2. Full question text (LaTeX for math)
3. Any given values, tables, or conditions
4. Diagram descriptions if present
5. Mark allocation if shown

Format:
---
Q[number]: ([marks] marks)
Text: [complete question with $LaTeX$]
Given: [any provided values/conditions]
Diagram: [description or "None"]
---"""


LONG_ANSWER_PROMPT = """This is a Long Answer/Problem Solving section from a P6 Math exam.

Extract each question completely:
1. Question number and parts (a, b, c if applicable)
2. Full problem statement with all details
3. Any tables, charts, or data provided
4. Diagram descriptions
5. Mark allocation for each part

Format:
---
Q[number]: ([total marks] marks)
Text: [complete problem with $LaTeX$]
Parts:
  (a) [part a question] ([marks])
  (b) [part b question] ([marks])
Given Data: [any tables/values]
Diagram: [detailed description or "None"]
---"""


ANSWER_EXTRACTION_PROMPT = """This is an Answer Key / Marking Scheme page.

Extract ALL answers and worked solutions:

For each question:
1. Question number
2. FINAL ANSWER (look for: Ans:, Answer:, boxed/underlined values, last = result)
3. Complete worked solution/steps if shown
4. Accept/Award criteria if shown

Format:
---
Q[number]:
Answer: [final answer only, e.g., "$45.60", "3:5", "25%"]
Working: [step-by-step solution if provided, or "Not shown"]
Notes: [marking notes/criteria if any]
---

IMPORTANT: Identify the FINAL answer - look for explicit markers, boxed values, or the last calculated result."""


MULTI_PART_EXTRACTION_PROMPT = """Extract ALL questions from this P6 Math exam page.

IMPORTANT: Many questions have MULTIPLE PARTS - (a), (b), (c). You MUST extract ALL parts.

For EACH question:
1. Question NUMBER (e.g., 6, 7, 8)
2. MAIN question text (the problem statement/stem that applies to all parts)
3. SUB-PARTS if any:
   - (a) specific question
   - (b) specific question
   - (c) specific question
4. Marks for each part if shown
5. Diagram description if present

Format EXACTLY like this:
---
Q[number]:
Main: [main question/problem statement - include ALL context, tables, given values]
(a): [part a question text] ([marks] marks)
(b): [part b question text] ([marks] marks)
(c): [part c question text if exists] ([marks] marks)
Diagram: [detailed description or "None"]
---

If a question has NO sub-parts, use:
---
Q[number]:
Main: None
Text: [the complete question]
Diagram: [description or "None"]
---

CRITICAL:
- Do NOT skip any sub-parts (a), (b), (c)
- Include the MAIN question text that provides context for all parts
- Use LaTeX for math: $\\frac{1}{2}$, $x^2$, etc.
- Extract EVERY question visible on this page"""


def create_client(api_key: Optional[str] = None) -> GeminiClient:
    """Factory function to create a GeminiClient."""
    return GeminiClient(api_key=api_key)


if __name__ == "__main__":
    # Quick test
    print("Testing Gemini connection...")
    try:
        client = GeminiClient()
        if client.test_connection():
            print("✓ Gemini API connection successful!")
            print(f"  Model: {client.model_name}")
        else:
            print("✗ Connection test failed")
    except ValueError as e:
        print(f"✗ {e}")
