from fastapi import APIRouter, Depends  # Per creare le rotte e gestire le dipendenze
from sqlalchemy.orm import Session      # Per gestire la sessione del database
from app.database import get_db         # Connessione al DB
from app import models                  # Modelli e schemi Pydantic

# ✅ Creazione del router per la sezione "Client"
router = APIRouter()


# ✅ ENDPOINT: Aggiungi un nuovo cliente
@router.post("/clients/")
def create_client(client: models.ClientCreate, db: Session = Depends(get_db)):
    """
    Crea un nuovo cliente nel database.
    - `client`: dati ricevuti dal corpo della richiesta
    - `db`: connessione al database, fornita automaticamente
    """
    db_client = models.Client(**client.dict())
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client


# ✅ ENDPOINT: Elenco di tutti i clienti
@router.get("/clients/")
def read_clients(db: Session = Depends(get_db)):
    """
    Ritorna tutti i clienti registrati.
    """
    return db.query(models.Client).all()


# ✅ ENDPOINT: Dettaglio cliente per ID
@router.get("/clients/{client_id}")
def read_client_by_id(client_id: int, db: Session = Depends(get_db)):
    """
    Ritorna i dati del cliente con ID specificato.
    """
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        return {"error": "Cliente non trovato"}
    return client


# ✅ ENDPOINT: Dettaglio cliente per Instagram username
@router.get("/clients/by_username/{username}")
def read_client_by_username(username: str, db: Session = Depends(get_db)):
    """
    Ritorna il cliente associato allo username Instagram.
    """
    client = db.query(models.Client).filter(models.Client.instagram_username == username).first()
    if not client:
        return {"error": "Cliente non trovato"}
    return client


@router.get("/clients/{client_id}")
def read_client_by_id(client_id: int, db: Session = Depends(get_db)):
    """
    Ritorna i dati di un singolo cliente tramite il suo ID.
    """
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        return {"error": "Cliente non trovato"}
    return client


@router.get("/clients/by_username/{username}")
def read_client_by_username(username: str, db: Session = Depends(get_db)):
    """
    Ritorna i dati di un cliente tramite lo username Instagram.
    """
    client = db.query(models.Client).filter(models.Client.instagram_username == username).first()
    if not client:
        return {"error": "Cliente non trovato"}
    return client
