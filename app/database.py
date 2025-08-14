from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Percorso al database SQLite
SQLALCHEMY_DATABASE_URL = "sqlite:///./mfai.db"

# Creazione del motore
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Sessione
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base per i modelli
Base = declarative_base()

# ✅ Funzione che ci darà la connessione da usare nei vari endpoint
def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
