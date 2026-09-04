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


def clean_comment(text: str) -> str:
    compact = re.sub(r"\s+", " ", (text or "").strip())
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


def deduplicate_boilerplate(comments: list[str], frequency_threshold: float = 0.08) -> set[str]:
    if not comments:
        return set()
    normalized = [re.sub(r"\W+", " ", comment.lower()).strip() for comment in comments]
    counts: dict[str, int] = {}
    for value in normalized:
        counts[value] = counts.get(value, 0) + 1
    minimum = max(4, int(len(comments) * frequency_threshold))
    return {value for value, count in counts.items() if count >= minimum and len(value) < 120}
