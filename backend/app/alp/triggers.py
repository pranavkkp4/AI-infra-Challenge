DIRECT_CAUSE_MARKERS = (
    "caused by",
    "due to",
    "resulted from",
    "root cause was",
)
UNSUPPORTED_CAUSE_PHRASES = (
    "not due to",
    "not caused by",
    "may be due to",
    "might be due to",
    "could be due to",
    "possibly due to",
    "suspected to be due to",
    "delayed due to",
    "delay due to",
    "closing due to",
    "closed due to",
    "cancelled due to",
    "canceled due to",
)


def direct_cause_sentence(notes: list[str]) -> str | None:
    for note in notes:
        for sentence in note.split("."):
            lowered = sentence.lower()
            if any(phrase in lowered for phrase in UNSUPPORTED_CAUSE_PHRASES):
                continue
            if any(marker in lowered for marker in DIRECT_CAUSE_MARKERS):
                return f"{sentence.strip()}."
    return None
