from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.realtime.websocket import manager
from app.security import decode_access_token

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    if not token:
        token = websocket.query_params.get("token")

    payload = decode_access_token(token) if token else None
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = payload["sub"]
    role = payload["role"]

    await manager.connect(websocket, user_id, role)
    try:
        while True:
            # We don't require the client to send anything; just keep the
            # connection open and drain any messages (e.g. pings) it sends.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id, role)
