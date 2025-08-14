from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import requests

from app.database import SessionLocal, get_db
from app.models import Client

router = APIRouter()

# ✅ Funzione interna per ottenere la sessione DB (se non la importi)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ✅ Endpoint per registrare un nuovo cliente
@router.post("/register")
def register_client(name: str, instagram_username: str, api_key: str):
    """
    Registra un nuovo cliente nel sistema.
    """
    db = next(get_db())

    # Controlla se il nome è già usato
    existing = db.query(Client).filter_by(name=name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Cliente già registrato.")

    new_client = Client(
        name=name,
        instagram_username=instagram_username,
        api_key=api_key,
        active=True
    )
    db.add(new_client)
    db.commit()
    db.refresh(new_client)

    return {"message": "Cliente registrato", "client_id": new_client.id}

# ✅ Endpoint per aggiornare il token Instagram
@router.post("/update-token")
def update_token(instagram_username: str, short_token: str, db: Session = Depends(get_db)):
    """
    Riceve il token breve, lo converte in token lungo e lo salva.
    """
    client = db.query(Client).filter(Client.instagram_username == instagram_username).first()

    if not client:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    long_token, expiry = convert_token(short_token)

    client.short_lived_token = short_token
    client.long_lived_token = long_token
    client.token_expiry = expiry
    print(f"✅ Token salvato per {instagram_username}")

    db.commit()

    return {
        "message": "Token aggiornato con successo",
        "long_token": long_token,
        "scade_il": expiry
    }

# ✅ Funzione che converte il token breve in lungo
def convert_token(short_token: str):
    app_secret = "INSERISCI_APP_SECRET"
    url = "https://graph.instagram.com/access_token"
    params = {
        "grant_type": "ig_exchange_token",
        "client_secret": app_secret,
        "access_token": short_token
    }

    response = requests.get(url, params=params)

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Errore nella chiamata a Meta")

    data = response.json()
    long_token = data["access_token"]
    expires_in = data["expires_in"]
    expiry_date = datetime.utcnow() + timedelta(seconds=expires_in)
    return long_token, expiry_date.isoformat()
