import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from geoalchemy2.functions import ST_DWithin, ST_Distance
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.enums import ActivityLevel, CaseStatus
from app.models.models import DiseaseCase
from app.services.geo import make_point


def _activity_level(growth_percentage: float, total_cases: int) -> str:
    if total_cases >= settings.OUTBREAK_CRITICAL_MIN_CASES and growth_percentage >= settings.OUTBREAK_CRITICAL_GROWTH:
        return ActivityLevel.CRITICAL.value
    if growth_percentage >= settings.OUTBREAK_HIGH_GROWTH:
        return ActivityLevel.HIGH.value
    if growth_percentage >= settings.OUTBREAK_ELEVATED_GROWTH:
        return ActivityLevel.ELEVATED.value
    if growth_percentage >= settings.OUTBREAK_WATCH_GROWTH:
        return ActivityLevel.WATCH.value
    return ActivityLevel.NORMAL.value


def growth_percentage(current: int, previous: int) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 2)


async def nearby_cases_query(
    db: AsyncSession,
    latitude: float,
    longitude: float,
    radius_km: float,
    disease: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
):
    center = make_point(latitude, longitude)
    radius_m = radius_km * 1000
    stmt = select(DiseaseCase).where(ST_DWithin(DiseaseCase.location, center, radius_m))
    if disease:
        stmt = stmt.where(DiseaseCase.disease == disease)
    if since:
        stmt = stmt.where(DiseaseCase.reported_at >= since)
    if until:
        stmt = stmt.where(DiseaseCase.reported_at < until)
    stmt = stmt.order_by(ST_Distance(DiseaseCase.location, center))
    return stmt


async def get_nearby_cases(
    db: AsyncSession,
    latitude: float,
    longitude: float,
    radius_km: float,
    disease: Optional[str] = None,
    time_window_days: Optional[int] = None,
) -> list[DiseaseCase]:
    since = None
    if time_window_days:
        since = datetime.now(timezone.utc) - timedelta(days=time_window_days)
    stmt = await nearby_cases_query(db, latitude, longitude, radius_km, disease, since)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_nearby_summary(
    db: AsyncSession,
    latitude: float,
    longitude: float,
    radius_km: float,
    disease: Optional[str] = None,
    time_window_days: int = 7,
) -> dict:
    """Return aggregate-only data for the privacy-sensitive nearby API."""
    center = make_point(latitude, longitude)
    filters = [
        ST_DWithin(DiseaseCase.location, center, radius_km * 1000),
        DiseaseCase.reported_at >= datetime.now(timezone.utc) - timedelta(days=time_window_days),
    ]
    if disease:
        filters.append(DiseaseCase.disease == disease)

    totals_stmt = select(
        func.count(DiseaseCase.id),
        func.sum(case((DiseaseCase.case_status == CaseStatus.SUSPECTED.value, 1), else_=0)),
        func.sum(case((DiseaseCase.case_status == CaseStatus.PROBABLE.value, 1), else_=0)),
        func.sum(case((DiseaseCase.case_status == CaseStatus.CONFIRMED.value, 1), else_=0)),
    ).where(*filters)
    total, suspected, probable, confirmed = (await db.execute(totals_stmt)).one()

    by_disease_stmt = (
        select(DiseaseCase.disease, func.count(DiseaseCase.id))
        .where(*filters)
        .group_by(DiseaseCase.disease)
    )
    by_disease = {name: count for name, count in (await db.execute(by_disease_stmt)).all()}
    return {
        "total_cases": total or 0,
        "cases_by_disease": by_disease,
        "suspected": suspected or 0,
        "probable": probable or 0,
        "confirmed": confirmed or 0,
        "time_window_days": time_window_days,
    }


async def _count_cases(
    db: AsyncSession,
    latitude: float,
    longitude: float,
    radius_km: float,
    disease: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> int:
    center = make_point(latitude, longitude)
    radius_m = radius_km * 1000
    stmt = select(func.count(DiseaseCase.id)).where(ST_DWithin(DiseaseCase.location, center, radius_m))
    if disease:
        stmt = stmt.where(DiseaseCase.disease == disease)
    if since:
        stmt = stmt.where(DiseaseCase.reported_at >= since)
    if until:
        stmt = stmt.where(DiseaseCase.reported_at < until)
    result = await db.execute(stmt)
    return result.scalar_one()


async def get_disease_activity(
    db: AsyncSession,
    latitude: float,
    longitude: float,
    radius_km: float,
    disease: Optional[str] = None,
) -> dict:
    now = datetime.now(timezone.utc)
    center = make_point(latitude, longitude)
    radius_m = radius_km * 1000

    base_filter = ST_DWithin(DiseaseCase.location, center, radius_m)

    # totals + status breakdown + per-disease breakdown, done in the DB.
    stmt = select(
        func.count(DiseaseCase.id),
        func.sum(case((DiseaseCase.case_status == CaseStatus.SUSPECTED.value, 1), else_=0)),
        func.sum(case((DiseaseCase.case_status == CaseStatus.PROBABLE.value, 1), else_=0)),
        func.sum(case((DiseaseCase.case_status == CaseStatus.CONFIRMED.value, 1), else_=0)),
        func.sum(case((DiseaseCase.reported_at >= now - timedelta(hours=24), 1), else_=0)),
    ).where(base_filter)
    if disease:
        stmt = stmt.where(DiseaseCase.disease == disease)
    row = (await db.execute(stmt)).one()
    total_cases, suspected, probable, confirmed, last_24h = row
    total_cases = total_cases or 0
    suspected = suspected or 0
    probable = probable or 0
    confirmed = confirmed or 0
    last_24h = last_24h or 0

    # cases by disease (only meaningful when not already filtered to one disease)
    disease_stmt = select(DiseaseCase.disease, func.count(DiseaseCase.id)).where(base_filter)
    if disease:
        disease_stmt = disease_stmt.where(DiseaseCase.disease == disease)
    disease_stmt = disease_stmt.group_by(DiseaseCase.disease)
    disease_rows = (await db.execute(disease_stmt)).all()
    cases_by_disease = {d: c for d, c in disease_rows}

    current_7d = await _count_cases(db, latitude, longitude, radius_km, disease, since=now - timedelta(days=7))
    previous_7d = await _count_cases(
        db,
        latitude,
        longitude,
        radius_km,
        disease,
        since=now - timedelta(days=14),
        until=now - timedelta(days=7),
    )
    growth = growth_percentage(current_7d, previous_7d)
    activity_level = _activity_level(growth, current_7d)

    per_disease_growth: dict[str, dict[str, float]] = {}
    for d in cases_by_disease:
        d_current = await _count_cases(db, latitude, longitude, radius_km, d, since=now - timedelta(days=7))
        d_previous = await _count_cases(
            db, latitude, longitude, radius_km, d, since=now - timedelta(days=14), until=now - timedelta(days=7)
        )
        per_disease_growth[d] = {
            "current_7d": d_current,
            "previous_7d": d_previous,
            "growth_percentage": growth_percentage(d_current, d_previous),
        }

    return {
        "total_cases": total_cases,
        "cases_by_disease": cases_by_disease,
        "suspected": suspected,
        "probable": probable,
        "confirmed": confirmed,
        "cases_last_24h": last_24h,
        "cases_last_7d": current_7d,
        "cases_previous_7d": previous_7d,
        "growth_percentage": growth,
        "activity_level": activity_level,
        "per_disease_growth": per_disease_growth,
    }


CELL_SIZE_DEG = 0.02  # ~2.2km grid cells, simple and good enough for a hackathon heatmap


def _cell_id(lat: float, lon: float) -> str:
    cell_lat = math.floor(lat / CELL_SIZE_DEG)
    cell_lon = math.floor(lon / CELL_SIZE_DEG)
    return f"{cell_lat}_{cell_lon}"


async def get_map_data(
    db: AsyncSession,
    latitude: float,
    longitude: float,
    radius_km: float,
    disease: Optional[str] = None,
    time_window_days: Optional[int] = None,
) -> list[dict]:
    """Aggregate nearby cases into coarse grid cells so exact patient
    locations are never exposed through the map API."""
    # The visible map represents the requested, recent period.  Activity is
    # compared with the immediately preceding equal period, just as the
    # dashboard-wide activity calculation compares the current and previous
    # seven days.  Only coarse cells leave this service.
    window_days = time_window_days or 7
    now = datetime.now(timezone.utc)
    current_cases = await get_nearby_cases(
        db, latitude, longitude, radius_km, disease, window_days
    )
    previous_stmt = await nearby_cases_query(
        db,
        latitude,
        longitude,
        radius_km,
        disease,
        since=now - timedelta(days=window_days * 2),
        until=now - timedelta(days=window_days),
    )
    previous_cases = list((await db.execute(previous_stmt)).scalars().all())

    cells: dict[str, dict] = {}
    for c in current_cases:
        cid = _cell_id(c.latitude, c.longitude)
        if cid not in cells:
            cell_lat = (math.floor(c.latitude / CELL_SIZE_DEG) + 0.5) * CELL_SIZE_DEG
            cell_lon = (math.floor(c.longitude / CELL_SIZE_DEG) + 0.5) * CELL_SIZE_DEG
            cells[cid] = {
                "cell_id": cid,
                "latitude": cell_lat,
                "longitude": cell_lon,
                "case_count": 0,
                "diseases": {},
                "previous_case_count": 0,
            }
        cells[cid]["case_count"] += 1
        cells[cid]["diseases"][c.disease] = cells[cid]["diseases"].get(c.disease, 0) + 1

    for c in previous_cases:
        cid = _cell_id(c.latitude, c.longitude)
        if cid in cells:
            cells[cid]["previous_case_count"] += 1

    for cell in cells.values():
        cell["activity_level"] = _activity_level(
            growth_percentage(cell["case_count"], cell["previous_case_count"]),
            cell["case_count"],
        )
        del cell["previous_case_count"]

    return list(cells.values())
