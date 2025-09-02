# app/main.py
# ============================================================
# MF.AI — FastAPI
#
# Endpoints:
# - /health, /db/health
# - /login (HTML)
# - /save-token, /clients, /tokens/active, /tokens/refresh, /tokens/expiring
# - /oauth/callback (Instagram Business Login)
#
# Requisiti:
#   .env:
#     - API_KEY
#     - DATABASE_URL = postgresql+asyncpg://.../mfai   (senza querystring)
# DB engine (app/db.py):
#   create_async_engine(DATABASE_URL, connect_args={
#     "ssl": True, "server_settings": {"search_path": "mfai_app,public"}
#   })
# ============================================================

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import engine  # engine async verso Neon
from app.routers import admin_api
from app.routers.meta_webhook import router as meta_webhook_router
from app.admin_ui.routes import router as admin_ui_router

# ----------------------------
# App & config base
# ----------------------------
APP_NAME = "MF.AI"
app = FastAPI(title=APP_NAME)

# Static (monta solo se esiste la cartella per evitare errori in deploy)
if os.path.isdir("app/admin_ui/static"):
    app.mount("/static", StaticFiles(directory="app/admin_ui/static"), name="static")

# Routers principali
app.include_router(admin_api.router)     # API amministrative (JSON)
app.include_router(meta_webhook_router)  # Webhook Meta (GET verify + POST eventi)
app.include_router(admin_ui_router)      # Admin UI (Basic Auth)

# Public UI (/c/*) — import "safe" (se manca il modulo non blocca il deploy)
try:
    from app.public_ui.routes import router as public_ui_router  # type: ignore
    app.include_router(public_ui_router)
except Exception as e:
    print("Public UI router non caricato:", e)

# Templates (HTML)
templates = Jinja2Templates(directory="app/templates")

# CORS (restringi ai domini di produzione)
ALLOWED_ORIGINS = [
    "https://mid-ranna-soluzionidigitaliroma-f8d1ef2a.koyeb.app",
    "https://api.soluzionidigitali.roma.it",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers (middleware)
@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.update(
        {
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
            "Cache-Control": "no-store",
            "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
            "Content-Security-Policy": (
                "default-src 'self'; "
                "style-src 'self' https://cdn.jsdelivr.net; "
                "img-src 'self' data:"
            ),
        }
    )
    return resp

# --- API Key guard ---
API_KEY = os.getenv("API_KEY", "")
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


async def require_api_key(key: Optional[str] = Depends(api_key_header)) -> None:
    if not API_KEY or key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

# ---------------------------------------------------------
# Schema & indici (prefisso mfai_app.)
# ---------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mfai_app.clients (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mfai_app.instagram_accounts (
  id BIGSERIAL PRIMARY KEY,
  client_id BIGINT NOT NULL REFERENCES mfai_app.clients(id) ON DELETE CASCADE,
  ig_user_id TEXT UNIQUE NOT NULL,
  username TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mfai_app.tokens (
  id BIGSERIAL PRIMARY KEY,
  ig_account_id BIGINT NOT NULL REFERENCES mfai_app.instagram_accounts(id) ON DELETE CASCADE,
  access_token TEXT NOT NULL,
  expires_at TIMESTAMPTZ,
  long_lived BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now(),
  active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS mfai_app.message_logs (
  id BIGSERIAL PRIMARY KEY,
  ig_account_id BIGINT REFERENCES mfai_app.instagram_accounts(id) ON DELETE SET NULL,
  direction TEXT NOT NULL CHECK (direction IN ('in','out')),
  payload TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tokens_igacct_created
  ON mfai_app.tokens(ig_account_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ig_accounts_client
  ON mfai_app.instagram_accounts(client_id);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_token_per_acct
  ON mfai_app.tokens(ig_account_id)
  WHERE active = TRUE;
"""


def _split_sql(sql: str):
    for part in sql.split(";"):
        stmt = part.strip()
        if stmt:
            yield stmt


@app.on_event("startup")
async def ensure_schema():
    async with engine.begin() as conn:
        # 1) Assicura schema e search_path
        await conn.exec_driver_sql(
            "CREATE SCHEMA IF NOT EXISTS mfai_app AUTHORIZATION mfai_owner;"
        )
        await conn.exec_driver_sql("SET search_path TO mfai_app;")

        # 2) Debug identità
        who = (await conn.execute(text("SELECT current_user, current_schema();"))).first()
        print("DB identity:", who)

        # 3) Crea/aggiorna oggetti schema
        for stmt in _split_sql(SCHEMA_SQL):
            await conn.exec_driver_sql(stmt)

# ----------------------------
# Routes semplici
# ----------------------------
@app.get("/")
def home():
    return {"ok": True, "app": APP_NAME}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/db/health")
async def db_health():
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT 'ok'"))
        return {"db": r.scalar_one()}

# --- OAuth Callback Instagram (Business Login) ---
@app.get("/oauth/callback")
async def oauth_callback(request: Request):
    """
    Callback del flusso OAuth (Instagram Business Login).
    Per ora conferma solo la ricezione del "code" e dello "state".
    """
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code:
        raise HTTPException(status_code=400, detail="Missing ?code in callback")
    return {
        "status": "ok",
        "received_code": True,
        "code_preview": (code[:12] + "..."),
        "state": state,
    }

# ----------------------------
# Modelli I/O (Pydantic)
# ----------------------------
class SaveTokenPayload(BaseModel):
    token: str = Field(..., min_length=5)
    ig_user_id: str = Field(..., min_length=3)
    username: str = Field(..., min_length=1)
    client_name: str = "Default Client"
    client_email: Optional[str] = None
    # se None -> +60 giorni da ora (UTC)
    expires_at: Optional[datetime] = None


class RefreshTokenPayload(BaseModel):
    ig_user_id: str = Field(..., min_length=3)
    token: str = Field(..., min_length=5)
    expires_in_days: int = Field(default=60, ge=1, le=365)

# ---------------------------------------------------------
# Salva token/cliente/account (idempotente su email e ig_user_id)
# ---------------------------------------------------------
@app.post("/save-token", dependencies=[Depends(require_api_key)])
async def save_token(data: SaveTokenPayload):
    try:
        exp = data.expires_at or (datetime.now(timezone.utc) + timedelta(days=60))

        async with engine.begin() as conn:
            # 1) Upsert client su email
            res = await conn.execute(
                text(
                    """
                    INSERT INTO mfai_app.clients (name, email)
                    VALUES (
                      :name,
                      COALESCE(:email, REPLACE(LOWER(:name),' ','_') || '@example.local')
                    )
                    ON CONFLICT (email) DO UPDATE
                      SET name = EXCLUDED.name
                    RETURNING id
                    """
                ),
                {"name": data.client_name, "email": data.client_email},
            )
            client_id = res.scalar_one()

            # 2) Upsert instagram_account su ig_user_id
            res = await conn.execute(
                text(
                    """
                    INSERT INTO mfai_app.instagram_accounts (client_id, ig_user_id, username, active)
                    VALUES (:client_id, :ig_user_id, :username, TRUE)
                    ON CONFLICT (ig_user_id) DO UPDATE
                      SET username = EXCLUDED.username,
                          active   = TRUE
                    RETURNING id
                    """
                ),
                {
                    "client_id": client_id,
                    "ig_user_id": data.ig_user_id,
                    "username": data.username,
                },
            )
            ig_account_id = res.scalar_one()

            # 3) Disattiva token attivi precedenti
            await conn.execute(
                text(
                    """
                    UPDATE mfai_app.tokens
                    SET active = FALSE
                    WHERE ig_account_id = :ig_account_id
                      AND active = TRUE
                    """
                ),
                {"ig_account_id": ig_account_id},
            )

            # 4) Inserisci nuovo token attivo
            await conn.execute(
                text(
                    """
                    INSERT INTO mfai_app.tokens (ig_account_id, access_token, expires_at, long_lived, active)
                    VALUES (:ig_account_id, :token, :expires_at, TRUE, TRUE)
                    """
                ),
                {"ig_account_id": ig_account_id, "token": data.token, "expires_at": exp},
            )

            # 5) Log tecnico
            await conn.execute(
                text(
                    """
                    INSERT INTO mfai_app.message_logs (ig_account_id, direction, payload)
                    VALUES (:ig_account_id, 'in', :payload)
                    """
                ),
                {
                    "ig_account_id": ig_account_id,
                    "payload": f"Saved token (len={len(data.token)})",
                },
            )

        return {
            "status": "ok",
            "client_id": client_id,
            "ig_account_id": ig_account_id,
            "expires_at": exp.isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{e.__class__.__name__}: {e}")

# ---------------------------------------------------------
# Elenco clienti + IG account (debug rapido)
# ---------------------------------------------------------
@app.get("/clients")
async def list_clients():
    q = text(
        """
        SELECT
          c.id AS client_id,
          c.name,
          c.email,
          ia.id AS ig_account_id,
          ia.ig_user_id,
          ia.username,
          ia.active,
          (
            SELECT t.expires_at
            FROM mfai_app.tokens t
            WHERE t.ig_account_id = ia.id AND t.active = TRUE
            ORDER BY t.expires_at DESC NULLS LAST
            LIMIT 1
          ) AS active_token_exp
        FROM mfai_app.clients c
        LEFT JOIN mfai_app.instagram_accounts ia ON ia.client_id = c.id
        ORDER BY c.id DESC, ia.id DESC
        LIMIT 50
        """
    )
    async with engine.connect() as conn:
        rows = (await conn.execute(q)).mappings().all()
    return {"items": rows}

# --- Leggi token attivo per un IG user ---
@app.get("/tokens/active")
async def get_active_token(ig_user_id: str):
    q = text(
        """
        SELECT t.access_token, t.expires_at
        FROM mfai_app.tokens t
        JOIN mfai_app.instagram_accounts ia ON ia.id = t.ig_account_id
        WHERE ia.ig_user_id = :ig AND t.active = TRUE
        ORDER BY t.created_at DESC
        LIMIT 1
        """
    )
    async with engine.connect() as conn:
        row = (await conn.execute(q, {"ig": ig_user_id})).first()
    if not row:
        raise HTTPException(status_code=404, detail="Nessun token attivo trovato")
    return {"ig_user_id": ig_user_id, "access_token": row[0], "expires_at": row[1]}

# --- Refresh: ruota il token in 1 chiamata ---
@app.post("/tokens/refresh", dependencies=[Depends(require_api_key)])
async def refresh_token(data: RefreshTokenPayload):
    exp = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)

    async with engine.begin() as conn:
        # trova l'account IG
        row = (
            await conn.execute(
                text(
                    """
                    SELECT id
                    FROM mfai_app.instagram_accounts
                    WHERE ig_user_id = :ig AND active = TRUE
                    LIMIT 1
                    """
                ),
                {"ig": data.ig_user_id},
            )
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="Instagram account non trovato")

        ig_account_id = row[0]

        # disattiva il token attivo esistente
        await conn.execute(
            text(
                """
                UPDATE mfai_app.tokens
                SET active = FALSE
                WHERE ig_account_id = :id AND active = TRUE
                """
            ),
            {"id": ig_account_id},
        )

        # inserisci il nuovo token come attivo
        await conn.execute(
            text(
                """
                INSERT INTO mfai_app.tokens (ig_account_id, access_token, expires_at, long_lived, active)
                VALUES (:ig_account_id, :token, :expires_at, TRUE, TRUE)
                """
            ),
            {"ig_account_id": ig_account_id, "token": data.token, "expires_at": exp},
        )

    return {"status": "ok", "ig_user_id": data.ig_user_id, "expires_at": exp.isoformat()}

# --- Token in scadenza ---
@app.get("/tokens/expiring")
async def tokens_expiring(days: int = 10):
    """Token attivi che scadono entro N giorni (default 10)."""
    threshold = datetime.now(timezone.utc) + timedelta(days=days)
    q = text(
        """
        SELECT
          ia.username,
          ia.ig_user_id,
          t.id AS token_id,
          t.expires_at
        FROM mfai_app.tokens t
        JOIN mfai_app.instagram_accounts ia ON ia.id = t.ig_account_id
        WHERE t.active = TRUE
          AND t.expires_at IS NOT NULL
          AND t.expires_at <= :threshold
        ORDER BY t.expires_at ASC
        LIMIT 200
        """
    )
    async with engine.connect() as conn:
        rows = (await conn.execute(q, {"threshold": threshold})).mappings().all()
    return {"items": rows}
