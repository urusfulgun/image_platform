from datetime import UTC, datetime


def get_utc_now() -> datetime:
    return datetime.now(UTC)


def get_utc_now_iso_format() -> str:
    return get_utc_now().isoformat()
