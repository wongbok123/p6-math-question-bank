#!/usr/bin/env python3
"""
tag_topics.py - AI-powered topic, type, and heuristic tagging for questions.

Two-pass workflow:
  Pass 1 (calibration): Tag ~30 questions, review in UI, export corrections
  Pass 2 (full run):    Load corrected examples as few-shot, tag all 624

Usage:
    export GEMINI_API_KEY="your-key"

    # Pass 1 — calibrate on a small batch
    python tag_topics.py --limit 30
    python tag_topics.py --limit 30 --dry-run          # preview without saving

    # Pass 2 — full run with few-shot examples
    python tag_topics.py --force --examples few_shot_examples.json

    # Utilities
    python tag_topics.py --school "Tao Nan" --section P2
    python tag_topics.py --validate                     # check stored tags
"""

import os
import re
import sys
import json
import time
import argparse
import io
from pathlib import Path
from typing import Optional, Dict, List
from difflib import get_close_matches

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    TOPICS, HEURISTICS,
    TOPIC_CLASSIFICATION_PROMPT,
)
from utils.gemini_client import GeminiClient

# Use Firebase by default, SQLite fallback
USE_FIREBASE = os.environ.get('USE_FIREBASE', 'true').lower() == 'true'

try:
    if USE_FIREBASE:
        from firebase_db import get_questions, update_topic_tags
        USING_FIREBASE = True
    else:
        raise ImportError("Firebase disabled")
except Exception:
    from database import get_questions
    USING_FIREBASE = False

    def update_topic_tags(question_id, topics=None,
                          heuristics=None, confidence=None, needs_review=False):
        """SQLite fallback for update_topic_tags."""
        import sqlite3
        from config import DATABASE_PATH
        conn = sqlite3.connect(DATABASE_PATH)
        updates = []
        params = []
        if topics is not None:
            updates.append("topics = ?")
            params.append(json.dumps(topics))
        if heuristics is not None:
            updates.append("heuristics = ?")
            params.append(json.dumps(heuristics))
        if confidence is not None:
            updates.append("confidence = ?")
            params.append(confidence)
        updates.append("needs_review = ?")
        params.append(1 if needs_review else 0)

        if not updates:
            conn.close()
            return False
        params.append(question_id)
        query = f"UPDATE questions SET {', '.join(updates)} WHERE id = ?"
        cursor = conn.execute(query, params)
        conn.commit()
        ok = cursor.rowcount > 0
        conn.close()
        return ok


# All valid tags for validation
ALL_TOPICS = set(TOPICS)
ALL_HEURISTICS = set(HEURISTICS)

# Remap old heuristic names (26 → 15 consolidation)
HEURISTIC_REMAP = {
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


def load_few_shot_examples(path: str) -> str:
    """Load few-shot examples from a JSON file and format for the prompt."""
    with open(path) as f:
        examples = json.load(f)

    if not examples:
        return "(No examples provided.)"

    lines = []
    for i, ex in enumerate(examples, 1):
        lines.append(f"Example {i}:")
        lines.append(f"  Question: {ex.get('question_text', 'N/A')}")
        if ex.get('main_context'):
            lines.append(f"  Context: {ex['main_context']}")
        lines.append(f"  Answer: {ex.get('answer', 'N/A')}")
        lines.append(f"  Section: {ex.get('section', 'N/A')}")
        tags = {
            "topics": ex.get("topics", []),
            "heuristics": ex.get("heuristics", []),
        }
        lines.append(f"  Classification: {json.dumps(tags)}")
        lines.append("")
    return "\n".join(lines)


def fuzzy_match_tag(value: str, valid_set: set) -> Optional[str]:
    """Try to fuzzy-match a tag against valid tags. Returns match or None."""
    if value in valid_set:
        return value
    # Try case-insensitive exact match
    for v in valid_set:
        if v.lower() == value.lower():
            return v
    # Try close matches
    matches = get_close_matches(value, valid_set, n=1, cutoff=0.8)
    return matches[0] if matches else None


def validate_tags(result: dict) -> dict:
    """Validate and fix classification result against taxonomy.

    Returns cleaned result with only valid tags.
    """
    cleaned = {"topics": [], "heuristics": []}

    for raw_topic in result.get("topics", []):
        matched = fuzzy_match_tag(raw_topic, ALL_TOPICS)
        if matched:
            cleaned["topics"].append(matched)
        else:
            print(f"    [WARN] Unknown topic: '{raw_topic}'")

    for raw_h in result.get("heuristics", []):
        # Remap old heuristic names to consolidated names
        remapped = HEURISTIC_REMAP.get(raw_h, raw_h)
        matched = fuzzy_match_tag(remapped, ALL_HEURISTICS)
        if matched:
            if matched not in cleaned["heuristics"]:
                cleaned["heuristics"].append(matched)
        else:
            print(f"    [WARN] Unknown heuristic: '{raw_h}'")

    # Ensure at least 1 topic
    if not cleaned["topics"]:
        cleaned["topics"] = ["Whole Numbers"]  # safe fallback
        print("    [WARN] No valid topics, defaulted to 'Whole Numbers'")

    # Confidence passthrough
    confidence = result.get("confidence", 0.5)
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        confidence = 0.5
    cleaned["confidence"] = confidence

    return cleaned


def load_question_image(q: dict) -> Optional[Image.Image]:
    """Load question image from URL or local path."""
    image_path_str = q.get("image_path", "")

    if image_path_str.startswith("http"):
        try:
            resp = requests.get(image_path_str, timeout=30)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content))
        except Exception as e:
            print(f"    [ERROR] Failed to download image: {e}")
            return None
    else:
        path = Path(image_path_str)
        if path.exists():
            return Image.open(path)
        print(f"    [ERROR] Image not found: {image_path_str}")
        return None


def classify_question(
    client: GeminiClient,
    q: dict,
    few_shot_text: str,
) -> Optional[dict]:
    """Classify a single question using Gemini Vision.

    Returns validated tag dict or None on failure.
    """
    prompt = TOPIC_CLASSIFICATION_PROMPT.format(
        few_shot_examples=few_shot_text,
        question_text=q.get("latex_text", ""),
        main_context=q.get("main_context") or "N/A",
        answer=q.get("answer") or "N/A",
        section=q.get("paper_section", ""),
    )

    image = load_question_image(q)
    if image is None:
        return None

    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = client.extract_from_image(image, prompt)

            if not result.success:
                print(f"    [ERROR] Gemini failed: {result.error}")
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"    [Retry in {wait}s...]")
                    time.sleep(wait)
                    continue
                return None

            response_text = result.question_text.strip()

            # Strip markdown code fences if present
            if response_text.startswith("```"):
                response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
                response_text = re.sub(r'\s*```$', '', response_text)

            # Extract JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}')
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end + 1]
                parsed = json.loads(json_str)
                return validate_tags(parsed)

            print(f"    [WARN] No JSON found in response")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return None

        except json.JSONDecodeError as e:
            print(f"    [WARN] JSON parse error: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return None
        except Exception as e:
            if '429' in str(e) or 'quota' in str(e).lower():
                wait = 2 ** (attempt + 2)  # longer wait for rate limits
                print(f"    [Rate limited] Waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"    [ERROR] {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return None


def validate_stored_tags(questions: List[dict]) -> dict:
    """Validate all stored tags against taxonomy. Returns stats."""
    stats = {"total": 0, "valid": 0, "invalid_topics": [],
             "invalid_heuristics": [], "untagged": 0}

    for q in questions:
        stats["total"] += 1
        q_topics = q.get("topics") or []
        q_heuristics = q.get("heuristics") or []

        if not q_topics:
            stats["untagged"] += 1
            continue

        valid = True
        for t in q_topics:
            if t not in ALL_TOPICS:
                stats["invalid_topics"].append((q.get("id"), t))
                valid = False
        for h in q_heuristics:
            if h not in ALL_HEURISTICS:
                stats["invalid_heuristics"].append((q.get("id"), h))
                valid = False

        if valid:
            stats["valid"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Tag questions with topics, types, and heuristics using Gemini"
    )
    parser.add_argument("--school", type=str, help="Tag specific school only")
    parser.add_argument("--section", type=str, help="Tag specific section (P1A, P1B, P2)")
    parser.add_argument("--force", action="store_true", help="Re-tag already-tagged questions")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--limit", type=int, help="Process only N questions")
    parser.add_argument("--validate", action="store_true", help="Check existing tags against taxonomy")
    parser.add_argument("--examples", type=str, help="Path to few-shot examples JSON file")
    args = parser.parse_args()

    # Validate mode — no API key needed
    if args.validate:
        print("=" * 60)
        print("VALIDATE STORED TAGS")
        print("=" * 60)
        questions = get_questions(
            school=args.school,
            paper_section=args.section,
        )
        stats = validate_stored_tags(questions)
        print(f"\nTotal questions: {stats['total']}")
        print(f"Untagged:       {stats['untagged']}")
        print(f"Valid tags:     {stats['valid']}")
        if stats["invalid_topics"]:
            print(f"\nInvalid topics ({len(stats['invalid_topics'])}):")
            for qid, tag in stats["invalid_topics"][:20]:
                print(f"  {qid}: '{tag}'")
        if stats["invalid_heuristics"]:
            print(f"\nInvalid heuristics ({len(stats['invalid_heuristics'])}):")
            for qid, tag in stats["invalid_heuristics"][:20]:
                print(f"  {qid}: '{tag}'")
        return

    # Tagging mode — requires API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY not set!")
        sys.exit(1)

    print("=" * 60)
    print("TOPIC TAGGING")
    print("AI-powered classification using Gemini Vision")
    print("=" * 60)

    client = GeminiClient(api_key=api_key)

    # Load few-shot examples
    few_shot_text = "(No examples provided — this is a calibration run.)"
    if args.examples:
        examples_path = Path(args.examples)
        if examples_path.exists():
            few_shot_text = load_few_shot_examples(str(examples_path))
            print(f"Loaded few-shot examples from {examples_path}")
        else:
            print(f"[WARN] Examples file not found: {examples_path}")

    # Fetch questions
    query_params = {}
    if args.school:
        query_params["school"] = args.school
    if args.section:
        query_params["paper_section"] = args.section

    questions = get_questions(**query_params)
    print(f"Found {len(questions)} questions")

    # Skip already-tagged unless --force
    if not args.force:
        original_count = len(questions)
        questions = [q for q in questions if not q.get("topics")]
        skipped = original_count - len(questions)
        if skipped:
            print(f"Skipping {skipped} already-tagged questions (use --force to re-tag)")

    # Apply limit
    if args.limit:
        questions = questions[:args.limit]
        print(f"Limiting to {len(questions)} questions")

    if not questions:
        print("No questions to tag.")
        return

    if args.dry_run:
        print("[DRY RUN] Will preview classifications without saving\n")
    else:
        print(f"\nTagging {len(questions)} questions...\n")

    # Process questions
    tagged = 0
    failed = 0
    flagged = 0

    for i, q in enumerate(questions):
        section = q.get("paper_section", "")
        qnum = q.get("pdf_question_num") or q.get("question_num", 0)
        part = f"({q['part_letter']})" if q.get("part_letter") else ""
        q_label = f"{q.get('school', '')} {section} Q{qnum}{part}"

        print(f"[{i+1}/{len(questions)}] {q_label}...", end=" ")

        result = classify_question(client, q, few_shot_text)

        if result is None:
            print("[FAILED]")
            failed += 1
            continue

        confidence = result.get("confidence", 0.5)
        needs_review = confidence < 0.7

        if needs_review:
            flagged += 1

        # Display
        review_flag = " ⚠️ REVIEW" if needs_review else ""
        print(f"[conf={confidence:.2f}{review_flag}]")
        print(f"    Topics:     {result['topics']}")
        print(f"    Heuristics: {result['heuristics']}")

        if not args.dry_run:
            question_id = q.get("id")
            if question_id:
                ok = update_topic_tags(
                    question_id=question_id,
                    topics=result["topics"],
                    heuristics=result["heuristics"],
                    confidence=confidence,
                    needs_review=needs_review,
                )
                if ok:
                    tagged += 1
                else:
                    print(f"    [ERROR] Failed to save tags for {question_id}")
                    failed += 1
            else:
                print("    [WARN] No question ID, cannot save")
                failed += 1
        else:
            tagged += 1  # count as success for dry-run

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"Processed:    {tagged + failed}")
    print(f"Tagged:       {tagged}")
    print(f"Failed:       {failed}")
    print(f"Needs review: {flagged} (confidence < 0.7)")
    if args.dry_run:
        print("\n[DRY RUN] No changes were saved.")


if __name__ == "__main__":
    main()
