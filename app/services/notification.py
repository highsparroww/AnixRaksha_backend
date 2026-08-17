from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Notification
from app.realtime.websocket import publish_event


async def create_notification(
    db: AsyncSession,
    user_id: str,
    type_: str,
    title: str,
    message: str,
    data: Optional[dict[str, Any]] = None,
    push_realtime: bool = True,
) -> Notification:
    notification = Notification(user_id=user_id, type=type_, title=title, message=message, data=data)
    db.add(notification)
    await db.flush()

    if push_realtime:
        await publish_event(
            "notifications",
            "NOTIFICATION",
            {
                "id": notification.id,
                "type": notification.type,
                "title": notification.title,
                "message": notification.message,
                "data": notification.data,
            },
            user_ids=[user_id],
        )

    return notification
