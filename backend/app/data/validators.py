from datetime import UTC, datetime

MIN_DATE = datetime(1990, 1, 1, tzinfo=UTC)


def valid_identifier(value: object) -> bool:
    if value is None:
        return False
    normalized = str(value).strip()
    return bool(normalized and normalized.lower() not in {"null", "none", "nan", "0"})


def parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for pattern in ("%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(text, pattern).replace(tzinfo=UTC)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    if parsed < MIN_DATE or parsed > datetime.now(UTC).replace(microsecond=0):
        return None
    return parsed.replace(tzinfo=None)


def build_asset_key(entity_type: object, entity_uid: object) -> str:
    if not valid_identifier(entity_type) or not valid_identifier(entity_uid):
        raise ValueError("EntityType and EntityUid are both required for asset identity")
    normalized_type = "_".join(str(entity_type).strip().upper().split())
    normalized_uid = str(entity_uid).strip().upper()
    return f"{normalized_type}:{normalized_uid}"
