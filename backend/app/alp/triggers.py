DIRECT_CAUSE_MARKERS = (
    "confirmed a failed",
    "documented root intrusion",
    "documented water infiltration",
    "documented heat damage",
    "observed a corroded",
    "found a longitudinal break",
)


def direct_cause_sentence(notes: list[str]) -> str | None:
    for note in notes:
        for sentence in note.split("."):
            if any(marker in sentence.lower() for marker in DIRECT_CAUSE_MARKERS):
                return f"{sentence.strip()}."
    return None
