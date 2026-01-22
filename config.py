"""
Configuration constants for P6 Math Question Extraction Pipeline.
"""

from pathlib import Path

# Directory paths
PROJECT_ROOT = Path(__file__).parent
PDF_DIR = PROJECT_ROOT / "pdfs"
OUTPUT_DIR = PROJECT_ROOT / "output"
IMAGES_DIR = OUTPUT_DIR / "images"
DATABASE_PATH = OUTPUT_DIR / "p6_questions.db"

# Ensure output directories exist
OUTPUT_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)

# Ollama configuration
OLLAMA_BASE_URL = "http://localhost:11434"
VISION_MODEL = "minicpm-v:8b-2.6-fp16"
TEXT_MODEL = "llama3.1:8b"

# Section code to full name mapping for UI display
SECTION_FULL_NAMES = {
    "P1A": "Paper 1 Booklet A",
    "P1B": "Paper 1 Booklet B",
    "P2": "Paper 2",
}

# Paper structure definitions
PAPER_SECTIONS = {
    "P1A": {
        "name": "Paper 1 Booklet A",
        "question_ranges": [
            {"start": 1, "end": 10, "marks": 1, "type": "mcq"},
            {"start": 11, "end": 18, "marks": 2, "type": "mcq"},
        ],
        "total_questions": 18,
    },
    "P1B": {
        "name": "Paper 1 Booklet B",
        "question_ranges": [
            {"start": 1, "end": 5, "marks": 2, "type": "short_answer"},
            {"start": 6, "end": 15, "marks": None, "type": "open_ended"},  # 3-5 marks
        ],
        "total_questions": 15,
    },
    "P2": {
        "name": "Paper 2",
        "question_ranges": [
            {"start": 1, "end": 5, "marks": 2, "type": "short_answer"},
            {"start": 6, "end": 17, "marks": None, "type": "long_answer"},  # 3-5 marks
        ],
        "total_questions": 17,
    },
}

# Section detection anchors (PaddleOCR will search for these)
SECTION_ANCHORS = {
    "P1A": [
        "Booklet A",
        "Paper 1",
        "Questions 1 to 10 carry 1 mark",
        "Questions 11 to 18 carry 2 marks",
        "Multiple Choice",
    ],
    "P1B": [
        "Booklet B",
        "Paper 1",
        "Short Answer",
        "Show your working",
    ],
    "P2": [
        "Paper 2",
        "Show your working clearly",
        "Write your answers",
    ],
    "ANSWER_KEY": [
        "Answer Key",
        "Marking Scheme",
        "Answers",
        "Answer Sheet",
    ],
}

# Mark assignment rules for variable-mark questions
MARK_KEYWORDS = {
    1: ["1 mark", "(1)", "[1]", "1m"],
    2: ["2 marks", "(2)", "[2]", "2m"],
    3: ["3 marks", "(3)", "[3]", "3m"],
    4: ["4 marks", "(4)", "[4]", "4m"],
    5: ["5 marks", "(5)", "[5]", "5m"],
}

# Answer extraction markers
ANSWER_MARKERS = {
    "explicit": ["Ans:", "Answer:", "Ans =", "Answer =", "Total:", "Total ="],
    "symbols": ["∴", "therefore", "Thus,", "Hence,"],
    "visual": ["double underline", "boxed", "circled"],
}

# Answer type validation patterns
ANSWER_TYPE_PATTERNS = {
    "money": r"\$[\d,]+\.?\d*",
    "ratio": r"\d+\s*:\s*\d+",
    "percentage": r"\d+\.?\d*\s*%",
    "fraction": r"\d+/\d+",
    "time": r"\d+\s*(h|hr|hour|min|minute|s|sec)",
    "decimal": r"\d+\.\d+",
    "integer": r"^\d+$",
}

# OpenCV segmentation parameters
SEGMENTATION = {
    "canny_low": 50,
    "canny_high": 150,
    "morph_kernel_width": 100,
    "morph_kernel_height": 1,
    "min_line_length": 200,
    "line_gap_threshold": 20,
    "min_question_height": 50,
    "max_question_height": 800,
}

# PDF processing settings
PDF_DPI = 200
PDF_IMAGE_FORMAT = "png"

# Vision model prompts
QUESTION_EXTRACTION_PROMPT = """Analyze this math question image and extract:

1. **Question Text**: Transcribe the full question in LaTeX format for any math expressions.
2. **MCQ Options**: If this is a multiple choice question, list options A, B, C, D.
3. **Diagram Description**: If there's a diagram, describe it in detail for searchability.

Format your response as:
<text>Full question text with LaTeX math</text>
<options>{"A": "option A text", "B": "option B text", ...}</options>
<diagram>Detailed diagram description or "None"</diagram>
"""

ANSWER_EXTRACTION_PROMPT = """Analyze this answer/solution image and extract:

1. Transcribe the COMPLETE solution with all working steps
2. Identify the FINAL answer using these markers:
   - Look for "Ans:", "Answer:", or "Total:"
   - Find double-underlined or boxed values
   - Locate the last equals sign result
3. If the answer is a diagram, describe it in detail

Format your response as:
<working>Step-by-step solution with LaTeX math</working>
<answer>Final value only (e.g., $45.60, 3:5, 25%)</answer>
<diagram_answer>Description if answer is a diagram, otherwise "None"</diagram_answer>
"""

# Streamlit UI settings
UI_PAGE_TITLE = "P6 Math Question Bank"
UI_PAGE_ICON = "📐"
UI_LAYOUT = "wide"
