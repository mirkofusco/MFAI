from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Client, Message
from app.prompt_engine import get_gpt_reply

router = APIRouter()

# Funzione interna per ottenere una sessione DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/message")
async def receive_message(request: Request):
    """
    Riceve un messaggio da un client (Instagram), genera una risposta e la salva.
    """
    data = await request.json()
    api_key = data.get("api_key")
    text = data.get("text")
    sender = data.get("sender")
    post_id = data.get("post_id")

    if not api_key or not text or not sender:
        raise HTTPException(status_code=400, detail="Dati mancanti")

    db = next(get_db())

    client = db.query(Client).filter_by(api_key=api_key, active=True).first()
    if not client:
        raise HTTPException(status_code=403, detail="API key non valida")

    reply = get_gpt_reply(text)

    message = Message(
        client_id=client.id,
        sender=sender,
        text=text,
        reply=reply,
        post_id=post_id
    )
    db.add(message)
    db.commit()

    return {"reply": reply}
