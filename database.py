"""
SQLite database schema and operations for P6 Math Question Bank.
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from config import DATABASE_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school TEXT NOT NULL,
    year INTEGER NOT NULL,
    paper_section TEXT NOT NULL,  -- P1A, P1B, P2
    question_num INTEGER NOT NULL,
    part_letter TEXT DEFAULT '',  -- 'a', 'b', 'c', or '' for non-multi-part questions
    pdf_question_num INTEGER,     -- Original question number from PDF (e.g., 16 for P1B Q1)
    pdf_page_num INTEGER,         -- PDF page number where question appears
    marks INTEGER NOT NULL,
    latex_text TEXT NOT NULL,     -- Part-specific question text
    main_context TEXT,            -- Shared problem context for multi-part questions
    diagram_description TEXT,
    image_path TEXT NOT NULL,
    options TEXT,                  -- JSON for MCQ: {"A":"...", "B":"..."}
    answer TEXT,                   -- Final answer only
    worked_solution TEXT,          -- Full working steps
    answer_diagram_description TEXT, -- For diagram-based answers
    topic_tags TEXT,               -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(school, year, paper_section, question_num, part_letter)
);

CREATE INDEX IF NOT EXISTS idx_school ON questions(school);
CREATE INDEX IF NOT EXISTS idx_year ON questions(year);
CREATE INDEX IF NOT EXISTS idx_section ON questions(paper_section);
CREATE INDEX IF NOT EXISTS idx_marks ON questions(marks);
CREATE INDEX IF NOT EXISTS idx_part ON questions(part_letter);
"""


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database with schema."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)
    print(f"Database initialized at {DATABASE_PATH}")


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
    answer_diagram_description: Optional[str] = None,
    topic_tags: Optional[List[str]] = None,
    pdf_question_num: Optional[int] = None,
    pdf_page_num: Optional[int] = None,
    part_letter: Optional[str] = None,
    main_context: Optional[str] = None,
) -> int:
    """Insert a question into the database.

    Args:
        pdf_question_num: Original question number from PDF (e.g., 16 for P1B Q1)
        pdf_page_num: PDF page number where question appears
        part_letter: 'a', 'b', 'c', etc. for multi-part questions, or None
        main_context: Shared problem context for multi-part questions
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR REPLACE INTO questions (
                school, year, paper_section, question_num, part_letter, pdf_question_num, pdf_page_num,
                marks, latex_text, main_context, diagram_description, image_path, options,
                answer, worked_solution, answer_diagram_description, topic_tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                school,
                year,
                paper_section,
                question_num,
                part_letter or '',  # Use empty string instead of None
                pdf_question_num if pdf_question_num is not None else question_num,
                pdf_page_num,
                marks,
                latex_text,
                main_context,
                diagram_description,
                str(image_path),
                json.dumps(options) if options else None,
                answer,
                worked_solution,
                answer_diagram_description,
                json.dumps(topic_tags) if topic_tags else None,
            ),
        )
        return cursor.lastrowid


def get_question(
    school: str, year: int, paper_section: str, question_num: int,
    part_letter: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get a specific question.

    Args:
        part_letter: 'a', 'b', 'c', etc. for multi-part questions, or None/''
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM questions
            WHERE school = ? AND year = ? AND paper_section = ? AND question_num = ? AND part_letter = ?
            """,
            (school, year, paper_section, question_num, part_letter or ''),
        ).fetchone()
        return _row_to_dict(row) if row else None


def get_question_parts(
    school: str, year: int, paper_section: str, question_num: int
) -> List[Dict[str, Any]]:
    """Get all parts of a multi-part question.

    Returns list of question dicts, one for each part (a, b, c, etc.)
    or a single-item list if the question has no parts.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM questions
            WHERE school = ? AND year = ? AND paper_section = ? AND question_num = ?
            ORDER BY COALESCE(part_letter, '')
            """,
            (school, year, paper_section, question_num),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]


def get_questions(
    school: Optional[str] = None,
    year: Optional[int] = None,
    paper_section: Optional[str] = None,
    marks: Optional[int] = None,
    topic_tag: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query questions with filters."""
    query = "SELECT * FROM questions WHERE 1=1"
    params = []

    if school:
        query += " AND school = ?"
        params.append(school)
    if year:
        query += " AND year = ?"
        params.append(year)
    if paper_section:
        query += " AND paper_section = ?"
        params.append(paper_section)
    if marks:
        query += " AND marks = ?"
        params.append(marks)
    if topic_tag:
        query += " AND topic_tags LIKE ?"
        params.append(f"%{topic_tag}%")

    # Sort by school, year, then section ASCENDING (P1A→P1B→P2), then question number
    query += """ ORDER BY school, year,
        CASE paper_section
            WHEN 'P1A' THEN 1
            WHEN 'P1B' THEN 2
            WHEN 'P2' THEN 3
            ELSE 4
        END,
        question_num, COALESCE(part_letter, '')"""

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(row) for row in rows]


def get_all_schools() -> List[str]:
    """Get list of all schools in database."""
    with get_connection() as conn:
        rows = conn.execute("SELECT DISTINCT school FROM questions ORDER BY school").fetchall()
        return [row["school"] for row in rows]


def get_all_years() -> List[int]:
    """Get list of all years in database."""
    with get_connection() as conn:
        rows = conn.execute("SELECT DISTINCT year FROM questions ORDER BY year DESC").fetchall()
        return [row["year"] for row in rows]


def get_statistics() -> Dict[str, Any]:
    """Get database statistics."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) as count FROM questions").fetchone()["count"]
        by_school = conn.execute(
            "SELECT school, COUNT(*) as count FROM questions GROUP BY school"
        ).fetchall()
        by_section = conn.execute(
            "SELECT paper_section, COUNT(*) as count FROM questions GROUP BY paper_section"
        ).fetchall()
        by_marks = conn.execute(
            "SELECT marks, COUNT(*) as count FROM questions GROUP BY marks ORDER BY marks"
        ).fetchall()

        return {
            "total_questions": total,
            "by_school": {row["school"]: row["count"] for row in by_school},
            "by_section": {row["paper_section"]: row["count"] for row in by_section},
            "by_marks": {row["marks"]: row["count"] for row in by_marks},
        }


def update_answer(
    school: str,
    year: int,
    paper_section: str,
    question_num: int,
    answer: str,
    worked_solution: Optional[str] = None,
    answer_diagram_description: Optional[str] = None,
    overwrite: bool = False,
    part_letter: Optional[str] = None,
) -> bool:
    """Update answer fields for a question.

    Args:
        overwrite: If False, only update if no answer exists yet.
                   If True, always overwrite existing answer.
        part_letter: 'a', 'b', 'c', etc. for multi-part questions, or None/''
    """
    with get_connection() as conn:
        # Use empty string for part_letter if None
        part = part_letter or ''
        params_base = (school, year, paper_section, question_num, part)

        # Check if answer already exists (unless overwrite is True)
        if not overwrite:
            existing = conn.execute(
                """
                SELECT answer FROM questions
                WHERE school = ? AND year = ? AND paper_section = ? AND question_num = ? AND part_letter = ?
                """,
                params_base,
            ).fetchone()

            if existing and existing["answer"]:
                # Answer already exists, don't overwrite
                return False

        cursor = conn.execute(
            """
            UPDATE questions
            SET answer = ?, worked_solution = ?, answer_diagram_description = ?
            WHERE school = ? AND year = ? AND paper_section = ? AND question_num = ? AND part_letter = ?
            """,
            (answer, worked_solution, answer_diagram_description) + params_base,
        )
        return cursor.rowcount > 0


def update_question_text(
    school: str,
    year: int,
    paper_section: str,
    question_num: int,
    latex_text: str,
    main_context: Optional[str] = None,
    part_letter: Optional[str] = None,
) -> bool:
    """Update question text fields.

    Args:
        latex_text: The part-specific question text
        main_context: Shared problem context for multi-part questions
        part_letter: 'a', 'b', 'c', etc. for multi-part questions, or None/''
    """
    with get_connection() as conn:
        part = part_letter or ''
        cursor = conn.execute(
            """
            UPDATE questions
            SET latex_text = ?, main_context = ?
            WHERE school = ? AND year = ? AND paper_section = ?
            AND question_num = ? AND part_letter = ?
            """,
            (latex_text, main_context, school, year, paper_section, question_num, part),
        )
        return cursor.rowcount > 0


def update_question_metadata(
    question_id: int,
    marks: Optional[int] = None,
    question_num: Optional[int] = None,
    paper_section: Optional[str] = None,
    pdf_question_num: Optional[int] = None,
) -> bool:
    """Update question metadata (marks, question_num, paper_section).

    Args:
        question_id: The database ID of the question
        marks: New marks value (optional)
        question_num: New question number (optional)
        paper_section: New paper section P1A/P1B/P2 (optional)
        pdf_question_num: New PDF question number for display (optional)
    """
    with get_connection() as conn:
        # Build dynamic update query
        updates = []
        params = []

        if marks is not None:
            updates.append("marks = ?")
            params.append(marks)
        if question_num is not None:
            updates.append("question_num = ?")
            params.append(question_num)
        if paper_section is not None:
            updates.append("paper_section = ?")
            params.append(paper_section)
        if pdf_question_num is not None:
            updates.append("pdf_question_num = ?")
            params.append(pdf_question_num)

        if not updates:
            return False

        params.append(question_id)
        query = f"UPDATE questions SET {', '.join(updates)} WHERE id = ?"

        cursor = conn.execute(query, params)
        return cursor.rowcount > 0


def delete_question(
    school: str, year: int, paper_section: str, question_num: int,
    part_letter: Optional[str] = None
) -> bool:
    """Delete a question from the database.

    Args:
        part_letter: 'a', 'b', 'c', etc. for multi-part questions, or None.
                     If None, deletes all parts of the question.
    """
    with get_connection() as conn:
        if part_letter:
            cursor = conn.execute(
                """
                DELETE FROM questions
                WHERE school = ? AND year = ? AND paper_section = ? AND question_num = ? AND part_letter = ?
                """,
                (school, year, paper_section, question_num, part_letter),
            )
        else:
            cursor = conn.execute(
                """
                DELETE FROM questions
                WHERE school = ? AND year = ? AND paper_section = ? AND question_num = ?
                """,
                (school, year, paper_section, question_num),
            )
        return cursor.rowcount > 0


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a database row to a dictionary with parsed JSON fields."""
    d = dict(row)
    if d.get("options"):
        d["options"] = json.loads(d["options"])
    if d.get("topic_tags"):
        d["topic_tags"] = json.loads(d["topic_tags"])
    return d


def cleanup_question_text():
    """Clean up common extraction artifacts in existing question text."""
    import re

    with get_connection() as conn:
        rows = conn.execute("SELECT id, latex_text FROM questions").fetchall()
        updated = 0

        for row in rows:
            original = row["latex_text"]
            cleaned = original

            # Remove "(a) None" or "(a): None" patterns
            cleaned = re.sub(r'\n?\s*\([a-z]\)\s*:?\s*None\s*', '', cleaned, flags=re.IGNORECASE)

            # Remove standalone "None" lines
            cleaned = re.sub(r'^\s*None\s*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)

            # Fix missing spaces after periods
            cleaned = re.sub(r'\.([A-Z])', r'. \1', cleaned)

            # Clean up whitespace
            cleaned = re.sub(r'[ \t]+', ' ', cleaned)
            cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

            # Clean up lines
            lines = [line.strip() for line in cleaned.split('\n')]
            cleaned = '\n'.join(lines).strip()

            if cleaned != original:
                conn.execute(
                    "UPDATE questions SET latex_text = ? WHERE id = ?",
                    (cleaned, row["id"])
                )
                updated += 1

        print(f"Cleaned up {updated} question texts")
        return updated


if __name__ == "__main__":
    init_db()
    print("Database schema created successfully.")
    stats = get_statistics()
    print(f"Current statistics: {stats}")
