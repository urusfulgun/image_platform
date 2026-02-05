# Recommended helper for timezone-aware UTC
from datetime import datetime, timezone


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)
