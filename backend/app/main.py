"""
Flood Live Data — FastAPI Application Entry Point.

Initializes the database, starts the file watcher service, and mounts
all API routers. Includes CORS middleware for frontend dev server.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import API_V1_PREFIX, CORS_ORIGINS, WATCH_INTERVAL_SECONDS
from app.database import init_db
from app.routers import forecasts, alerts, dashboard
from app.services.file_watcher import FileWatcherService, scan_directory

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-20s │ %(levelname)-7s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("flood.main")

# ─── Services ────────────────────────────────────────────────────────────────
watcher_service = FileWatcherService()
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle management."""

    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("  FLOOD LIVE DATA — Starting up")
    logger.info("=" * 60)

    # Initialize database tables and seed node metadata
    await init_db()
    logger.info("Database initialized.")

    # Start file watcher (watchdog observer)
    loop = asyncio.get_running_loop()
    watcher_service.start(loop)

    # Start APScheduler for periodic directory scan (hourly fallback)
    scheduler.add_job(
        scan_directory,
        "interval",
        seconds=WATCH_INTERVAL_SECONDS,
        id="periodic_scan",
        name="Hourly CSV directory scan",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Periodic scanner scheduled (every {WATCH_INTERVAL_SECONDS}s).")

    # Run an initial scan on startup
    await scan_directory()
    logger.info("Initial directory scan complete.")

    logger.info("=" * 60)
    logger.info("  FLOOD LIVE DATA — Ready")
    logger.info("=" * 60)

    yield  # Application runs here

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("Shutting down...")
    scheduler.shutdown(wait=False)
    watcher_service.stop()
    logger.info("Shutdown complete.")


# ─── FastAPI App ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="Flood Live Data API",
    description=(
        "Automated flood forecasting platform. "
        "Monitors ICM simulation CSV outputs and exposes live forecast data "
        "via plugin-friendly REST API endpoints."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS Middleware ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Mount Routers ───────────────────────────────────────────────────────────
app.include_router(forecasts.router)
app.include_router(alerts.router)
app.include_router(dashboard.router)


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {
        "service": "Flood Live Data API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    """Detailed health check with watcher status."""
    return {
        "status": "healthy",
        "watcher_running": watcher_service.is_running,
        "scheduler_running": scheduler.running,
    }
