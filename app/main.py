from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, clinics, dev, doctor, environmental_risk, health, notifications, patient, prediction, surveillance, ws
from app.config import settings
from app.realtime.redis_bus import redis_bus
from app.realtime.websocket import manager
from app.services.prediction import prediction_registry
from app.services.environmental_risk import environmental_risk_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    await prediction_registry.startup()
    app.state.prediction_registry = prediction_registry
    await environmental_risk_registry.startup()
    app.state.environmental_risk_registry = environmental_risk_registry

    await redis_bus.connect()
    await manager.start_redis_listener()

    yield

    await manager.stop_redis_listener()
    await redis_bus.disconnect()
    await prediction_registry.shutdown()
    await environmental_risk_registry.shutdown()


app = FastAPI(
    title="WaterWatch API",
    description="Realtime water-borne disease surveillance, prediction, and local outbreak early-warning API.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        error = detail
    else:
        error = {"code": "HTTP_ERROR", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content={"success": False, "data": None, "error": error})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "data": None,
            "error": {"code": "VALIDATION_ERROR", "message": str(exc.errors())},
        },
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(patient.router)
app.include_router(doctor.router)
app.include_router(prediction.router)
app.include_router(environmental_risk.router)
app.include_router(surveillance.router)
app.include_router(clinics.router)
app.include_router(notifications.router)
app.include_router(dev.router)
app.include_router(ws.router)
