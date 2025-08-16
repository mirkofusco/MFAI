from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

APP_NAME = "MF.AI"

app = FastAPI(title=f"{APP_NAME}")

# Templates (HTML)
templates = Jinja2Templates(directory="app/templates")

# CORS (per ora aperti, poi li chiudiamo ai tuoi domini)
ALLOWED_ORIGINS = [
    "https://mid-ranna-soluzionidigitaliroma-f8d1ef2a.koyeb.app",
    "https://api.soluzionidigitali.roma.it",  # quando colleghi il dominio
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"ok": True, "app": APP_NAME}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

class TokenData(BaseModel):
    token: str = Field(..., min_length=1)

@app.post("/token")
def receive_token(data: TokenData):
    return {"message": "Token ricevuto correttamente."}

TOKEN_FILE = Path("access_token.txt")

@app.post("/save-token")
def save_token(data: TokenData):
    try:
        TOKEN_FILE.write_text(data.token, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Errore salvataggio token") from e
    return {"status": "success"}
