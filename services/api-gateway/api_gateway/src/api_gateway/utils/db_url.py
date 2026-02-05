from api_gateway.config import settings


def get_url() -> str:
    user = settings.POSTGRES_USER
    password = settings.POSTGRES_PASSWORD
    host = settings.POSTGRES_HOST
    db = settings.POSTGRES_DB
    return f"postgresql+asyncpg://{user}:{password}@{host}/{db}"