"""
Firebase database and storage operations for P6 Math Question Bank.

Replaces SQLite with Firebase Firestore for data and Firebase Storage for images.
"""

import os
import json
import base64
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore, storage

# Initialize Firebase
_firebase_app = None
_db = None
_bucket = None


def _get_credentials():
    """Get Firebase credentials from file or Streamlit secrets."""
    # Try local file first
    key_path = Path(__file__).parent / "firebase-key.json"
    if key_path.exists():
        return credentials.Certificate(str(key_path))

    # Try Streamlit secrets (for cloud deployment)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'firebase' in st.secrets:
            cred_dict = dict(st.secrets['firebase'])
            # Handle private key newlines
            if 'private_key' in cred_dict:
                cred_dict['private_key'] = cred_dict['private_key'].replace('\\n', '\n')
            return credentials.Certificate(cred_dict)
    except Exception:
        pass

    # Try environment variable
    if os.environ.get('FIREBASE_CREDENTIALS'):
        cred_dict = json.loads(os.environ['FIREBASE_CREDENTIALS'])
        return credentials.Certificate(cred_dict)

    raise ValueError(
        "Firebase credentials not found. Provide firebase-key.json, "
        "set FIREBASE_CREDENTIALS env var, or configure Streamlit secrets."
    )


def init_firebase():
    """Initialize Firebase app, Firestore, and Storage."""
    global _firebase_app, _db, _bucket

    if _firebase_app is not None:
        return _db, _bucket

    cred = _get_credentials()
    _firebase_app = firebase_admin.initialize_app(cred, {
        'storageBucket': 'p6-math-question-bank.firebasestorage.app'
    })

    _db = firestore.client()
    _bucket = storage.bucket()

    print("Firebase initialized successfully")
    return _db, _bucket


def get_db():
    """Get Firestore client."""
    global _db
    if _db is None:
        init_firebase()
    return _db


def get_bucket():
    """Get Storage bucket."""
    global _bucket
    if _bucket is None:
        init_firebase()
    return _bucket


# ============================================================================
# QUESTION OPERATIONS (Firestore)
# ============================================================================

def _question_to_doc(question: Dict[str, Any]) -> Dict[str, Any]:
    """Convert question dict to Firestore document format."""
    doc = {**question}
    # Convert options dict to JSON string if present
    if doc.get('options') and isinstance(doc['options'], dict):
        doc['options'] = json.dumps(doc['options'])
    if doc.get('topic_tags') and isinstance(doc['topic_tags'], list):
        doc['topic_tags'] = json.dumps(doc['topic_tags'])
    # Add timestamp
    doc['updated_at'] = firestore.SERVER_TIMESTAMP
    return doc


def _doc_to_question(doc) -> Dict[str, Any]:
    """Convert Firestore document to question dict."""
    data = doc.to_dict()
    data['id'] = doc.id
    # Parse JSON fields
    if data.get('options') and isinstance(data['options'], str):
        try:
            data['options'] = json.loads(data['options'])
        except json.JSONDecodeError:
            pass
    if data.get('topic_tags') and isinstance(data['topic_tags'], str):
        try:
            data['topic_tags'] = json.loads(data['topic_tags'])
        except json.JSONDecodeError:
            pass
    return data


def insert_question(
    school: str,
    year: int,
    paper_section: str,
    question_num: int,
    marks: int,
    latex_text: str,
    image_path: str,
    diagram_description: Optional[str] = None,
    options: Optional[Dict[str, str]] = None,
    answer: Optional[str] = None,
    worked_solution: Optional[str] = None,
    question_diagram: Optional[str] = None,
    topic_tags: Optional[List[str]] = None,
    pdf_question_num: Optional[int] = None,
    pdf_page_num: Optional[int] = None,
    part_letter: Optional[str] = None,
    main_context: Optional[str] = None,
) -> str:
    """Insert a question into Firestore. Returns document ID."""
    db = get_db()

    # Create unique document ID
    doc_id = f"{school}_{year}_{paper_section}_{question_num}"
    if part_letter:
        doc_id += f"_{part_letter}"
    doc_id = doc_id.replace(" ", "_")

    doc_data = {
        'school': school,
        'year': year,
        'paper_section': paper_section,
        'question_num': question_num,
        'part_letter': part_letter or '',
        'pdf_question_num': pdf_question_num or question_num,
        'pdf_page_num': pdf_page_num,
        'marks': marks,
        'latex_text': latex_text,
        'main_context': main_context,
        'diagram_description': diagram_description,
        'image_path': image_path,
        'options': json.dumps(options) if options else None,
        'answer': answer,
        'worked_solution': worked_solution,
        'question_diagram': question_diagram,
        'topic_tags': json.dumps(topic_tags) if topic_tags else None,
        'created_at': firestore.SERVER_TIMESTAMP,
        'updated_at': firestore.SERVER_TIMESTAMP,
    }

    db.collection('questions').document(doc_id).set(doc_data)
    return doc_id


def get_question(
    school: str, year: int, paper_section: str, question_num: int,
    part_letter: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get a specific question."""
    db = get_db()

    doc_id = f"{school}_{year}_{paper_section}_{question_num}"
    if part_letter:
        doc_id += f"_{part_letter}"
    doc_id = doc_id.replace(" ", "_")

    doc = db.collection('questions').document(doc_id).get()
    if doc.exists:
        return _doc_to_question(doc)
    return None


def get_questions(
    school: Optional[str] = None,
    year: Optional[int] = None,
    paper_section: Optional[str] = None,
    marks: Optional[int] = None,
    topic_tag: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query questions with filters."""
    db = get_db()

    query = db.collection('questions')

    if school:
        query = query.where('school', '==', school)
    if year:
        query = query.where('year', '==', year)
    if paper_section:
        query = query.where('paper_section', '==', paper_section)
    if marks:
        query = query.where('marks', '==', marks)

    docs = query.stream()
    questions = [_doc_to_question(doc) for doc in docs]

    # Filter by topic_tag in Python (Firestore doesn't support array-contains on JSON string)
    if topic_tag:
        questions = [q for q in questions if topic_tag in str(q.get('topic_tags', ''))]

    # Sort: P1A -> P1B -> P2, then by question_num
    section_order = {'P1A': 1, 'P1B': 2, 'P2': 3}
    questions.sort(key=lambda q: (
        q.get('school', ''),
        q.get('year', 0),
        section_order.get(q.get('paper_section', ''), 4),
        q.get('question_num', 0),
        q.get('part_letter', '')
    ))

    return questions


def get_all_schools() -> List[str]:
    """Get list of all schools in database."""
    db = get_db()
    docs = db.collection('questions').stream()
    schools = set(doc.to_dict().get('school') for doc in docs)
    return sorted([s for s in schools if s])


def get_all_years() -> List[int]:
    """Get list of all years in database."""
    db = get_db()
    docs = db.collection('questions').stream()
    years = set(doc.to_dict().get('year') for doc in docs)
    return sorted([y for y in years if y], reverse=True)


def get_statistics() -> Dict[str, Any]:
    """Get database statistics."""
    db = get_db()
    docs = list(db.collection('questions').stream())

    by_school = {}
    by_section = {}
    by_marks = {}

    for doc in docs:
        data = doc.to_dict()
        school = data.get('school', 'Unknown')
        section = data.get('paper_section', 'Unknown')
        marks = data.get('marks', 0)

        by_school[school] = by_school.get(school, 0) + 1
        by_section[section] = by_section.get(section, 0) + 1
        by_marks[marks] = by_marks.get(marks, 0) + 1

    return {
        'total_questions': len(docs),
        'by_school': by_school,
        'by_section': by_section,
        'by_marks': by_marks,
    }


def update_answer(
    school: str,
    year: int,
    paper_section: str,
    question_num: int,
    answer: str,
    worked_solution: Optional[str] = None,
    question_diagram: Optional[str] = None,
    overwrite: bool = False,
    part_letter: Optional[str] = None,
) -> bool:
    """Update answer fields for a question."""
    db = get_db()

    doc_id = f"{school}_{year}_{paper_section}_{question_num}"
    if part_letter:
        doc_id += f"_{part_letter}"
    doc_id = doc_id.replace(" ", "_")

    doc_ref = db.collection('questions').document(doc_id)
    doc = doc_ref.get()

    if not doc.exists:
        return False

    # Check if answer exists (unless overwrite)
    if not overwrite:
        existing = doc.to_dict()
        if existing.get('answer'):
            return False

    update_data = {
        'answer': answer,
        'updated_at': firestore.SERVER_TIMESTAMP,
    }
    if worked_solution is not None:
        update_data['worked_solution'] = worked_solution
    if question_diagram is not None:
        update_data['question_diagram'] = question_diagram

    doc_ref.update(update_data)
    return True


def update_question_text(
    school: str,
    year: int,
    paper_section: str,
    question_num: int,
    latex_text: str,
    main_context: Optional[str] = None,
    part_letter: Optional[str] = None,
) -> bool:
    """Update question text fields."""
    db = get_db()

    doc_id = f"{school}_{year}_{paper_section}_{question_num}"
    if part_letter:
        doc_id += f"_{part_letter}"
    doc_id = doc_id.replace(" ", "_")

    doc_ref = db.collection('questions').document(doc_id)

    update_data = {
        'latex_text': latex_text,
        'updated_at': firestore.SERVER_TIMESTAMP,
    }
    if main_context is not None:
        update_data['main_context'] = main_context

    try:
        doc_ref.update(update_data)
        return True
    except Exception:
        return False


def update_question_metadata(
    question_id: str,
    marks: Optional[int] = None,
    question_num: Optional[int] = None,
    paper_section: Optional[str] = None,
    pdf_question_num: Optional[int] = None,
) -> bool:
    """Update question metadata."""
    db = get_db()

    doc_ref = db.collection('questions').document(question_id)

    update_data = {'updated_at': firestore.SERVER_TIMESTAMP}
    if marks is not None:
        update_data['marks'] = marks
    if question_num is not None:
        update_data['question_num'] = question_num
    if paper_section is not None:
        update_data['paper_section'] = paper_section
    if pdf_question_num is not None:
        update_data['pdf_question_num'] = pdf_question_num

    try:
        doc_ref.update(update_data)
        return True
    except Exception:
        return False


def delete_question(
    school: str, year: int, paper_section: str, question_num: int,
    part_letter: Optional[str] = None
) -> bool:
    """Delete a question."""
    db = get_db()

    doc_id = f"{school}_{year}_{paper_section}_{question_num}"
    if part_letter:
        doc_id += f"_{part_letter}"
    doc_id = doc_id.replace(" ", "_")

    try:
        db.collection('questions').document(doc_id).delete()
        return True
    except Exception:
        return False


# ============================================================================
# IMAGE OPERATIONS (Firebase Storage)
# ============================================================================

def upload_image(local_path: str, storage_path: str) -> str:
    """
    Upload an image to Firebase Storage.

    Args:
        local_path: Local file path
        storage_path: Path in Firebase Storage (e.g., 'images/school_2025_p01.png')

    Returns:
        Public URL of the uploaded image
    """
    bucket = get_bucket()
    blob = bucket.blob(storage_path)
    blob.upload_from_filename(local_path)
    blob.make_public()
    return blob.public_url


def upload_image_bytes(image_bytes, storage_path: str, content_type: str = 'image/png') -> str:
    """
    Upload image bytes to Firebase Storage.

    Args:
        image_bytes: Image data as bytes, memoryview, or BytesIO
        storage_path: Path in Firebase Storage
        content_type: MIME type of the image

    Returns:
        Public URL of the uploaded image
    """
    bucket = get_bucket()
    blob = bucket.blob(storage_path)

    # Convert to bytes if needed
    if hasattr(image_bytes, 'tobytes'):
        # memoryview
        image_bytes = image_bytes.tobytes()
    elif hasattr(image_bytes, 'read'):
        # file-like object (BytesIO)
        image_bytes = image_bytes.read()
    elif not isinstance(image_bytes, bytes):
        # Try direct conversion as last resort
        image_bytes = bytes(image_bytes)

    blob.upload_from_string(image_bytes, content_type=content_type)
    blob.make_public()
    return blob.public_url


def get_image_url(storage_path: str) -> Optional[str]:
    """Get public URL for an image in Firebase Storage."""
    bucket = get_bucket()
    blob = bucket.blob(storage_path)
    if blob.exists():
        return blob.public_url
    return None


def delete_image(storage_path: str) -> bool:
    """Delete an image from Firebase Storage."""
    bucket = get_bucket()
    blob = bucket.blob(storage_path)
    try:
        blob.delete()
        return True
    except Exception:
        return False


def list_images(prefix: str = 'images/') -> List[str]:
    """List all images in Firebase Storage with given prefix."""
    bucket = get_bucket()
    blobs = bucket.list_blobs(prefix=prefix)
    return [blob.name for blob in blobs]


# ============================================================================
# MIGRATION HELPER
# ============================================================================

def migrate_from_sqlite(sqlite_path: str, upload_images: bool = False):
    """
    Migrate data from SQLite database to Firebase.

    Args:
        sqlite_path: Path to SQLite database
        upload_images: If True, also upload images to Firebase Storage
    """
    import sqlite3

    print(f"Migrating from {sqlite_path}...")

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all questions
    cursor.execute("SELECT * FROM questions")
    rows = cursor.fetchall()

    print(f"Found {len(rows)} questions to migrate")

    db = get_db()
    batch = db.batch()
    batch_count = 0

    for i, row in enumerate(rows):
        data = dict(row)

        # Create document ID
        doc_id = f"{data['school']}_{data['year']}_{data['paper_section']}_{data['question_num']}"
        if data.get('part_letter'):
            doc_id += f"_{data['part_letter']}"
        doc_id = doc_id.replace(" ", "_")

        # Remove SQLite id field
        if 'id' in data:
            del data['id']

        # Handle None values
        for key, value in data.items():
            if value is None:
                data[key] = None

        # Ensure part_letter is string
        if data.get('part_letter') is None:
            data['part_letter'] = ''

        doc_ref = db.collection('questions').document(doc_id)
        batch.set(doc_ref, data)
        batch_count += 1

        # Commit batch every 500 documents
        if batch_count >= 500:
            batch.commit()
            print(f"  Committed {i + 1} documents...")
            batch = db.batch()
            batch_count = 0

    # Commit remaining
    if batch_count > 0:
        batch.commit()

    print(f"Migration complete! {len(rows)} questions migrated to Firebase.")
    conn.close()


# For backwards compatibility - init on import
def init_db():
    """Initialize Firebase (backwards compatible with SQLite interface)."""
    init_firebase()
    print("Firebase database ready")


if __name__ == "__main__":
    # Test connection
    print("Testing Firebase connection...")
    init_firebase()
    stats = get_statistics()
    print(f"Connected! Questions in database: {stats['total_questions']}")
