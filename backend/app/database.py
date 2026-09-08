"""
Async SQLite database engine, session management, and initialization.
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},  # Required for SQLite
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """FastAPI dependency — yields a database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables and seed initial node metadata."""
    from app.models import Node  # noqa: F401 — import to register models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed node metadata
    from app.config import NODE_METADATA

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select

        for node_id, meta in NODE_METADATA.items():
            result = await session.execute(select(Node).where(Node.id == node_id))
            existing = result.scalar_one_or_none()

            if existing is None:
                node = Node(
                    id=node_id,
                    name=meta["name"],
                    latitude=meta["latitude"],
                    longitude=meta["longitude"],
                    node_type=meta["node_type"],
                    warning_threshold=meta["warning_threshold"],
                    alert_threshold=meta["alert_threshold"],
                )
                session.add(node)
            else:
                existing.name = meta["name"]
                existing.latitude = meta["latitude"]
                existing.longitude = meta["longitude"]
                existing.node_type = meta["node_type"]
                existing.warning_threshold = meta["warning_threshold"]
                existing.alert_threshold = meta["alert_threshold"]

        await session.commit()
