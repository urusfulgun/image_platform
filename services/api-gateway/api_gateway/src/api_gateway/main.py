from api_gateway.middlewares.dpop import DPoPMiddleware
from api_gateway.lifespans.hub import lifespan
from fastapi import FastAPI

app = FastAPI(lifespan=lifespan)
app.add_middleware(DPoPMiddleware)
