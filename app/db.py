import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL non impostata nelle variabili d'ambiente")

class Base(DeclarativeBase):
    pass

engine = create_async_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
)
