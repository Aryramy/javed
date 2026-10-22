"""WebSocket endpoint for bidirectional real-time communication."""

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.status import WS_1008_POLICY_VIOLATION

logger = logging.getLogger("javed.api.v1.ws")
router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str | None = Query(default=None),
) -> None:
    """Versioned WebSocket endpoint for heartbeats, status queries, and events."""
    app_state = websocket.app.state
    ws_manager = app_state.ws_manager

    # 1. Validate Origin header
    origin = websocket.headers.get("origin")
    if not ws_manager.is_origin_allowed(origin):
        logger.warning("Rejected WebSocket connection from unauthorized origin: %s", origin)
        await websocket.close(code=WS_1008_POLICY_VIOLATION, reason="Origin not allowed")
        return

    # 2. Establish connection and obtain client ID
    cid = await ws_manager.connect(websocket, client_id=client_id)

    # 3. Message processing loop
    try:
        while True:
            text_data = await websocket.receive_text()
            await ws_manager.handle_message(cid, text_data)
    except WebSocketDisconnect as e:
        logger.info("WebSocket client %s disconnected: code %s", cid, e.code)
    except Exception as e:
        logger.warning("Unexpected error in WebSocket loop for %s: %s", cid, e)
    finally:
        await ws_manager.disconnect(cid)
