#!/usr/bin/env python3
"""
validate_extraction.py - Automated validation of extracted questions

Checks for common extraction errors:
1. Missing questions (gaps in sequence)
2. Invalid question numbers (Q0, duplicates)
3. Duplicate multi-part answers
4. Suspicious answer text
5. Section count validation

Usage:
    python validate_extraction.py                    # Validate all schools
    python validate_extraction.py --school "Ai Tong" # Validate one school
    python validate_extraction.py --fix              # Auto-fix with AI (requires API key)
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent))

from database import get_questions, get_all_schools

# Expected question counts per section
EXPECTED_COUNTS = {
    "P1A": 15,  # Q1-Q15 MCQ
    "P1B": 15,  # Q16-Q30 (stored as Q1-Q15)
    "P2": 17,   # Q1-Q17 (varies by school, 15-18)
}

# Suspicious answer patterns
SUSPICIOUS_PATTERNS = [
    r"blank\s*page",
    r"no\s*(answer|question)",
    r"see\s*(image|attached|solution)",
    r"cannot\s*(identify|read)",
    r"image\s*(is|too)\s*(unclear|blurry)",
    r"sorry",
    r"there is no",
]


@dataclass
class ValidationIssue:
    """A validation issue found in the data."""
    school: str
    section: str
    question_num: int
    part_letter: Optional[str]
    issue_type: str
    description: str
    severity: str  # "error", "warning"
    question_id: Optional[int] = None


def check_question_sequence(questions: List[dict], section: str) -> List[ValidationIssue]:
    """Check for missing or duplicate question numbers."""
    issues = []

    # Group by question_num (ignoring parts)
    seen_nums = {}
    for q in questions:
        qnum = q['question_num']
        if qnum not in seen_nums:
            seen_nums[qnum] = []
        seen_nums[qnum].append(q)

    # Check for Q0 (invalid)
    if 0 in seen_nums:
        for q in seen_nums[0]:
            issues.append(ValidationIssue(
                school=q['school'],
                section=section,
                question_num=0,
                part_letter=q.get('part_letter'),
                issue_type="invalid_qnum",
                description=f"Q0 is invalid - likely wrong question number detected. Page {q.get('pdf_page_num')}",
                severity="error",
                question_id=q['id']
            ))

    # Check for gaps in sequence
    expected_range = range(1, EXPECTED_COUNTS.get(section, 15) + 1)
    actual_nums = set(seen_nums.keys()) - {0}

    missing = set(expected_range) - actual_nums
    if missing and len(missing) <= 5:  # Only report if not too many missing
        for m in sorted(missing):
            issues.append(ValidationIssue(
                school=questions[0]['school'] if questions else "Unknown",
                section=section,
                question_num=m,
                part_letter=None,
                issue_type="missing_question",
                description=f"Q{m} is missing from {section}",
                severity="warning"
            ))

    # Check for unexpected high numbers (wrong section?)
    for qnum in actual_nums:
        if section == "P1B" and qnum > 15:
            issues.append(ValidationIssue(
                school=questions[0]['school'],
                section=section,
                question_num=qnum,
                part_letter=None,
                issue_type="wrong_section",
                description=f"Q{qnum} in P1B should be Q{qnum-15} (stored) or might belong to P2",
                severity="warning"
            ))

    return issues


def check_multipart_duplicates(questions: List[dict]) -> List[ValidationIssue]:
    """Check if multi-part questions have identical answers (likely extraction error)."""
    issues = []

    # Group by (section, question_num)
    grouped = {}
    for q in questions:
        key = (q['paper_section'], q['question_num'])
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(q)

    for (section, qnum), parts in grouped.items():
        if len(parts) > 1:  # Multi-part question
            answers = [q.get('answer', '') for q in parts]
            # Check if all non-empty answers are identical
            non_empty = [a for a in answers if a and a.strip()]
            if len(non_empty) > 1 and len(set(non_empty)) == 1:
                issues.append(ValidationIssue(
                    school=parts[0]['school'],
                    section=section,
                    question_num=qnum,
                    part_letter=None,
                    issue_type="duplicate_multipart_answer",
                    description=f"Q{qnum} parts all have same answer: '{non_empty[0][:50]}...'",
                    severity="error",
                    question_id=parts[0]['id']
                ))

    return issues


def check_suspicious_answers(questions: List[dict]) -> List[ValidationIssue]:
    """Check for suspicious answer text that indicates extraction failure."""
    issues = []

    for q in questions:
        answer = q.get('answer', '') or ''
        text = q.get('latex_text', '') or ''

        # Check answer
        for pattern in SUSPICIOUS_PATTERNS:
            if re.search(pattern, answer, re.IGNORECASE):
                issues.append(ValidationIssue(
                    school=q['school'],
                    section=q['paper_section'],
                    question_num=q['question_num'],
                    part_letter=q.get('part_letter'),
                    issue_type="suspicious_answer",
                    description=f"Suspicious answer: '{answer[:80]}...'",
                    severity="error",
                    question_id=q['id']
                ))
                break

        # Check if question text mentions "BLANK PAGE"
        if re.search(r"blank\s*page", text, re.IGNORECASE):
            issues.append(ValidationIssue(
                school=q['school'],
                section=q['paper_section'],
                question_num=q['question_num'],
                part_letter=q.get('part_letter'),
                issue_type="blank_page_question",
                description=f"Question text contains 'BLANK PAGE' - likely wrong page",
                severity="error",
                question_id=q['id']
            ))

    return issues


def check_section_counts(questions: List[dict], school: str) -> List[ValidationIssue]:
    """Check if each section has reasonable question count."""
    issues = []

    by_section = {}
    for q in questions:
        sec = q['paper_section']
        if sec not in by_section:
            by_section[sec] = set()
        by_section[sec].add(q['question_num'])

    for section, expected in EXPECTED_COUNTS.items():
        actual = len(by_section.get(section, set()))
        if actual == 0:
            issues.append(ValidationIssue(
                school=school,
                section=section,
                question_num=0,
                part_letter=None,
                issue_type="missing_section",
                description=f"No questions found for {section}",
                severity="error"
            ))
        elif actual < expected - 3:  # Allow some variance
            issues.append(ValidationIssue(
                school=school,
                section=section,
                question_num=0,
                part_letter=None,
                issue_type="low_question_count",
                description=f"{section} has only {actual} questions (expected ~{expected})",
                severity="warning"
            ))

    return issues


def validate_school(school: str) -> List[ValidationIssue]:
    """Run all validations for a school."""
    questions = get_questions(school=school)
    if not questions:
        return [ValidationIssue(
            school=school,
            section="ALL",
            question_num=0,
            part_letter=None,
            issue_type="no_data",
            description=f"No questions found for {school}",
            severity="error"
        )]

    all_issues = []

    # Group by section
    by_section = {}
    for q in questions:
        sec = q['paper_section']
        if sec not in by_section:
            by_section[sec] = []
        by_section[sec].append(q)

    # Run checks
    for section, section_questions in by_section.items():
        all_issues.extend(check_question_sequence(section_questions, section))

    all_issues.extend(check_multipart_duplicates(questions))
    all_issues.extend(check_suspicious_answers(questions))
    all_issues.extend(check_section_counts(questions, school))

    return all_issues


def print_issues(issues: List[ValidationIssue], school: str):
    """Print validation issues in a readable format."""
    if not issues:
        print(f"\n✓ {school}: No issues found")
        return

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    print(f"\n{'='*60}")
    print(f"{school}: {len(errors)} errors, {len(warnings)} warnings")
    print('='*60)

    if errors:
        print("\n🔴 ERRORS:")
        for issue in errors:
            part = f"({issue.part_letter})" if issue.part_letter else ""
            print(f"  [{issue.section} Q{issue.question_num}{part}] {issue.issue_type}")
            print(f"     {issue.description}")

    if warnings:
        print("\n🟡 WARNINGS:")
        for issue in warnings:
            part = f"({issue.part_letter})" if issue.part_letter else ""
            print(f"  [{issue.section} Q{issue.question_num}{part}] {issue.issue_type}")
            print(f"     {issue.description}")


def generate_fix_report(issues: List[ValidationIssue]) -> str:
    """Generate a report of issues that need manual fixing."""
    report = []
    report.append("# Extraction Issues Report\n")

    # Group by school
    by_school = {}
    for issue in issues:
        if issue.school not in by_school:
            by_school[issue.school] = []
        by_school[issue.school].append(issue)

    for school, school_issues in by_school.items():
        report.append(f"\n## {school}\n")

        errors = [i for i in school_issues if i.severity == "error"]
        if errors:
            report.append("### Errors (need fixing)\n")
            for issue in errors:
                part = f"({issue.part_letter})" if issue.part_letter else ""
                report.append(f"- **{issue.section} Q{issue.question_num}{part}**: {issue.description}")

        warnings = [i for i in school_issues if i.severity == "warning"]
        if warnings:
            report.append("\n### Warnings\n")
            for issue in warnings:
                part = f"({issue.part_letter})" if issue.part_letter else ""
                report.append(f"- {issue.section} Q{issue.question_num}{part}: {issue.description}")

    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description="Validate extracted questions")
    parser.add_argument("--school", type=str, help="Validate specific school only")
    parser.add_argument("--report", action="store_true", help="Generate markdown report")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    print("="*60)
    print("EXTRACTION VALIDATION")
    print("="*60)

    if args.school:
        schools = [args.school]
    else:
        schools = get_all_schools()

    all_issues = []
    for school in schools:
        issues = validate_school(school)
        all_issues.extend(issues)
        print_issues(issues, school)

    # Summary
    total_errors = len([i for i in all_issues if i.severity == "error"])
    total_warnings = len([i for i in all_issues if i.severity == "warning"])

    print(f"\n{'='*60}")
    print(f"SUMMARY: {total_errors} errors, {total_warnings} warnings across {len(schools)} schools")
    print("="*60)

    if args.report:
        report = generate_fix_report(all_issues)
        report_path = Path("output/validation_report.md")
        report_path.write_text(report)
        print(f"\nReport saved to: {report_path}")

    # Return exit code based on errors
    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
