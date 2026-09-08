"""
Dashboard aggregation endpoint — summary statistics for the frontend header.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Node, WaterLevelReading, AlertDefinition
from app.schemas import DashboardSummary
from app.routers.alerts import _is_alert_active

router = APIRouter(prefix="/api/v1", tags=["Dashboard"])


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def get_dashboard_summary(db: AsyncSession = Depends(get_db)):
    """
    Return summary statistics for the dashboard header.
    Aggregates: total nodes, active alerts, latest update, max water level.
    """

    # Total nodes
    node_count_result = await db.execute(select(func.count(Node.id)))
    total_nodes = node_count_result.scalar() or 0

    # Active alerts
    alerts_result = await db.execute(select(AlertDefinition))
    all_alerts = alerts_result.scalars().all()
    active_alerts = sum(1 for a in all_alerts if _is_alert_active(a))

    # Latest update timestamp
    latest_result = await db.execute(
        select(WaterLevelReading.ingested_at)
        .order_by(desc(WaterLevelReading.ingested_at))
        .limit(1)
    )
    latest_update = latest_result.scalar_one_or_none()

    # Max water level across all nodes (latest readings only)
    # Get the latest reading per node and find the max
    nodes_result = await db.execute(select(Node))
    nodes = nodes_result.scalars().all()

    max_level = None
    max_level_node = None
    nodes_warning = 0
    nodes_alert = 0

    for node in nodes:
        latest_reading_result = await db.execute(
            select(WaterLevelReading.water_level)
            .where(WaterLevelReading.node_id == node.id)
            .order_by(desc(WaterLevelReading.timestamp))
            .limit(1)
        )
        level = latest_reading_result.scalar_one_or_none()

        if level is not None:
            if max_level is None or level > max_level:
                max_level = level
                max_level_node = node.id

            if level >= node.alert_threshold:
                nodes_alert += 1
            elif level >= node.warning_threshold:
                nodes_warning += 1

    return DashboardSummary(
        total_nodes=total_nodes,
        active_alerts=active_alerts,
        latest_update=latest_update,
        max_water_level=max_level,
        max_water_level_node=max_level_node,
        nodes_in_warning=nodes_warning,
        nodes_in_alert=nodes_alert,
    )
