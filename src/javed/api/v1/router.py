"""Aggregation router for API version 1."""

from fastapi import APIRouter

from javed.api.v1.chat import router as chat_router
from javed.api.v1.health import router as health_router
from javed.api.v1.models import router as models_router
from javed.api.v1.sse import router as sse_router
from javed.api.v1.system import router as system_router
from javed.api.v1.ws import router as ws_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(health_router)
api_v1_router.include_router(system_router)
api_v1_router.include_router(ws_router)
api_v1_router.include_router(sse_router)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(models_router)

