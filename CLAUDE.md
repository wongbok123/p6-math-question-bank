# P6 Math Question Extraction Pipeline

## Project Roadmap

### Phase Checklist

- [x] **Logic Phase**: Rule-based mark extraction by position
- [ ] **Vision Phase**: Handle visual MCQ options (diagram choices)
- [x] **Matching Phase**: Link question ID to answer sheet value
- [x] **Extraction Strategy**: "Final Value Priority" rule (Ans:, Total:, final =)
- [ ] **Diagram-to-Text**: Generate searchable metadata for answer diagrams
- [x] **Step-by-Step Archiving**: Store working steps in `worked_solution` field
- [x] **Prototype UI**: Streamlit viewer for verification
- [x] **Hybrid Verify-Solve**: AI verifies answer key matches, solves if wrong (v0.4)
- [x] **Multi-Part Splitting**: Q6(a), Q6(b) stored as separate entries (v0.5)

### Recent Fixes (v0.5) - January 2025

#### Multi-Part Question Splitting
- **Problem**: Multi-part questions (Q6 with parts a, b, c) were stored as single entries with combined answers like "(a) 109° (b) 72°"
- **Solution**: Each part is now stored as a **separate database entry**:
  - Q6(a) → `question_num=6, part_letter='a'`
  - Q6(b) → `question_num=6, part_letter='b'`
- **Benefits**:
  - Each part has its own answer field
  - Direct matching with answer key entries like `P2_6A`, `P2_6B`
  - UI displays "Q6(a)", "Q6(b)" separately
  - Shared context stored in `main_context` field

#### Database Schema Updates (v0.5)
- **New columns**: `part_letter` ('a', 'b', 'c', or NULL), `main_context` (shared problem stem)
- **Updated UNIQUE constraint**: Now includes `part_letter` for proper multi-part storage
- **New function**: `get_question_parts()` retrieves all parts of a question

#### Answer Key Images Saved
- Answer key page images now saved to `output/images/answer_keys/`
- Filename format: `School_Year_answer_p##.png` (e.g., `Red_Swastika_2025_answer_p37.png`)
- Useful for referencing original worked solutions

#### Migration Required
After updating code, you must re-extract questions:
```bash
rm output/p6_questions.db
python3 gemini_pipeline.py --pdf "file.pdf" --pages 1-36
python3 verify_and_solve.py --pdf "file.pdf" --answer-pages 37-42
```

---

### Previous Fixes (v0.4) - January 2025

#### New Hybrid Approach: Verify-and-Solve
- **Problem**: Answer key Q# often don't match extracted question Q# (different schools use different numbering)
- **Solution**: `verify_and_solve.py` - hybrid approach that:
  1. Extracts candidate answers from answer key pages
  2. For each question, sends image + candidate answer to Gemini
  3. Asks "Is this answer correct for this question?"
  4. If CORRECT → keeps the answer
  5. If WRONG → Gemini solves the question directly
- **Benefits**: Self-correcting, works across different PDF formats

#### AI-Powered Question Solver
- **New**: `solve_questions.py` - directly solves questions using Gemini vision
- Generates step-by-step working for each question
- Can verify AI answers against existing answers

#### Database Schema Updates
- **New fields**: `pdf_question_num` (original PDF Q#), `pdf_page_num` (source page)
- Preserves original numbering for display while storing normalized Q# internally

#### UI Improvements
- Display format: "Paper 1 Booklet B Q16" (full name + original PDF number)
- PDF page number shown for cross-referencing
- Section filter shows full names

### Previous Fixes (v0.3)

- **MCQ Answer Conversion**: `normalize_mcq_answer()` converts 1→A, 2→B, 3→C, 4→D
- **P1B Question Numbering**: PDF Q16-30 → stored as Q1-15
- **Answer Overwriting Prevention**: `update_answer()` won't overwrite valid answers
- **Section Detection**: Detects "Ans: ___" blank lines as question pages
- **Text Cleanup**: `clean_extracted_text()` fixes OCR artifacts

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. EXTRACT QUESTIONS (gemini_pipeline.py)                          │
│    PDF pages → Gemini Vision → questions table                      │
│                                                                     │
│    Multi-part questions split into separate entries:               │
│    Q6 with (a),(b) → Q6(a) + Q6(b) as separate rows                │
│    Each part stores: latex_text (part), main_context (shared)      │
└─────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 2. VERIFY AND SOLVE (verify_and_solve.py) [RECOMMENDED]            │
│                                                                     │
│    Answer Key Pages → Extract candidate answers (P2_6A, P2_6B)     │
│                                    ↓                                │
│    For each question part:                                          │
│    ┌─────────────────────────────────────────────────────────────┐ │
│    │ Match P2_6A → question_num=6, part_letter='a'               │ │
│    │         ↓                                                   │ │
│    │ Store answer for that specific part                         │ │
│    └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 3. VIEW (streamlit run ui/app.py)                                  │
│    Browse questions, filter by school/section, show answers        │
│    Displays: "Q6(a)", "Q6(b)" with context + part-specific text    │
└─────────────────────────────────────────────────────────────────────┘
```

**Alternative flows:**
- `solve_questions.py` - Solve all questions directly (no answer key needed)
- `parse_answers.py` - Simple Q# matching (legacy, less reliable)

---

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Set Gemini API key (get free key at https://aistudio.google.com/app/apikey)
export GEMINI_API_KEY="your-key"
# Or add to .env file: GEMINI_API_KEY=your-key

#=============================================================================
# RECOMMENDED WORKFLOW: Extract + Verify-and-Solve
#=============================================================================

# Step 1: Extract questions from PDF (skip answer key pages)
python3 gemini_pipeline.py --pdf "2025-P6-Maths-Prelim Exam-School.pdf" --pages 1-32

# Step 2: Verify answers and solve if wrong (RECOMMENDED)
python3 verify_and_solve.py --pdf "2025-P6-Maths-Prelim Exam-School.pdf" --answer-pages 33-38

# Step 3: Launch viewer
streamlit run ui/app.py

#=============================================================================
# ALTERNATIVE: Direct solving (no answer key)
#=============================================================================

# Solve all questions directly using Gemini
python3 solve_questions.py --section P2

# Re-solve with force (overwrite existing answers)
python3 solve_questions.py --section P2 --force

#=============================================================================
# LEGACY: Simple Q# matching (less reliable)
#=============================================================================

# Parse answer key with Q# matching
python3 parse_answers.py --pdf "file.pdf" --pages 45-48

#=============================================================================
# UTILITIES
#=============================================================================

# Clean database and re-extract
rm output/p6_questions.db
python3 gemini_pipeline.py --pdf "file.pdf"
python3 verify_and_solve.py --pdf "file.pdf" --answer-pages <pages>
```

---

## Paper Structure Reference

**Note**: Structure varies by school. Examples:

### St Nicholas 2025 (48 pages)
| Section | Questions | Pages | Notes |
|---------|-----------|-------|-------|
| Paper 1 Booklet A | Q1-15: MCQ | 1-10 | PDF shows Q1-15 |
| Paper 1 Booklet B | Q1-15: Short/Open | 13-23 | PDF shows Q16-30, store as Q1-15 |
| Paper 2 | Q1-17: Long answer | 26-44 | Multi-part questions |
| Answer Key | | 45-48 | |

### Tao Nan 2025 (38 pages)
| Section | Questions | Pages | Notes |
|---------|-----------|-------|-------|
| Paper 1 Booklet A | Q1-15: MCQ | 1-9 | |
| Paper 1 Booklet B | Q1-15: Short/Open | 10-18 | |
| Paper 2 | Q1-17: Long answer | 19-32 | |
| Answer Key | | 33-38 | |

---

## Database Schema

```sql
CREATE TABLE questions (
    id INTEGER PRIMARY KEY,
    school TEXT NOT NULL,
    year INTEGER NOT NULL,
    paper_section TEXT NOT NULL,      -- P1A, P1B, P2
    question_num INTEGER NOT NULL,    -- Normalized Q# (1-15 for P1B)
    part_letter TEXT DEFAULT '',      -- 'a', 'b', 'c', or '' for non-multi-part
    pdf_question_num INTEGER,         -- Original PDF Q# (16-30 for P1B)
    pdf_page_num INTEGER,             -- Source PDF page number
    marks INTEGER NOT NULL,
    latex_text TEXT NOT NULL,         -- Part-specific question text
    main_context TEXT,                -- Shared problem context for multi-part questions
    diagram_description TEXT,         -- AI description of diagrams
    image_path TEXT NOT NULL,         -- Path to page image
    options TEXT,                     -- JSON for MCQ: {"A":"...", "B":"..."}
    answer TEXT,                      -- Final answer for this part
    worked_solution TEXT,             -- Step-by-step working
    answer_diagram_description TEXT,  -- For diagram-based answers
    topic_tags TEXT,                  -- JSON array
    created_at TIMESTAMP,
    UNIQUE(school, year, paper_section, question_num, COALESCE(part_letter, ''))
);
```

---

## File Structure

```
P6 Bank/
├── gemini_pipeline.py    # Extract questions from PDF pages
├── verify_and_solve.py   # Hybrid: verify answer key + solve if wrong [NEW]
├── solve_questions.py    # Direct AI solver for questions [NEW]
├── parse_answers.py      # Legacy: simple Q# matching
├── database.py           # SQLite operations
├── config.py             # Paths and settings
├── .env                  # GEMINI_API_KEY (not committed)
├── utils/
│   └── gemini_client.py  # Gemini API client + prompts
├── ui/
│   └── app.py            # Streamlit viewer
├── pdfs/                 # Input PDFs
├── output/
│   ├── p6_questions.db   # SQLite database
│   └── images/           # Extracted page images
│       └── answer_keys/  # Answer key page images (worked solutions)
└── CLAUDE.md             # This file
```

---

## How Verify-and-Solve Works

The hybrid approach solves the answer key matching problem:

### The Problem
- Answer keys use various numbering (Q1-30 combined, or Q1-15 per section)
- Different schools have different structures
- Simple Q# matching often links wrong answers to wrong questions

### The Solution
```
1. Extract candidate answers from answer key (by Q#)
2. For each question in database:
   a. Find candidate answer (best Q# match)
   b. Send question IMAGE + candidate to Gemini
   c. Ask: "Is this the correct answer for this question?"
   d. If YES → store the verified answer
   e. If NO → Gemini solves it directly
3. Store answer + working steps
```

### Why It Works
- **Visual verification**: Gemini sees the actual question image
- **Self-correcting**: Wrong matches are detected and fixed
- **Efficient**: Only solves when verification fails
- **Robust**: Works across different PDF formats

---

## Known Issues / Future Work

### Extraction Quality
- **Multi-page questions**: Some questions span 2 pages
- **Diagram descriptions**: Could be more detailed
- **LaTeX formatting**: Not always consistent

### Answer Quality
- ~~**Multi-part answers**: Shows "(a) 135°" instead of just "135°"~~ **FIXED in v0.5**
- **Verbose explanations**: Some AI answers include extra text

### UI/UX
- [ ] Add question filtering by topic
- [ ] Add export to PDF/Word functionality
- [ ] Add batch processing UI
- [ ] Add answer verification dashboard
- [x] Save answer key page images for worked solution reference (v0.5)

---

## Tested Schools

| School | Year | P1A | P1B | P2 | Total | Status |
|--------|------|-----|-----|----|----|--------|
| St Nicholas | 2025 | 15 | 15 | 17 | 47 | ✓ Complete |
| Tao Nan | 2025 | 12 | 15 | 15 | 42 | ✓ Complete |
| Red Swastika | 2025 | 15 | 15 | 17 | 47 | ✓ Complete |
| **Total** | | **42** | **45** | **49** | **136** | |

### PDF Structure by School

| School | Pages | Questions | Answer Key |
|--------|-------|-----------|------------|
| St Nicholas | 48 | 1-44 | 45-48 |
| Tao Nan | 38 | 1-32 | 33-38 |
| Red Swastika | 42 | 1-36 | 37-42 |
