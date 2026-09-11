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
        re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]*\d{3}[-.\s]\d{4}(?!\d)"),
        "[PHONE_REDACTED]",
    ),
    (
        "EMPLOYEE_ID",
        re.compile(
            r"\b(?:employee|emp|badge|tech)\s*(?:id|#|no\.?)?\s*[:#-]?\s*"
            r"[A-Z]{0,3}-?\d{4,8}\b",
            re.I,
        ),
        "[EMPLOYEE_ID_REDACTED]",
    ),
    (
        "PERSON_NAME",
        re.compile(
            r"\bby\s+(?!(?:replac\w*|repair\w*|inspect\w*|check\w*|install\w*|"
            r"patch\w*|clear\w*|reset\w*|seal\w*)\b)"
            r"[a-z][a-z'-]{1,30}(?:\s+[a-z][a-z'-]{1,30})?,\s*"
            r"[a-z][a-z'-]{1,30}(?:\s+[a-z][a-z'-]{1,30})?\s*:",
            re.I,
        ),
        "By [PERSON_REDACTED]:",
    ),
    (
        "PERSON_NAME",
        re.compile(
            r"\b(?:contact|technician|caller|reported by|dispatched to)\s*[:=-]?\s*"
            r"(?!(?:check|replace|repair|inspect|pump|valve|site|work|crew|shop|"
            r"evidence|record|records|note|notes|maintenance|intervention|signal)\b)"
            r"[a-z][a-z'-]+\s+[a-z][a-z'-]+\b",
            re.I,
        ),
        "[PERSON_REDACTED]",
    ),
    (
        "PERSON_NAME",
        re.compile(
            r"\b[A-Z][a-z]{1,24}(?:-[A-Z][a-z]{1,24})?\s+"
            r"[A-Z][a-z]{1,30}(?:'[A-Z][a-z]{1,30})?(?='s\s+(?:office|desk|cubicle|workspace)\b)"
        ),
        "[PERSON_REDACTED]",
    ),
)

EXTERNAL_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "ADDRESS",
        re.compile(
            r"\b\d{1,6}\s+(?:[NESW]\.?(?:\s+|$))?"
            r"(?:[A-Z0-9.'-]+\s+){0,5}"
            r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|"
            r"court|ct|place|pl|parkway|pkwy|highway|hwy|way|circle|cir|terrace|ter)\b"
            r"(?:\s*(?:#|apt|suite|unit)\s*[A-Z0-9-]+)?",
            re.I,
        ),
        "[ADDRESS_REDACTED]",
    ),
    (
        "ADDRESS",
        re.compile(r"\bP\.?\s*O\.?\s+Box\s+\d+[A-Z0-9-]*\b", re.I),
        "[ADDRESS_REDACTED]",
    ),
    (
        "LOCATION",
        re.compile(
            r"\b(?:\d{1,3}(?:st|nd|rd|th)|[A-Z][A-Za-z0-9'-]+\s+"
            r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr))\s*"
            r"(?:&|and)\s*(?:\d{1,3}(?:st|nd|rd|th)|[A-Z][A-Za-z0-9'-]+"
            r"(?:\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr))?)\b"
        ),
        "[LOCATION_REDACTED]",
    ),
    (
        "LOCATION",
        re.compile(
            r"\b(?:ADDRESSES?|CITYFACILITIES|CITY[ _]FACILITIES):[A-Z0-9_-]+\b|"
            r"\b(?:room|suite|office)\s*[#:-]?\s*[A-Z]?\d+[A-Z0-9-]*\b",
            re.I,
        ),
        "[LOCATION_REDACTED]",
    ),
    (
        "COORDINATES",
        re.compile(r"(?<!\d)-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}(?!\d)"),
        "[COORDINATES_REDACTED]",
    ),
)


def redact_pii(text: str) -> RedactionResult:
    return _redact(text, PATTERNS)


def redact_external_identifiers(text: str) -> RedactionResult:
    return _redact(text, PATTERNS + EXTERNAL_PATTERNS)


def _redact(text: str, patterns: tuple[tuple[str, re.Pattern[str], str], ...]) -> RedactionResult:
    redacted = text
    found: list[str] = []
    for entity_type, pattern, replacement in patterns:
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            found.append(entity_type)
    return RedactionResult(redacted, bool(found), tuple(found))
