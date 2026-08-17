from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import AppError
from app.models.enums import UserRole
from app.models.models import Doctor, Patient, User
from app.schemas.schemas import Envelope, LoginRequest, RegisterRequest, TokenResponse
from app.security import create_access_token, hash_password, verify_password
from app.services.geo import make_point

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=Envelope[TokenResponse], status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise AppError(status.HTTP_409_CONFLICT, "EMAIL_TAKEN", "An account with this email already exists")

    user = User(
        email=payload.email,
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

    await db.commit()

    token = create_access_token(user.id, user.role)
    return Envelope(data=TokenResponse(access_token=token, role=UserRole(user.role), user_id=user.id))


@router.post("/login", response_model=Envelope[TokenResponse])
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise AppError(status.HTTP_401_UNAUTHORIZED, "INVALID_CREDENTIALS", "Invalid email or password")

    token = create_access_token(user.id, user.role)
    return Envelope(data=TokenResponse(access_token=token, role=UserRole(user.role), user_id=user.id))
