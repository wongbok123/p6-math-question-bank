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
# NOTE: This applies to Singapore P6 Preliminary Examination papers only.
# Total marks: P1A (20) + P1B (25) + P2 (55) = 100 marks.
# If extracting P1-P5 papers in the future, add a 'level' column to the DB
# and define separate structures per level — P1-P5 layouts differ significantly.
PAPER_SECTIONS = {
    "P1A": {
        "name": "Paper 1 Booklet A",
        "total_marks": 20,
        "total_questions": 15,
        # Mark allocation varies by school. Common split:
        #   10 × 1 mark + 5 × 2 marks = 20 marks (most schools)
        # Some schools may use a different split — always verify from the paper.
        "question_ranges": [
            {"start": 1, "end": 15, "marks": None, "type": "mcq"},  # marks vary by school
        ],
    },
    "P1B": {
        "name": "Paper 1 Booklet B",
        "total_marks": 25,
        "total_questions": 15,
        # PDF shows Q16-Q30; stored as Q1-Q15 (normalized: question_num = pdf_num - 15)
        "pdf_start_offset": 15,
        "question_ranges": [
            {"start": 1, "end": 5, "marks": 1, "type": "short_answer"},   # PDF Q16-20
            {"start": 6, "end": 15, "marks": 2, "type": "short_answer"},  # PDF Q21-30
        ],
    },
    "P2": {
        "name": "Paper 2",
        "total_marks": 55,
        "total_questions": 17,
        "question_ranges": [
            {"start": 1, "end": 5, "marks": 2, "type": "short_answer"},   # 10 marks
            {"start": 6, "end": 17, "marks": None, "type": "long_answer"},  # 45 marks total, 3-5 marks each
        ],
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

# ============================================================================
# TOPIC TAGGING TAXONOMY (aligned to MOE P1-P6 syllabus)
# ============================================================================

# Topics (18) — mapped to syllabus sub-strands, sorted alphabetically
TOPICS = [
    "Algebra",
    "Area & Perimeter",
    "Data Analysis (Average)",
    "Data Analysis (Graphs & Tables)",
    "Decimals",
    "Fractions",
    "Geometry",
    "Measurement",
    "Money",
    "Number Properties",
    "Patterns & Sequences",
    "Percentage",
    "Rate",
    "Ratio",
    "Speed",
    "Time",
    "Volume",
    "Whole Numbers",
]

# Heuristics (15) — Singapore Math problem-solving strategies, sorted alphabetically
# Consolidated from 26 (v0.8) to 15 (v0.9) by merging related sub-techniques.
HEURISTICS = [
    "Before-After",
    "Boomerang & Rugby",
    "Branching",
    "Constant Quantity",
    "Equal Portions",
    "Model Drawing",
    "Pattern Recognition",
    "Quantity × Value",
    "Repeated Items",
    "Simultaneous Concept",
    "Spatial Reasoning",
    "Supposition",
    "Unitary Method",
    "Using Parallel Lines",
    "Working Backwards",
]

# Classification prompt for Gemini — tags a question with topics and heuristics
TOPIC_CLASSIFICATION_PROMPT = """You are a Singapore Primary 6 Mathematics curriculum expert.

Classify the following math question by assigning tags from EXACTLY the lists below.
You will be given the question image, extracted text, and the answer.

=== VALID TOPICS (pick 1-2) ===
- "Whole Numbers": place value, four operations, factors & multiples, order of operations
- "Fractions": fraction operations, mixed numbers, equivalent fractions, fraction of a set
- "Decimals": decimal operations, conversion to/from fractions
- "Percentage": finding %, discount, GST, % increase/decrease, % of a quantity
- "Ratio": equivalent ratios, dividing in a given ratio, fraction-ratio relationship
- "Rate": quantity per unit (cost per item, litres per min, etc.)
- "Speed": speed-distance-time problems
- "Algebra": expressions, simplification, substitution, solving linear equations
- "Money": dollars & cents, buying/selling, change, bills
- "Measurement": length, mass, capacity, unit conversion (NOT time — use "Time" instead)
- "Time": finding start time, end time, or duration given the other two; reading clocks, 24-hour time, time intervals
- "Geometry": angles, shape properties, symmetry, nets, quadrilateral properties, circle properties
- "Area & Perimeter": rectangles, triangles, circles, composite figures — area or perimeter calculation
- "Volume": cubes, cuboids, liquid volume, water tanks
- "Data Analysis (Graphs & Tables)": bar graphs, picture graphs, line graphs, pie charts, reading tables
- "Data Analysis (Average)": average, total from average, finding missing value from average
- "Patterns & Sequences": number patterns, shape patterns, nth term
- "Number Properties": factors, multiples, HCF, LCM, primes, divisibility rules

=== VALID HEURISTICS (pick 0-3) ===
- "Model Drawing": bar model / tape diagram approach
- "Before-After": comparing quantities before and after a change — includes one-item-unchanged (one quantity stays constant, make its units the same in before/after ratios) and all-items-changed (all quantities change, use a working table to track before/after values)
- "Working Backwards": starting from end result to find the beginning
- "Unitary Method": using units/parts to represent unknowns (e.g., 3 units = 120) — also covers direct/inverse proportionality (scaling up/down, more workers = less time)
- "Pattern Recognition": finding number/shape patterns
- "Branching": sequential multi-step processing where each step depends on the previous result — primarily the remainder concept in P6 (e.g., "spent 1/3, then 1/4 of the remainder"). Also covers tree diagrams and systematic listing. Only tag when there are MULTIPLE sequential steps, NOT for a single fraction/spending operation
- "Constant Quantity": an invariant quantity persists through a change — either a constant difference (e.g., age gap never changes) or a constant total (e.g., transfer problems where the sum stays the same)
- "Equal Portions": fraction/percentage/decimal of A = fraction/percentage/decimal of B (equating portions of different wholes)
- "Supposition": "Suppose all are X, then adjust..." approach — also covers guess-and-check (systematic trial) and excess-and-shortage (comparing two distribution scenarios)
- "Simultaneous Concept": two unknowns, two conditions
- "Repeated Items": a common item appears in two different ratios — make its units consistent across both before combining (e.g., A:B = 2:3 and B:C = 4:5, make B the same)
- "Quantity × Value": items with different unit values (price, legs, wheels, etc.) organised in a quantity × unit value = total value table. Tag when ONE total is given and the table computes the other. If BOTH totals are given and the question asks for the breakdown, that is "Supposition" (which may use a QxV table as setup)
- "Boomerang & Rugby": composite area/perimeter using boomerang (quadrant removed from square) or half-rugby (triangle removed from quadrant)
- "Spatial Reasoning": perceiving or manipulating shapes — includes folded shapes (paper folding, preserved lengths/angles), gap & overlap (total = A + B − overlap), spotting hidden shapes (embedded triangles/rectangles), and visual regrouping / cut & paste (rearranging parts to simplify area/perimeter)
- "Using Parallel Lines": using properties of parallel lines (alternate angles, corresponding angles) to bridge disjointed parts of a figure

=== RULES ===
1. You MUST pick at least 1 topic. Pick at most 2 topics.
2. Tag ONLY the primary mathematical topic of the question. Do NOT add "Whole Numbers" just because the question involves numbers or arithmetic — only tag it when whole number concepts (place value, factors, multiples, order of operations) are the core focus.
3. Tag "Money" when the question involves dollar amounts, buying/selling, pricing, discount, or change — even if another topic (e.g., Percentage, Ratio) is also tagged.
4. A ratio question is "Ratio", not "Ratio" + "Whole Numbers". A percentage question is "Percentage", not "Percentage" + "Whole Numbers".
5. Pick 0-3 heuristics. Only tag a heuristic if it is clearly the intended solving strategy. P1A MCQ and simple P1B questions often have 0 heuristics.
6. For P6 word problems, prefer "Unitary Method" or "Model Drawing" over "Algebra" unless the question explicitly uses variables (x, y) or asks for an algebraic expression.
7. Area & Perimeter questions involving circles should be tagged BOTH "Area & Perimeter" AND "Geometry".
8. If a specific heuristic is used to execute a logic (e.g., Model Drawing for a Constant Total problem), tag BOTH.
9. Tags must match the valid lists EXACTLY (spelling, capitalisation, punctuation).

=== FEW-SHOT EXAMPLES ===
{few_shot_examples}

=== QUESTION TO CLASSIFY ===
Question text: {question_text}
Context: {main_context}
Answer: {answer}
Section: {section}

Look at the attached question image, then return ONLY valid JSON (no markdown, no explanation):
{{"topics": [...], "heuristics": [...], "confidence": 0.0-1.0}}
"""

# Streamlit UI settings
UI_PAGE_TITLE = "P6 Math Question Bank"
UI_PAGE_ICON = "📐"
UI_LAYOUT = "wide"
