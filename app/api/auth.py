from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import AppError
from app.models.enums import UserRole
from app.models.models import Doctor, Patient, User, UserSession
from app.schemas.schemas import Envelope, LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.security import create_access_token, hash_password, hash_refresh_token, new_refresh_token, verify_password
from app.config import settings
from app.services.geo import make_point

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


async def _create_session(db: AsyncSession, user: User) -> str:
    token = new_refresh_token()
    db.add(UserSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.flush()
    return token


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.REFRESH_TOKEN_COOKIE_NAME, token, max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True, secure=settings.REFRESH_TOKEN_SECURE, samesite=settings.REFRESH_TOKEN_SAMESITE, path="/api/v1/auth",
    )


@router.post("/register", response_model=Envelope[TokenResponse], status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    email = str(payload.email).lower()
    existing = await db.execute(select(User).where(func.lower(User.email) == email))
    if existing.scalar_one_or_none():
        raise AppError(status.HTTP_409_CONFLICT, "EMAIL_TAKEN", "An account with this email already exists")

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        role=payload.role.value,
        full_name=payload.full_name,
        phone=payload.phone,
    )
    db.add(user)
    await db.flush()

    if payload.role == UserRole.PATIENT:
        patient = Patient(
            user_id=user.id,
            age=payload.age,
            gender=payload.gender.value if payload.gender else None,
            latitude=payload.latitude,
            longitude=payload.longitude,
            location=make_point(payload.latitude, payload.longitude) if payload.latitude is not None else None,
        )
        db.add(patient)
    elif payload.role == UserRole.DOCTOR:
        doctor = Doctor(
            user_id=user.id,
            specialization=payload.specialization,
            license_number=payload.license_number,
            clinic_id=payload.clinic_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            location=make_point(payload.latitude, payload.longitude) if payload.latitude is not None else None,
        )
        db.add(doctor)

    refresh_token = await _create_session(db, user)
    await db.commit()

    token = create_access_token(user.id, user.role)
    _set_refresh_cookie(response, refresh_token)
    return Envelope(data=TokenResponse(access_token=token, role=UserRole(user.role), user_id=user.id))


@router.post("/login", response_model=Envelope[TokenResponse])
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    email = str(payload.email).lower()
    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise AppError(status.HTTP_401_UNAUTHORIZED, "INVALID_CREDENTIALS", "Invalid email or password")

    refresh_token = await _create_session(db, user)
    await db.commit()
    token = create_access_token(user.id, user.role)
    _set_refresh_cookie(response, refresh_token)
    return Envelope(data=TokenResponse(access_token=token, role=UserRole(user.role), user_id=user.id))


@router.post("/refresh", response_model=Envelope[TokenResponse])
async def refresh(
    response: Response,
    payload: RefreshRequest | None = None,
    refresh_cookie: str | None = Cookie(None, alias=settings.REFRESH_TOKEN_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    raw_token = (payload.refresh_token if payload else None) or refresh_cookie
    if not raw_token:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "INVALID_REFRESH_TOKEN", "Invalid refresh token")
    session = (await db.execute(select(UserSession).where(UserSession.refresh_token_hash == hash_refresh_token(raw_token)))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not session or session.revoked_at or session.expires_at <= now:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "INVALID_REFRESH_TOKEN", "Invalid refresh token")
    user = (await db.execute(select(User).where(User.id == session.user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "INVALID_REFRESH_TOKEN", "Invalid refresh token")
    # Rotation revokes the old secret before issuing the replacement.
    session.revoked_at = now
    session.last_used_at = now
    new_token = await _create_session(db, user)
    await db.commit()
    _set_refresh_cookie(response, new_token)
    return Envelope(data=TokenResponse(access_token=create_access_token(user.id, user.role), role=UserRole(user.role), user_id=user.id))


@router.post("/logout", response_model=Envelope[dict])
async def logout(
    response: Response,
    payload: RefreshRequest | None = None,
    refresh_cookie: str | None = Cookie(None, alias=settings.REFRESH_TOKEN_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    raw_token = (payload.refresh_token if payload else None) or refresh_cookie
    if raw_token:
        session = (await db.execute(select(UserSession).where(UserSession.refresh_token_hash == hash_refresh_token(raw_token)))).scalar_one_or_none()
        if session and not session.revoked_at:
            session.revoked_at = datetime.now(timezone.utc)
            await db.commit()
    response.delete_cookie(settings.REFRESH_TOKEN_COOKIE_NAME, path="/api/v1/auth")
    return Envelope(data={"logged_out": True})
