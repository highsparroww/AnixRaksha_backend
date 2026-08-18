# WaterWatch — Backend

Realtime water-borne disease surveillance, prediction, and local outbreak
early-warning API. Built as a hackathon prototype: one FastAPI application,
PostgreSQL + PostGIS for geospatial data, Redis for realtime pub/sub, plain
WebSockets for push — no Docker, no microservices, no message queues.

## Use case

WaterWatch helps patients, clinicians, and public-health users understand
local water-borne disease activity without exposing individual patient
locations or health records. A patient can record structured health concerns,
find care, and receive locality-based risk alerts. A clinician can document
clinically assessed cases—including walk-in patients without an account.

Only **clinically confirmed** disease cases appear on the surveillance map.
Predictions, symptom submissions, suspected cases, and probable cases are not
presented as confirmed map cases.

## Core workflow

```text
Patient
  → enters symptoms / structured health intake
  → receives educational prediction and care guidance
  → may book a doctor appointment and opt in to sharing a structured snapshot

Doctor / clinic
  → assesses a patient, including registered and walk-in patients
  → records a disease case with clinical status and reporting location
  → confirmed case contributes to the coarse, privacy-preserving map

Surveillance
  → aggregates confirmed cases into approximately 2.2 km map cells
  → measures recent case growth by disease and locality
  → creates an outbreak alert when configured thresholds are met
  → notifies registered patients whose saved location is within the alert area
  → delivers in-app notifications and real-time WebSocket events
```

### Appointment workflow

```text
Patient
  → symptom assessment
  → risk / guidance
  → chooses “Talk to a doctor”
  → chooses a doctor and an available slot
  → confirms the booking
  → appointment is created
  → optionally shares the structured symptoms relevant to that assessment
     with that doctor for that appointment only
```

The shared information is an immutable appointment snapshot. Later changes to
the patient’s intake do not alter what the doctor received, and the doctor
cannot browse the patient’s other assessments or conversational UI state.

### Health-data privacy

- Conversational UI state is temporary; the backend persists structured intake
  fields, not a raw conversation transcript.
- A doctor receives only an appointment-specific, patient-approved structured
  health snapshot—not the patient’s full intake history.
- Map and nearby-surveillance APIs return coarse aggregate data rather than
  patient identities or exact locations.
- A model prediction is educational and does not create a confirmed disease
  case or alter map counts.

## Stack

- Python 3.12, FastAPI, Uvicorn, Pydantic v2
- SQLAlchemy 2.x (async) + asyncpg, Alembic migrations
- PostgreSQL + PostGIS (GeoAlchemy2) for all geospatial queries
- Redis (pub/sub) + native FastAPI WebSockets for realtime push
- JWT auth (python-jose) + bcrypt password hashing
- pytest / pytest-asyncio / httpx / httpx-ws for tests

## Project layout

```
app/
  api/            route handlers (auth, patient, doctor, prediction,
                  surveillance, clinics, notifications, dev, ws, health)
  models/         SQLAlchemy models + shared enums
  schemas/        Pydantic request/response schemas
  services/       business logic (prediction, surveillance, outbreak,
                  notification, appointment, disease-case creation, geo)
  realtime/       Redis pub/sub bus + WebSocket connection manager
  config.py       environment-driven settings
  database.py     async engine/session
  security.py     JWT + password hashing
  dependencies.py auth + RBAC dependencies
  main.py         FastAPI app, lifespan wiring, CORS, error envelope
alembic/          migrations (async env.py)
tests/            pytest suite (see below)
seed.py           demo data seeder
smoke_test.py     manual end-to-end HTTP smoke test (run against a live server)
ws_smoke_test.py  manual realtime WebSocket smoke test (run against a live server)
```

## Prerequisites

Install locally (no Docker):

- Python 3.12+
- PostgreSQL 16 with the PostGIS extension available
- Redis

On Debian/Ubuntu:

```bash
sudo apt-get install postgresql postgresql-contrib postgis postgresql-16-postgis-3 redis-server
sudo service postgresql start
redis-server --daemonize yes
```

Create the database and enable PostGIS:

```bash
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
sudo -u postgres psql -c "CREATE DATABASE waterwatch;"
sudo -u postgres psql -d waterwatch -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env    # adjust DATABASE_URL / REDIS_URL / JWT_SECRET as needed
alembic upgrade head
python3 seed.py
uvicorn app.main:app --reload
```

## Run everything with Docker

With Docker Desktop running, start the API, PostGIS, and Redis together:

```bash
docker compose up --build
```

The API runs migrations automatically and is available at
`http://localhost:8000`; interactive API documentation is at
`http://localhost:8000/docs`. Use `docker compose down` to stop the stack.
Database and Redis data are retained in named volumes; use
`docker compose down -v` only when you intentionally want a fresh local
database.

The Compose file defaults to `ML_MODE=mock`. To use the existing external ML
service, set `ML_MODE=external` and `ML_SERVICE_URL` in your environment (or
an `.env` file) before starting Compose.

### Environmental-risk model contract

Set `ENVIRONMENTAL_RISK_MODE=external` and point
`ENVIRONMENTAL_RISK_SERVICE_URL` at a service that accepts:

```json
{ "latitude": 26.45, "longitude": 80.33 }
```

It must return an environmental (not clinical) assessment such as:

```json
{
  "risk_level": "ELEVATED",
  "risk_score": 0.72,
  "potential_water_borne_diseases": ["CHOLERA", "TYPHOID"],
  "potential_vector_borne_diseases": ["MALARIA"],
  "contributing_factors": [
    {"factor": "FLOODING", "severity": "HIGH", "reason": "Recent flooding"},
    {"factor": "OPEN_SEWAGE", "severity": "ELEVATED", "reason": "Sanitation hazard"}
  ],
  "prevention_guidance": ["Use treated water", "Avoid standing water"],
  "data_status": "LIVE_ENVIRONMENTAL_MODEL"
}
```

`GET /api/v1/environmental-risk/me` sends the signed-in patient's saved
coordinates to that model. Elevated, high, and critical responses create an
in-app notification and a realtime `NOTIFICATION` event, with a 24-hour
duplicate guard. The model should source and validate weather, flood,
water-body, and sanitation data; WaterWatch does not infer those conditions
from patient records.

The API is then live at `http://localhost:8000`, with interactive docs at
`/docs` and `/redoc`, and the raw schema at `/openapi.json`.

Seeded accounts (see `seed.py` output for the exact cluster coordinates):

| Role    | Emails                              | Password       |
|---------|--------------------------------------|----------------|
| Admin   | `admin@waterwatch.dev`               | `Admin123!`    |
| Doctor  | `doctor1@waterwatch.dev` … `doctor3@waterwatch.dev` | `Doctor123!` |
| Patient | `patient1@waterwatch.dev` … `patient10@waterwatch.dev` | `Patient123!` |

## Configuration (`.env`)

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/waterwatch
REDIS_URL=redis://localhost:6379/0

JWT_SECRET=change-me-in-production
JWT_EXPIRE_MINUTES=60

ML_MODE=mock                # or "external"
ML_SERVICE_URL=http://localhost:8001/predict

ALERT_RADIUS_KM=10          # 10 / 11 / 12 all supported, just change this

APP_ENV=development          # dev-only /api/v1/dev/* endpoints require this
FRONTEND_URL=http://localhost:3000
```

## Running tests

Tests run against a **separate** Postgres database (`waterwatch_test`) so
they never touch your seeded dev data:

```bash
sudo -u postgres psql -c "CREATE DATABASE waterwatch_test;"
sudo -u postgres psql -d waterwatch_test -c "CREATE EXTENSION IF NOT EXISTS postgis;"

python3 -m pytest tests/ -q
```

31 tests covering auth/RBAC, patient flows (symptom checker, prediction
history, dashboard), doctor flows (slots, appointment booking with
double-booking protection, pre-test info, case registration for both
registered and unregistered patients), PostGIS surveillance queries (nearby,
activity counts, growth %, map aggregation), clinics, notifications, the dev
simulator, realtime WebSocket delivery, and one full end-to-end scenario test
mirroring the hackathon demo script below.

Tables are truncated between tests for isolation; the schema itself is
created once per test run.

## Manual / live demo scripts

With the server running (`uvicorn app.main:app --reload`) and seeded:

```bash
python3 smoke_test.py      # full HTTP walkthrough of the demo scenario
python3 ws_smoke_test.py   # proves the realtime pipeline: case -> outbreak
                            # -> notification -> WebSocket push, no polling
```

## API overview

All responses use a consistent envelope:

```json
{ "success": true, "data": { ... }, "error": null }
{ "success": false, "data": null, "error": { "code": "...", "message": "..." } }
```

- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`
- `GET/PUT /api/v1/patient/me`, `GET /api/v1/patient/dashboard`
- `POST /api/v1/patient/symptoms` → mock/external ML prediction, stored
- `GET /api/v1/patient/predictions`, `GET/POST /api/v1/patient/appointments`
- `GET /api/v1/patient/disease-activity`, `GET /api/v1/patient/nearby-clinics`
- `GET/PUT /api/v1/doctor/me`, `GET /api/v1/doctor/dashboard`
- `POST/GET/PUT/DELETE /api/v1/doctor/slots`
- `GET /api/v1/doctor/appointments`, `GET /api/v1/doctor/appointments/{id}` (pre-test info)
- `POST/PUT /api/v1/doctor/cases` (patient_id is **nullable** — unregistered/walk-in patients supported)
- `GET /api/v1/doctor/surveillance`
- `GET /api/v1/predictions/{id}` — prediction retrieval; `POST /api/v1/patient/symptoms` is the single symptom-to-prediction workflow
- `GET /api/v1/environmental-risk/me` — an environmental ML risk assessment for the signed-in patient's saved area; elevated risk sends one in-app/WebSocket notification per 24 hours
- `GET /api/v1/surveillance/nearby|map|activity|outbreaks` — all PostGIS-backed (`ST_DWithin`/`ST_Distance`); `nearby` returns aggregate counts only and `map` returns coarse cells only
- `GET /api/v1/clinics/nearby`
- `GET /api/v1/notifications`, `PATCH /api/v1/notifications/{id}/read`, `PATCH /api/v1/notifications/read-all`
- `POST /api/v1/dev/simulate-case`, `POST /api/v1/dev/simulate-outbreak` (dev-mode only)
- `WS /ws?token=<jwt>` — events: `NEW_CASE`, `SURVEILLANCE_UPDATED`, `OUTBREAK_ALERT`, `APPOINTMENT_BOOKED`, `NOTIFICATION`
- `GET /health`, `/health/db`, `/health/redis`, `/health/ml`

## Design notes

- **Unregistered patients**: `DiseaseCase.patient_id` is nullable. A doctor
  can register a confirmed case for a walk-in patient with no WaterWatch
  account; the case still counts toward surveillance, map aggregation, and
  outbreak detection — it just can't receive notifications.
- **Privacy**: `surveillance/nearby` returns aggregate counts and disease
  breakdowns only. `surveillance/map` returns only coarse grid cells with an
  activity level. Neither endpoint exposes individual case records, patient
  identity, demographics, or coordinates.
- **Symptom-checker guidance**: every prediction includes general,
  disease-specific prevention precautions. It remains educational guidance,
  not personalised medical advice or a confirmed diagnosis.
- **Environmental risk alerts**: an optional external ML endpoint can assess
  weather/flood, nearby-water-body, and sanitation signals for a patient's
  area. These alerts distinguish potential water-borne disease from
  mosquito-borne risk (such as malaria), are not diagnoses, and include
  general prevention guidance. `mock` mode deliberately reports that no live
  environmental data is available rather than fabricating a risk.
- **Outbreak detection**: a transparent, configurable heuristic (see
  `OUTBREAK_*` settings in `config.py`) comparing the current 7-day case
  count and growth rate against previous 7 days, within `ALERT_RADIUS_KM`.
  It is explicitly *not* a medically validated algorithm — this is stated in
  the surrounding docs and in the DoD but not exposed as clinical fact to
  end users.
- **Realtime**: REST gives initial state; all live updates flow over Redis
  pub/sub → a single in-process `ConnectionManager` → WebSocket. No polling
  anywhere.
- **ML integration**: `PredictionService` is an abstract interface with a
  `MockPredictionService` (deterministic-ish symptom-weighted heuristic) and
  an `ExternalMLPredictionService` (calls `ML_SERVICE_URL` with one reusable
  `httpx.AsyncClient`, created once at startup). Switch with `ML_MODE`.
- **Booking race safety**: `book_appointment` takes a row lock
  (`SELECT ... FOR UPDATE`) on the slot before booking, so two patients
  racing for the same slot get a clean `409 SLOT_ALREADY_BOOKED` instead of
  a double-booked appointment.
