"""
Flood Inundation Contours API Router.

Serves converted 2D flood inundation GeoJSON files and timesteps listing
for Leaflet visualization in the frontend.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from app.config import GEOJSON_DIR, API_V1_PREFIX
from app.services.gis_converter import extract_timestep

logger = logging.getLogger("flood.contours")

router = APIRouter(prefix="/api/v1/contours", tags=["Contours"])


def _get_geojson_files() -> list[Path]:
    """Retrieve all valid GeoJSON files in the output directory, sorted by timestep."""
    dir_path = Path(GEOJSON_DIR)
    if not dir_path.exists():
        return []
    return sorted(dir_path.glob("*.geojson"))


@router.get("/timesteps", response_model=list[str])
async def list_contour_timesteps():
    """
    Return an ordered list of available contour timesteps.

    Example response:
        ["1000", "1100", "1200", "1300", "1400", "1500", "1600", "1700", "1800"]
    """
    files = _get_geojson_files()
    timesteps: list[str] = []

    for f in files:
        meta = extract_timestep(f.name)
        ts = meta.get("timestep")
        if ts and ts not in timesteps:
            timesteps.append(ts)

    # Sort timesteps chronologically / numerically, with non-numeric (e.g. Maxima) at the end
    timesteps.sort(key=lambda x: (0, int(x)) if x.isdigit() else (1, x))
    return timesteps


@router.get("/metadata")
async def get_contours_metadata():
    """
    Return extended metadata for all available simulation contour frames,
    including frame labels, file names, dates, and bounding boxes.
    """
    files = _get_geojson_files()
    frames = []

    for f in files:
        meta = extract_timestep(f.name)
        stat = f.stat()
        frames.append({
            "timestep": meta.get("timestep"),
            "label": meta.get("label"),
            "date": meta.get("date"),
            "filename": f.name,
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
        })

    frames.sort(
        key=lambda x: (0, int(x["timestep"]))
        if str(x["timestep"]).isdigit()
        else (1, str(x["timestep"]))
    )
    return {
        "total_frames": len(frames),
        "timesteps": [frame["timestep"] for frame in frames if frame.get("timestep")],
        "frames": frames,
    }


@router.get("/{timestamp}")
async def get_contour_geojson(timestamp: str):
    """
    Return the GeoJSON FeatureCollection payload for a specific timestep.

    Examples:
        - GET /api/v1/contours/1000
        - GET /api/v1/contours/260826_1000
        - GET /api/v1/contours/FloodContours_260826_1000
    """
    dir_path = Path(GEOJSON_DIR)
    if not dir_path.exists():
        raise HTTPException(status_code=404, detail="No contour data available.")

    # Clean requested timestamp query
    target = timestamp.replace(".geojson", "").strip()

    # Search strategy:
    # 1. Exact match <target>.geojson
    # 2. Ends with _<target>.geojson
    # 3. Contains <target>
    matched_file: Path | None = None
    all_files = list(dir_path.glob("*.geojson"))

    for f in all_files:
        stem = f.stem
        if stem == target:
            matched_file = f
            break
        # Match pattern like FloodContours_260826_1000 when querying '1000'
        if stem.endswith(f"_{target}") or stem.endswith(f"_{target.zfill(4)}"):
            matched_file = f
            break

    if not matched_file:
        # Fallback substring match
        for f in all_files:
            if target in f.stem:
                matched_file = f
                break

    if not matched_file or not matched_file.exists():
        available = [extract_timestep(f.name).get("timestep") for f in all_files]
        raise HTTPException(
            status_code=404,
            detail=f"Contour layer for timestep '{timestamp}' not found. Available timesteps: {available}",
        )

    try:
        content = matched_file.read_text(encoding="utf-8")
        return Response(content=content, media_type="application/geo+json")
    except Exception as e:
        logger.error(f"Error reading GeoJSON {matched_file}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to read contour GeoJSON layer.")
