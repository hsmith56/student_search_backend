from fastapi import APIRouter, HTTPException, WebSocket, WebSocketException, status
from starlette.websockets import WebSocketDisconnect

from core.placement_notifications import placement_notification_hub
from routers.auth import (
    REFRESH_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    get_current_user_for_websocket,
)

router: APIRouter = APIRouter(prefix="/notifications", tags=["notifications"])


@router.websocket(path="/ws/placements")
async def placement_notifications(websocket: WebSocket) -> None:
    try:
        get_current_user_for_websocket(
            session_id=websocket.cookies.get(SESSION_COOKIE_NAME),
            refresh_token=websocket.cookies.get(REFRESH_COOKIE_NAME),
        )
    except HTTPException:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    await placement_notification_hub.connect(websocket)
    await websocket.send_json(
        {
            "type": "connected",
            "message": "Listening for unassigned_to_allocated events",
        }
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await placement_notification_hub.disconnect(websocket)
