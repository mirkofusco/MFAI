# ============================================================
# MF.AI — FastAPI (main.py) — UI /ui2 + Prompts + Bot + Logs
# ============================================================

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import engine  # async engine
from app.services.client_prompts import list_prompts_for_client, upsert_prompt_for_client
from app.routers import meta_webhook  # >>> ADD


# === CREA APP
APP_NAME = "MF.AI"
app = FastAPI(title=APP_NAME)

import logging
logger = logging.getLogger("uvicorn")
logger.info(f"[DEBUG] OPENAI_API_KEY loaded: {bool(os.getenv('OPENAI_API_KEY'))}")


#app.include_router(meta_webhook.router)  # >>> ADD


# --- FORCE BASIC AUTH ON /ui2 (regardless of routes) ---
import base64, hmac, os
from starlette.responses import PlainTextResponse

ADMIN_USER = os.getenv("ADMIN_USER", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

@app.middleware("http")
async def protect_ui2(request, call_next):
    path = request.url.path
    logger.info(f"[PROTECT_UI2] path={path}")  # ← AGGIUNGI QUESTA RIGA
    
    if path.startswith("/ui2"):
        auth = request.headers.get("authorization")
        if not auth or not auth.lower().startswith("basic "):
            logger.warning(f"[PROTECT_UI2] BLOCKED: no auth for {path}")  # ← AGGIUNGI
            return PlainTextResponse(
                "Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="MF.AI Admin"'},
            )
        try:
            decoded = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            logger.warning(f"[PROTECT_UI2] BLOCKED: bad auth for {path}")  # ← AGGIUNGI
            return PlainTextResponse(
                "Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="MF.AI Admin"'},
            )
        if not (hmac.compare_digest(username, ADMIN_USER) and hmac.compare_digest(password, ADMIN_PASSWORD)):
            logger.warning(f"[PROTECT_UI2] BLOCKED: wrong credentials for {path}")  # ← AGGIUNGI
            return PlainTextResponse(
                "Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="MF.AI Admin"'},
            )
    return await call_next(request)
# --- END FORCE BASIC AUTH ---

# 🔍 LOG GLOBALE: ogni richiesta POST
@app.middleware("http")
async def log_all_posts(request, call_next):
    if request.method == "POST":
        logger.info(f"🟣 [GLOBAL] POST to {request.url.path} from {request.client.host}")
    return await call_next(request)


# === UI2 router + static
from app.admin_ui import routes as ui2_routes
app.include_router(ui2_routes.router)

if os.path.isdir("app/admin_ui/static"):
    app.mount("/ui2/static", StaticFiles(directory="app/admin_ui/static"), name="ui2_static")

# === UI2: injection middleware (popup centrato, no conflitti CSS) ===
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

UI2_HEAD_INJECT = """
<style>
#mfai-overlay{position:fixed;left:0;top:0;width:100vw;height:100vh;background:rgba(0,0,0,.55);display:none;z-index:2147483646}
#mfai-card{position:fixed;left:50vw;top:50vh;transform:translate(-50%,-50%);width:min(560px,92vw);background:#101218;color:#e8eaef;border:1px solid #282d38;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.6);display:none;z-index:2147483647}
.mfai-hd{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid #282d38}
.mfai-ttl{margin:0;font-size:16px;font-weight:600}
.mfai-x{background:#1a1f2b;border:1px solid #2e3544;border-radius:50%;width:28px;height:28px;color:#cfd5df;cursor:pointer;display:inline-flex;align-items:center;justify-content:center}
.mfai-bd{padding:16px}
.mfai-ft{display:flex;gap:8px;justify-content:flex-end;padding:0 16px 16px}
.mfai-row{display:grid;gap:6px;margin-bottom:12px}
.mfai-inp,.mfai-txa{background:#0c0f15;border:1px solid #2b3240;color:#e8eaef;padding:10px;border-radius:8px;outline:none;width:100%}
.mfai-inp:focus,.mfai-txa:focus{border-color:#4c8bf5;box-shadow:0 0 0 2px rgba(76,139,245,.25)}
.mfai-btn{padding:8px 12px;border-radius:8px;background:#1c2230;color:#e8eaef;border:1px solid #2e3544;cursor:pointer}
.mfai-btn:hover{background:#232b3b}
.mfai-btn-primary{background:#4c8bf5;border-color:#3c74cc;color:#fff}
.mfai-btn-primary:hover{background:#3c74cc}
#mfai-open{position:fixed;right:16px;bottom:16px;z-index:2147483647}
</style>
""".strip()

UI2_BODY_INJECT = """
<!-- UI2_ADD_CLIENT_INJECT -->
<div id="mfai-overlay" aria-hidden="true"></div>

<div id="mfai-card" role="dialog" aria-modal="true" aria-labelledby="mfai-add-title">
  <div class="mfai-hd">
    <h3 id="mfai-add-title" class="mfai-ttl">Aggiungi cliente</h3>
    <button class="mfai-x" id="mfai-close" aria-label="Chiudi">×</button>
  </div>
  <div class="mfai-bd">
    <form id="mfai-form" action="/ui2/clients/create" method="post" autocomplete="off">
      <div class="mfai-row">
        <label class="form-label mb-0">Nome *</label>
        <input class="mfai-inp" type="text" name="name" required>
      </div>
      <div class="mfai-row">
        <label class="form-label mb-0">Instagram username *</label>
        <input class="mfai-inp" type="text" name="instagram_username" placeholder="@cliente" required>
      </div>
      <div class="mfai-row">
        <label class="form-label mb-0">API Key *</label>
        <input class="mfai-inp" type="text" name="api_key" minlength="8" required>
      </div>
      <div class="mfai-row">
        <label class="form-label mb-0">AI Prompt (opzionale)</label>
        <textarea class="mfai-txa" name="ai_prompt" rows="3" placeholder="Prompt personalizzato..."></textarea>
      </div>
      <div class="mfai-row">
        <label class="form-check-label">
          <input class="form-check-input me-2" type="checkbox" name="active"> Attivo
        </label>
      </div>
      <div class="mfai-ft">
        <button type="button" class="mfai-btn" id="mfai-cancel">Annulla</button>
        <button type="submit" class="mfai-btn mfai-btn-primary">Crea</button>
      </div>
    </form>
  </div>
</div>

<button id="mfai-open" class="btn btn-primary btn-sm">+ Aggiungi cliente</button>

<script>
(function(){
  function show(open){
    var overlay=document.getElementById('mfai-overlay');
    var card=document.getElementById('mfai-card');
    if(!overlay||!card) return;
    if(open){
      overlay.style.display='block';
      card.style.display='block';
      card.setAttribute('aria-hidden','false');
      var first=card.querySelector('input[name="name"]');
      if(first){try{first.focus();}catch(e){}}
    }else{
      overlay.style.display='none';
      card.style.display='none';
      card.setAttribute('aria-hidden','true');
    }
  }
  var openBtn=document.getElementById('mfai-open');
  var closeBtn=document.getElementById('mfai-close');
  var cancelBtn=document.getElementById('mfai-cancel');
  var overlay=document.getElementById('mfai-overlay');
  var form=document.getElementById('mfai-form');
  if(openBtn&&!openBtn._b){openBtn.addEventListener('click',function(){show(true)});openBtn._b=1;}
  if(closeBtn&&!closeBtn._b){closeBtn.addEventListener('click',function(){show(false)});closeBtn._b=1;}
  if(cancelBtn&&!cancelBtn._b){cancelBtn.addEventListener('click',function(){show(false)});cancelBtn._b=1;}
  if(overlay&&!overlay._b){overlay.addEventListener('click',function(){show(false)});overlay._b=1;}
  document.addEventListener('keydown',function(e){if(e.key==='Escape')show(false);});
  if(form&&!form._b){
    form.addEventListener('submit',function(e){
      var name=(form.querySelector('input[name="name"]')||{}).value||'';
      var ig=(form.querySelector('input[name="instagram_username"]')||{}).value||'';
      var api=(form.querySelector('input[name="api_key"]')||{}).value||'';
      if(!name.trim()||!ig.trim()||!api.trim()||api.trim().length<8){
        e.preventDefault(); alert('Compila Nome, Username IG e API Key (min 8 caratteri).');
      }
    }); form._b=1;
  }
})();
</script>
""".strip()

class UI2InjectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        ct = resp.headers.get("content-type", "")
        if not request.url.path.startswith("/ui2") or "text/html" not in ct:
            return resp

        # raccogli corpo
        body = b""
        if hasattr(resp, "body_iterator"):
            async for chunk in resp.body_iterator:
                body += chunk
        else:
            body = getattr(resp, "body", b"")

        try:
            html = body.decode("utf-8", errors="ignore")
        except Exception:
            return resp

        # Evita doppia iniezione
        if "UI2_ADD_CLIENT_INJECT" not in html:
            if "</head>" in html:
                html = html.replace("</head>", UI2_HEAD_INJECT + "\n</head>", 1)
            else:
                html = UI2_HEAD_INJECT + "\n" + html
            if "</body>" in html:
                html = html.replace("</body>", UI2_BODY_INJECT + "\n</body>", 1)
            else:
                html = html + "\n" + UI2_BODY_INJECT

        new_resp = StarletteResponse(content=html, status_code=resp.status_code, media_type="text/html")
        for (k, v) in resp.headers.items():
            if k.lower() not in {"content-length", "content-type"}:
                new_resp.headers[k] = v
        return new_resp

# Registra UNA SOLA volta il middleware
app.add_middleware(UI2InjectMiddleware)

# === Client Prompts (inline)
class _PromptUpdate(BaseModel):
    value: str = Field(..., min_length=1, max_length=5000)

@app.get("/admin/client/{client_id}/prompts", dependencies=[Depends(lambda: None)])
async def _get_client_prompts(client_id: int):
    data = await list_prompts_for_client(client_id)
    return [{"key": k, "value": v} for k, v in sorted(data.items())]

@app.put("/admin/client/{client_id}/prompts/{key}", dependencies=[Depends(lambda: None)])
async def _put_client_prompt(client_id: int, key: str, body: _PromptUpdate):
    try:
        saved = await upsert_prompt_for_client(client_id, key, body.value)
        return {"ok": True, "key": saved}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# === CORS
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

# -----------------------------------------------------------
# Robots.txt (permette scraping a facebookexternalhit)
# -----------------------------------------------------------
ROBOTS_TEXT = """User-agent: *
Disallow:

User-agent: facebookexternalhit
Allow: /
"""

@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt():
    return ROBOTS_TEXT

# -----------------------------------------------------------
# Security headers (CSP adattiva + X-Robots-Tag)
# -----------------------------------------------------------
@app.middleware("http")
async def security_headers(request: Request, call_next):
    # ⚠️ NON toccare webhook Meta (deve essere pubblico)
    if request.url.path.startswith("/webhook/"):
        return await call_next(request)
    
    resp = await call_next(request)
    
    # CSP: su /ui2* e /meta/* servono inline style/script per l'injection
    path = request.url.path or ""
    if path.startswith("/ui2") or path.startswith("/meta") or path.startswith("/login"):
        csp = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:"
    else:
        csp = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:"
    
    resp.headers.update(
        {
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
            "Cache-Control": "no-store",
            "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
            "Content-Security-Policy": csp,
            # consenti l'indicizzazione/scaricamento dati pubblici e aiuta lo scraper
            "X-Robots-Tag": "all",
        }
    )
    return resp

# -----------------------------------------------------------
# Templates (Jinja2 opzionali)
# -----------------------------------------------------------
templates = Jinja2Templates(directory="app/templates") if os.path.isdir("app/templates") else None

# -----------------------------------------------------------
# API Key guard (per alcune POST/PUT opzionali)
# -----------------------------------------------------------
API_KEY = os.getenv("API_KEY", "")
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

async def require_api_key(key: Optional[str] = Depends(api_key_header)) -> None:
    if not API_KEY or key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

# -----------------------------------------------------------
# SCHEMA SQL (con bot_enabled) + startup
# -----------------------------------------------------------
# -----------------------------------------------------------
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
  -- bot_enabled BOOLEAN NOT NULL DEFAULT FALSE,  -- già esistente nel DB
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

CREATE TABLE IF NOT EXISTS mfai_app.public_spaces (
  id BIGSERIAL PRIMARY KEY,
  client_id BIGINT NOT NULL REFERENCES mfai_app.clients(id) ON DELETE CASCADE,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  intro TEXT,
  system_prompt TEXT NOT NULL,
  logo_url TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_public_spaces_client
  ON mfai_app.public_spaces(client_id);

CREATE INDEX IF NOT EXISTS idx_public_spaces_active
  ON mfai_app.public_spaces(active);

CREATE TABLE IF NOT EXISTS mfai_app.client_prompts (
  id BIGSERIAL PRIMARY KEY,
  client_id BIGINT NOT NULL REFERENCES mfai_app.clients(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (client_id, key)
);
"""

def _split_sql(sql: str):
    for part in sql.split(";"):
        stmt = part.strip()
        if stmt:
            yield stmt

@app.on_event("startup")
async def ensure_schema():
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS mfai_app AUTHORIZATION mfai_owner;")
        await conn.exec_driver_sql("SET search_path TO mfai_app;")

        for stmt in _split_sql(SCHEMA_SQL):
            await conn.exec_driver_sql(stmt)

        # --- FIX DEADLOCK: aggiungi colonna bot_enabled solo se manca ---
        try:
            await conn.exec_driver_sql("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'mfai_app'
                        AND table_name = 'instagram_accounts'
                        AND column_name = 'bot_enabled'
                    ) THEN
                        ALTER TABLE mfai_app.instagram_accounts
                        ADD COLUMN bot_enabled BOOLEAN NOT NULL DEFAULT FALSE;
                    END IF;
                END $$;
            """)
            logger.info("Column bot_enabled ensured safely.")
        except Exception as e:
            logger.warning(f"bot_enabled check skipped: {e}")

        # --- FIX DEADLOCK: seed demo eseguito una sola volta, senza blocchi ---
        if os.getenv("PUBLIC_SEED_DEMO", "1") == "1":
            try:
                await conn.exec_driver_sql("""
                    DO $$
                    DECLARE
                        cid BIGINT;
                    BEGIN
                        -- Inserisce o recupera il client demo
                        INSERT INTO mfai_app.clients(name, email)
                        VALUES ('Public Demo', 'public.demo@example.local')
                        ON CONFLICT (email) DO UPDATE
                            SET name = EXCLUDED.name
                        RETURNING id INTO cid;

                        -- Inserisce lo spazio pubblico demo se non esiste
                        IF NOT EXISTS (
                            SELECT 1 FROM mfai_app.public_spaces WHERE slug = 'dietologa-demo'
                        ) THEN
                            INSERT INTO mfai_app.public_spaces(
                                client_id, slug, title, intro, system_prompt, logo_url, active
                            )
                            VALUES (
                                cid,
                                'dietologa-demo',
                                'Dietologa — Demo',
                                'Benvenuto nello spazio demo della Dietologa.',
                                'Sei una dietologa professionale. Rispondi SEMPRE in italiano, con tono empatico e pratico. Offri esempi concreti e suggerimenti alimentari bilanciati. Se la domanda è clinica, invita a consultare un medico.',
                                NULL,
                                TRUE
                            );
                        END IF;
                    END $$;
                """)
                logger.info("Public demo seeded safely.")
            except Exception as e:
                logger.warning(f"Seed demo skipped: {e}")





# -----------------------------------------------------------
# Routes base / health
# -----------------------------------------------------------
@app.get("/")
def home():
    return {"ok": True, "app": APP_NAME}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/ping")
def ping():
    return {"pong": True}

@app.get("/db/health")
async def db_health():
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT 'ok'"))
        return {"db": r.scalar_one()}

# -----------------------------------------------------------
# Admin classico (ponte)
# -----------------------------------------------------------
@app.get("/admin/ui", response_class=HTMLResponse)
def admin_ui_bridge():
    return """<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>Admin classico</title></head><body style="font-family:system-ui;padding:20px">
<h2>Admin classico</h2>
<p>Se il vecchio pannello è disponibile, lo trovi qui:
  <a href="/ui/clients">/ui/clients</a>
</p>
<p>Oppure usa la nuova interfaccia: <a href="/ui2">/ui2</a></p>
</body></html>"""

# -----------------------------------------------------------
# UI2 minimal (single page: /ui2 con /ui2.css e /ui2.js)
# -----------------------------------------------------------
@app.get("/ui2", response_class=HTMLResponse)
def ui2_page():
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>MF.AI — Clients</title>
  <link rel="stylesheet" href="/ui2.css">
  <style>
    .connect-btn {
      padding: 8px 14px;
      border-radius: 8px;
      background: #1877f2;
      color: white;
      border: none;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
      transition: all 0.2s;
      box-shadow: 0 2px 8px rgba(24, 119, 242, 0.3);
    }
    .connect-btn:hover {
      background: #166fe5;
      box-shadow: 0 4px 12px rgba(24, 119, 242, 0.4);
      transform: translateY(-1px);
    }
  </style>
</head>
<body>
  <!-- Top Bar: Language + Connect -->
  <div style="position:fixed;top:12px;right:12px;z-index:10000;display:flex;gap:8px;align-items:center;">
    <a href="/meta/login" style="text-decoration:none">
      <button class="connect-btn" title="Connect Instagram Business Account via Meta Login">
        🔗 Connect with Meta
      </button>
    </a>
    <button id="lang-it" class="lang-btn" onclick="setLang('it')" title="Italiano">🇮🇹 IT</button>
    <button id="lang-en" class="lang-btn" onclick="setLang('en')" title="English">🇬🇧 EN</button>
  </div>
  
  <div id="app"></div>
  
  <script>
    // Language data
    window.LANG = {
  it: {
    brand: 'MF.AI — Clienti',
    searchPlaceholder: 'Cerca cliente…',
    loading: 'Carico clienti…',
    noClient: 'Nessun cliente',
    selectClient: 'Seleziona un cliente dalla lista.',
    loadingHint: 'Carico…',
    clientsLabel: 'Clienti: ',
    loadingCard: 'Carico scheda…',
    ready: 'Pronto',
    client: 'Cliente',
    refresh: 'Ricarica scheda',
    adminClassic: 'Admin classico',
    adminClassicTitle: 'Apri l\\'Admin classico in una nuova scheda',
    noResults: 'Nessun risultato',
    bot: 'Bot',
    active: 'Attivo',
    inactive: 'Disattivo',
    enableBot: 'Attiva bot',
    disableBot: 'Disattiva bot',
    noIGAccount: 'Nessun account IG collegato.',
    promptTitle: 'Prompt cliente (unico)',
    promptPlaceholder: 'Scrivi qui il prompt completo...',
    save: 'Salva',
    saved: 'Salvato',
    error: 'Errore',
    sectionDisabled: 'Sezione disabilitata',
    endpointUnavailable: '/ui2/prompts/{client_id} non disponibile',
    retry: 'Riprova',
    tokens: 'Token',
    noTokens: 'Nessun token per questo account.',
    expires: 'scade',
    logs: 'Ultimi log',
    noLogs: 'Nessun log recente.',
    status: 'Stato',
    uiError: '⚠️ Errore UI',
    clientId: 'Client ID',
    ig: 'IG',
    igUserId: 'IG_USER_ID'
  },
  en: {
    brand: 'MF.AI — Clients',
    searchPlaceholder: 'Search client…',
    loading: 'Loading clients…',
    noClient: 'No client selected',
    selectClient: 'Select a client from the list.',
    loadingHint: 'Loading…',
    clientsLabel: 'Clients: ',
    loadingCard: 'Loading card…',
    ready: 'Ready',
    client: 'Client',
    refresh: 'Refresh card',
    adminClassic: 'Classic Admin',
    adminClassicTitle: 'Open Classic Admin in a new tab',
    noResults: 'No results',
    bot: 'Bot',
    active: 'Active',
    inactive: 'Inactive',
    enableBot: 'Enable bot',
    disableBot: 'Disable bot',
    noIGAccount: 'No IG account connected.',
    promptTitle: 'Client Prompt (single)',
    promptPlaceholder: 'Write the complete prompt here...',
    save: 'Save',
    saved: 'Saved',
    error: 'Error',
    sectionDisabled: 'Section disabled',
    endpointUnavailable: '/ui2/prompts/{client_id} unavailable',
    retry: 'Retry',
    tokens: 'Tokens',
    noTokens: 'No tokens for this account.',
    expires: 'expires',
    logs: 'Recent logs',
    noLogs: 'No recent logs.',
    status: 'Status',
    uiError: '⚠️ UI Error',
    clientId: 'Client ID',
    ig: 'IG',
    igUserId: 'IG_USER_ID'
  }
};
    
    window.currentLang = localStorage.getItem('mfai_lang') || 'it';
    
    function setLang(lang) {
      window.currentLang = lang;
      localStorage.setItem('mfai_lang', lang);
      document.querySelectorAll('.lang-btn').forEach(btn => btn.classList.remove('active'));
      const btn = document.getElementById('lang-' + lang);
      if (btn) btn.classList.add('active');
      // Trigger re-render if app is loaded
      if (window.reloadUI) window.reloadUI();
    }
    
    function t(key) {
      return window.LANG[window.currentLang][key] || key;
    }
    
    // Set initial language button state
    document.addEventListener('DOMContentLoaded', function() {
      const btn = document.getElementById('lang-' + window.currentLang);
      if (btn) btn.classList.add('active');
    });
  </script>
  
  <script src="/ui2.js" defer></script>
</body>
</html>"""

@app.get("/ui2.css")
def ui2_css():
    return Response(
        """:root{--bg:#0b0f19;--panel:#12182a;--text:#e8eef6;--muted:#8ea0b5;--border:#1f2942;--accent:#4da3ff;--ok:#22c55e;--bad:#ef4444;--btn:#0f1730}
*{box-sizing:border-box}html,body{height:100%}body{margin:0;background:var(--bg);color:var(--text);font:14px system-ui,Segoe UI,Roboto}
.app{display:grid;grid-template-columns:300px 1fr;height:100vh}
.side{border-right:1px solid var(--border);background:var(--panel);display:flex;flex-direction:column}
.brand{padding:14px 12px;border-bottom:1px solid var(--border);font-weight:700}
.search{padding:10px 12px}.search input{width:100%;padding:10px;border-radius:10px;border:1px solid var(--border);background:#0d1322;color:var(--text)}
.list{overflow:auto;padding:8px}
.item{padding:10px;border-radius:10px;cursor:pointer;margin:6px 4px}
.item:hover{background:#0e162c}.item.active{outline:1px solid var(--accent);background:#0e1a33}
.item h4{margin:0 0 4px 0;font-size:14px}.meta{color:var(--muted);font-size:12px}
.main{display:flex;flex-direction:column}
.bar{display:flex;gap:8px;align-items:center;border-bottom:1px solid var(--border);padding:10px;background:#0d1426;justify-content:space-between}
.crumb{padding:6px 10px;border:1px solid var(--border);border-radius:999px}
.hint{color:var(--muted)}
.content{padding:16px;overflow:auto}
.card{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:14px;margin-bottom:14px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:10px 0}
.kv{display:flex;gap:6px;align-items:center;background:#0e1528;border:1px solid var(--border);padding:8px 10px;border-radius:10px}
.kv b{opacity:.9}
input[type="text"],textarea{width:100%;padding:10px;border-radius:10px;border:1px solid var(--border);background:#0d1322;color:var(--text);font:13px}
button{padding:10px 12px;border-radius:10px;border:1px solid var(--border);background:var(--btn);color:var(--text);cursor:pointer}
button.primary{outline:1px solid var(--accent)}
button.danger{border-color:rgba(239,68,68,.4)}
button:hover{filter:brightness(1.1)}
.chip{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border:1px solid var(--border);border-radius:999px;font-size:12px}
.chip.ok{background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.3);color:var(--ok)}
.chip.bad{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.3);color:var(--bad)}
.chip.neutral{background:#0e1528;color:#c7d2e2}
.group{display:flex;align-items:center;gap:10px}
.headerline{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.title{font-size:18px;font-weight:700}
.log{font-family:ui-monospace,Menlo,Consolas;font-size:12px;background:#0c1222;border:1px solid #1b2442;border-radius:10px;padding:10px;white-space:pre-wrap;max-height:220px;overflow:auto}
#app{display:grid;grid-template-columns:300px 1fr;height:100vh}
.lang-btn{padding:6px 10px;border:1px solid var(--border);border-radius:8px;background:var(--btn);color:var(--text);cursor:pointer;font-size:12px;transition:all 0.2s}
.lang-btn:hover{background:#1a2442;border-color:var(--accent)}
.lang-btn.active{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
""",
        media_type="text/css"
    )

@app.get("/ui2.js")
def ui2_js():
    JS = '''(function(){
  // === USE TRANSLATION FROM PARENT ===
  function t(key) { 
    return window.LANG && window.LANG[window.currentLang] 
      ? window.LANG[window.currentLang][key] 
      : key; 
  }
  
  window.reloadUI = function() {
    boot();
  };
  
  // === ORIGINAL CODE ===
  var api = {
    clients: '/admin/clients',
    accounts: '/admin/accounts',
    tokens: '/admin/tokens',
    logs: '/admin/logs',
    prompts: function(cid){ return '/ui2/prompts/'+cid; },
    adminUI: '/admin/ui'
  };
  var state = {clients:[], accounts:[], tokens:[], selected:null};
  function $(s, el){ return (el||document).querySelector(s); }
  function esc(s){ s=(s==null?'':String(s)); return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function repAll(str, find, repl){ return String(str).split(find).join(repl); }
  function j(u,o){ o=o||{}; o.credentials='include'; return fetch(u,o).then(function(r){ if(!r.ok) return r.text().then(function(t){ throw new Error('HTTP '+r.status+' '+r.statusText+' on '+u+'\\n'+t); }); return r.json(); }); }
  var root = document.getElementById('app');
  
  function boot(){
    root.innerHTML =
      '<aside class="side">'
      + '<div class="brand">'+t('brand')+'</div>'
      + '<div class="search"><input id="q" placeholder="'+t('searchPlaceholder')+'"></div>'
      + '<div id="list" class="list"><div class="card empty">'+t('loading')+'</div></div>'
      + '</aside>'
      + '<main class="main">'
      + '  <div class="bar">'
      + '    <div style="display:flex;align-items:center;gap:8px">'
      + '      <div id="crumb" class="crumb">'+t('noClient')+'</div>'
      + '      <span id="hint" class="hint"></span>'
      + '    </div>'
      + '    <div><a href="/admin/ui" target="_blank"><button title="'+t('adminClassicTitle')+'">'+t('adminClassic')+'</button></a></div>'
      + '  </div>'
      + '  <div id="detail" class="content"><div class="card empty">'+t('selectClient')+'</div></div>'
      + '</main>';
    
    $('#hint').textContent = t('loadingHint');
    Promise.all([ j(api.clients), j(api.accounts), j(api.tokens).catch(function(){ return []; }) ])
    .then(function(arr){
      state.clients=arr[0]; state.accounts=arr[1]; state.tokens=arr[2];
      renderList();
      $('#hint').textContent = t('clientsLabel')+state.clients.length;
      $('#q').addEventListener('input', function(e){ renderList(e.target.value); });
    }).catch(function(err){ showFatal(err); console.error(err); });
  }
  
  function renderList(f){
    f=f||''; var box=$('#list'); box.innerHTML='';
    var q=String(f).trim().toLowerCase();
    var items = state.clients.filter(function(c){
      var s = ((c.id||'')+' '+(c.name||'')+' '+(c.company||'')+' '+(c.email||'')).toLowerCase();
      return !q || s.indexOf(q)!==-1;
    });
    items.forEach(function(c){
      var acc = state.accounts.find(function(a){ return a.client_id===c.id; });
      var el = document.createElement('div');
      var username = acc ? '@'+esc(acc.username) : '—';
      var botEnabled = (acc && acc.bot_enabled) ? 'ON' : 'OFF';
      el.className = 'item' + (state.selected===c.id?' active':'');
      el.innerHTML = '<h4>' + esc(c.name||c.company||(t('client')+' #'+c.id)) + '</h4>'
                   + '<div class="meta">' + username + ' · '+t('bot')+' ' + botEnabled + '</div>';
      el.onclick = function(){ select(c.id); };
      box.appendChild(el);
    });
    if(items.length===0) box.innerHTML='<div class="card empty">'+t('noResults')+'</div>';
  }
  
  function select(clientId){
    state.selected=clientId; renderList($('#q').value||'');
    var c = state.clients.find(function(x){ return x.id===clientId; });
    var acc = state.accounts.find(function(x){ return x.client_id===clientId; });
    $('#crumb').textContent = (c && (c.name||c.company)) ? (c.name||c.company) : (t('client')+' #'+clientId);
    $('#hint').textContent=t('loadingCard');
    var prompts=null, promptsErr=null, logs=[];
    j(api.prompts(clientId)).then(function(p){ prompts=p; })
      .catch(function(e){ promptsErr=String(e); })
      .then(function(){ return j(api.logs+'?client_id='+clientId+'&limit=30').then(function(l){ logs=l; }).catch(function(){}); })
      .then(function(){
        var toks=[]; if(acc){ for(var i=0;i<state.tokens.length;i++){ if(state.tokens[i].ig_account_id===acc.id) toks.push(state.tokens[i]); } }
        renderDetail({c:c,acc:acc,toks:toks,logs:logs,prompts:prompts,promptsErr:promptsErr});
        $('#hint').textContent=t('ready');
      })
      .catch(function(err){ showFatal(err); console.error(err); });
  }
  
  function headerLine(name){
  return '<div class="headerline">'
  + '<div class="title">'+esc(name||t('client'))+'</div>'
  + '<div class="group">'
  +   '<button id="refresh">'+t('refresh')+'</button>'
  +   '<button id="deleteClient" class="danger">Elimina cliente</button>'  // ← QUESTA È LA NUOVA RIGA
  +   '<a href="/admin/ui" target="_blank"><button>'+t('adminClassic')+'</button></a>'
  + '</div>'
  + '</div>';
}
  
  function renderDetail(ctx){
    var c=ctx.c, acc=ctx.acc, toks=ctx.toks, logs=ctx.logs, prompts=ctx.prompts, promptsErr=ctx.promptsErr;
    var d=document.getElementById('detail');
    var statusChip = (acc && acc.active) ? '<span class="chip ok">'+t('active')+'</span>' : '<span class="chip bad">'+t('inactive')+'</span>';
    var botChip = (acc && acc.bot_enabled) ? '<span id="botchip" class="chip ok">ON</span>' : '<span id="botchip" class="chip bad">OFF</span>';
    var botButtons = acc
      ? '<div class="group" id="botButtons">'
          + '<button id="btnBotOn"  class="primary">'+t('enableBot')+'</button>'
          + '<button id="btnBotOff" class="danger">'+t('disableBot')+'</button>'
          + botChip
          + '<span id="bots" class="hint"></span>'
        + '</div>'
      : '<span class="hint">'+t('noIGAccount')+'</span>';
    var promptsCard='';
    if(prompts){
      var val = prompts.system || '';
      val = repAll(repAll(val,'<','&lt;'),'>','&gt;');
      promptsCard =
        '<div class="card">'
        + '<h3>'+t('promptTitle')+'</h3>'
        + '<div class="row"><textarea id="system" rows="8" placeholder="'+t('promptPlaceholder')+'">'+val+'</textarea></div>'
        + '<div class="row" style="justify-content:flex-end">'
        +   '<span id="ps" class="hint" style="margin-right:8px"></span>'
        +   '<button id="savep" class="primary">'+t('save')+'</button>'
        + '</div>'
        + '</div>';
    } else {
      var info = promptsErr ? String(promptsErr).split('\\n')[0] : t('endpointUnavailable');
      promptsCard =
        '<div class="card">'
        + '<h3>'+t('promptTitle')+'</h3>'
        + '<div class="row">'
        +   '<span class="chip neutral">'+t('sectionDisabled')+'</span>'
        +   '<span class="hint">'+esc(info)+'</span>'
        + '</div>'
        + '<div class="row"><button id="retryPrompts">'+t('retry')+'</button>'
        + '<a href="/admin/ui" target="_blank"><button>'+t('adminClassic')+'</button></a></div>'
        + '</div>';
    }
    var toksHtml = '';
    if(toks && toks.length){
      var lines = [];
      for(var i=0;i<toks.length;i++){
        var t_tok=toks[i];
        var when = t_tok.expires_at ? new Date(t_tok.expires_at).toLocaleString() : '—';
        lines.push('• ' + (t_tok.long_lived?'LLT':'SLT') + ' | '+t('expires')+': ' + when + ' | active=' + t_tok.active);
      }
      toksHtml = '<div class="log">'+esc(lines.join('\\n'))+'</div>';
    } else {
      toksHtml = '<div class="meta">'+t('noTokens')+'</div>';
    }
    var logsHtml = '';
    if(logs && logs.length){
      var L = [];
      for(var i=0;i<logs.length;i++){
        var x=logs[i];
        var ts = new Date(x.ts || x.created_at).toLocaleString();
        var dir = x.direction || '';
        var payload = x.payload ? JSON.stringify(x.payload) : '';
        L.push('['+ts+'] '+dir+' '+payload);
      }
      logsHtml = '<div class="log">'+esc(L.join('\\n'))+'</div>';
    } else {
      logsHtml = '<div class="meta">'+t('noLogs')+'</div>';
    }
    d.innerHTML =
      '<div class="card">'
      +   headerLine((c && (c.name||c.company)) ? (c.name||c.company) : (t('client')+' #'+c.id))
      +   '<div class="row">'
      +     '<div class="kv"><b>Client ID</b> '+String(c.id)+'</div>'
      +     '<div class="kv"><b>IG</b> '+(acc?('@'+esc(acc.username)):'—')+'</div>'
      +     '<div class="kv"><b>IG_USER_ID</b> '+(acc?esc(acc.ig_user_id):'—')+'</div>'
      +     '<div class="kv"><b>'+t('status')+'</b> '+statusChip+'</div>'
      +   '</div>'
      +   '<div class="row">'+botButtons+'</div>'
      + '</div>'
      + promptsCard
      + '<div class="card"><h3>'+t('tokens')+'</h3>'+toksHtml+'</div>'
      + '<div class="card"><h3>'+t('logs')+'</h3>'+logsHtml+'</div>';
    var refresh=$('#refresh'); if(refresh){ refresh.onclick=function(){ select(c.id); }; }
    var refresh=$('#refresh'); if(refresh){ refresh.onclick=function(){ select(c.id); }; }

// ← AGGIUNGI QUESTE RIGHE QUI:
var delBtn=$('#deleteClient');
if(delBtn){
  delBtn.onclick=function(){
    var nome = (c.name||c.company||('#'+c.id));
    if(!confirm('Eliminare il cliente "' + nome + '"? Operazione irreversibile!')){
      return;
    }
    j('/admin/clients/'+c.id, {method:'DELETE'})
      .then(function(){ 
        window.location.href='/ui2?ok=deleted'; 
      })
      .catch(function(err){ 
        alert('Errore eliminazione: '+err.message); 
      });
  };
}

var btnOn=$('#btnBotOn'), btnOff=$('#btnBotOff'), bots=$('#bots'), botchip=$('#botchip');
    var btnOn=$('#btnBotOn'), btnOff=$('#btnBotOff'), bots=$('#bots'), botchip=$('#botchip');
    function setBot(enabled){
      bots.textContent='…';
      j(api.accounts,{
        method:'PATCH',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ ig_user_id: acc.ig_user_id, bot_enabled: enabled })
      }).then(function(){
        botchip.textContent = enabled ? 'ON' : 'OFF';
        botchip.className = 'chip ' + (enabled ? 'ok' : 'bad');
        bots.textContent=t('saved');
        for(var i=0;i<state.accounts.length;i++){
          if(state.accounts[i].id===acc.id){ state.accounts[i].bot_enabled = enabled; break; }
        }
      }).catch(function(){ bots.textContent=t('error'); });
    }
    if(btnOn && btnOff && acc){ btnOn.onclick=function(){ setBot(true); }; btnOff.onclick=function(){ setBot(false); }; }
    var savep=$('#savep'), ps=$('#ps');
    if(savep){
      savep.onclick=function(){
        ps.textContent='…';
        fetch(api.prompts(c.id),{
          method:'PUT',
          credentials:'include',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({ system: $('#system').value })
        }).then(function(){ ps.textContent=t('saved'); })
          .catch(function(){ ps.textContent=t('error'); });
      };
    }
    var retry=$('#retryPrompts'); if(retry){ retry.onclick=function(){ select(c.id); }; }
  }
  
  function showFatal(msg){
    var app=document.getElementById('app');
    app.innerHTML='<div style="padding:20px;font-family:system-ui"><h2>'+t('uiError')+'</h2>'
      + '<pre style="white-space:pre-wrap;background:#111;color:#eee;padding:12px;border-radius:8px;border:1px solid #333;max-height:50vh;overflow:auto">'
      + esc(String(msg)) + '</pre></div>';
  }
  
  try { boot(); } catch (e) { showFatal(e); console.error(e); }
})();'''
    return Response(JS, media_type="application/javascript")

# -----------------------------------------------------------
# Admin JSON minimi che servono alla UI /ui2
# -----------------------------------------------------------
# 1) Clients (lista)
@app.get("/admin/clients")
async def admin_clients():
    q = text("SELECT id, name, email FROM mfai_app.clients ORDER BY id DESC LIMIT 500")
    async with engine.connect() as conn:
        rows = (await conn.execute(q)).mappings().all()
    return rows

# 2) Accounts (GET lista + PATCH toggle bot)
class PatchAccountPayload(BaseModel):
    ig_user_id: str
    bot_enabled: bool

@app.get("/admin/accounts")
async def admin_accounts():
    q = text("""
      SELECT id, client_id, ig_user_id, username, active, bot_enabled, created_at
      FROM mfai_app.instagram_accounts
      ORDER BY id DESC
      LIMIT 1000
    """)
    async with engine.connect() as conn:
        rows = (await conn.execute(q)).mappings().all()
    return rows

@app.patch("/admin/accounts")
async def admin_accounts_patch(body: PatchAccountPayload):
    ig = body.ig_user_id.strip()
    async with engine.begin() as conn:
        res = await conn.execute(text("""
          UPDATE mfai_app.instagram_accounts
          SET bot_enabled = :flag
          WHERE ig_user_id = :ig
          RETURNING id
        """), {"flag": body.bot_enabled, "ig": ig})
        row = res.first()
        if not row:
            raise HTTPException(status_code=404, detail="Instagram account non trovato")
    return {"status": "ok", "ig_user_id": ig, "bot_enabled": body.bot_enabled}

# 3) Logs (GET)
@app.get("/admin/logs")
async def admin_logs(
    client_id: Optional[int] = Query(None),
    ig_account_id: Optional[int] = Query(None),
    limit: int = Query(30, ge=1, le=500),
):
    if client_id:
        q = text("""
            SELECT ml.id, ml.ig_account_id, ml.direction, ml.payload, ml.created_at
            FROM mfai_app.message_logs ml
            WHERE ml.ig_account_id IN (
              SELECT ia.id FROM mfai_app.instagram_accounts ia WHERE ia.client_id = :cid
            )
            ORDER BY ml.created_at DESC
            LIMIT :lim
        """)
        params: Dict[str, Any] = {"cid": client_id, "lim": limit}
    elif ig_account_id:
        q = text("""
            SELECT ml.id, ml.ig_account_id, ml.direction, ml.payload, ml.created_at
            FROM mfai_app.message_logs ml
            WHERE ml.ig_account_id = :aid
            ORDER BY ml.created_at DESC
            LIMIT :lim
        """)
        params = {"aid": ig_account_id, "lim": limit}
    else:
        q = text("""
            SELECT ml.id, ml.ig_account_id, ml.direction, ml.payload, ml.created_at
            FROM mfai_app.message_logs ml
            ORDER BY ml.created_at DESC
            LIMIT :lim
        """)
        params = {"lim": limit}
    async with engine.connect() as conn:
        rows = (await conn.execute(q, params)).mappings().all()
    return rows

# 4) Tokens (GET elenco “safe”)
@app.get("/admin/tokens")
async def admin_tokens(
    client_id: Optional[int] = Query(None),
    ig_account_id: Optional[int] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
):
    base = """
        SELECT t.id, t.ig_account_id, t.expires_at, t.long_lived, t.active, t.created_at
        FROM mfai_app.tokens t
    """
    params: Dict[str, object] = {"lim": limit}
    if client_id:
        q = text(base + """
            WHERE t.ig_account_id IN (
              SELECT ia.id FROM mfai_app.instagram_accounts ia WHERE ia.client_id = :cid
            )
            ORDER BY t.created_at DESC
            LIMIT :lim
        """)
        params["cid"] = client_id
    elif ig_account_id:
        q = text(base + """
            WHERE t.ig_account_id = :aid
            ORDER BY t.created_at DESC
            LIMIT :lim
        """)
        params["aid"] = ig_account_id
    else:
        q = text(base + """
            ORDER BY t.created_at DESC
            LIMIT :lim
        """)
    async with engine.connect() as conn:
        rows = (await conn.execute(q, params)).mappings().all()
    return rows

# -----------------------------------------------------------
# Prompts endpoints dedicati per /ui2 (singolo campo "system")
# -----------------------------------------------------------
class ClientPromptSystem(BaseModel):
    system: str = ""

@app.get("/ui2/prompts/{client_id}")
async def ui2_get_prompts(client_id: int):
    async with engine.connect() as conn:
        rows = (await conn.execute(text("""
          SELECT key, value
          FROM mfai_app.client_prompts
          WHERE client_id = :cid
        """), {"cid": client_id})).mappings().all()
    data: Dict[str, str] = {r["key"]: r["value"] for r in rows}
    return {"system": data.get("system", "")}

@app.put("/ui2/prompts/{client_id}")
async def ui2_put_prompts(client_id: int, body: ClientPromptSystem):
    async with engine.begin() as conn:
        await conn.execute(text("""
          INSERT INTO mfai_app.client_prompts (client_id, key, value)
          VALUES (:cid, 'system', :v)
          ON CONFLICT (client_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """), {"cid": client_id, "v": body.system})
    return {"status": "ok"}

# -----------------------------------------------------------
# OAuth callback (generico: per debug)
# -----------------------------------------------------------
@app.get("/oauth/callback")
async def oauth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code:
        raise HTTPException(status_code=400, detail="Missing ?code in callback")
    return {"status": "ok", "received_code": True, "code_preview": (code[:12] + "..."), "state": state}

# -----------------------------------------------------------
# Token utilities
# -----------------------------------------------------------
class SaveTokenPayload(BaseModel):
    token: str = Field(..., min_length=5)
    ig_user_id: str = Field(..., min_length=3)
    username: str = Field(..., min_length=1)
    client_name: str = "Default Client"
    client_email: Optional[str] = None
    expires_at: Optional[datetime] = None

class RefreshTokenPayload(BaseModel):
    ig_user_id: str = Field(..., min_length=3)
    token: str = Field(..., min_length=5)
    expires_in_days: int = Field(default=60, ge=1, le=365)

@app.post("/save-token", dependencies=[Depends(require_api_key)])
async def save_token(data: SaveTokenPayload):
    try:
        exp = data.expires_at or (datetime.now(timezone.utc) + timedelta(days=60))
        async with engine.begin() as conn:
            client_id = (await conn.execute(
                text("""
                  INSERT INTO mfai_app.clients (name, email)
                  VALUES (:name, COALESCE(:email, REPLACE(LOWER(:name),' ','_') || '@example.local'))
                  ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
                  RETURNING id
                """), {"name": data.client_name, "email": data.client_email}
            )).scalar_one()

            ig_account_id = (await conn.execute(
                text("""
                  INSERT INTO mfai_app.instagram_accounts (client_id, ig_user_id, username, active)
                  VALUES (:client_id, :ig_user_id, :username, TRUE)
                  ON CONFLICT (ig_user_id) DO UPDATE SET username = EXCLUDED.username, active = TRUE
                  RETURNING id
                """), {"client_id": client_id, "ig_user_id": data.ig_user_id, "username": data.username}
            )).scalar_one()

            await conn.execute(text("UPDATE mfai_app.tokens SET active = FALSE WHERE ig_account_id = :ig AND active = TRUE"),
                               {"ig": ig_account_id})

            await conn.execute(text("""
              INSERT INTO mfai_app.tokens (ig_account_id, access_token, expires_at, long_lived, active)
              VALUES (:ig_account_id, :token, :exp, TRUE, TRUE)
            """), {"ig_account_id": ig_account_id, "token": data.token, "exp": exp})

            await conn.execute(text("""
              INSERT INTO mfai_app.message_logs (ig_account_id, direction, payload)
              VALUES (:id, 'in', :p)
            """), {"id": ig_account_id, "p": f"Saved token (len={len(data.token)})"})

        return {"status":"ok","client_id":client_id,"ig_account_id":ig_account_id,"expires_at":exp.isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{e.__class__.__name__}: {e}")

@app.get("/tokens/active")
async def get_active_token(ig_user_id: str):
    q = text("""
        SELECT t.access_token, t.expires_at
        FROM mfai_app.tokens t
        JOIN mfai_app.instagram_accounts ia ON ia.id = t.ig_account_id
        WHERE ia.ig_user_id = :ig AND t.active = TRUE
        ORDER BY t.created_at DESC
        LIMIT 1
    """)
    async with engine.connect() as conn:
        row = (await conn.execute(q, {"ig": ig_user_id})).first()
    if not row:
        raise HTTPException(status_code=404, detail="Nessun token attivo trovato")
    return {"ig_user_id": ig_user_id, "access_token": row[0], "expires_at": row[1]}

@app.post("/tokens/refresh", dependencies=[Depends(require_api_key)])
async def refresh_token(data: RefreshTokenPayload):
    exp = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)
    async with engine.begin() as conn:
        row = (await conn.execute(
            text("SELECT id FROM mfai_app.instagram_accounts WHERE ig_user_id = :ig AND active = TRUE LIMIT 1"),
            {"ig": data.ig_user_id},
        )).first()
        if not row:
            raise HTTPException(status_code=404, detail="Instagram account non trovato")
        ig_account_id = row[0]
        await conn.execute(text("UPDATE mfai_app.tokens SET active = FALSE WHERE ig_account_id = :id AND active = TRUE"),
                           {"id": ig_account_id})
        await conn.execute(text("""
          INSERT INTO mfai_app.tokens (ig_account_id, access_token, expires_at, long_lived, active)
          VALUES (:ig, :token, :exp, TRUE, TRUE)
        """), {"ig": ig_account_id, "token": data.token, "exp": exp})
    return {"status": "ok", "ig_user_id": data.ig_user_id, "expires_at": exp.isoformat()}

# -----------------------------------------------------------
# Include router esterni
# -----------------------------------------------------------
try:
    from app.routers.meta_webhook import router as meta_webhook_router
    app.include_router(meta_webhook_router)
except Exception as e:
    print("Meta webhook router non caricato:", e)

try:
    from app.routers import admin_api
    app.include_router(admin_api.router)
except Exception as e:
    print("Admin routers non caricati:", e)

# === Meta Login (OAuth) ===
try:
    from app.routers import meta_login
    app.include_router(meta_login.router)
except Exception as e:
    print("Meta login router non caricato:", e)

# Alias comodo: /login -> /meta/login
@app.get("/login", include_in_schema=False)
def login_alias():
    return Response(status_code=307, headers={"Location": "/meta/login"})

# -----------------------------------------------------------
# Debug
# -----------------------------------------------------------
@app.get("/__debug")
def __debug():
    return {
        "ok": True,
        "file": __file__,
        "repo_hint": "MFAI",
        "koyeb_commit": os.getenv("KOYEB_GIT_COMMIT", "local")
    }

@app.get("/__routes")
def __routes():
    return {"routes":[getattr(r, "path", None) for r in app.routes]}

@app.on_event("shutdown")  # >>> ADD
async def _shutdown_pool():
    # chiude il client httpx riusato dal webhook Meta
    await meta_webhook._close_httpx()
  
  
  
  
