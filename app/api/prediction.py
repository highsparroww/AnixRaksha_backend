from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import AppError, get_current_patient
from app.models.models import Patient, Prediction
from app.schemas.schemas import Envelope, PredictionResponse

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])


@router.get("/{prediction_id}", response_model=Envelope[PredictionResponse])
async def get_prediction(
    prediction_id: str,
    db: AsyncSession = Depends(get_db),
    patient: Patient = Depends(get_current_patient),
):
    result = await db.execute(select(Prediction).where(Prediction.id == prediction_id))
    prediction = result.scalar_one_or_none()
    if not prediction or prediction.patient_id != patient.id:
        raise AppError(status.HTTP_404_NOT_FOUND, "PREDICTION_NOT_FOUND", "Prediction not found")
    return Envelope(data=PredictionResponse.model_validate(prediction))
