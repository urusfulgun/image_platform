from shared_core.middlewares.dpop import DPoPMiddleware
from api_gateway.lifespans.hub import lifespan_manager
from fastapi import FastAPI

from api_gateway.api import crud
from api_gateway.config import settings

app = FastAPI(lifespan=lifespan_manager)

app.include_router(crud.router)

app.add_middleware(
    DPoPMiddleware,
    authz_public_key=settings.KEYCLOAK_PUBLIC_KEY,
    allowed_issuer=settings.ALLOWED_ISSUER,
    leeway_seconds=settings.ACCESS_TOKEN_LEEWAY
)
