import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache

from app.models.domain import CanonicalWorkOrder, IssueFamily, TemporalFeatures
from app.retrieval.embeddings import EmbeddingIndex

ISSUE_KEYWORDS: dict[IssueFamily, tuple[str, ...]] = {
    IssueFamily.MAIN_BREAK: (
        "main break",
        "broken main",
        "water main burst",
        "water line break",
        "broke the main",
    ),
    IssueFamily.LOW_PRESSURE: (
        "low pressure",
        "no pressure",
        "pressure dropped",
        "weak flow",
        "no water pressure",
    ),
    IssueFamily.WATER_LEAK: (
        "water leak",
        "leaking",
        "standing water",
        "service line leak",
        "water running",
        "leak at meter",
    ),
    IssueFamily.SEWER_BACKUP: (
        "sewer backup",
        "sewer backups",
        "backed up",
        "back up",
        "stopped up",
        "stop up",
        "stoppage",
        "overflowing sewer",
        "blocked sewer",
        "roots in line",
        "grease in line",
        "jetted line",
        "line cleaning",
    ),
    IssueFamily.POTHOLE: ("pothole", "hole in roadway"),
    IssueFamily.PAVEMENT_DAMAGE: ("pavement", "asphalt", "road crack", "surface failure"),
    IssueFamily.METER_FAILURE: (
        "meter failed",
        "meter not reading",
        "meter fault",
        "bad meter",
        "meter problem",
        "changeout meter",
    ),
    IssueFamily.HVAC_FAILURE: (
        "hvac",
        "air handler",
        "no heat",
        "no cooling",
        "no cool",
        "a/c",
        "air cond",
        "not producing cold air",
        "compressor",
    ),
    IssueFamily.ELECTRICAL_ISSUE: (
        "electrical",
        "power outage",
        "breaker",
        "streetlight",
        "streetlights out",
        "short circuit",
    ),
    IssueFamily.RECONNECT: (
        "reconnect",
        "reconnection",
        "restore service",
        "turn on service",
        "service turn on",
    ),
}
TRIGGER_EXEMPLARS: dict[IssueFamily, tuple[str, ...]] = {
    IssueFamily.METER_FAILURE: (
        "meter not reading; unreadable meter register",
        "damaged meter; stuck meter; broken meter",
    ),
    IssueFamily.POTHOLE: (
        "pothole; road surface hole; roadway cavity",
        "sunken road hole; washed out road hole",
    ),
    IssueFamily.PAVEMENT_DAMAGE: (
        "pavement or asphalt is cracked deteriorating rough or failing",
        "roadway surface is sinking or washed out",
    ),
    IssueFamily.WATER_LEAK: (
        "surfacing water leak; standing water leak; leaking service line",
        "leaking water meter; leaking hydrant; leaking water line",
    ),
    IssueFamily.MAIN_BREAK: (
        "water main or water line is broken busted burst or gushing",
        "water is coming up through pavement above a broken main",
    ),
    IssueFamily.LOW_PRESSURE: (
        "service has very low weak intermittent or no water pressure",
        "water flow is weak and there is not enough pressure",
    ),
    IssueFamily.SEWER_BACKUP: (
        "sewer drain or manhole is backed up stopped clogged blocked or overflowing",
        "roots grease or another blockage are restricting the sewer line",
    ),
    IssueFamily.HVAC_FAILURE: (
        "air conditioner not cooling; warm air conditioner",
        "heater failure; furnace failure; compressor failure; HVAC fan failure",
    ),
    IssueFamily.ELECTRICAL_ISSUE: (
        "street light or security light is out blinking flickering or cycling",
        "electrical service has no power exposed wires a short or a tripped breaker",
    ),
    IssueFamily.RECONNECT: (
        "restore water or electric service after a disconnect",
        "reconnect service or turn service back on",
    ),
}
ISSUE_RETRIEVAL_THRESHOLD = 0.195
ISSUE_RETRIEVAL_MARGIN = 0.03
FAMILY_SUPPORT = {
    IssueFamily.WATER_LEAK: re.compile(
        r"\b(?:standing water|water (?:running|surfacing|bubbling|gushing)|"
        r"water coming (?:up|from))\b|\b(?:water|water main|water line|service line|"
        r"hydrant|water meter)\b[^.!?]{0,80}\bleak\w*\b|\bleak\w*\b[^.!?]{0,80}"
        r"\b(?:water|water main|water line|service line|hydrant|water meter)\b",
        re.I,
    ),
    IssueFamily.MAIN_BREAK: re.compile(
        r"(?=.*\bwater (?:main|line)\b)(?=.*\b(?:break\w*|broke|burst|busted|gushing)\b)",
        re.I,
    ),
    IssueFamily.LOW_PRESSURE: re.compile(
        r"\b(?:low|no|weak|intermittent) (?:water )?pressure\b|"
        r"\b(?:pressure drop\w*|weak water flow)\b",
        re.I,
    ),
    IssueFamily.SEWER_BACKUP: re.compile(
        r"(?=.*\b(?:sewer|drain|manhole)\b)(?=.*\b(?:backups?|backed up|stoppage|"
        r"clog\w*|block\w*|overflow\w*|roots?|grease)\b)",
        re.I,
    ),
    IssueFamily.POTHOLE: re.compile(
        r"\bpotholes?\b|\b(?:road|roadway|street|lane|pavement)\b[^.!?]{0,120}"
        r"\b(?:hole|cavity|depression)\b|\b(?:hole|cavity|depression)\b[^.!?]{0,120}"
        r"\b(?:road|roadway|street|lane|pavement)\b",
        re.I,
    ),
    IssueFamily.PAVEMENT_DAMAGE: re.compile(
        r"(?=.*\b(?:pavement|asphalt|roadway|road surface)\b)(?=.*\b(?:crack\w*|"
        r"deteriorat\w*|rough|fail\w*|sink\w*|washed out|damage\w*)\b)",
        re.I,
    ),
    IssueFamily.METER_FAILURE: re.compile(
        r"\b(?:meter|register|endpoint)\b[^.!?]{0,60}\b(?:not reading|unreadable|"
        r"failed read|fault\w*|broken|damaged|stuck)\b|\b(?:not reading|unreadable|"
        r"failed read|fault\w*|broken|damaged|stuck)\b[^.!?]{0,60}"
        r"\b(?:meter|register|endpoint)\b|\bmeter problem\b",
        re.I,
    ),
    IssueFamily.HVAC_FAILURE: re.compile(
        r"\b(?:no heat|no cool(?:ing)?)\b|\b(?:hvac|air conditioner|air handler|heater|"
        r"furnace|compressor|thermostat|fan)\b[^.!?]{0,80}\b(?:fail\w*|not working|"
        r"warm air|broken|out|off)\b|\b(?:fail\w*|not working|warm air|broken|out|off)\b"
        r"[^.!?]{0,80}\b(?:hvac|air conditioner|air handler|heater|furnace|compressor|"
        r"thermostat|fan)\b",
        re.I,
    ),
    IssueFamily.ELECTRICAL_ISSUE: re.compile(
        r"(?=.*\b(?:lights?|streetlights?|power|electrical|breaker|wire|circuit)\b)"
        r"(?=.*\b(?:out|off|outage|blink\w*|flicker\w*|cycl\w*|trip\w*|short|"
        r"exposed|broken|fail\w*)\b)",
        re.I,
    ),
    IssueFamily.RECONNECT: re.compile(
        r"\breconnect\w*\b|\breconnection\b|\b(?:restore|turn on)\s+(?:water|electric)?\s*service\b",
        re.I,
    ),
}


@dataclass(frozen=True)
class IssueClassification:
    family: IssueFamily
    method: str
    trigger: str | None
    score: float


REPAIR_TERMS = (
    "replaced",
    "repaired",
    "patched",
    "cleared",
    "reset",
    "sealed",
    "installed",
    "added refrigerant",
    "charged unit",
    "changed light",
    "changed bulb",
    "changed ballast",
    "repair complete",
    "repaired complete",
    "repair work completed",
    "patching completed",
)
RESOLUTION_TERMS = (
    "resolved",
    "returned to service",
    "no additional complaint",
    "operating normally",
    "working properly",
    "unit running",
)
NO_ISSUE_TERMS = ("no problem found", "no issue found", "unable to reproduce")
CONFLICT_TERMS = (
    "not resolved",
    "issue returned",
    "still leaking",
    "still broken",
    "still not working",
    "not cooling",
    "no cooling",
    "not heating",
    "no heat",
    "failed again",
    "called back",
    "recurring",
)
EXPERT_NOTE_PATTERNS = {
    "no_problem_found": NO_ISSUE_TERMS,
    "jetting_or_line_cleaning": ("jetting", "jetted line", "line cleaning", "cleaned line"),
    "repeat_or_still_broken": CONFLICT_TERMS,
    "roots_or_grease": ("roots in line", "root intrusion", "grease in line", "grease buildup"),
    "reconnect_action": ("reconnect", "reconnection", "restore service", "turn on service"),
}


def classify_issue(text: str, prefer_transformer: bool = False) -> IssueFamily:
    return classify_issue_with_evidence(text, prefer_transformer).family


def classify_issue_with_evidence(
    text: str, prefer_transformer: bool = False
) -> IssueClassification:
    lowered = text.lower()
    supported = {family for family, pattern in FAMILY_SUPPORT.items() if pattern.search(lowered)}
    if not supported:
        return IssueClassification(IssueFamily.UNKNOWN, "no_supported_family", None, 0.0)
    matches = {
        family: sum(lowered.count(keyword) for keyword in keywords)
        for family, keywords in ISSUE_KEYWORDS.items()
        if family in supported
    }
    family, count = max(matches.items(), key=lambda item: item[1])
    if count:
        trigger = max(ISSUE_KEYWORDS[family], key=lowered.count)
        return IssueClassification(family, "exact_corpus_trigger", trigger, 1.0)
    index, records = _trigger_index(prefer_transformer)
    neighbors = index.query(text, len(records))
    if not neighbors:
        return IssueClassification(IssueFamily.UNKNOWN, "no_match", None, 0.0)
    by_family: dict[IssueFamily, tuple[float, str]] = {}
    for neighbor in neighbors:
        family, trigger = records[neighbor.identifier]
        if family in supported and family not in by_family:
            by_family[family] = (neighbor.score, trigger)
    ranked = sorted(by_family.items(), key=lambda item: (-item[1][0], item[0].value))
    family, (score, trigger) = ranked[0]
    margin = score - (ranked[1][1][0] if len(ranked) > 1 else 0)
    if score < ISSUE_RETRIEVAL_THRESHOLD:
        return IssueClassification(IssueFamily.UNKNOWN, "below_score_threshold", None, score)
    if margin < ISSUE_RETRIEVAL_MARGIN:
        return IssueClassification(IssueFamily.UNKNOWN, "below_family_margin", None, score)
    return IssueClassification(family, index.backend, trigger, score)


def detect_expert_note_patterns(text: str) -> list[str]:
    """Return corpus-grounded note patterns for ALP sequence reasoning."""

    return [name for name, terms in EXPERT_NOTE_PATTERNS.items() if _contains_term(text, terms)]


def propagate_sequence_context(orders: list[CanonicalWorkOrder]) -> list[CanonicalWorkOrder]:
    """Recover follow-up note labels when a crew note omits the asset's issue noun."""

    by_asset: dict[str, list[CanonicalWorkOrder]] = {}
    for order in orders:
        for asset_key in order.primary_asset_keys or order.asset_keys:
            by_asset.setdefault(asset_key, []).append(order)
    updates: dict[str, CanonicalWorkOrder] = {}
    for asset_orders in by_asset.values():
        known = [item for item in asset_orders if item.issue_family != IssueFamily.UNKNOWN]
        if not known:
            continue
        for order in asset_orders:
            if order.issue_family != IssueFamily.UNKNOWN:
                continue
            note = " ".join(order.redacted_notes)
            if not _has_follow_up_context(note):
                continue
            nearest = min(known, key=lambda item: abs((order.date - item.date).total_seconds()))
            if abs((order.date - nearest.date).total_seconds()) > 180 * 86_400:
                continue
            metadata = {
                **order.metadata,
                "issue_match_method": "sequence_context",
                "issue_trigger": f"follow-up to {nearest.work_order_id}",
                "issue_trigger_score": 0.70,
            }
            updates[order.work_order_id] = order.model_copy(
                update={"issue_family": nearest.issue_family, "metadata": metadata}
            )
    return [updates.get(order.work_order_id, order) for order in orders]


@lru_cache(maxsize=2)
def _trigger_index(
    prefer_transformer: bool,
) -> tuple[EmbeddingIndex, dict[str, tuple[IssueFamily, str]]]:
    records = {
        f"{family.value}:{index}": (family, trigger)
        for family, triggers in TRIGGER_EXEMPLARS.items()
        for index, trigger in enumerate(triggers)
    }
    index = EmbeddingIndex("sentence-transformers/all-mpnet-base-v2", prefer_transformer).fit(
        list(records), [trigger for _, trigger in records.values()]
    )
    return index, records


def has_repair_signal(text: str) -> bool:
    return _contains_term(text, REPAIR_TERMS)


def resolution_signal(text: str) -> str:
    if _contains_term(text, CONFLICT_TERMS):
        return "UNRESOLVED"
    if _contains_term(text, RESOLUTION_TERMS):
        return "RESOLVED"
    if _contains_term(text, NO_ISSUE_TERMS):
        return "NO_ISSUE_OBSERVED"
    if has_repair_signal(text):
        return "REPAIR_RECORDED"
    return "UNKNOWN"


def _contains_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", text, re.I) for term in terms)


def _has_follow_up_context(text: str) -> bool:
    return _contains_term(
        text,
        (
            "again",
            "returned",
            "prior",
            "previous",
            "remains",
            "continued",
            "repaired",
            "replaced",
            "cleared",
            "cleaned",
            "jetted",
            "restored",
            "inspection",
            "inspected",
            "reset",
            "reconnected",
        ),
    )


def engineer_temporal_features(orders: list[CanonicalWorkOrder]) -> dict[str, TemporalFeatures]:
    by_asset: dict[str, list[CanonicalWorkOrder]] = {}
    for order in orders:
        for asset_key in order.asset_keys:
            by_asset.setdefault(asset_key, []).append(order)
    features: dict[str, TemporalFeatures] = {}
    for asset_orders in by_asset.values():
        sorted_orders = sorted(asset_orders, key=lambda order: order.date)
        for index, order in enumerate(sorted_orders):
            prior = sorted_orders[:index]
            same_issue = [item for item in prior if item.issue_family == order.issue_family]
            intervals = [
                (same_issue[position].date - same_issue[position - 1].date).days
                for position in range(1, len(same_issue))
            ]
            features[order.work_order_id] = TemporalFeatures(
                days_since_previous=(order.date - prior[-1].date).days if prior else None,
                incidents_30d=_count_since(prior, order.date, 30),
                incidents_90d=_count_since(prior, order.date, 90),
                incidents_365d=_count_since(prior, order.date, 365),
                recurrence_interval_days=sum(intervals) / len(intervals) if intervals else None,
                previous_repair_attempts=sum(
                    has_repair_signal(" ".join(item.cleaned_notes)) for item in same_issue
                ),
                issue_persistence=min(1.0, len(same_issue) / 4),
            )
    return features


def issue_distribution(orders: list[CanonicalWorkOrder]) -> Counter[IssueFamily]:
    return Counter(order.issue_family for order in orders)


def _count_since(orders: list[CanonicalWorkOrder], date: datetime, days: int) -> int:
    cutoff = date - timedelta(days=days)
    return sum(order.date >= cutoff for order in orders)
