#!/usr/bin/env python3
"""
migrate_heuristics.py - Remap old heuristic names to consolidated taxonomy (26 → 15).

Reads all tagged questions from Firebase, replaces old heuristic names with new
consolidated names, deduplicates, and saves back.

Usage:
    # Preview changes (dry run, default)
    python scripts/migrate_heuristics.py

    # Apply changes to Firebase
    python scripts/migrate_heuristics.py --apply
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import HEURISTICS

# Old name → new consolidated name
REMAP = {
    "All Items Changed": "Before-After",
    "One Item Unchanged": "Before-After",
    "Constant Difference": "Constant Quantity",
    "Constant Total": "Constant Quantity",
    "Excess & Shortage": "Supposition",
    "Folded Shapes": "Spatial Reasoning",
    "Gap & Overlap": "Spatial Reasoning",
    "Guess & Check": "Supposition",
    "Make a List / Table": "Branching",
    "Proportionality": "Unitary Method",
    "Remainder Concept": "Branching",
    "Spotting Hidden Shapes": "Spatial Reasoning",
    "Visual Regrouping (Cut & Paste)": "Spatial Reasoning",
}

VALID_HEURISTICS = set(HEURISTICS)


def remap_heuristics(heuristics: list) -> list:
    """Remap old heuristic names and deduplicate."""
    result = []
    for h in heuristics:
        new_name = REMAP.get(h, h)
        if new_name not in result:
            result.append(new_name)
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Remap old heuristic names to consolidated taxonomy"
    )
    parser.add_argument("--apply", action="store_true",
                        help="Apply changes to Firebase (default is dry run)")
    args = parser.parse_args()

    # Import Firebase
    try:
        from firebase_db import get_questions, update_topic_tags
    except Exception as e:
        print(f"[ERROR] Could not import firebase_db: {e}")
        print("Make sure firebase-key.json is present and dependencies are installed.")
        sys.exit(1)

    print("=" * 60)
    print("HEURISTIC MIGRATION: 26 → 15 consolidated taxonomy")
    print("=" * 60)
    if not args.apply:
        print("[DRY RUN] Preview only. Use --apply to save changes.\n")
    else:
        print("[APPLY MODE] Changes will be saved to Firebase.\n")

    questions = get_questions()
    print(f"Total questions: {len(questions)}\n")

    changed = 0
    unchanged = 0
    untagged = 0
    invalid_after = []

    for q in questions:
        q_id = q.get("id", "?")
        old_heuristics = q.get("heuristics") or []

        if not old_heuristics:
            untagged += 1
            continue

        new_heuristics = remap_heuristics(old_heuristics)

        # Check if anything changed
        if new_heuristics == old_heuristics:
            unchanged += 1
            continue

        # Validate new tags
        for h in new_heuristics:
            if h not in VALID_HEURISTICS:
                invalid_after.append((q_id, h))

        school = q.get("school", "")
        section = q.get("paper_section", "")
        qnum = q.get("question_num", 0)
        part = f"({q.get('part_letter', '')})" if q.get("part_letter") else ""
        label = f"{school} {section} Q{qnum}{part}"

        print(f"  {label}")
        print(f"    OLD: {old_heuristics}")
        print(f"    NEW: {new_heuristics}")

        if args.apply:
            ok = update_topic_tags(
                question_id=q_id,
                heuristics=new_heuristics,
            )
            if ok:
                changed += 1
            else:
                print(f"    [ERROR] Failed to update {q_id}")
        else:
            changed += 1

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"Total questions:  {len(questions)}")
    print(f"Untagged:         {untagged}")
    print(f"Unchanged:        {unchanged}")
    print(f"Remapped:         {changed}")

    if invalid_after:
        print(f"\n[WARN] Invalid heuristics after remap ({len(invalid_after)}):")
        for qid, h in invalid_after[:20]:
            print(f"  {qid}: '{h}'")

    if not args.apply:
        print("\n[DRY RUN] No changes saved. Use --apply to commit.")


if __name__ == "__main__":
    main()
