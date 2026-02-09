"""
Heuristics Glossary page for P6 Math Question Bank.
Displays all 15 heuristics with definitions, tagging guidance, and examples.
"""

import streamlit as st
from pathlib import Path
import sys
import re

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import HEURISTICS, UI_PAGE_ICON


GLOSSARY_PATH = Path(__file__).parent.parent.parent / "HEURISTICS_GLOSSARY.md"

# ── Visual anchor icons ───────────────────────────────────────────────────────
ICONS = {
    "Before-After": "\U0001f504",         # 🔄
    "Boomerang & Rugby": "\U0001f3c9",    # 🏉
    "Branching": "\U0001f33f",            # 🌿
    "Constant Quantity": "\u2696\ufe0f",  # ⚖️
    "Equal Portions": "\U0001f7f0",       # 🟰
    "Model Drawing": "\U0001f4ca",        # 📊
    "Pattern Recognition": "\U0001f522",  # 🔢
    "Quantity \u00d7 Value": "\U0001f4b0",# 💰
    "Repeated Items": "\U0001f517",       # 🔗
    "Simultaneous Concept": "\u26a1",     # ⚡
    "Spatial Reasoning": "\U0001f4d0",    # 📐
    "Supposition": "\U0001f914",          # 🤔
    "Unitary Method": "1\ufe0f\u20e3",   # 1️⃣
    "Using Parallel Lines": "\u2197\ufe0f",# ↗️
    "Working Backwards": "\u23ea",        # ⏪
}

# ── Difficulty / frequency badges ─────────────────────────────────────────────
META = {
    "Before-After":        {"freq": "Very Common", "level": "P4\u2013P6", "paper": "P1B / P2"},
    "Boomerang & Rugby":   {"freq": "Common",      "level": "P5\u2013P6", "paper": "P2 Only"},
    "Branching":           {"freq": "Common",       "level": "P4\u2013P6", "paper": "P1B / P2"},
    "Constant Quantity":   {"freq": "Common",       "level": "P5\u2013P6", "paper": "P2 Only"},
    "Equal Portions":      {"freq": "Moderate",     "level": "P5\u2013P6", "paper": "P2 Only"},
    "Model Drawing":       {"freq": "Very Common",  "level": "P3\u2013P6", "paper": "P1B / P2"},
    "Pattern Recognition": {"freq": "Common",       "level": "P3\u2013P6", "paper": "P1B / P2"},
    "Quantity \u00d7 Value":{"freq": "Moderate",    "level": "P5\u2013P6", "paper": "P2 Only"},
    "Repeated Items":      {"freq": "Common",       "level": "P5\u2013P6", "paper": "P2 Only"},
    "Simultaneous Concept":{"freq": "Common",       "level": "P5\u2013P6", "paper": "P2 Only"},
    "Spatial Reasoning":   {"freq": "Common",       "level": "P5\u2013P6", "paper": "P2 Only"},
    "Supposition":         {"freq": "Common",       "level": "P5\u2013P6", "paper": "P2 Only"},
    "Unitary Method":      {"freq": "Very Common",  "level": "P3\u2013P6", "paper": "P1B / P2"},
    "Using Parallel Lines":{"freq": "Moderate",     "level": "P5\u2013P6", "paper": "P2 Only"},
    "Working Backwards":   {"freq": "Common",       "level": "P4\u2013P6", "paper": "P1B / P2"},
}

# ── Illustration images for visual heuristics ─────────────────────────────────
IMAGES_DIR = Path(__file__).parent.parent / "glossary_images"

# Maps heuristic name → list of (filename, caption) tuples
ILLUSTRATIONS = {
    "Boomerang & Rugby": [
        ("boomerang_and_rugby.png", "Boomerang (square \u2212 quadrant) and half-rugby (quadrant \u2212 triangle)"),
    ],
    "Branching": [
        ("branching.png", "Remainder concept \u2014 fraction-of-remainder chain with branching diagram"),
    ],
    "Model Drawing": [
        ("model_before_after.png", "Before-after bar model (Sally & Mel \u2014 tickets)"),
        ("model_working_backwards.png", "Working-backwards bar model (Jessie & David \u2014 money)"),
    ],
}

# ── Page CSS ──────────────────────────────────────────────────────────────────
PAGE_CSS = """
<style>
/* Example callout boxes — target blockquotes inside markdown */
[data-testid="stMarkdownContainer"] blockquote {
    background-color: #eef4fb !important;
    border-left: 4px solid #4393e5 !important;
    padding: 12px 16px !important;
    margin: 14px 0 !important;
    border-radius: 0 6px 6px 0 !important;
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
"""

BADGE_CSS = (
    "display:inline-block;padding:3px 10px;border-radius:12px;"
    "font-size:0.78em;font-weight:600;margin-right:6px;line-height:1.6;"
)

FREQ_STYLES = {
    "Very Common": "background-color:#fee2e2;color:#991b1b",
    "Common":      "background-color:#ffedd5;color:#9a3412",
    "Moderate":    "background-color:#dbeafe;color:#1e40af",
}


def parse_glossary(md_text: str) -> dict:
    """Parse HEURISTICS_GLOSSARY.md into a dict of {name: body}."""
    entries = {}
    parts = re.split(r'\n## ', md_text)
    for part in parts[1:]:  # skip preamble before first ##
        lines = part.strip().split('\n', 1)
        name = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        body = re.sub(r'\n---\s*$', '', body).strip()
        entries[name] = body
    return entries


def render_badges(name: str):
    """Render frequency / level / paper badges as colored pills."""
    meta = META.get(name)
    if not meta:
        return
    freq_style = FREQ_STYLES.get(meta["freq"], "")
    st.markdown(
        f'<div style="margin-bottom:10px">'
        f'<span style="{BADGE_CSS}{freq_style}">{meta["freq"]}</span>'
        f'<span style="{BADGE_CSS}background-color:#f3e8ff;color:#6b21a8">{meta["level"]}</span>'
        f'<span style="{BADGE_CSS}background-color:#ecfdf5;color:#065f46">{meta["paper"]}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_body(name: str, body: str):
    """Render glossary body with proper heading hierarchy.

    Main title is rendered as h2 (by the caller).
    Sub-types are rendered as styled inline elements — visually smaller.
    """
    # Split into main body and sub-type sections
    sections = re.split(r'\n### Sub-type: ', body)
    main_body = sections[0].strip()

    # Illustration images for visual heuristics
    if name in ILLUSTRATIONS:
        for filename, caption in ILLUSTRATIONS[name]:
            img_path = IMAGES_DIR / filename
            if img_path.exists():
                st.image(str(img_path), caption=caption, use_column_width=True)

    # Render main body (What it is, When to tag, Example)
    st.markdown(main_body)

    # Render sub-types — visually subordinate with left border
    for section in sections[1:]:
        lines = section.strip().split('\n', 1)
        subtype_name = lines[0].strip()
        subtype_body = lines[1].strip() if len(lines) > 1 else ""

        st.markdown(
            f'<div style="border-left:3px solid #d1d5db;padding-left:12px;'
            f'margin-top:20px;margin-bottom:4px">'
            f'<span style="font-size:0.75em;font-weight:600;color:#9ca3af;'
            f'text-transform:uppercase;letter-spacing:0.05em">SUB-TYPE</span>'
            f'<br>'
            f'<span style="font-size:0.95em;font-weight:700;color:#6b7280">'
            f'{subtype_name}</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown(subtype_body)


def main():
    st.set_page_config(
        page_title="Heuristics Glossary",
        page_icon=UI_PAGE_ICON,
        layout="wide",
    )

    # Inject CSS for example callout styling
    st.markdown(PAGE_CSS, unsafe_allow_html=True)

    st.title(f"{UI_PAGE_ICON} Heuristics Glossary")
    st.markdown(
        "Problem-solving strategies (heuristics) used in Singapore Primary Mathematics. "
        "These are the methods students use to solve word problems, not the topics themselves."
    )
    st.markdown(
        "A question can have **0\u20133 heuristics**. Simple Paper 1 Booklet A MCQs and "
        "straightforward computation questions typically have **none**. "
        "Paper 2 multi-step word problems often use 1\u20132."
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

    # Filter
    filtered = [
        h for h in HEURISTICS
        if not search
        or search.lower() in h.lower()
        or (h in entries and search.lower() in entries[h].lower())
    ]

    st.caption(f"Showing {len(filtered)} of {len(HEURISTICS)} heuristics")

    # Render each heuristic
    for name in filtered:
        body = entries.get(name, "*No glossary entry found.*")
        icon = ICONS.get(name, "")

        with st.expander(f"{icon}  **{name}**", expanded=not search):
            # h2 title — clearly larger than sub-type text
            st.markdown(f"## :orange[{name}]")
            render_badges(name)
            render_body(name, body)


if __name__ == "__main__":
    main()
