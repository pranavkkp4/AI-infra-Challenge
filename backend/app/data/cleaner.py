import re

BOILERPLATE_PATTERNS = (
    re.compile(r"^work order (created|assigned|closed)( automatically)?[.!]*$", re.I),
    re.compile(r"^status (changed|updated) to .+$", re.I),
    re.compile(r"^dispatched to crew[.!]*$", re.I),
    re.compile(r"^notification sent[.!]*$", re.I),
    re.compile(r"^please advise[.!]*$", re.I),
    re.compile(r"^no comment[.!]*$", re.I),
)
SYSTEM_PREFIXES = ("system:", "auto-generated:", "workflow:")
MEANINGLESS = {"ok", "done", "complete", "completed", "n/a", "na", "test", "none"}
CITYWORKS_SCAFFOLD = (
    re.compile(r"(?is)^\s*from:\s*request id:.*?\bproblem details:\s*"),
    re.compile(r"(?im)^\s*from:\s*request id:.*$"),
    re.compile(r"(?im)^\s*problem details:\s*"),
    re.compile(r"(?im)^\s*problem comments:\s*"),
)
NON_MAINTENANCE_PATTERNS = (
    re.compile(r"\bjanitorial suppl(?:y|ies)\b", re.I),
    re.compile(r"\bsupply order\b", re.I),
    re.compile(r"\b(?:attend(?:ed)?|staff) (?:a )?(?:training|meeting|conference)\b", re.I),
    re.compile(r"\btraining (?:class|course|session)\b", re.I),
)


def clean_comment(text: str) -> str:
    stripped = text or ""
    for pattern in CITYWORKS_SCAFFOLD:
        stripped = pattern.sub("", stripped)
    compact = re.sub(r"\s+", " ", stripped.strip())
    if not compact or compact.lower() in MEANINGLESS:
        return ""
    if compact.lower().startswith(SYSTEM_PREFIXES):
        return ""
    if any(pattern.match(compact) for pattern in BOILERPLATE_PATTERNS):
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", compact)
    deduplicated: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        key = re.sub(r"\W+", " ", sentence.lower()).strip()
        if (
            key
            and key not in seen
            and not any(pattern.match(sentence) for pattern in BOILERPLATE_PATTERNS)
        ):
            seen.add(key)
            deduplicated.append(sentence.strip())
    result = " ".join(deduplicated)
    return result if len(re.sub(r"\W", "", result)) >= 8 else ""


def is_maintenance_comment(text: str) -> bool:
    return bool(text) and not any(pattern.search(text) for pattern in NON_MAINTENANCE_PATTERNS)


def deduplicate_boilerplate(comments: list[str], frequency_threshold: float = 0.08) -> set[str]:
    if not comments:
        return set()
    normalized = [re.sub(r"\W+", " ", comment.lower()).strip() for comment in comments]
    counts: dict[str, int] = {}
    for value in normalized:
        counts[value] = counts.get(value, 0) + 1
    minimum = max(4, int(len(comments) * frequency_threshold))
    return {value for value, count in counts.items() if count >= minimum and len(value) < 120}
