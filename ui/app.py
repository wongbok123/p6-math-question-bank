"""
Streamlit UI for P6 Math Question Bank viewer.
"""

import re
import streamlit as st
from pathlib import Path
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    UI_PAGE_TITLE, UI_PAGE_ICON, UI_LAYOUT, PAPER_SECTIONS, SECTION_FULL_NAMES,
    TOPICS, HEURISTICS, SCREENSHOT_TRANSCRIPTION_PROMPT, TOPIC_CLASSIFICATION_PROMPT,
)

# Display label overrides for topics (canonical name → UI label)
TOPIC_DISPLAY = {
    "Speed": "Speed (not in PSLE from 2026)",
}

def _topic_label(name: str) -> str:
    """Return display label for a topic name."""
    return TOPIC_DISPLAY.get(name, name)

# Use Firebase if available, fallback to SQLite
USE_FIREBASE = os.environ.get('USE_FIREBASE', 'true').lower() == 'true'

try:
    if USE_FIREBASE:
        from firebase_db import (
            get_questions,
            get_all_schools,
            get_all_years,
            get_statistics,
            init_db,
            update_answer,
            update_question_text,
            update_question_metadata,
            update_topic_tags,
            upload_image_bytes,
            get_image_url,
            delete_question,
            insert_question,
        )
        USING_FIREBASE = True
    else:
        raise ImportError("Firebase disabled")
except Exception as e:
    # Fallback to SQLite
    from database import (
        get_questions,
        get_all_schools,
        get_all_years,
        get_statistics,
        init_db,
        update_answer,
        update_question_text,
        update_question_metadata,
    )
    USING_FIREBASE = False
    upload_image_bytes = None
    get_image_url = None
    update_topic_tags = None
    delete_question = None
    insert_question = None

# ── Gemini API key detection (for screenshot transcription) ───────────
def _get_gemini_api_key() -> str | None:
    """Check env var, .env file, and Streamlit secrets for a Gemini API key."""
    # 1. Environment variable
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    # 2. .env file in project root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                val = line.split("=", 1)[1].strip().strip("'\"")
                if val:
                    return val
    # 3. Streamlit secrets
    try:
        key = st.secrets.get("GEMINI_API_KEY")
        if key:
            return key
    except Exception:
        pass
    return None

GEMINI_API_KEY = _get_gemini_api_key()


def transcribe_screenshot(image_bytes: bytes) -> dict | None:
    """Send a screenshot to Gemini Vision and return extracted fields as a dict."""
    import json
    from PIL import Image
    import io
    from utils.gemini_client import GeminiClient

    try:
        client = GeminiClient(api_key=GEMINI_API_KEY)
        pil_image = Image.open(io.BytesIO(image_bytes))
        result = client.extract_from_image(pil_image, SCREENSHOT_TRANSCRIPTION_PROMPT)
        if not result.success:
            return None
        raw = result.raw_response.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        # Find the JSON object
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(raw[start:end])
    except Exception:
        return None


def classify_question(image_bytes: bytes | None, question_text: str,
                      main_context: str, answer: str, section: str) -> dict | None:
    """Classify a question's topics and heuristics using Gemini Vision."""
    import json
    from utils.gemini_client import GeminiClient

    prompt = TOPIC_CLASSIFICATION_PROMPT.format(
        few_shot_examples="(No examples provided.)",
        question_text=question_text or "",
        main_context=main_context or "N/A",
        answer=answer or "N/A",
        section=section or "",
    )
    try:
        client = GeminiClient(api_key=GEMINI_API_KEY)
        if image_bytes:
            from PIL import Image
            import io
            pil_image = Image.open(io.BytesIO(image_bytes))
            result = client.extract_from_image(pil_image, prompt)
        else:
            # Text-only classification (no image)
            result = client.extract_from_image(
                __import__('PIL.Image', fromlist=['Image']).Image.new('RGB', (1, 1)),
                prompt,
            )
        if not result.success:
            return None
        raw = result.raw_response.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        data = json.loads(raw[start:end])
        # Validate against taxonomy
        data["topics"] = [t for t in (data.get("topics") or []) if t in TOPICS]
        data["heuristics"] = [h for h in (data.get("heuristics") or []) if h in HEURISTICS]
        return data
    except Exception:
        return None


# Directory for uploaded solution images (local fallback)
SOLUTIONS_DIR = Path(__file__).parent.parent / "output" / "images" / "solutions"
SOLUTIONS_DIR.mkdir(parents=True, exist_ok=True)

QUESTIONS_PER_PAGE = 20


# ── Cached data fetchers ──────────────────────────────────────────────
@st.cache_data(ttl=300)
def cached_get_statistics():
    return get_statistics()

@st.cache_data(ttl=300)
def cached_get_schools():
    return get_all_schools()

@st.cache_data(ttl=300)
def cached_get_years():
    return get_all_years()

@st.cache_data(ttl=120)
def cached_get_questions(school=None, year=None, paper_section=None):
    """Fetch questions with base filters only. Topic/heuristic filtering done client-side."""
    params = {}
    if school:
        params["school"] = school
    if year:
        params["year"] = year
    if paper_section:
        params["paper_section"] = paper_section
    return get_questions(**params)


def filter_questions_client_side(questions, topics=None, heuristics=None, needs_review=False):
    """Fast client-side filtering for topic/heuristic selections."""
    result = questions
    if topics:
        result = [q for q in result if any(t in (q.get('topics') or []) for t in topics)]
    if heuristics:
        result = [q for q in result if any(h in (q.get('heuristics') or []) for h in heuristics)]
    if needs_review:
        result = [q for q in result if q.get('needs_review')]
    return result


def main():
    """Main Streamlit application."""
    st.set_page_config(
        page_title=UI_PAGE_TITLE,
        page_icon=UI_PAGE_ICON,
        layout=UI_LAYOUT,
    )

    st.title(f"{UI_PAGE_ICON} {UI_PAGE_TITLE}")

    # Custom CSS: match sidebar filter pills to question tag styling
    st.markdown("""
    <style>
    /* All sidebar multiselect pills: rounded, white text, blue default */
    section[data-testid="stSidebar"] [data-baseweb="tag"] {
        background-color: #3b82f6 !important;
        border-radius: 12px !important;
    }
    section[data-testid="stSidebar"] [data-baseweb="tag"] span,
    section[data-testid="stSidebar"] [data-baseweb="tag"] svg {
        color: white !important;
        fill: white !important;
    }
    /* Heuristics (second sidebar multiselect) - orange */
    section[data-testid="stSidebar"] :nth-child(2 of :has([data-testid="stMultiSelect"])) [data-baseweb="tag"] {
        background-color: #f59e0b !important;
    }
    /* Rename "app" nav label to "Question Bank" */
    [data-testid="stSidebarNav"] li:first-child span {
        font-size: 0;
    }
    [data-testid="stSidebarNav"] li:first-child span::before {
        content: "Question Bank";
        font-size: 14px;
    }
    </style>
    """, unsafe_allow_html=True)

    # Initialize database if needed
    try:
        stats = cached_get_statistics()
    except Exception:
        init_db()
        stats = cached_get_statistics()

    # Sidebar filters
    with st.sidebar:
        st.header("Filters")

        # School filter
        schools = cached_get_schools()
        if schools:
            selected_school = st.selectbox(
                "School",
                ["All"] + schools,
                index=0,
            )
        else:
            selected_school = "All"
            st.info("No schools in database yet")

        # Year filter
        years = cached_get_years()
        if years:
            selected_year = st.selectbox(
                "Year",
                ["All"] + [str(y) for y in years],
                index=0,
            )
        else:
            selected_year = "All"

        # Paper section filter with full names
        section_options = {
            "All": "All",
            "P1A": "Paper 1 Booklet A",
            "P1B": "Paper 1 Booklet B",
            "P2": "Paper 2",
        }
        selected_section_display = st.selectbox(
            "Paper Section",
            list(section_options.values()),
            index=0,
        )
        # Convert display name back to code
        selected_section = next(
            (code for code, name in section_options.items() if name == selected_section_display),
            "All"
        )

        # Show answer toggle (default ON for easy verification)
        show_answers = st.checkbox("Show Answers", value=True)

        st.divider()

        # Topic filters
        st.header("Topic Filters")

        selected_topics = st.multiselect("Topics", options=TOPICS, default=[], format_func=_topic_label)
        selected_heuristics = st.multiselect("Heuristics", options=HEURISTICS, default=[])

        show_needs_review = st.checkbox("Show Only Needs Review", value=False)

        st.divider()

        # Edit mode with password protection
        st.header("Edit Mode")
        EDIT_PASSWORD = "p6math2026"  # Change this to your desired password

        # Initialize session state for edit mode
        if "edit_mode_unlocked" not in st.session_state:
            st.session_state.edit_mode_unlocked = False

        # Initialize session state for screenshot transcription
        if "add_q_transcription" not in st.session_state:
            st.session_state.add_q_transcription = {}
        if "add_q_image_bytes" not in st.session_state:
            st.session_state.add_q_image_bytes = None
        if "add_q_ai_tags" not in st.session_state:
            st.session_state.add_q_ai_tags = {}
        if "add_q_uploader_key" not in st.session_state:
            st.session_state.add_q_uploader_key = 0

        if not st.session_state.edit_mode_unlocked:
            password_input = st.text_input("Enter password to edit", type="password", key="edit_password")
            if st.button("Unlock Edit Mode"):
                if password_input == EDIT_PASSWORD:
                    st.session_state.edit_mode_unlocked = True
                    st.rerun()
                else:
                    st.error("Incorrect password")
            edit_mode = False
        else:
            edit_mode = st.checkbox("Enable Editing", value=False)
            if st.button("Lock Edit Mode"):
                st.session_state.edit_mode_unlocked = False
                st.rerun()

        st.divider()

        # Statistics
        st.header("Statistics")
        st.metric("Total Questions", stats["total_questions"])

        if stats["by_section"]:
            st.subheader("By Section")
            for section, count in stats["by_section"].items():
                st.text(f"{section}: {count}")

        # Tagging progress
        st.subheader("Tagging")
        tagged_count = stats.get("tagged_count", "—")
        review_count = stats.get("review_count", "—")
        st.text(f"Tagged: {tagged_count} / {stats['total_questions']}")
        st.text(f"Needs Review: {review_count}")

    # ── Fetch and filter questions ────────────────────────────────────
    base_school = selected_school if selected_school != "All" else None
    base_year = int(selected_year) if selected_year != "All" else None
    base_section = selected_section if selected_section != "All" else None

    all_questions = cached_get_questions(
        school=base_school,
        year=base_year,
        paper_section=base_section,
    )

    # Client-side filtering for topics/heuristics (instant, no Firebase call)
    questions = filter_questions_client_side(
        all_questions,
        topics=selected_topics or None,
        heuristics=selected_heuristics or None,
        needs_review=show_needs_review,
    )

    if not questions:
        st.info("No questions found. Run the pipeline to extract questions from PDFs.")

        # Show instructions
        with st.expander("Getting Started"):
            st.markdown("""
            ### Setup Instructions

            1. **Install dependencies:**
               ```bash
               pip install -r requirements.txt
               ```

            2. **Get a free Gemini API key:**
               - Go to: https://aistudio.google.com/app/apikey
               - Create a key (free tier)

            3. **Set your API key:**
               ```bash
               export GEMINI_API_KEY="your-key-here"
               ```

            4. **Place PDF files in the `pdfs/` directory**

            5. **Run the extraction pipeline:**
               ```bash
               python gemini_pipeline.py
               ```

            6. **Parse answer keys:**
               ```bash
               python parse_answers.py --pdf "your-file.pdf" --pages 39-48
               ```

            7. **Refresh this page to see extracted questions**
            """)
        return

    # ── Pagination ────────────────────────────────────────────────────
    total_questions = len(questions)
    total_pages = max(1, (total_questions + QUESTIONS_PER_PAGE - 1) // QUESTIONS_PER_PAGE)

    # Initialize page in session state
    if "page" not in st.session_state:
        st.session_state.page = 1
    # Reset to page 1 when filters change
    filter_key = f"{base_school}|{base_year}|{base_section}|{selected_topics}|{selected_heuristics}|{show_needs_review}"
    if st.session_state.get("_last_filter_key") != filter_key:
        st.session_state.page = 1
        st.session_state._last_filter_key = filter_key

    current_page = st.session_state.page

    st.subheader(f"Questions ({total_questions} results)")

    # Top pagination controls
    if total_pages > 1:
        col_prev, col_info, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("← Previous", disabled=current_page <= 1, key="prev_top"):
                st.session_state.page = max(1, current_page - 1)
                st.rerun()
        with col_info:
            st.markdown(f"**Page {current_page} of {total_pages}**")
        with col_next:
            if st.button("Next →", disabled=current_page >= total_pages, key="next_top"):
                st.session_state.page = min(total_pages, current_page + 1)
                st.rerun()

    # Slice questions for current page
    start_idx = (current_page - 1) * QUESTIONS_PER_PAGE
    end_idx = start_idx + QUESTIONS_PER_PAGE
    page_questions = questions[start_idx:end_idx]

    # ── Add New Question (edit mode only) ──────────────────────────────
    if edit_mode and insert_question:
        with st.expander("+ Add New Question"):
            tx = st.session_state.add_q_transcription  # shorthand

            # ── Screenshot transcription (outside form) ──────────────
            if GEMINI_API_KEY:
                uploaded_screenshot = st.file_uploader(
                    "Upload a question screenshot",
                    type=["png", "jpg", "jpeg"],
                    key=f"add_q_screenshot_{st.session_state.add_q_uploader_key}",
                )
                if uploaded_screenshot:
                    # Persist bytes so they survive reruns
                    st.session_state.add_q_image_bytes = uploaded_screenshot.getvalue()

                # Show preview from session state (survives reruns even when uploader resets)
                if st.session_state.add_q_image_bytes:
                    st.image(st.session_state.add_q_image_bytes, caption="Uploaded screenshot", width=400)

                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("Transcribe with AI", disabled=st.session_state.add_q_image_bytes is None):
                        with st.spinner("Transcribing screenshot..."):
                            result = transcribe_screenshot(st.session_state.add_q_image_bytes)
                        if result:
                            st.session_state.add_q_transcription = result
                            st.success("Transcription complete — review the pre-filled fields below.")
                            st.rerun()
                        else:
                            st.error("Transcription failed. Fill in the fields manually.")
                with btn_col2:
                    can_tag = bool(tx.get("question_text") or st.session_state.add_q_image_bytes)
                    if st.button("Tag Topics with AI", disabled=not can_tag):
                        with st.spinner("Classifying topics & heuristics..."):
                            tag_result = classify_question(
                                image_bytes=st.session_state.add_q_image_bytes,
                                question_text=tx.get("question_text") or "",
                                main_context=tx.get("main_context") or "",
                                answer=tx.get("answer") or "",
                                section=tx.get("paper_section") or "",
                            )
                        if tag_result and (tag_result.get("topics") or tag_result.get("heuristics")):
                            st.session_state.add_q_ai_tags = tag_result
                            tags_summary = ", ".join(tag_result.get("topics", []) + tag_result.get("heuristics", []))
                            st.success(f"Tagged: {tags_summary}")
                            st.rerun()
                        else:
                            st.error("Classification failed. Select topics manually.")

                st.divider()

            # ── Form (reads defaults from transcription) ─────────────
            with st.form("add_question_form"):
                if tx:
                    st.info("Fields pre-filled from AI transcription. Review and edit before submitting.")

                st.markdown("**New Question Details**")

                add_col1, add_col2, add_col3 = st.columns(3)
                with add_col1:
                    school_opts = schools if schools else []
                    school_idx = 0
                    if base_school and base_school in school_opts:
                        school_idx = school_opts.index(base_school)
                    add_school = st.selectbox(
                        "School",
                        options=school_opts,
                        index=school_idx,
                        key="add_school",
                    )
                with add_col2:
                    add_year = st.number_input(
                        "Year", min_value=2020, max_value=2030,
                        value=2025, key="add_year",
                    )
                with add_col3:
                    # Default section from transcription, then sidebar filter
                    section_opts = ["P1A", "P1B", "P2"]
                    tx_section = tx.get("paper_section") or base_section
                    section_idx = section_opts.index(tx_section) if tx_section in section_opts else 2
                    add_section = st.selectbox(
                        "Paper Section",
                        options=section_opts,
                        index=section_idx,
                        key="add_section",
                    )

                add_col4, add_col5, add_col6 = st.columns(3)
                with add_col4:
                    add_q_num = st.number_input(
                        "Question Number", min_value=1, max_value=30,
                        value=int(tx["question_num"]) if tx.get("question_num") else 1,
                        key="add_q_num",
                    )
                with add_col5:
                    add_part = st.text_input(
                        "Part Letter (blank, a, b, c)",
                        value=tx.get("part_letter") or "",
                        key="add_part",
                    )
                with add_col6:
                    add_marks = st.number_input(
                        "Marks", min_value=1, max_value=10,
                        value=int(tx["marks"]) if tx.get("marks") else 2,
                        key="add_marks",
                    )

                add_question_text = st.text_area(
                    "Question Text *",
                    value=tx.get("question_text") or "",
                    height=100,
                    key="add_question_text",
                )
                add_main_context = st.text_area(
                    "Main Context (shared stem for multi-part)",
                    value=tx.get("main_context") or "",
                    height=80,
                    key="add_main_context",
                )

                add_answer = st.text_input(
                    "Answer",
                    value=tx.get("answer") or "",
                    key="add_answer",
                )

                # MCQ options (editable JSON) — shown when transcription detected options
                import json as _json
                tx_options = tx.get("options")
                options_default = ""
                if isinstance(tx_options, dict) and tx_options:
                    options_default = _json.dumps(tx_options, indent=2)
                add_options_str = st.text_area(
                    'MCQ Options (JSON, e.g. {"A": "300", "B": "3000", ...})',
                    value=options_default,
                    height=80,
                    key="add_options",
                )

                add_worked = st.text_area(
                    "Worked Solution",
                    height=100,
                    key="add_worked",
                )

                ai_tags = st.session_state.add_q_ai_tags
                add_topics = st.multiselect(
                    "Topics",
                    options=TOPICS,
                    default=[t for t in (ai_tags.get("topics") or []) if t in TOPICS],
                    key="add_topics",
                    format_func=_topic_label,
                )
                add_heuristics = st.multiselect(
                    "Heuristics",
                    options=HEURISTICS,
                    default=[h for h in (ai_tags.get("heuristics") or []) if h in HEURISTICS],
                    key="add_heuristics",
                )

                add_submitted = st.form_submit_button("Add Question")
                if add_submitted:
                    if not add_school:
                        st.error("School is required.")
                    elif not add_question_text.strip():
                        st.error("Question text is required.")
                    else:
                        try:
                            part = add_part.strip().lower() or None
                            # Upload screenshot to Firebase if available
                            img_path = ""
                            img_bytes = st.session_state.add_q_image_bytes
                            if img_bytes and USING_FIREBASE and upload_image_bytes:
                                fname = f"{add_school}_{add_year}_{add_section}_Q{add_q_num}"
                                if part:
                                    fname += f"_{part}"
                                fname = fname.replace(" ", "_") + ".png"
                                try:
                                    img_path = upload_image_bytes(
                                        img_bytes,
                                        f"images/questions/{fname}",
                                        "image/png",
                                    )
                                except Exception:
                                    pass  # non-critical; image_path stays empty

                            # Parse MCQ options from text area
                            parsed_options = None
                            if add_options_str.strip():
                                try:
                                    parsed_options = _json.loads(add_options_str)
                                    if not isinstance(parsed_options, dict):
                                        parsed_options = None
                                except _json.JSONDecodeError:
                                    pass

                            # User enters the paper number (e.g. 16 for P1B Q16).
                            # For P1B, normalize: question_num = paper_num - 15
                            paper_num = int(add_q_num)
                            if add_section == "P1B" and paper_num > 15:
                                internal_num = paper_num - 15
                            else:
                                internal_num = paper_num

                            doc_id = insert_question(
                                school=add_school,
                                year=int(add_year),
                                paper_section=add_section,
                                question_num=internal_num,
                                marks=int(add_marks),
                                latex_text=add_question_text.strip(),
                                image_path=img_path,
                                diagram_description=tx.get("diagram_description"),
                                main_context=add_main_context.strip() or None,
                                answer=add_answer.strip() or None,
                                worked_solution=add_worked.strip() or None,
                                part_letter=part,
                                options=parsed_options,
                                pdf_question_num=paper_num,
                            )
                            if (add_topics or add_heuristics) and update_topic_tags:
                                update_topic_tags(
                                    question_id=doc_id,
                                    topics=add_topics or [],
                                    heuristics=add_heuristics or [],
                                )
                            # Clear transcription and tagging state
                            st.session_state.add_q_transcription = {}
                            st.session_state.add_q_image_bytes = None
                            st.session_state.add_q_ai_tags = {}
                            # Clear form widget keys so fields reset on rerun
                            for k in [
                                "add_question_text", "add_main_context",
                                "add_answer", "add_worked", "add_options",
                                "add_part",
                            ]:
                                st.session_state.pop(k, None)
                            # Increment uploader key to reset file uploader widget
                            st.session_state.add_q_uploader_key += 1
                            st.success(f"Question added! (ID: {doc_id})")
                            cached_get_questions.clear()
                            cached_get_statistics.clear()
                            cached_get_schools.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to add question: {e}")

            # Cancel button (outside form so it works independently)
            if st.button("Cancel", key="add_q_cancel"):
                st.session_state.add_q_transcription = {}
                st.session_state.add_q_image_bytes = None
                st.session_state.add_q_ai_tags = {}
                for k in [
                    "add_question_text", "add_main_context",
                    "add_answer", "add_worked", "add_options",
                    "add_part",
                ]:
                    st.session_state.pop(k, None)
                st.session_state.add_q_uploader_key += 1
                st.rerun()

    # ── Display questions ─────────────────────────────────────────────
    for i, q in enumerate(page_questions):
        with st.container():
            # Header row
            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                # Display full paper name with original PDF question number
                section_name = SECTION_FULL_NAMES.get(q['paper_section'], q['paper_section'])
                # Use pdf_question_num if available, otherwise fall back to question_num
                display_num = q.get('pdf_question_num') or q['question_num']
                # Add part letter if present (e.g., Q6(a), Q6(b))
                if q.get('part_letter'):
                    display_num = f"{display_num}({q['part_letter']})"
                st.markdown(
                    f"**{q['school']} {q['year']} - {section_name} Q{display_num}**"
                )

            with col2:
                st.markdown(f"**{q['marks']} mark{'s' if q['marks'] > 1 else ''}**")

            with col3:
                if q.get("options"):
                    st.markdown("*MCQ*")

            # Question content columns
            col_img, col_text = st.columns([1, 2])

            with col_img:
                # Display question image
                image_path_str = q.get("image_path", "")

                # Check if it's a URL (Firebase Storage)
                if image_path_str.startswith("http"):
                    st.image(image_path_str, use_column_width=True)
                else:
                    # Handle local paths
                    image_path = Path(image_path_str) if image_path_str else None

                    if image_path and image_path.exists():
                        st.image(str(image_path), use_column_width=True)
                    else:
                        # Try relative path from project root
                        if image_path:
                            filename = image_path.name
                            relative_path = Path(__file__).parent.parent / "output" / "images" / filename
                            if relative_path.exists():
                                st.image(str(relative_path), use_column_width=True)
                            else:
                                st.info("Image not available on cloud")

            with col_text:
                # LaTeX text - show main context first if available
                if q.get("main_context"):
                    st.markdown("**Context:**")
                    st.markdown(q["main_context"])
                    st.markdown("**Part:**")
                    st.markdown(q["latex_text"])
                elif q["latex_text"]:
                    st.markdown("**Question:**")
                    st.markdown(q["latex_text"])

                # MCQ options
                if q.get("options"):
                    st.markdown("**Options:**")
                    for letter, text in q["options"].items():
                        st.markdown(f"({letter}) {text}")

                # Diagram description
                if q.get("diagram_description"):
                    with st.expander("Diagram Description"):
                        st.markdown(q["diagram_description"])

            # Answer section - shown directly for easy verification
            if show_answers and q.get("answer"):
                st.success(f"**Answer:** {q['answer']}")

                # Show worked solution if available
                if q.get("worked_solution"):
                    worked = q["worked_solution"]
                    img_match = re.search(r'\[Solution Image: (.+?)\]', worked)
                    img_url_match = re.search(r'\[Solution URL: (.+?)\]', worked)

                    with st.expander("View Worked Solution"):
                        # Show text part (without image references)
                        text_part = re.sub(r'\[Solution (?:Image|URL): .+?\]', '', worked).strip()
                        if text_part:
                            st.markdown(text_part)

                        # Show image from Firebase URL
                        if img_url_match:
                            st.image(img_url_match.group(1), caption="Solution", use_column_width=True)
                        # Or show local image
                        elif img_match:
                            img_filename = img_match.group(1)
                            img_path = SOLUTIONS_DIR / img_filename
                            if img_path.exists():
                                st.image(str(img_path), caption="Solution", use_column_width=True)

                # Show question diagram if available
                if q.get("question_diagram"):
                    diagram_desc = q["question_diagram"]
                    diag_url_match = re.search(r'\[Diagram URL: (.+?)\]', diagram_desc)
                    diag_img_match = re.search(r'\[Diagram Image: (.+?)\]', diagram_desc)

                    with st.expander("View Question Diagram"):
                        if diag_url_match:
                            st.image(diag_url_match.group(1), caption="Question Diagram", use_column_width=True)
                        elif diag_img_match:
                            diag_filename = diag_img_match.group(1)
                            diag_path = SOLUTIONS_DIR / diag_filename
                            if diag_path.exists():
                                st.image(str(diag_path), caption="Question Diagram", use_column_width=True)
                        else:
                            # Plain text description
                            st.markdown(diagram_desc)

            # Topic tag pills
            tag_pills = []
            for t in (q.get('topics') or []):
                tag_pills.append(f'<span style="background:#3b82f6;color:#fff;padding:2px 8px;border-radius:12px;font-size:0.8em;margin-right:4px;">{_topic_label(t)}</span>')
            for h in (q.get('heuristics') or []):
                tag_pills.append(f'<span style="background:#f59e0b;color:#fff;padding:2px 8px;border-radius:12px;font-size:0.8em;margin-right:4px;">{h}</span>')
            if tag_pills:
                st.markdown("".join(tag_pills), unsafe_allow_html=True)

            # Edit section (only shown when edit mode is enabled)
            if edit_mode:
                with st.expander(f"Edit Q{display_num}"):
                    # Metadata editing (marks, question num, paper section)
                    st.markdown("**Question Metadata**")
                    meta_col1, meta_col2, meta_col3 = st.columns(3)

                    with meta_col1:
                        new_marks = st.number_input(
                            "Marks",
                            min_value=1,
                            max_value=10,
                            value=q.get("marks") or 1,
                            key=f"marks_{q['id']}"
                        )

                    with meta_col2:
                        new_q_num = st.number_input(
                            "Question Number",
                            min_value=1,
                            max_value=30,
                            value=q.get("question_num") or 1,
                            key=f"qnum_{q['id']}"
                        )

                    with meta_col3:
                        edit_section_options = ["P1A", "P1B", "P2"]
                        current_section_idx = edit_section_options.index(q['paper_section']) if q['paper_section'] in edit_section_options else 0
                        new_section = st.selectbox(
                            "Paper Section",
                            edit_section_options,
                            index=current_section_idx,
                            key=f"section_{q['id']}"
                        )

                    st.markdown("**Answer & Solution**")

                    # Answer editing
                    new_answer = st.text_input(
                        "Answer",
                        value=q.get("answer") or "",
                        key=f"answer_{q['id']}"
                    )

                    # Working solution editing
                    new_working = st.text_area(
                        "Worked Solution (text)",
                        value=q.get("worked_solution") or "",
                        height=150,
                        key=f"working_{q['id']}"
                    )

                    # Image upload for worked solution
                    st.markdown("**Or upload solution image:**")
                    uploaded_solution = st.file_uploader(
                        "Upload solution image",
                        type=["png", "jpg", "jpeg"],
                        key=f"upload_solution_{q['id']}"
                    )

                    if uploaded_solution:
                        st.image(uploaded_solution, caption="Solution Preview", width=300)

                    # Image upload for question diagram
                    st.markdown("**Or upload question diagram:**")
                    uploaded_diagram = st.file_uploader(
                        "Upload question diagram",
                        type=["png", "jpg", "jpeg"],
                        key=f"upload_diagram_{q['id']}"
                    )

                    if uploaded_diagram:
                        st.image(uploaded_diagram, caption="Diagram Preview", width=300)

                    st.markdown("**Question Text**")

                    # Question text editing
                    new_question_text = st.text_area(
                        "Question Text",
                        value=q.get("latex_text") or "",
                        height=100,
                        key=f"question_{q['id']}"
                    )

                    # Main context editing (for multi-part questions)
                    new_main_context = None
                    if q.get("part_letter"):
                        new_main_context = st.text_area(
                            "Main Context (shared across parts)",
                            value=q.get("main_context") or "",
                            height=100,
                            key=f"context_{q['id']}"
                        )

                    st.markdown("**Topic Tags**")
                    new_topics = st.multiselect(
                        "Topics",
                        options=TOPICS,
                        default=q.get("topics") or [],
                        key=f"topics_{q['id']}",
                        format_func=_topic_label,
                    )
                    new_heuristics = st.multiselect(
                        "Heuristics",
                        options=HEURISTICS,
                        default=q.get("heuristics") or [],
                        key=f"heuristics_{q['id']}"
                    )

                    # Save and Delete buttons
                    col_save, col_delete, col_status = st.columns([1, 1, 1])
                    with col_save:
                        if st.button("Save", key=f"save_{q['id']}"):
                            success = True
                            new_diagram_desc = q.get("question_diagram") or ""

                            # Handle solution image upload
                            if uploaded_solution:
                                img_filename = f"{q['school']}_{q['year']}_{q['paper_section']}_Q{q['question_num']}"
                                if q.get('part_letter'):
                                    img_filename += f"_{q['part_letter']}"
                                img_filename += f"_solution.{uploaded_solution.name.split('.')[-1]}"
                                img_filename = img_filename.replace(" ", "_")

                                img_bytes = uploaded_solution.getvalue()

                                if USING_FIREBASE and upload_image_bytes:
                                    try:
                                        storage_path = f"images/solutions/{img_filename}"
                                        ext = uploaded_solution.name.split('.')[-1].lower()
                                        content_type = f"image/{ext if ext != 'jpg' else 'jpeg'}"
                                        img_url = upload_image_bytes(
                                            img_bytes,
                                            storage_path,
                                            content_type
                                        )
                                        img_ref = f"[Solution URL: {img_url}]"
                                        st.success(f"Solution image uploaded to cloud")
                                    except Exception as e:
                                        st.warning(f"Cloud upload failed: {e}. Saving locally...")
                                        img_path = SOLUTIONS_DIR / img_filename
                                        with open(img_path, "wb") as f:
                                            f.write(img_bytes)
                                        img_ref = f"[Solution Image: {img_filename}]"
                                else:
                                    img_path = SOLUTIONS_DIR / img_filename
                                    with open(img_path, "wb") as f:
                                        f.write(img_bytes)
                                    img_ref = f"[Solution Image: {img_filename}]"

                                if img_ref:
                                    if new_working:
                                        new_working = f"{new_working}\n\n{img_ref}"
                                    else:
                                        new_working = img_ref

                            # Handle diagram image upload
                            if uploaded_diagram:
                                diag_filename = f"{q['school']}_{q['year']}_{q['paper_section']}_Q{q['question_num']}"
                                if q.get('part_letter'):
                                    diag_filename += f"_{q['part_letter']}"
                                diag_filename += f"_diagram.{uploaded_diagram.name.split('.')[-1]}"
                                diag_filename = diag_filename.replace(" ", "_")

                                diag_bytes = uploaded_diagram.getvalue()

                                if USING_FIREBASE and upload_image_bytes:
                                    try:
                                        storage_path = f"images/diagrams/{diag_filename}"
                                        ext = uploaded_diagram.name.split('.')[-1].lower()
                                        content_type = f"image/{ext if ext != 'jpg' else 'jpeg'}"
                                        diag_url = upload_image_bytes(
                                            diag_bytes,
                                            storage_path,
                                            content_type
                                        )
                                        new_diagram_desc = f"[Diagram URL: {diag_url}]"
                                        st.success(f"Diagram image uploaded to cloud")
                                    except Exception as e:
                                        st.warning(f"Diagram upload failed: {e}. Saving locally...")
                                        diag_path = SOLUTIONS_DIR / diag_filename
                                        with open(diag_path, "wb") as f:
                                            f.write(diag_bytes)
                                        new_diagram_desc = f"[Diagram Image: {diag_filename}]"
                                else:
                                    diag_path = SOLUTIONS_DIR / diag_filename
                                    with open(diag_path, "wb") as f:
                                        f.write(diag_bytes)
                                    new_diagram_desc = f"[Diagram Image: {diag_filename}]"

                            # Check what changed
                            answer_changed = new_answer != (q.get("answer") or "")
                            working_changed = new_working != (q.get("worked_solution") or "")
                            diagram_changed = new_diagram_desc != (q.get("question_diagram") or "")
                            text_changed = new_question_text != (q.get("latex_text") or "")
                            context_changed = q.get("part_letter") and new_main_context != (q.get("main_context") or "")
                            marks_changed = new_marks != q.get("marks")
                            qnum_changed = new_q_num != q.get("question_num")
                            section_changed = new_section != q.get("paper_section")
                            topics_changed = sorted(new_topics) != sorted(q.get("topics") or [])
                            heuristics_changed = sorted(new_heuristics) != sorted(q.get("heuristics") or [])

                            # Update metadata if changed
                            if marks_changed or qnum_changed or section_changed:
                                success = update_question_metadata(
                                    question_id=q['id'],
                                    marks=new_marks if marks_changed else None,
                                    question_num=new_q_num if qnum_changed else None,
                                    paper_section=new_section if section_changed else None,
                                    pdf_question_num=new_q_num if qnum_changed else None,
                                ) and success

                            if answer_changed or working_changed or diagram_changed:
                                success = update_answer(
                                    school=q['school'],
                                    year=q['year'],
                                    paper_section=new_section,  # Use new section
                                    question_num=new_q_num,     # Use new question num
                                    answer=new_answer,
                                    worked_solution=new_working,
                                    question_diagram=new_diagram_desc if diagram_changed else None,
                                    part_letter=q.get('part_letter'),
                                    overwrite=True
                                ) and success

                            if text_changed or context_changed:
                                success = update_question_text(
                                    school=q['school'],
                                    year=q['year'],
                                    paper_section=new_section,  # Use new section
                                    question_num=new_q_num,     # Use new question num
                                    latex_text=new_question_text,
                                    main_context=new_main_context if q.get("part_letter") else None,
                                    part_letter=q.get('part_letter')
                                ) and success

                            if (topics_changed or heuristics_changed) and update_topic_tags:
                                success = update_topic_tags(
                                    question_id=q['id'],
                                    topics=new_topics if topics_changed else None,
                                    heuristics=new_heuristics if heuristics_changed else None,
                                ) and success

                            if success:
                                st.success("Saved!")
                                # Clear cache so changes show up
                                cached_get_questions.clear()
                                cached_get_statistics.clear()
                                st.rerun()
                            else:
                                st.error("Failed to save")

                    with col_delete:
                        # Two-click delete: first click shows confirmation, second deletes
                        confirm_key = f"confirm_delete_{q['id']}"
                        if st.session_state.get(confirm_key):
                            st.warning("Click again to confirm")
                            if st.button("Confirm Delete", key=f"do_delete_{q['id']}", type="primary"):
                                if delete_question:
                                    ok = delete_question(
                                        q['school'], q['year'], q['paper_section'],
                                        q['question_num'], q.get('part_letter') or None
                                    )
                                    if ok:
                                        st.success("Deleted!")
                                        st.session_state.pop(confirm_key, None)
                                        cached_get_questions.clear()
                                        cached_get_statistics.clear()
                                        st.rerun()
                                    else:
                                        st.error("Delete failed")
                                else:
                                    st.error("Delete not available (SQLite mode)")
                            if st.button("Cancel", key=f"cancel_delete_{q['id']}"):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()
                        else:
                            if st.button("Delete", key=f"delete_{q['id']}", type="secondary"):
                                st.session_state[confirm_key] = True
                                st.rerun()

            # Show PDF reference info on hover/detail
            if q.get("pdf_page_num"):
                st.caption(f"PDF page: {q['pdf_page_num']}")

            st.divider()

    # Bottom pagination controls
    if total_pages > 1:
        col_prev, col_info, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("← Previous", disabled=current_page <= 1, key="prev_bottom"):
                st.session_state.page = max(1, current_page - 1)
                st.rerun()
        with col_info:
            st.markdown(f"**Page {current_page} of {total_pages}**")
        with col_next:
            if st.button("Next →", disabled=current_page >= total_pages, key="next_bottom"):
                st.session_state.page = min(total_pages, current_page + 1)
                st.rerun()


def show_paper_structure():
    """Display paper structure reference."""
    st.subheader("Paper Structure Reference")

    for section, info in PAPER_SECTIONS.items():
        total_marks = info.get('total_marks', '')
        marks_label = f" — {total_marks} marks" if total_marks else ""
        st.markdown(f"**{info['name']} ({section}){marks_label}**")
        for range_info in info["question_ranges"]:
            marks = range_info["marks"]
            if marks:
                marks_text = f"{marks} mark{'s' if marks > 1 else ''} each"
            else:
                marks_text = "marks vary"
            st.markdown(
                f"- Q{range_info['start']}-{range_info['end']}: "
                f"{range_info['type'].replace('_', ' ').title()} "
                f"({marks_text})"
            )


if __name__ == "__main__":
    main()
