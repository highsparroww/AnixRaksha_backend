from fastapi import APIRouter, Depends, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import AppError, get_current_user
from app.models.models import Notification, User
from app.schemas.schemas import Envelope, NotificationResponse

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=Envelope[list[NotificationResponse]])
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc())
    result = await db.execute(stmt)
    items = result.scalars().all()
    return Envelope(data=[NotificationResponse.model_validate(n) for n in items])


@router.patch("/{notification_id}/read", response_model=Envelope[NotificationResponse])
async def mark_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Notification).where(Notification.id == notification_id))
    notification = result.scalar_one_or_none()
    if not notification or notification.user_id != user.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "NOTIFICATION_NOT_FOUND", "Notification not found")
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return Envelope(data=NotificationResponse.model_validate(notification))


@router.patch("/read-all", response_model=Envelope[dict])
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await db.execute(
        update(Notification).where(Notification.user_id == user.id, Notification.is_read == False).values(is_read=True)  # noqa: E712
    )
    await db.commit()
    return Envelope(data={"updated": True})
