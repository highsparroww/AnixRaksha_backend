from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.enums import (
    ActivityLevel,
    AlertSeverity,
    AppointmentStatus,
    CaseSource,
    CaseStatus,
    ClinicType,
    Disease,
    Gender,
    NotificationType,
    Severity,
    SlotStatus,
    Symptom,
    UserRole,
    ConversationStatus,
    SurveillanceSignalType,
)

# ---------- Generic envelope ----------

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str


class Envelope(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None


# ---------- Auth ----------


class RegisterRequest(BaseModel):
    role: UserRole
    full_name: str
    email: EmailStr
    password: str = Field(min_length=8)
    phone: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[Gender] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # doctor-only optional fields
    specialization: Optional[str] = None
    license_number: Optional[str] = None
    clinic_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_role_fields(self):
        if self.role == UserRole.DOCTOR and not self.license_number:
            raise ValueError("license_number is required for doctors")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    user_id: str


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


# ---------- Patient ----------


class PatientProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    full_name: str
    email: str
    phone: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PatientUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[Gender] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


# ---------- Doctor ----------


class DoctorProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    full_name: str
    email: str
    phone: Optional[str] = None
    specialization: Optional[str] = None
    license_number: Optional[str] = None
    clinic_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class DoctorUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    specialization: Optional[str] = None
    license_number: Optional[str] = None
    clinic_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


# ---------- Symptom / Prediction ----------


class SymptomSubmitRequest(BaseModel):
    symptoms: list[Symptom]
    duration_hours: Optional[int] = None
    temperature: Optional[float] = None
    severity: Optional[Severity] = None
    notes: Optional[str] = None


class SymptomSuggestion(BaseModel):
    """A UI hint informed by anonymous local surveillance, not a diagnosis."""

    symptom: Symptom
    related_diseases: list[Disease]
    reason: str


class SymptomSuggestionsResponse(BaseModel):
    suggestions: list[SymptomSuggestion]
    local_diseases: list[str]
    disclaimer: str = (
        "Suggestions reflect local public-health activity only. Select symptoms only if you are experiencing them; this does not diagnose a disease."
    )


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    predicted_disease: str
    is_water_borne: bool
    confidence: float
    model_version: str
    created_at: datetime
    precautions: list[str] = Field(default_factory=list)
    disclaimer: str = "This is a model prediction, not a confirmed diagnosis."

    @model_validator(mode="after")
    def add_general_precautions(self):
        """Educational prevention guidance; never a clinical diagnosis or plan."""
        if not self.precautions:
            from app.services.prediction import precautions_for_disease

            self.precautions = precautions_for_disease(self.predicted_disease)
        return self


# ---------- Internal environmental-model contracts ----------


class EnvironmentalFeatureSet(BaseModel):
    """Validated internal features for future disease-risk inference."""

    latitude: float
    longitude: float
    observed_at: datetime
    source: str
    rainfall_mm_24h: Optional[float] = Field(default=None, ge=0)
    temperature_c: Optional[float] = None
    humidity_percent: Optional[float] = Field(default=None, ge=0, le=100)
    flood_status: Optional[str] = None
    water_quality_status: Optional[str] = None
    sanitation_status: Optional[str] = None
    additional_signals: dict[str, Any] = Field(default_factory=dict)
    data_status: str = "AVAILABLE"


class DiseaseRiskExplanation(BaseModel):
    explanation: str
    contributing_signals: list[str] = Field(default_factory=list)
    uncertainty: Optional[str] = None
    evidence_context: dict[str, Any] = Field(default_factory=dict)


class EnvironmentalDiseaseRiskResult(BaseModel):
    """Internal model output. It is not returned directly to patients."""

    disease: str
    risk_level: AlertSeverity
    confidence: float = Field(ge=0, le=1)
    explanation: DiseaseRiskExplanation
    evaluated_at: datetime


# ---------- Government forecasting foundation (no inference implementation) ----------


class SurveillanceSignalCreateRequest(BaseModel):
    signal_type: SurveillanceSignalType
    source: str = Field(min_length=1, max_length=100)
    latitude: float
    longitude: float
    observed_at: datetime
    disease: Optional[Disease] = None
    data: dict[str, Any] = Field(default_factory=dict)


class SurveillanceSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    signal_type: str
    disease: Optional[str]
    source: str
    observed_at: datetime
    created_at: datetime


class ForecastAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    disease: str
    risk_level: str
    confidence: float
    model_version: str
    explanation: dict[str, Any]
    evidence_context: dict[str, Any]
    forecast_start: datetime
    forecast_end: datetime
    status: str
    created_at: datetime


class ForecastMapCell(BaseModel):
    id: str
    disease: str
    latitude: float
    longitude: float
    radius_km: float
    risk_level: str
    confidence: float
    explanation: dict[str, Any]
    forecast_start: datetime
    forecast_end: datetime


class ForecastMapResponse(BaseModel):
    forecasts: list[ForecastMapCell]


# ---------- Clinics ----------


class ClinicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    type: str
    address: Optional[str] = None
    phone: Optional[str] = None
    latitude: float
    longitude: float
    opening_time: Optional[str] = None
    closing_time: Optional[str] = None
    distance_km: Optional[float] = None


# ---------- Doctor Slots ----------


class SlotCreateRequest(BaseModel):
    start_time: datetime
    end_time: datetime


class SlotUpdateRequest(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[SlotStatus] = None


class SlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    doctor_id: str
    start_time: datetime
    end_time: datetime
    status: str


# ---------- Appointments ----------


class AppointmentCreateRequest(BaseModel):
    doctor_id: str
    slot_id: str
    reason: Optional[str] = None
    health_intake_id: Optional[str] = None
    share_health_summary: bool = False


class AppointmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    doctor_id: str
    slot_id: str
    status: str
    reason: Optional[str] = None
    created_at: datetime
    health_summary_shared: bool = False


class AppointmentDetailResponse(AppointmentResponse):
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    latest_symptoms: Optional[list[str]] = None
    duration_hours: Optional[int] = None
    temperature: Optional[float] = None
    severity: Optional[str] = None
    patient_notes: Optional[str] = None
    prediction: Optional[PredictionResponse] = None
    slot: Optional[SlotResponse] = None
    health_summary_snapshot: Optional[dict[str, Any]] = None


# ---------- Health conversations ----------


class ConversationCreateRequest(BaseModel):
    structured_data: dict[str, Any] = Field(default_factory=dict)


class HealthIntakeUpdateRequest(BaseModel):
    """Structured fields extracted from temporary UI/AI state or entered manually."""
    structured_data: dict[str, Any] = Field(default_factory=dict)
    summary: Optional[str] = Field(default=None, max_length=5000)


class HealthConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    health_intake_id: str
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime
    health_intake: dict[str, Any] = Field(default_factory=dict)


class HealthConversationDetailResponse(HealthConversationResponse):
    pass


# ---------- Disease cases ----------


class DoctorCaseCreateRequest(BaseModel):
    disease: Disease
    case_status: CaseStatus
    patient_id: Optional[str] = None  # registered patient (optional)
    age: Optional[int] = None
    gender: Optional[Gender] = None
    latitude: float
    longitude: float
    clinic_id: Optional[str] = None
    symptoms: Optional[list[Symptom]] = None
    symptom_onset: Optional[datetime] = None
    notes: Optional[str] = None
    reported_at: Optional[datetime] = None


class DoctorCaseUpdateRequest(BaseModel):
    disease: Optional[Disease] = None
    case_status: Optional[CaseStatus] = None
    notes: Optional[str] = None


class DiseaseCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: Optional[str] = None
    doctor_id: Optional[str] = None
    clinic_id: Optional[str] = None
    disease: str
    case_status: str
    source: str
    age: Optional[int] = None
    gender: Optional[str] = None
    latitude: float
    longitude: float
    reported_at: datetime
    notes: Optional[str] = None


# ---------- Surveillance ----------


class SurveillanceQuery(BaseModel):
    latitude: float
    longitude: float
    radius_km: float = 10.0
    disease: Optional[Disease] = None
    time_window_days: Optional[int] = 7


class DiseaseActivityResponse(BaseModel):
    total_cases: int
    cases_by_disease: dict[str, int]
    suspected: int
    probable: int
    confirmed: int
    cases_last_24h: int
    cases_last_7d: int
    cases_previous_7d: int
    growth_percentage: float
    activity_level: str
    per_disease_growth: dict[str, dict[str, float]]


class MapCell(BaseModel):
    cell_id: str
    latitude: float
    longitude: float
    case_count: int
    diseases: dict[str, int]
    activity_level: ActivityLevel


class NearbySurveillanceResponse(BaseModel):
    """Aggregate-only response for the privacy-sensitive nearby endpoint."""

    total_cases: int
    cases_by_disease: dict[str, int]
    suspected: int
    probable: int
    confirmed: int
    time_window_days: int


class MapResponse(BaseModel):
    cells: list[MapCell]


class OutbreakAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    disease: str
    center_latitude: float
    center_longitude: float
    radius_meters: float
    severity: str
    case_count: int
    growth_rate: float
    message: str
    prevention_guidance: list[str]
    created_at: datetime
    expires_at: datetime


# ---------- Notifications ----------


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    type: str
    title: str
    message: str
    data: Optional[dict[str, Any]] = None
    is_read: bool
    created_at: datetime


# ---------- Dev simulation ----------


class SimulateCaseRequest(BaseModel):
    disease: Disease
    latitude: float
    longitude: float
    case_status: CaseStatus = CaseStatus.CONFIRMED
    age: Optional[int] = 30
    gender: Optional[Gender] = Gender.OTHER


class SimulateOutbreakRequest(BaseModel):
    disease: Disease
    latitude: float
    longitude: float
    radius_km: float = 5.0
    number_of_cases: int = 20
    hours: int = 24


# ---------- Dashboards ----------


class PatientDashboardResponse(BaseModel):
    profile: PatientProfile
    disease_activity: DiseaseActivityResponse
    rising_diseases: list[dict[str, Any]]
    outbreak_alerts: list[OutbreakAlertResponse]
    map: MapResponse
    upcoming_appointments: list[AppointmentResponse]
    unread_notification_count: int
    notifications: list[NotificationResponse]
    nearby_clinics: list[ClinicResponse]
    recent_predictions: list[PredictionResponse]


class DoctorDashboardResponse(BaseModel):
    profile: DoctorProfile
    todays_appointments: list[AppointmentResponse]
    upcoming_appointments: list[AppointmentResponse]
    appointment_count: int
    recent_cases: list[DiseaseCaseResponse]
    disease_activity: DiseaseActivityResponse
    rising_diseases: list[dict[str, Any]]
    outbreak_alerts: list[OutbreakAlertResponse]
    notifications: list[NotificationResponse]
    map: MapResponse
    available_slots: list[SlotResponse]
