"""
Forecast API endpoints — node listings and time-series water level data.
"""

import math
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Node, WaterLevelReading
from app.schemas import NodeResponse, ForecastResponse, WaterLevelReadingResponse, LatestForecastResponse

router = APIRouter(prefix="/api/v1", tags=["Forecasts"])


def _compute_status(water_level: float | None, warning: float, alert: float) -> str:
    """Determine node status based on current water level vs thresholds."""
    if water_level is None:
        return "normal"
    if water_level >= alert:
        return "alert"
    if water_level >= warning:
        return "warning"
    return "normal"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@router.get("/nodes", response_model=list[NodeResponse])
async def list_nodes(db: AsyncSession = Depends(get_db)):
    """Return all monitoring nodes with their current status."""
    result = await db.execute(select(Node))
    nodes = result.scalars().all()

    response = []
    for node in nodes:
        # Get latest water level reading for this node
        latest_result = await db.execute(
            select(WaterLevelReading.water_level)
            .where(WaterLevelReading.node_id == node.id)
            .order_by(desc(WaterLevelReading.timestamp))
            .limit(1)
        )
        latest_level = latest_result.scalar_one_or_none()

        response.append(NodeResponse(
            id=node.id,
            name=node.name,
            latitude=node.latitude,
            longitude=node.longitude,
            node_type=node.node_type,
            warning_threshold=node.warning_threshold,
            alert_threshold=node.alert_threshold,
            current_water_level=latest_level,
            status=_compute_status(latest_level, node.warning_threshold, node.alert_threshold),
        ))

    return response


@router.get("/node-forecast", response_model=ForecastResponse)
async def get_node_forecast(
    node_id: str = Query(..., description="Node identifier, e.g. Drain_53"),
    start: datetime | None = Query(None, description="Start of time range (ISO 8601)"),
    end: datetime | None = Query(None, description="End of time range (ISO 8601)"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of readings"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return simulated hourly water levels for a specific node.

    Plugin-friendly endpoint: external tools can pull forecast data via:
        GET /api/v1/node-forecast?node_id=Drain_53
    """
    # Get node metadata
    node_result = await db.execute(select(Node).where(Node.id == node_id))
    node = node_result.scalar_one_or_none()

    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    # Build query for readings
    query = (
        select(WaterLevelReading)
        .where(WaterLevelReading.node_id == node_id)
        .order_by(WaterLevelReading.timestamp)
    )

    if start:
        query = query.where(WaterLevelReading.timestamp >= start)
    if end:
        query = query.where(WaterLevelReading.timestamp <= end)

    query = query.limit(limit)

    result = await db.execute(query)
    readings = result.scalars().all()

    return ForecastResponse(
        node_id=node.id,
        node_name=node.name,
        latitude=node.latitude,
        longitude=node.longitude,
        warning_threshold=node.warning_threshold,
        alert_threshold=node.alert_threshold,
        readings=[
            WaterLevelReadingResponse(
                timestamp=r.timestamp,
                seconds=r.seconds,
                water_level=r.water_level,
            )
            for r in readings
        ],
        total_readings=len(readings),
    )


@router.get("/node-forecast/latest", response_model=LatestForecastResponse)
async def get_latest_forecast_by_location(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the latest spatial flood prediction for the nearest node.

    Plugin-friendly endpoint:
        GET /api/v1/node-forecast/latest?lat=1.4908&lon=110.2738
    """
    result = await db.execute(select(Node))
    nodes = result.scalars().all()

    if not nodes:
        raise HTTPException(status_code=404, detail="No monitoring nodes configured")

    # Find nearest node
    nearest = None
    min_distance = float("inf")

    for node in nodes:
        dist = _haversine_km(lat, lon, node.latitude, node.longitude)
        if dist < min_distance:
            min_distance = dist
            nearest = node

    # Get latest reading for nearest node
    latest_result = await db.execute(
        select(WaterLevelReading)
        .where(WaterLevelReading.node_id == nearest.id)
        .order_by(desc(WaterLevelReading.timestamp))
        .limit(1)
    )
    latest = latest_result.scalar_one_or_none()

    latest_reading = None
    current_level = None
    if latest:
        latest_reading = WaterLevelReadingResponse(
            timestamp=latest.timestamp,
            seconds=latest.seconds,
            water_level=latest.water_level,
        )
        current_level = latest.water_level

    return LatestForecastResponse(
        node_id=nearest.id,
        node_name=nearest.name,
        latitude=nearest.latitude,
        longitude=nearest.longitude,
        distance_km=round(min_distance, 3),
        latest_reading=latest_reading,
        warning_threshold=nearest.warning_threshold,
        alert_threshold=nearest.alert_threshold,
        status=_compute_status(current_level, nearest.warning_threshold, nearest.alert_threshold),
    )
