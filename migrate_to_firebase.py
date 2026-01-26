#!/usr/bin/env python3
"""
Migrate data from SQLite to Firebase.

Usage:
    python migrate_to_firebase.py
    python migrate_to_firebase.py --upload-images  # Also upload images to Firebase Storage
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from firebase_db import migrate_from_sqlite, init_firebase, get_statistics, upload_image
from config import DATABASE_PATH, IMAGES_DIR


def migrate_images():
    """Upload all local images to Firebase Storage."""
    print("\nUploading images to Firebase Storage...")

    # Question page images
    image_files = list(IMAGES_DIR.glob("*.png"))
    print(f"Found {len(image_files)} question images")

    for i, img_path in enumerate(image_files):
        storage_path = f"images/{img_path.name}"
        try:
            url = upload_image(str(img_path), storage_path)
            if (i + 1) % 50 == 0:
                print(f"  Uploaded {i + 1}/{len(image_files)}")
        except Exception as e:
            print(f"  Error uploading {img_path.name}: {e}")

    print(f"Uploaded {len(image_files)} question images")

    # Answer key images
    answer_key_dir = IMAGES_DIR / "answer_keys"
    if answer_key_dir.exists():
        answer_images = list(answer_key_dir.glob("*.png"))
        print(f"\nFound {len(answer_images)} answer key images")

        for i, img_path in enumerate(answer_images):
            storage_path = f"images/answer_keys/{img_path.name}"
            try:
                url = upload_image(str(img_path), storage_path)
                if (i + 1) % 20 == 0:
                    print(f"  Uploaded {i + 1}/{len(answer_images)}")
            except Exception as e:
                print(f"  Error uploading {img_path.name}: {e}")

        print(f"Uploaded {len(answer_images)} answer key images")

    # Solution images
    solutions_dir = IMAGES_DIR / "solutions"
    if solutions_dir.exists():
        solution_images = list(solutions_dir.glob("*"))
        print(f"\nFound {len(solution_images)} solution images")

        for img_path in solution_images:
            if img_path.is_file():
                storage_path = f"images/solutions/{img_path.name}"
                try:
                    upload_image(str(img_path), storage_path)
                except Exception as e:
                    print(f"  Error uploading {img_path.name}: {e}")

        print(f"Uploaded {len(solution_images)} solution images")


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite to Firebase")
    parser.add_argument(
        "--upload-images",
        action="store_true",
        help="Also upload images to Firebase Storage"
    )
    parser.add_argument(
        "--images-only",
        action="store_true",
        help="Only upload images, skip database migration"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("MIGRATE TO FIREBASE")
    print("=" * 60)

    # Initialize Firebase
    print("\nInitializing Firebase...")
    init_firebase()

    # Check current Firebase state
    stats = get_statistics()
    print(f"Current Firebase questions: {stats['total_questions']}")

    if not args.images_only:
        # Migrate database
        if not DATABASE_PATH.exists():
            print(f"\n[ERROR] SQLite database not found: {DATABASE_PATH}")
            sys.exit(1)

        print(f"\nMigrating from: {DATABASE_PATH}")
        migrate_from_sqlite(str(DATABASE_PATH))

        # Verify migration
        stats = get_statistics()
        print(f"\nFirebase now has: {stats['total_questions']} questions")
        print(f"By school: {stats['by_school']}")

    if args.upload_images or args.images_only:
        migrate_images()

    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
