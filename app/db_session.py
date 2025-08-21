import os
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

def _adapt_dsn(dsn: Optional[str]) -> str:
    if not dsn:
        # fallback locale (solo per sviluppo)
        return "sqlite+aiosqlite:///./local.db"
    low = dsn.lower()
    if low.startswith("postgres://"):
        return "postgresql+asyncpg://" + dsn.split("://", 1)[1]
    if low.startswith("postgresql://"):
        return "postgresql+asyncpg://" + dsn.split("://", 1)[1]
    return dsn  # già async o altro driver

DATABASE_URL = _adapt_dsn(os.environ.get("DATABASE_URL"))

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

async_session_maker = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)
