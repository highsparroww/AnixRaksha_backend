from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Doctor, Patient, User
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "NOT_AUTHENTICATED", "Missing authentication token")
    payload = decode_access_token(token)
    if not payload:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "INVALID_TOKEN", "Invalid or expired token")
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise AppError(status.HTTP_401_UNAUTHORIZED, "INVALID_USER", "User not found or inactive")
    return user


def require_role(*roles: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise AppError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "You do not have access to this resource")
        return user

    return checker


async def get_current_patient(
    user: User = Depends(require_role("PATIENT")),
    db: AsyncSession = Depends(get_db),
) -> Patient:
    result = await db.execute(select(Patient).where(Patient.user_id == user.id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise AppError(status.HTTP_404_NOT_FOUND, "PATIENT_NOT_FOUND", "Patient profile not found")
    return patient


async def get_current_doctor(
    user: User = Depends(require_role("DOCTOR")),
    db: AsyncSession = Depends(get_db),
) -> Doctor:
    result = await db.execute(select(Doctor).where(Doctor.user_id == user.id))
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise AppError(status.HTTP_404_NOT_FOUND, "DOCTOR_NOT_FOUND", "Doctor profile not found")
    return doctor
