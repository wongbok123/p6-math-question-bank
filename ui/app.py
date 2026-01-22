"""
Streamlit UI for P6 Math Question Bank viewer.
"""

import streamlit as st
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import UI_PAGE_TITLE, UI_PAGE_ICON, UI_LAYOUT, PAPER_SECTIONS, SECTION_FULL_NAMES
from database import (
    get_questions,
    get_all_schools,
    get_all_years,
    get_statistics,
    init_db,
    update_answer,
    update_question_text,
)


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
        EDIT_PASSWORD = "p6math2025"  # Change this to your desired password

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
                # Handle both absolute paths (local) and relative paths (cloud)
                image_path = Path(q["image_path"])
                if image_path.exists():
                    st.image(str(image_path), use_container_width=True)
                else:
                    # Try relative path from project root (for Streamlit Cloud)
                    filename = image_path.name
                    relative_path = Path(__file__).parent.parent / "output" / "images" / filename
                    if relative_path.exists():
                        st.image(str(relative_path), use_container_width=True)
                    else:
                        st.warning("Image not found")

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

            # Edit section (only shown when edit mode is enabled)
            if edit_mode:
                with st.expander(f"✏️ Edit Q{display_num}"):
                    # Answer editing
                    new_answer = st.text_input(
                        "Answer",
                        value=q.get("answer") or "",
                        key=f"answer_{q['id']}"
                    )

                    # Working solution editing
                    new_working = st.text_area(
                        "Worked Solution",
                        value=q.get("worked_solution") or "",
                        height=150,
                        key=f"working_{q['id']}"
                    )

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
                            # Update answer if changed
                            answer_changed = new_answer != (q.get("answer") or "")
                            working_changed = new_working != (q.get("worked_solution") or "")
                            text_changed = new_question_text != (q.get("latex_text") or "")
                            context_changed = q.get("part_letter") and new_main_context != (q.get("main_context") or "")

                            success = True

                            if answer_changed or working_changed:
                                success = update_answer(
                                    school=q['school'],
                                    year=q['year'],
                                    paper_section=q['paper_section'],
                                    question_num=q['question_num'],
                                    answer=new_answer,
                                    worked_solution=new_working,
                                    part_letter=q.get('part_letter'),
                                    overwrite=True
                                ) and success

                            if text_changed or context_changed:
                                success = update_question_text(
                                    school=q['school'],
                                    year=q['year'],
                                    paper_section=q['paper_section'],
                                    question_num=q['question_num'],
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
