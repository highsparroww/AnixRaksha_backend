import enum


class UserRole(str, enum.Enum):
    PATIENT = "PATIENT"
    DOCTOR = "DOCTOR"
    ADMIN = "ADMIN"
    GOVERNMENT = "GOVERNMENT"


class SurveillanceSignalType(str, enum.Enum):
    SYMPTOM_AGGREGATE = "SYMPTOM_AGGREGATE"
    WASTEWATER = "WASTEWATER"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    LAB_SAMPLE = "LAB_SAMPLE"




class ConversationStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"




class Gender(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class Symptom(str, enum.Enum):
    DIARRHEA = "DIARRHEA"
    VOMITING = "VOMITING"
    FEVER = "FEVER"
    ABDOMINAL_PAIN = "ABDOMINAL_PAIN"
    DEHYDRATION = "DEHYDRATION"
    NAUSEA = "NAUSEA"
    BLOOD_IN_STOOL = "BLOOD_IN_STOOL"
    HEADACHE = "HEADACHE"
    WEAKNESS = "WEAKNESS"
    MUSCLE_CRAMPS = "MUSCLE_CRAMPS"


class Severity(str, enum.Enum):
    MILD = "MILD"
    MODERATE = "MODERATE"
    SEVERE = "SEVERE"


class Disease(str, enum.Enum):
    CHOLERA = "CHOLERA"
    TYPHOID = "TYPHOID"
    HEPATITIS_A = "HEPATITIS_A"
    HEPATITIS_E = "HEPATITIS_E"
    DYSENTERY = "DYSENTERY"
    ROTAVIRUS = "ROTAVIRUS"
    OTHER_WATER_BORNE = "OTHER_WATER_BORNE"


class SlotStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"


class AppointmentStatus(str, enum.Enum):
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"


class CaseStatus(str, enum.Enum):
    SUSPECTED = "SUSPECTED"
    PROBABLE = "PROBABLE"
    CONFIRMED = "CONFIRMED"
    RECOVERED = "RECOVERED"
    REJECTED = "REJECTED"


class CaseSource(str, enum.Enum):
    PATIENT = "PATIENT"
    DOCTOR = "DOCTOR"
    LAB = "LAB"
    IMPORTED = "IMPORTED"


class ClinicType(str, enum.Enum):
    GOVERNMENT = "GOVERNMENT"
    PRIVATE = "PRIVATE"


class AlertSeverity(str, enum.Enum):
    WATCH = "WATCH"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActivityLevel(str, enum.Enum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NotificationType(str, enum.Enum):
    OUTBREAK_ALERT = "OUTBREAK_ALERT"
    APPOINTMENT = "APPOINTMENT"
    SURVEILLANCE = "SURVEILLANCE"
    HEALTH = "HEALTH"
    ENVIRONMENTAL_RISK = "ENVIRONMENTAL_RISK"
    FORECAST_ALERT = "FORECAST_ALERT"
    SYSTEM = "SYSTEM"
