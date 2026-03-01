from datetime import datetime, timezone


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)

def get_utc_now_iso_format() -> str:
    return get_utc_now().isoformat()