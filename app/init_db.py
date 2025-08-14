from app.database import Base, engine
from app.models import Client

print("🛠️ Creazione del database...")

# Crea tutte le tabelle
Base.metadata.create_all(bind=engine)

print("✅ Database creato con successo.")
