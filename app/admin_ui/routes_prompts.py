from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db  # deve esistere già
from app.models import Client     # contiene la colonna clients.ai_prompt

router = APIRouter(prefix="/admin", tags=["admin:prompts"])

# Schema input per il PUT
class PromptUpdate(BaseModel):
    ai_prompt: str = Field(default="", max_length=8000)

@router.get("/clients/{client_id}/prompt")
def get_client_prompt(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    return {"client_id": client.id, "ai_prompt": client.ai_prompt or ""}

@router.put("/clients/{client_id}/prompt")
def put_client_prompt(client_id: int, payload: PromptUpdate, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    # pulizia base (spazi ai lati)
    text = (payload.ai_prompt or "").strip()
    client.ai_prompt = text
    db.add(client)
    db.commit()
    db.refresh(client)

    return {"client_id": client.id, "ai_prompt": client.ai_prompt or ""}
