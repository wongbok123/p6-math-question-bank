#!/usr/bin/env python3
"""
Update all image_path values in Firestore to use Firebase Storage URLs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from firebase_db import init_firebase, get_db

# Firebase Storage base URL
STORAGE_BASE = "https://storage.googleapis.com/p6-math-question-bank.firebasestorage.app"


def update_image_paths():
    """Update all image_path values to Firebase Storage URLs."""
    print("Initializing Firebase...")
    init_firebase()
    db = get_db()

    print("\nFetching all questions...")
    docs = list(db.collection('questions').stream())
    print(f"Found {len(docs)} questions")

    updated = 0
    skipped = 0

    for doc in docs:
        data = doc.to_dict()
        image_path = data.get('image_path', '')

        # Skip if already a URL
        if image_path.startswith('http'):
            skipped += 1
            continue

        # Convert local path to Firebase Storage URL
        # Local: output/images/School_2025_p01.png
        # Storage: images/School_2025_p01.png
        if image_path:
            # Extract just the filename
            filename = Path(image_path).name
            new_url = f"{STORAGE_BASE}/images/{filename}"

            # Update in Firestore
            doc.reference.update({'image_path': new_url})
            updated += 1

            if updated % 100 == 0:
                print(f"  Updated {updated} paths...")

    print(f"\nComplete!")
    print(f"  Updated: {updated}")
    print(f"  Skipped (already URLs): {skipped}")


if __name__ == "__main__":
    update_image_paths()
