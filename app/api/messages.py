from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models

# 🔹 Router dedicato alla gestione dei messaggi
router = APIRouter()

# ✅ ENDPOINT: Crea un nuovo messaggio per un cliente
@router.post("/messages/")
def create_message(msg: models.MessageCreate, db: Session = Depends(get_db)):
    """
    Crea un nuovo messaggio automatico associato a un cliente.
    - `msg`: dati con client_id, trigger e response
    """
    db_msg = models.Message(**msg.dict())
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)
    return db_msg

# ✅ ENDPOINT: Leggi tutti i messaggi di un cliente
@router.get("/messages/{client_id}")
def get_messages(client_id: int, db: Session = Depends(get_db)):
    """
    Ritorna tutti i messaggi automatici associati a un dato client_id.
    """
    return db.query(models.Message).filter(models.Message.client_id == client_id).all()


from fastapi import HTTPException
from pydantic import BaseModel

# ✅ Schema per ricevere un messaggio in ingresso da Instagram
class IncomingMessage(BaseModel):
    instagram_username: str
    message_in: str

# ✅ ENDPOINT: Elabora un messaggio in arrivo e trova la risposta automatica
@router.post("/handle/")
def handle_incoming_message(msg: IncomingMessage, db: Session = Depends(get_db)):
    """
    Riceve un messaggio da un utente e restituisce la risposta automatica
    se il trigger è stato definito per quel cliente.
    """
    # 1. Trova il cliente con quell'username
    client = db.query(models.Client).filter_by(instagram_username=msg.instagram_username).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    # 2. Cerca il messaggio automatico con trigger corrispondente
    auto_msg = db.query(models.Message).filter_by(client_id=client.id, trigger=msg.message_in).first()
    if not auto_msg:
        return {"reply": "Messaggio non riconosciuto."}

    # 3. Restituisci la risposta
    return {"reply": auto_msg.response}

