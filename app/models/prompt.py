from sqlalchemy import Column, BigInteger, Text, DateTime, func
from app.database import Base

class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = {"schema": "mfai_app"}

    id = Column(BigInteger, primary_key=True, index=True)
    key = Column(Text, unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
