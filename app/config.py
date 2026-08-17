from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/waterwatch"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    ML_MODE: str = "mock"  # mock | external
    ML_SERVICE_URL: str = "http://localhost:8001/predict"

    # Optional environmental-risk model. This is deliberately separate from
    # symptom prediction: it assesses public-health conditions, not patients.
    ENVIRONMENTAL_RISK_MODE: str = "mock"  # mock | external
    ENVIRONMENTAL_RISK_SERVICE_URL: str = "http://localhost:8002/assess"

    ALERT_RADIUS_KM: float = 10.0

    APP_ENV: str = "development"

    FRONTEND_URL: str = "http://localhost:3000"

    # Outbreak / surveillance thresholds (configurable, kept simple)
    OUTBREAK_MIN_CASES: int = 8
    OUTBREAK_WATCH_GROWTH: float = 30.0
    OUTBREAK_ELEVATED_GROWTH: float = 75.0
    OUTBREAK_HIGH_GROWTH: float = 150.0
    OUTBREAK_CRITICAL_GROWTH: float = 250.0
    OUTBREAK_CRITICAL_MIN_CASES: int = 15

    OUTBREAK_ALERT_TTL_HOURS: int = 48


settings = Settings()
