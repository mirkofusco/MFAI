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

