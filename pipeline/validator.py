"""
Validation utilities for the extraction pipeline.
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

from config import PAPER_SECTIONS


@dataclass
class ValidationResult:
    """Result of validation check."""
    is_valid: bool
    message: str
    details: Dict = field(default_factory=dict)


@dataclass
class DocumentValidation:
    """Complete document validation results."""
    pdf_name: str
    sections_found: List[str] = field(default_factory=list)
    questions_per_section: Dict[str, int] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.issues) == 0


class Validator:
    """Validates extraction results."""

    def __init__(self):
        self.expected_counts = {
            section: info["total_questions"]
            for section, info in PAPER_SECTIONS.items()
        }

    def validate_question_count(
        self, section: str, actual_count: int
    ) -> ValidationResult:
        """
        Validate that extracted question count matches expected.
        """
        expected = self.expected_counts.get(section, 0)

        if actual_count == expected:
            return ValidationResult(
                is_valid=True,
                message=f"{section}: {actual_count} questions (correct)",
            )
        elif actual_count < expected:
            return ValidationResult(
                is_valid=False,
                message=f"{section}: Missing questions - expected {expected}, got {actual_count}",
                details={"missing": expected - actual_count},
            )
        else:
            return ValidationResult(
                is_valid=False,
                message=f"{section}: Extra questions - expected {expected}, got {actual_count}",
                details={"extra": actual_count - expected},
            )

    def validate_marks(
        self, section: str, question_num: int, marks: int
    ) -> ValidationResult:
        """
        Validate that marks assignment is correct for the question.
        """
        if section not in PAPER_SECTIONS:
            return ValidationResult(
                is_valid=False,
                message=f"Unknown section: {section}",
            )

        expected_marks = self._get_expected_marks(section, question_num)

        if expected_marks is None:
            # Variable marks (3-5)
            if 3 <= marks <= 5:
                return ValidationResult(
                    is_valid=True,
                    message=f"Q{question_num}: {marks} marks (valid range)",
                )
            else:
                return ValidationResult(
                    is_valid=False,
                    message=f"Q{question_num}: {marks} marks - expected 3-5",
                )
        else:
            if marks == expected_marks:
                return ValidationResult(
                    is_valid=True,
                    message=f"Q{question_num}: {marks} marks (correct)",
                )
            else:
                return ValidationResult(
                    is_valid=False,
                    message=f"Q{question_num}: {marks} marks - expected {expected_marks}",
                )

    def _get_expected_marks(
        self, section: str, question_num: int
    ) -> Optional[int]:
        """Get expected marks for a question (None if variable)."""
        for range_info in PAPER_SECTIONS[section]["question_ranges"]:
            if range_info["start"] <= question_num <= range_info["end"]:
                return range_info["marks"]
        return None

    def validate_answer_format(
        self, answer: str, question_type: str
    ) -> ValidationResult:
        """
        Validate that answer format is appropriate for question type.
        """
        if not answer:
            return ValidationResult(
                is_valid=False,
                message="Empty answer",
            )

        if question_type == "mcq":
            if answer.upper() in ["A", "B", "C", "D"]:
                return ValidationResult(
                    is_valid=True,
                    message="Valid MCQ answer",
                )
            # Check for option number (1, 2, 3, 4)
            if answer in ["1", "2", "3", "4"]:
                return ValidationResult(
                    is_valid=True,
                    message="Valid MCQ answer (numeric)",
                )
            return ValidationResult(
                is_valid=False,
                message=f"Invalid MCQ answer: {answer}",
            )

        # For other types, just check it's not empty
        return ValidationResult(
            is_valid=True,
            message="Answer present",
        )

    def validate_document(
        self, extraction_results: Dict[str, List]
    ) -> DocumentValidation:
        """
        Validate complete document extraction results.
        """
        validation = DocumentValidation(pdf_name="")

        for section, questions in extraction_results.items():
            validation.sections_found.append(section)
            validation.questions_per_section[section] = len(questions)

            # Check question count
            count_result = self.validate_question_count(section, len(questions))
            if not count_result.is_valid:
                validation.issues.append(count_result.message)

            # Check each question
            for i, question in enumerate(questions):
                question_num = i + 1

                # Validate marks
                if "marks" in question:
                    marks_result = self.validate_marks(
                        section, question_num, question["marks"]
                    )
                    if not marks_result.is_valid:
                        validation.warnings.append(marks_result.message)

                # Check for missing content
                if not question.get("latex_text"):
                    validation.issues.append(
                        f"{section} Q{question_num}: Missing question text"
                    )

        # Check for missing sections
        expected_sections = set(PAPER_SECTIONS.keys())
        found_sections = set(validation.sections_found)
        missing_sections = expected_sections - found_sections

        for section in missing_sections:
            validation.issues.append(f"Missing section: {section}")

        return validation

    def validate_answer_key_coverage(
        self, questions: Dict[str, List], answers: Dict[str, Dict[int, str]]
    ) -> ValidationResult:
        """
        Validate that all questions have corresponding answers.
        """
        missing_answers = []

        for section, question_list in questions.items():
            section_answers = answers.get(section, {})

            for i, _ in enumerate(question_list):
                question_num = i + 1
                if question_num not in section_answers:
                    missing_answers.append(f"{section} Q{question_num}")

        if missing_answers:
            return ValidationResult(
                is_valid=False,
                message=f"Missing answers for: {', '.join(missing_answers[:10])}...",
                details={"missing": missing_answers},
            )

        return ValidationResult(
            is_valid=True,
            message="All questions have answers",
        )


def generate_validation_report(validation: DocumentValidation) -> str:
    """
    Generate a human-readable validation report.
    """
    lines = [
        "=" * 50,
        "VALIDATION REPORT",
        "=" * 50,
        "",
        f"Document: {validation.pdf_name}",
        "",
        "Sections Found:",
    ]

    for section in validation.sections_found:
        count = validation.questions_per_section.get(section, 0)
        expected = PAPER_SECTIONS.get(section, {}).get("total_questions", "?")
        status = "OK" if count == expected else "MISMATCH"
        lines.append(f"  {section}: {count}/{expected} questions [{status}]")

    if validation.issues:
        lines.extend(["", "ISSUES:"])
        for issue in validation.issues:
            lines.append(f"  ! {issue}")

    if validation.warnings:
        lines.extend(["", "WARNINGS:"])
        for warning in validation.warnings:
            lines.append(f"  * {warning}")

    lines.extend([
        "",
        "-" * 50,
        f"Status: {'PASSED' if validation.is_valid else 'FAILED'}",
        "=" * 50,
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    # Test validation
    validator = Validator()

    # Test question count validation
    print("Testing question count validation:")
    print(validator.validate_question_count("P1A", 18))
    print(validator.validate_question_count("P1A", 15))

    # Test marks validation
    print("\nTesting marks validation:")
    print(validator.validate_marks("P1A", 5, 1))
    print(validator.validate_marks("P1A", 15, 2))
    print(validator.validate_marks("P1B", 10, 4))
