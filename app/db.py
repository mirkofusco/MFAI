import os
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./dev.db").strip()

def connect_args_for(url: str):
    url = url.lower()
    if url.startswith("postgresql+asyncpg"):
        return {}
    return {}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args=connect_args_for(DATABASE_URL),
)
