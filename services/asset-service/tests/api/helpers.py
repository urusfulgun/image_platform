"""Constants and helpers shared by the API characterization tests."""

from datetime import UTC, datetime, timedelta

from asset_service.db.models import UserModel

BASE_URL = "http://asset-service"
WEBHOOK_TOKEN = "your-secure-shared-secret"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def user_headers(user: UserModel) -> dict[str, str]:
    return {"X-User-Sub": str(user.kc_sub)}


def later(n: int) -> datetime:
    return T0 + timedelta(minutes=n)
