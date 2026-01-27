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
- [x] **Manual Editing**: Password-protected UI editing (v0.6)
- [x] **P1B Multi-Part Fix**: Fixed P1B part (b) answer extraction (v0.6)
- [x] **Firebase Migration**: Cloud database + storage for persistent edits (v0.7)
- [x] **Topic Tagging Taxonomy**: 18 topics + 26 heuristics defined, aligned to MOE syllabus (v0.8)
- [x] **Topic Tagging Pipeline**: Gemini-powered auto-tagging with fuzzy matching (v0.8)
- [x] **Topic Tagging UI**: Multi-select filters, colored tag pills, pagination (v0.8)
- [ ] **Topic Tagging QA**: Review heuristic tags on P2 questions (in progress)
- [ ] **Heuristics Glossary Page**: Frontend page displaying glossary (pending)
- [ ] **Historical Data**: Extract 2023 and 2024 papers (Phase 3)

---

## Current Status

### 2025 Papers: Complete (624 questions)
- **13 schools** extracted and stored in Firebase
- **Manual QA in progress** - reviewers checking answers via UI
- **Edit mode available** - corrections saved to Firebase

### Phase 2: Topic Tagging (In Progress — v0.8)

**Taxonomy** (aligned to MOE P1-P6 syllabus):
- **18 topics**: Algebra, Area & Perimeter, Data Analysis (Average), Data Analysis (Graphs & Tables), Decimals, Fractions, Geometry, Measurement, Money, Number Properties, Patterns & Sequences, Percentage, Rate, Ratio, Speed, Time, Volume, Whole Numbers
- **26 heuristics**: All Items Changed, Before-After, Boomerang & Rugby, Branching, Constant Difference, Constant Total, Equal Portions, Excess & Shortage, Folded Shapes, Gap & Overlap, Guess & Check, Make a List / Table, Model Drawing, One Item Unchanged, Pattern Recognition, Proportionality, Quantity x Value, Remainder Concept, Repeated Items, Simultaneous Concept, Spotting Hidden Shapes, Supposition, Unitary Method, Using Parallel Lines, Visual Regrouping (Cut & Paste), Working Backwards
- Full glossary with examples: `HEURISTICS_GLOSSARY.md`

**Pipeline**: `tag_topics.py` — Gemini Vision auto-tags each question with topics (1-2) and heuristics (0-3). Fuzzy matching corrects near-misses. Confidence < 0.7 flagged for review.

**Current progress**:
- 30 calibration questions tagged and manually reviewed
- ~165 P2 questions tagged (heuristic review in progress)
- Remaining ~430 questions to be tagged after QA pass

**Two-pass workflow**:
1. `python tag_topics.py --limit 30` — calibrate on small batch
2. Review tags in UI, correct errors
3. `python tag_topics.py --force` — tag all questions

**UI**: Multi-select topic/heuristic filters, colored tag pills (blue = topic, orange = heuristic), pagination (20/page), "Needs Review" toggle.

### Future Phase: 2023/2024 Extraction
After topic tagging is stable:
- Extract 2023 prelim papers
- Extract 2024 prelim papers
- Apply same pipeline + topic tagging

---

## Quality Assurance Workflow

After extracting any paper:

```bash
# 1. Validate extraction
python3 validate_extraction.py --school "School Name"

# 2. Fix issues found
python3 fix_questions.py --school "School Name" --summary
python3 fix_questions.py --school "School Name" --renumber P2_0 P2_8

# 3. Use UI edit mode for manual corrections
# URL: [Streamlit Cloud URL]
# Password: p6math2026
```

**Common Issues:**
- Missing questions (gaps in Q# sequence)
- Invalid Q0 (wrong question number)
- Duplicate multi-part answers (a=b)
- Suspicious answers ("BLANK PAGE", "sorry", etc.)

---

### Recent: Topic Tagging (v0.8) - January 2025

#### Taxonomy Design
- **18 topics** aligned to MOE P1-P6 syllabus (sorted alphabetically in config.py)
- **26 heuristics** covering Singapore Math problem-solving strategies
- Full glossary with "What it is", "When to tag", and worked examples in `HEURISTICS_GLOSSARY.md`

#### Auto-Tagging Pipeline (`tag_topics.py`)
- Gemini Vision classifies each question using image + text + answer
- Fuzzy matching corrects near-misses (e.g., "Fraction" -> "Fractions")
- Confidence scoring: < 0.7 flagged for human review
- CLI flags: `--school`, `--section`, `--force`, `--dry-run`, `--limit N`, `--validate`
- Rate limiting (15 RPM) with exponential backoff

#### Database Updates
- New columns: `topics`, `heuristics`, `confidence`, `needs_review`
- Both SQLite (`database.py`) and Firebase (`firebase_db.py`) support topic fields
- `update_topic_tags()` function for saving classifications
- Query filtering by topics/heuristics (OR within, AND across)

#### UI Enhancements
- **Multi-select topic/heuristic filters** in sidebar
- **Colored tag pills**: blue (topics), orange (heuristics)
- **Pagination**: 20 questions per page with Previous/Next navigation
- **Caching**: `@st.cache_data` for Firebase calls (120-300s TTL)
- **Client-side filtering** for topics/heuristics (instant, no Firebase round-trip)
- **"Needs Review" toggle** to find low-confidence tags
- **Tagging stats** in sidebar (Tagged: X/624, Needs Review: Y)
- Removed Marks filter for cleaner UI
- Edit mode supports topic/heuristic editing per question

#### Data Cleanup
- Fixed bogus MCQ options on P1B short-answer questions (14 questions across 3 schools)
- Manual tag corrections on calibration batch (Q5-Q13 reviewed)

---

### Previous Fixes (v0.7) - January 2025

#### Firebase Migration
- **Cloud database**: All questions now stored in Firebase Firestore
- **Cloud storage**: All images stored in Firebase Storage with public URLs
- **Persistent edits**: Changes made in UI persist across redeployments
- **Upload features**: Solution images and answer diagrams can be uploaded

#### Enhanced UI Editing
- Upload solution images (stored in Firebase Storage)
- Upload answer diagram images
- Edit marks, question number, paper section
- All changes sync to Firebase immediately

---

### Previous Fixes (v0.6) - January 2025

#### Manual Editing Feature
- **Password-protected edit mode** in Streamlit UI
- Default password: `p6math2026`
- Editable fields: Answer, Worked solution, Question text, Main context
- Changes persist to Firebase

#### P1B Multi-Part Answer Extraction Fix
- **Problem**: P1B questions like Q21(a), Q21(b) only extracted part (a) answer
- **Root cause**: `EXTRACT_ANSWERS_PROMPT` had no P1B multi-part examples
- **Solution**:
  - Added P1B examples: `"P1B_21a": "11/12", "P1B_21b": "30"`
  - Updated fallback parser to handle part letters
  - Now extracts each part as separate key

#### New Database Function
- `update_question_text()` - update question text and main_context fields

#### GitHub Repository
- Code now hosted at: https://github.com/wongbok123/p6-math-question-bank.git

---

### Previous Fixes (v0.5) - January 2025

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
# TOPIC TAGGING (Phase 2)
#=============================================================================

# Tag 30 calibration questions (dry run first)
python3 tag_topics.py --dry-run --limit 30
python3 tag_topics.py --limit 30

# Tag all P2 questions
python3 tag_topics.py --section P2

# Re-tag with force (overwrite existing tags)
python3 tag_topics.py --force

# Tag a specific school
python3 tag_topics.py --school "ACS Junior"

# Validate all stored tags against taxonomy
python3 tag_topics.py --validate

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
    question_diagram TEXT,            -- For question diagram images
    topic_tags TEXT,                  -- JSON array (legacy)
    topics TEXT,                      -- JSON array of topic tags (e.g., ["Ratio", "Money"])
    heuristics TEXT,                  -- JSON array of heuristic tags (e.g., ["Unitary Method"])
    confidence REAL,                  -- AI classification confidence (0.0-1.0)
    needs_review INTEGER DEFAULT 0,  -- 1 if confidence < 0.7
    created_at TIMESTAMP,
    UNIQUE(school, year, paper_section, question_num, COALESCE(part_letter, ''))
);
```

---

## File Structure

```
P6 Bank/
├── gemini_pipeline.py    # Extract questions from PDF pages
├── verify_and_solve.py   # Hybrid: verify answer key + solve if wrong
├── solve_questions.py    # Direct AI solver for questions
├── tag_topics.py         # Gemini-powered topic & heuristic tagging
├── parse_answers.py      # Legacy: simple Q# matching (kept for reference)
├── segmenter.py          # OpenCV question region detection
├── database.py           # SQLite operations (local development)
├── firebase_db.py        # Firebase Firestore + Storage operations
├── config.py             # Paths, settings, taxonomy constants, classification prompt
├── requirements.txt      # Python dependencies
├── .env                  # GEMINI_API_KEY (not committed)
├── firebase-key.json     # Firebase credentials (not committed)
├── HEURISTICS_GLOSSARY.md # Heuristics reference with examples
├── scripts/              # One-time migration/fix scripts
│   ├── fix_p1a_mcq.py        # Fix P1A MCQ answers
│   ├── migrate_to_firebase.py # SQLite to Firebase migration
│   └── update_image_paths.py  # Update image paths to URLs
├── utils/
│   └── gemini_client.py  # Gemini API client + prompts
├── ui/
│   └── app.py            # Streamlit viewer with edit mode + topic filters
├── pdfs/                 # Input PDFs (not committed)
├── output/               # Local data (images backed up to Firebase)
│   ├── p6_questions.db   # SQLite database (local backup)
│   └── images/           # Extracted page images
└── CLAUDE.md             # This file
```

**Storage:**
- **Questions**: Firebase Firestore (cloud)
- **Images**: Firebase Storage (cloud URLs)
- **Local backup**: SQLite + local images (optional)

---

## For Reviewers: How to Check Answers

### Quick Start
1. Open the app: **[Your Streamlit URL]**
2. Use the **filters** on the left to select:
   - **School** (e.g., Red Swastika)
   - **Paper Section** (e.g., Paper 1 Booklet B)
3. Each question shows:
   - Question image (left)
   - Extracted text (right)
   - **Green box with answer** below

### What to Check
For each question, verify:
1. Does the **answer match** what you see in the question image?
2. For multi-part questions (a), (b), (c): Does each part have the **correct** answer?

### If You Find an Error
Report the following:
- School name
- Paper section (P1A, P1B, or P2)
- Question number
- What the answer **should be**

Example: "Red Swastika P1B Q21(b) should be 30, not 11/12"

---

## Deployment (Streamlit Cloud)

### Database: Firebase
The app now uses **Firebase Firestore** for persistent storage:
- Questions stored in Firestore (cloud database)
- Solution images stored in Firebase Storage
- Edits persist across redeployments

### Setup Steps
1. Push code to GitHub (already done)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Click "New app"
4. Select repo: `wongbok123/p6-math-question-bank`
5. Branch: `main`
6. Main file path: `ui/app.py`
7. **Add Secrets** (Settings → Secrets):
   - Copy contents from `firebase-key.json` into secrets as `[firebase]` section
   - See `.streamlit/secrets.toml.example` for format
8. Click "Deploy"

### Firebase Secrets Format (for Streamlit Cloud)
```toml
[firebase]
type = "service_account"
project_id = "p6-math-question-bank"
private_key_id = "your-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "firebase-adminsdk-xxxxx@p6-math-question-bank.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
```

### What Users Can Do
- Browse all questions by school/section/marks
- View question images and extracted text
- See answers and worked solutions
- **Edit answers** - changes persist in Firebase!
- **Upload solution images** - stored in Firebase Storage

### Edit Mode on Cloud
- Password: `p6math2026`
- Edits now **persist** (stored in Firebase)

### Updating Questions
1. Run extraction locally with your API key
2. Run `python migrate_to_firebase.py` to sync to Firebase
3. Push code to GitHub
4. Streamlit Cloud auto-redeploys

### Local Development
- Uses `firebase-key.json` for authentication
- Set `USE_FIREBASE=false` env var to use SQLite instead

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
- [x] Add question filtering by topic (v0.8)
- [ ] Add heuristics glossary page
- [ ] Add export to PDF/Word functionality
- [ ] Add batch processing UI
- [ ] Add answer verification dashboard
- [x] Save answer key page images for worked solution reference (v0.5)
- [x] Manual editing with password protection (v0.6)

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
