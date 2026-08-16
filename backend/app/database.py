from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from pathlib import Path
from .config import settings

db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate(conn)
    await _sync_settings()


async def _migrate(conn):
    """Add missing columns and fix known bad data."""
    import sqlalchemy as sa

    column_migrations = [
        ("athlete_profile", "max_sessions_per_day", "INTEGER DEFAULT 1"),
        ("athlete_profile", "current_weekly_hours", "FLOAT"),
        ("athlete_profile", "sport_limits", "JSON"),
        ("athlete_profile", "recovery_mode", "TEXT DEFAULT 'auto'"),
        ("athlete_profile", "recovery_cycle_weeks", "INTEGER"),
        ("athlete_profile", "volume_progression_mode", "TEXT DEFAULT 'ramp'"),
        ("athlete_profile", "training_style", "TEXT DEFAULT 'standard'"),
        ("athlete_profile", "quality_sport_priority", "JSON"),
    ]
    for table, column, col_type in column_migrations:
        try:
            await conn.execute(sa.text(
                f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
            ))
        except Exception:
            pass

    await conn.execute(sa.text(
        "UPDATE settings SET value = 'claude-fable-5' "
        "WHERE key = 'claude_model_heavy' AND value IN ('claude-sonnet-4-20250514', 'claude-sonnet-5')"
    ))


async def _sync_settings():
    """Load DB settings into the in-memory settings object at startup."""
    import sqlalchemy as sa

    async with async_session() as session:
        result = await session.execute(sa.text("SELECT key, value FROM settings"))
        for key, value in result.fetchall():
            if hasattr(settings, key):
                current = getattr(settings, key)
                if isinstance(current, int):
                    value = int(value)
                elif isinstance(current, float):
                    value = float(value)
                elif isinstance(current, bool):
                    value = value.lower() in ("true", "1", "yes")
                setattr(settings, key, value)
