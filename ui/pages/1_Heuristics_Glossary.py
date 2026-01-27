"""
Heuristics Glossary page for P6 Math Question Bank.
Displays all 26 heuristics with definitions, tagging guidance, and examples.
"""

import streamlit as st
from pathlib import Path
import sys
import re

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import HEURISTICS, UI_PAGE_ICON

GLOSSARY_PATH = Path(__file__).parent.parent.parent / "HEURISTICS_GLOSSARY.md"


def parse_glossary(md_text: str) -> dict:
    """Parse HEURISTICS_GLOSSARY.md into a dict of {name: body}."""
    entries = {}
    # Split on ## headings (level 2)
    parts = re.split(r'\n## ', md_text)
    for part in parts[1:]:  # skip preamble before first ##
        lines = part.strip().split('\n', 1)
        name = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        # Remove trailing --- separator
        body = re.sub(r'\n---\s*$', '', body).strip()
        entries[name] = body
    return entries


def main():
    st.set_page_config(
        page_title="Heuristics Glossary",
        page_icon=UI_PAGE_ICON,
        layout="wide",
    )

    st.title(f"{UI_PAGE_ICON} Heuristics Glossary")
    st.markdown(
        "Problem-solving strategies (heuristics) used in Singapore Primary Mathematics. "
        "These are the methods students use to solve word problems, not the topics themselves."
    )
    st.markdown(
        "A question can have **0-3 heuristics**. Simple P1A MCQs and straightforward "
        "computation questions typically have **none**. P2 multi-step word problems often use 1-2."
    )

    # Load and parse glossary
    if GLOSSARY_PATH.exists():
        md_text = GLOSSARY_PATH.read_text()
        entries = parse_glossary(md_text)
    else:
        st.error("HEURISTICS_GLOSSARY.md not found.")
        return

    # Search filter
    search = st.text_input("Search heuristics", placeholder="Type to filter...")

    st.divider()

    # Display count
    filtered = [h for h in HEURISTICS if not search or search.lower() in h.lower()
                or (h in entries and search.lower() in entries[h].lower())]

    st.caption(f"Showing {len(filtered)} of {len(HEURISTICS)} heuristics")

    # Render each heuristic
    for name in filtered:
        body = entries.get(name, "*No glossary entry found.*")

        with st.expander(f"**{name}**", expanded=not search):
            st.markdown(body)


if __name__ == "__main__":
    main()
