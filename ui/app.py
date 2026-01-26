"""
Streamlit UI for P6 Math Question Bank viewer.
"""

import streamlit as st
from pathlib import Path
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import UI_PAGE_TITLE, UI_PAGE_ICON, UI_LAYOUT, PAPER_SECTIONS, SECTION_FULL_NAMES

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
            upload_image_bytes,
            get_image_url,
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

# Directory for uploaded solution images (local fallback)
SOLUTIONS_DIR = Path(__file__).parent.parent / "output" / "images" / "solutions"
SOLUTIONS_DIR.mkdir(parents=True, exist_ok=True)


def main():
    """Main Streamlit application."""
    st.set_page_config(
        page_title=UI_PAGE_TITLE,
        page_icon=UI_PAGE_ICON,
        layout=UI_LAYOUT,
    )

    st.title(f"{UI_PAGE_ICON} {UI_PAGE_TITLE}")

    # Initialize database if needed
    try:
        stats = get_statistics()
    except Exception:
        init_db()
        stats = get_statistics()

    # Sidebar filters
    with st.sidebar:
        st.header("Filters")

        # School filter
        schools = get_all_schools()
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
        years = get_all_years()
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

        # Marks filter
        selected_marks = st.selectbox(
            "Marks",
            ["All", "1", "2", "3", "4", "5"],
            index=0,
        )

        # Show answer toggle (default ON for easy verification)
        show_answers = st.checkbox("Show Answers", value=True)

        st.divider()

        # Edit mode with password protection
        st.header("Edit Mode")
        EDIT_PASSWORD = "p6math2026"  # Change this to your desired password

        # Initialize session state for edit mode
        if "edit_mode_unlocked" not in st.session_state:
            st.session_state.edit_mode_unlocked = False

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

    # Build query parameters
    query_params = {}
    if selected_school != "All":
        query_params["school"] = selected_school
    if selected_year != "All":
        query_params["year"] = int(selected_year)
    if selected_section != "All":
        query_params["paper_section"] = selected_section
    if selected_marks != "All":
        query_params["marks"] = int(selected_marks)

    # Get questions
    questions = get_questions(**query_params)

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

    # Display questions
    st.subheader(f"Questions ({len(questions)} results)")

    for i, q in enumerate(questions):
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
                                st.info("📷 Image not available on cloud")

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
                    # Check if there's a solution image reference
                    import re
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

            # Edit section (only shown when edit mode is enabled)
            if edit_mode:
                with st.expander(f"✏️ Edit Q{display_num}"):
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
                        section_options = ["P1A", "P1B", "P2"]
                        current_section_idx = section_options.index(q['paper_section']) if q['paper_section'] in section_options else 0
                        new_section = st.selectbox(
                            "Paper Section",
                            section_options,
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
                    uploaded_image = st.file_uploader(
                        "Upload solution image",
                        type=["png", "jpg", "jpeg"],
                        key=f"upload_{q['id']}"
                    )

                    if uploaded_image:
                        st.image(uploaded_image, caption="Preview", width=300)

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

                    # Save button
                    col_save, col_status = st.columns([1, 2])
                    with col_save:
                        if st.button(f"💾 Save", key=f"save_{q['id']}"):
                            success = True

                            # Handle image upload
                            if uploaded_image:
                                img_filename = f"{q['school']}_{q['year']}_{q['paper_section']}_Q{q['question_num']}"
                                if q.get('part_letter'):
                                    img_filename += f"_{q['part_letter']}"
                                img_filename += f".{uploaded_image.name.split('.')[-1]}"
                                img_filename = img_filename.replace(" ", "_")

                                # Upload to Firebase Storage if available
                                img_ref = None
                                # Get image bytes (getvalue() returns bytes directly)
                                img_bytes = uploaded_image.getvalue()

                                if USING_FIREBASE and upload_image_bytes:
                                    try:
                                        storage_path = f"images/solutions/{img_filename}"
                                        ext = uploaded_image.name.split('.')[-1].lower()
                                        content_type = f"image/{ext if ext != 'jpg' else 'jpeg'}"
                                        img_url = upload_image_bytes(
                                            img_bytes,
                                            storage_path,
                                            content_type
                                        )
                                        # Add URL reference to worked solution
                                        img_ref = f"[Solution URL: {img_url}]"
                                        st.success(f"Image uploaded to cloud storage")
                                    except Exception as e:
                                        st.warning(f"Cloud upload failed: {e}. Saving locally...")
                                        # Fallback to local
                                        img_path = SOLUTIONS_DIR / img_filename
                                        with open(img_path, "wb") as f:
                                            f.write(img_bytes)
                                        img_ref = f"[Solution Image: {img_filename}]"
                                else:
                                    # Save locally
                                    img_path = SOLUTIONS_DIR / img_filename
                                    with open(img_path, "wb") as f:
                                        f.write(img_bytes)
                                    img_ref = f"[Solution Image: {img_filename}]"

                                if img_ref:
                                    if new_working:
                                        new_working = f"{new_working}\n\n{img_ref}"
                                    else:
                                        new_working = img_ref

                            # Check what changed
                            answer_changed = new_answer != (q.get("answer") or "")
                            working_changed = new_working != (q.get("worked_solution") or "")
                            text_changed = new_question_text != (q.get("latex_text") or "")
                            context_changed = q.get("part_letter") and new_main_context != (q.get("main_context") or "")
                            marks_changed = new_marks != q.get("marks")
                            qnum_changed = new_q_num != q.get("question_num")
                            section_changed = new_section != q.get("paper_section")

                            # Update metadata if changed
                            if marks_changed or qnum_changed or section_changed:
                                success = update_question_metadata(
                                    question_id=q['id'],
                                    marks=new_marks if marks_changed else None,
                                    question_num=new_q_num if qnum_changed else None,
                                    paper_section=new_section if section_changed else None,
                                    pdf_question_num=new_q_num if qnum_changed else None,
                                ) and success

                            if answer_changed or working_changed:
                                success = update_answer(
                                    school=q['school'],
                                    year=q['year'],
                                    paper_section=new_section,  # Use new section
                                    question_num=new_q_num,     # Use new question num
                                    answer=new_answer,
                                    worked_solution=new_working,
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

                            if success:
                                st.success("Saved!")
                                st.rerun()
                            else:
                                st.error("Failed to save")

            # Show PDF reference info on hover/detail
            if q.get("pdf_page_num"):
                st.caption(f"PDF page: {q['pdf_page_num']}")

            st.divider()


def show_paper_structure():
    """Display paper structure reference."""
    st.subheader("Paper Structure Reference")

    for section, info in PAPER_SECTIONS.items():
        st.markdown(f"**{info['name']} ({section})**")
        for range_info in info["question_ranges"]:
            marks = range_info["marks"] if range_info["marks"] else "3-5"
            st.markdown(
                f"- Q{range_info['start']}-{range_info['end']}: "
                f"{range_info['type'].replace('_', ' ').title()} "
                f"({marks} marks each)"
            )


if __name__ == "__main__":
    main()
