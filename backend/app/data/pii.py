import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RedactionResult:
    text: str
    was_redacted: bool
    entity_types: tuple[str, ...]


PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "EMAIL",
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
        "[EMAIL_REDACTED]",
    ),
    (
        "PHONE",
        re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"),
        "[PHONE_REDACTED]",
    ),
    (
        "EMPLOYEE_ID",
        re.compile(
            r"\b(?:employee|emp|badge|tech)\s*(?:id|#|no\.?)?\s*[:#-]?\s*[A-Z]{0,3}\d{4,8}\b", re.I
        ),
        "[EMPLOYEE_ID_REDACTED]",
    ),
    (
        "PERSON_NAME",
        re.compile(
            r"\b(?:contact|technician|caller|reported by)\s*[:=-]?\s*[A-Z][a-z]+\s+[A-Z][a-z]+\b",
            re.I,
        ),
        "[PERSON_REDACTED]",
    ),
)


def redact_pii(text: str) -> RedactionResult:
    redacted = text
    found: list[str] = []
    for entity_type, pattern, replacement in PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            found.append(entity_type)
    return RedactionResult(redacted, bool(found), tuple(found))
