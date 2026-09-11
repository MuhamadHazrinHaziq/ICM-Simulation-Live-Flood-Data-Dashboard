"""
GIS Inundation Shapefile Conversion Service.

Detects incoming InfoWorks ICM 2D flood inundation Shapefiles (.shp, .dbf, .shx),
verifies and normalizes CRS (Sarawak RSO / UTM / WGS84 to standard EPSG:4326),
and exports optimized GeoJSON files to the data/geojson/ directory for Leaflet.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np

from app.config import (
    DATA_DIR,
    DEFAULT_LOCAL_CRS,
    GEOJSON_DIR,
    SHAPEFILE_PATTERN,
    TARGET_CRS,
)

logger = logging.getLogger("flood.gis")


def extract_timestep(filename: str) -> dict[str, str | None]:
    """
    Extract timestep and date information from shapefile filename.
    Examples:
      - 'FloodContours_260826_1000.shp' -> date: '260826', timestep: '1000', label: '10:00'
      - 'FloodContours_1400.shp'        -> date: None,     timestep: '1400', label: '14:00'
      - 'FloodContours_1100_00.shp'     -> date: None,     timestep: '1100', label: '11:00'
    """
    name = Path(filename).stem

    # Pattern 1: FloodContours_YYMMDD_HHMM or FloodContours_YYYYMMDD_HHMM
    match_date_time = re.search(r"(\d{6,8})_(\d{4})", name)
    if match_date_time:
        date_part = match_date_time.group(1)
        time_part = match_date_time.group(2)
        hour = time_part[:2]
        minute = time_part[2:]
        return {
            "date": date_part,
            "timestep": time_part,
            "label": f"{hour}:{minute}",
            "raw": name,
        }

    # Pattern 2: FloodContours_HHMM
    match_time = re.search(r"_(\d{4})(?:_|$)", name)
    if match_time:
        time_part = match_time.group(1)
        hour = time_part[:2]
        minute = time_part[2:]
        return {
            "date": None,
            "timestep": time_part,
            "label": f"{hour}:{minute}",
            "raw": name,
        }

    # Fallback: extract any sequence of 3-4 digits
    fallback_digits = re.findall(r"\d+", name)
    if fallback_digits:
        last = fallback_digits[-1]
        padded = last.zfill(4)
        return {
            "date": None,
            "timestep": padded,
            "label": f"{padded[:2]}:{padded[2:]}",
            "raw": name,
        }

    return {"date": None, "timestep": name, "label": name, "raw": name}


def verify_shapefile_ready(shp_path: str | Path, wait_seconds: float = 3.0) -> bool:
    """
    Ensure that the core shapefile components (.shp, .shx, .dbf) exist
    and are not locked or actively being written.
    """
    path = Path(shp_path)
    base = path.with_suffix("")
    shx = base.with_suffix(".shx")
    dbf = base.with_suffix(".dbf")

    # Check for presence of essential companions
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if path.exists() and shx.exists() and dbf.exists():
            # Check sizes > 0
            if path.stat().st_size > 0 and dbf.stat().st_size > 0:
                return True
        time.sleep(0.5)

    return path.exists() and shx.exists() and dbf.exists()


def convert_shapefile_to_geojson(
    shp_path: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    """
    Read an ICM flood contour shapefile, inspect/reproject CRS to EPSG:4326,
    and save clean GeoJSON to output_dir (default: GEOJSON_DIR).

    Returns conversion metadata dict or None if conversion failed.
    """
    path = Path(shp_path)
    out_dir = Path(output_dir or GEOJSON_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        logger.error(f"Shapefile does not exist: {path}")
        return None

    if not verify_shapefile_ready(path):
        logger.warning(f"Shapefile companions (.shx, .dbf) not ready yet for: {path.name}")
        return None

    logger.info(f"Starting conversion for shapefile: {path.name}")

    try:
        # 1. Read shapefile into GeoDataFrame
        gdf = gpd.read_file(path)

        if gdf.empty:
            logger.info(f"Shapefile {path.name} contains 0 features (dry frame). Writing empty GeoJSON.")
            meta = extract_timestep(path.name)
            out_filename = f"{path.stem}.geojson"
            out_file = out_dir / out_filename
            empty_geojson = json.dumps({"type": "FeatureCollection", "features": []})
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(empty_geojson)
            return {
                "filename": out_filename,
                "filepath": str(out_file),
                "timestep": meta["timestep"],
                "date": meta["date"],
                "label": meta["label"],
                "feature_count": 0,
                "bounds": [0.0, 0.0, 0.0, 0.0],
                "min_depth": None,
                "max_depth": None,
                "original_crs": str(gdf.crs) if gdf.crs else None,
                "target_crs": TARGET_CRS,
            }

        orig_crs = str(gdf.crs) if gdf.crs else None
        logger.info(f"Loaded {len(gdf)} features from {path.name}. Detected CRS: {orig_crs}")

        # 2. CRS Verification and Reprojection
        # InfoWorks ICM exports in Sarawak often use Sarawak RSO (EPSG:29873 / EPSG:3376) or UTM
        if gdf.crs is None:
            # Inspect coordinate bounds to deduce coordinate system
            bounds = gdf.total_bounds  # minx, miny, maxx, maxy
            minx, miny, maxx, maxy = bounds

            if minx > 1000 and miny > 1000:
                # Coordinate values are in large meter units (e.g. 150,000, 170,000)
                logger.info(
                    f"CRS missing but coordinates in meter scale ({minx:.1f}, {miny:.1f}). "
                    f"Assuming local Sarawak RSO ({DEFAULT_LOCAL_CRS})."
                )
                gdf.set_crs(DEFAULT_LOCAL_CRS, inplace=True)
                gdf = gdf.to_crs(TARGET_CRS)
            elif 90 <= minx <= 140 and -10 <= miny <= 20:
                # Already in geographic degrees
                logger.info("CRS missing but coordinates appear to be WGS84 geographic degrees.")
                gdf.set_crs(TARGET_CRS, inplace=True)
            else:
                # Fallback to local CRS
                gdf.set_crs(DEFAULT_LOCAL_CRS, inplace=True)
                gdf = gdf.to_crs(TARGET_CRS)
        else:
            # Reproject to standard WGS84
            if gdf.crs.to_string() != TARGET_CRS:
                logger.info(f"Reprojecting from {gdf.crs} to {TARGET_CRS}...")
                gdf = gdf.to_crs(TARGET_CRS)

        # 3. Clean and normalize attribute table
        # Find depth & elevation columns if present and ensure JSON-serializable values
        depth_col = None
        elev_col = None
        for col in gdf.columns:
            lower = col.lower()
            if "depth" in lower or "depz" in lower or "height" in lower:
                depth_col = col
            elif "elev" in lower or "stage" in lower or "level" in lower:
                elev_col = col

        # Clean NaN/Inf values across all attribute columns
        for col in gdf.columns:
            if col != "geometry":
                # Convert pandas/numpy NaN to None
                gdf[col] = gdf[col].apply(
                    lambda v: None if (isinstance(v, (float, np.floating)) and np.isnan(v)) else v
                )

        # Add standardized helper properties for frontend consumption
        if depth_col and depth_col != "depth":
            gdf["depth"] = gdf[depth_col].apply(
                lambda v: round(float(v), 3) if v is not None else None
            )
        elif depth_col:
            gdf["depth"] = gdf[depth_col].apply(
                lambda v: round(float(v), 3) if v is not None else None
            )

        if elev_col and elev_col != "elevation":
            gdf["elevation"] = gdf[elev_col].apply(
                lambda v: round(float(v), 3) if v is not None else None
            )
        elif elev_col:
            gdf["elevation"] = gdf[elev_col].apply(
                lambda v: round(float(v), 3) if v is not None else None
            )

        # 4. Extract timestep metadata
        meta = extract_timestep(path.name)
        gdf["timestep"] = meta["timestep"]
        gdf["timestep_label"] = meta["label"]

        # 5. Export clean GeoJSON atomically
        out_filename = f"{path.stem}.geojson"
        out_file = out_dir / out_filename
        tmp_file = out_dir / f"{path.stem}.tmp.geojson"

        # Use GeoPandas to_json
        to_json_callable: Any = getattr(gdf, "to_json")
        geojson_str: str = str(to_json_callable(drop_id=True))
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(geojson_str)

        # Atomic replace
        shutil.move(str(tmp_file), str(out_file))

        total_bounds = [float(round(b, 6)) for b in gdf.total_bounds]

        depth_values = [
            float(v) for v in gdf["depth"].dropna().values
        ] if "depth" in gdf.columns else []

        summary = {
            "filename": out_filename,
            "filepath": str(out_file),
            "timestep": meta["timestep"],
            "date": meta["date"],
            "label": meta["label"],
            "feature_count": len(gdf),
            "bounds": total_bounds,
            "min_depth": min(depth_values) if depth_values else None,
            "max_depth": max(depth_values) if depth_values else None,
            "original_crs": orig_crs,
            "target_crs": TARGET_CRS,
        }

        logger.info(
            f"Successfully converted {path.name} -> {out_filename} "
            f"({len(gdf)} features, timestep={meta['timestep']})"
        )
        return summary

    except Exception as e:
        logger.error(f"Failed to convert shapefile {path.name}: {e}", exc_info=True)
        return None


def convert_all_shapefiles(
    exports_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    """
    Scan exports_dir for all .shp files matching SHAPEFILE_PATTERN
    and convert those that have not yet been converted or have been updated.
    """
    exp_path = Path(exports_dir or DATA_DIR)
    out_path = Path(output_dir or GEOJSON_DIR)
    out_path.mkdir(parents=True, exist_ok=True)

    if not exp_path.exists():
        return []

    shp_files = sorted(exp_path.glob("*.shp"))
    results = []

    for shp in shp_files:
        if SHAPEFILE_PATTERN.lower() not in shp.name.lower():
            continue

        target_geojson = out_path / f"{shp.stem}.geojson"

        # Check if already converted and up to date
        if not force and target_geojson.exists():
            if target_geojson.stat().st_mtime >= shp.stat().st_mtime:
                # Already up to date, skip
                continue

        result = convert_shapefile_to_geojson(shp, out_path)
        if result:
            results.append(result)

    return results
