"""FastAPI application factory and main entry point for Project Javed."""

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from javed.agent.runtime import AgentRuntimeManager
from javed.api.v1.browser_ws import BrowserWebSocketManager, browser_websocket_endpoint
from javed.api.v1.router import api_v1_router
from javed.browser.streamer import BrowserFrameStreamer
from javed.config import Settings, get_settings
from javed.extraction.tools import ExtractionToolsManager
from javed.mcp.gateway import SecureMCPGateway
from javed.mcp.registry import DynamicMCPRegistry
from javed.mcp.servers import create_playwright_mcp_config, create_time_server_config
from javed.providers.cheaper_inference import CheaperInferenceService
from javed.providers.registry import ProviderRegistry
from javed.providers.router import InferenceRouter
from javed.services.openrouter import OpenRouterService
from javed.transport.sse import SSEManager
from javed.transport.websocket import WebSocketManager
from javed.version import __version__

# Configure standard logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("javed.main")


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforce maximum request body size limit on incoming HTTP requests."""

    def __init__(
        self,
        app: FastAPI,
        max_bytes: int,
        max_upload_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes
        self.max_upload_bytes = max_upload_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        limit = (
            self.max_upload_bytes
            if request.url.path.startswith("/api/v1/extraction/upload")
            else self.max_bytes
        )
        if content_length and int(content_length) > limit:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={
                    "error": {
                        "code": "REQUEST_ENTITY_TOO_LARGE",
                        "message": f"Request body exceeds limit of {limit} bytes",
                    }
                },
            )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan: startup logging and graceful shutdown."""
    settings: Settings = app.state.settings

    logger.info(
        "Starting Javed Backend %s on %s:%d (env: %s)",
        __version__,
        settings.host,
        settings.port,
        settings.env,
    )

    # Initialize Deep Agents runtime & SQLite checkpointer
    if hasattr(app.state, "agent_runtime") and app.state.agent_runtime:
        try:
            await app.state.agent_runtime.initialize()
            if hasattr(app.state, "mcp_registry") and app.state.mcp_registry:
                app.state.mcp_registry.approval_store = app.state.agent_runtime.approval_store
                await app.state.mcp_registry.load_persisted_policies()
                # Attempt safe discovery for approved servers on startup
                for server in app.state.mcp_registry.list_servers():
                    if server.server_id == "time":
                        try:
                            await app.state.mcp_registry.discover_tools("time")
                        except Exception as disc_err:
                            logger.info(
                                "Deferred startup tool discovery for '%s': %s",
                                server.server_id,
                                disc_err,
                            )
        except Exception as e:
            logger.warning("Agent runtime initialization deferred or degraded: %s", e)

    # Ensure time__get_current_time is authoritatively configured as ALLOWED_READ_ONLY
    try:
        if hasattr(app.state, "mcp_registry") and app.state.mcp_registry:
            if not app.state.mcp_registry.get_tool("time__get_current_time"):
                await app.state.mcp_registry.discover_tools("time")
            app.state.mcp_registry.set_tool_permission(
                "time__get_current_time", "allowed_read_only"
            )
            logger.info(
                "Authoritative policy: time__get_current_time configured as ALLOWED_READ_ONLY"
            )
    except Exception as e:
        logger.warning("Could not configure time MCP tool policy: %s", e)

    # Safely initialize extraction storage on startup to avoid concurrency locks
    if hasattr(app.state, "extraction_tools_manager") and app.state.extraction_tools_manager:
        try:
            await app.state.extraction_tools_manager.storage.initialize_async()
            logger.info("Extraction storage initialized cleanly on startup")
        except Exception as e:
            logger.warning("Extraction storage initialization deferred: %s", e)

    # Initialize ProviderRegistry on startup
    if hasattr(app.state, "provider_registry") and app.state.provider_registry:
        try:
            await app.state.provider_registry.initialize()
            logger.info("ProviderRegistry initialized cleanly on startup")
        except Exception as e:
            logger.warning("ProviderRegistry initialization deferred: %s", e)

    # Yield control to run the application
    yield

    # Graceful shutdown: close MCP servers, checkpointer, and active WebSocket connections
    logger.info("Shutting down Javed Backend; closing active connections...")
    if hasattr(app.state, "mcp_registry") and app.state.mcp_registry:
        try:
            await app.state.mcp_registry.disconnect_all()
            logger.info("MCP registry servers disconnected cleanly")
        except Exception as e:
            logger.warning("Error disconnecting MCP servers: %s", e)

    if hasattr(app.state, "agent_runtime") and app.state.agent_runtime:
        try:
            await app.state.agent_runtime.close()
        except Exception as e:
            logger.warning("Error closing agent runtime: %s", e)

    if hasattr(app.state, "cheaper_service") and app.state.cheaper_service:
        try:
            await app.state.cheaper_service.close()
            logger.info("Cheaper Inference service closed cleanly")
        except Exception as e:
            logger.warning("Error closing Cheaper Inference service: %s", e)

    if hasattr(app.state, "extraction_tools_manager") and app.state.extraction_tools_manager:
        try:
            await app.state.extraction_tools_manager.close_async()
            logger.info("Extraction tools manager closed cleanly")
        except Exception as e:
            logger.warning("Error closing extraction tools manager: %s", e)

    if hasattr(app.state, "browser_ws_manager") and app.state.browser_ws_manager:
        try:
            await app.state.browser_ws_manager.close_all(code=1001, reason="Server shutting down")
        except Exception as e:
            logger.warning("Error closing browser WebSocket manager: %s", e)

    if hasattr(app.state, "browser_streamer") and app.state.browser_streamer:
        try:
            await app.state.browser_streamer.stop()
        except Exception as e:
            logger.warning("Error stopping browser frame streamer: %s", e)

    await app.state.ws_manager.close_all(code=1001, reason="Server shutting down")
    logger.info("Javed Backend shutdown complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app_settings = settings or get_settings()

    app = FastAPI(
        title="Javed — New JARVIS API",
        description="High-performance async REST & WebSocket gateway for JARVIS.",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if app_settings.env != "production" else None,
        redoc_url="/redoc" if app_settings.env != "production" else None,
    )

    # Initialize state attributes on app creation so they are always available
    app.state.settings = app_settings
    app.state.startup_time = time.time()
    app.state.ws_manager = WebSocketManager(app_settings)
    app.state.sse_manager = SSEManager()
    app.state.openrouter_service = OpenRouterService(app_settings)
    app.state.cheaper_service = CheaperInferenceService(app_settings)
    app.state.provider_registry = ProviderRegistry(app_settings)
    app.state.inference_router = InferenceRouter(
        settings=app_settings,
        registry=app.state.provider_registry,
        openrouter_service=app.state.openrouter_service,
        cheaper_service=app.state.cheaper_service,
    )
    app.state.browser_streamer = BrowserFrameStreamer()
    app.state.browser_ws_manager = BrowserWebSocketManager(
        app_settings, streamer=app.state.browser_streamer
    )
    app.state.mcp_registry = DynamicMCPRegistry()
    try:
        app.state.mcp_registry.register_server(create_time_server_config())
        app.state.mcp_registry.register_server(create_playwright_mcp_config())
    except Exception as exc:
        logger.warning("Could not register default MCP servers: %s", exc)
    app.state.mcp_gateway = SecureMCPGateway(app.state.mcp_registry)

    app.state.extraction_tools_manager = ExtractionToolsManager()

    app.state.agent_runtime = AgentRuntimeManager(
        app_settings,
        openrouter_service=app.state.openrouter_service,
        mcp_gateway=app.state.mcp_gateway,
        enable_extraction=True,
        extraction_tools_manager=app.state.extraction_tools_manager,
        inference_router=app.state.inference_router,
        provider_registry=app.state.provider_registry,
    )

    # 1. Body Size Limiter Middleware
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=app_settings.max_request_body_bytes)

    # 2. CORS Middleware with strictly controlled origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Correlation-ID", "X-Javed-Owner-Token"],
    )

    # 3. Global Exception Handler to prevent raw traceback leakage
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled server exception at %s: %s", request.url.path, exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected server error occurred.",
                }
            },
        )

    # 4. Include API v1 Router
    app.include_router(api_v1_router)

    # Route alias for root-level WebSocket /ws/browser
    app.websocket("/ws/browser")(browser_websocket_endpoint)

    # 5. Root status endpoint
    @app.get("/", summary="Root Health & Identity")
    async def root_index() -> dict[str, str]:
        return {
            "name": "Javed — New JARVIS",
            "version": __version__,
            "status": "online",
            "server_time": datetime.now(UTC).isoformat(),
        }

    return app


# Module-level default app instance for ASGI servers (Uvicorn)
app = create_app()
