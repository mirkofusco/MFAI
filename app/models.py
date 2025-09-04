from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base
from pydantic import BaseModel

# ✅ Modello per il database (tabella clients)
class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    instagram_username = Column(String, unique=True)
    api_key = Column(String)
    active = Column(Boolean, default=True)

# ✅ Schema Pydantic per ricevere i dati in POST
class ClientCreate(BaseModel):
    name: str
    instagram_username: str
    api_key: str
    active: bool = True


from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    trigger = Column(String, index=True)  # esempio: "ciao", "orari", ecc.
    response = Column(String)

    client = relationship("Client", backref="messages")


class MessageCreate(BaseModel):
    client_id: int
    trigger: str
    response: str


# --- Prompt model (added) ---
from sqlalchemy import Column, BigInteger, Text, DateTime, func
from app.database import Base

class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = {"schema": "mfai_app"}

    id = Column(BigInteger, primary_key=True, index=True)
    key = Column(Text, unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
# --- end Prompt model ---
