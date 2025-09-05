# ============================================================
# MF.AI — FastAPI (main.py) — UI /ui2 + Prompts endpoints
# ============================================================

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import engine  # engine async verso Neon

APP_NAME = "MF.AI"
app = FastAPI(title=APP_NAME)

# -----------------------------------------------------------
# UI /ui2 (CSP-safe: niente inline; asset locali)
# -----------------------------------------------------------
@app.get("/ui2", response_class=HTMLResponse)
def ui2_page():
    return """<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>MF.AI — Clienti</title>
  <link rel="stylesheet" href="/ui2.css">
</head>
<body>
  <div id="app"></div>
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
button:hover{filter:brightness(1.1)}
.switch input{display:none}.switch .track{width:46px;height:26px;border-radius:999px;background:#32405e;position:relative}
.switch .thumb{position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:.18s}
.switch input:checked + .track{background:var(--ok)}.switch input:checked + .track .thumb{left:23px}
.chip{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border:1px solid var(--border);border-radius:999px;font-size:12px}
.chip.ok{background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.3);color:var(--ok)}
.chip.bad{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.3);color:var(--bad)}
.chip.neutral{background:#0e1528;color:#c7d2e2}
.group{display:flex;align-items:center;gap:10px}
.headerline{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.title{font-size:18px;font-weight:700}
.log{font-family:ui-monospace,Menlo,Consolas;font-size:12px;background:#0c1222;border:1px solid #1b2442;border-radius:10px;padding:10px;white-space:pre-wrap;max-height:220px;overflow:auto}
#app{display:grid;grid-template-columns:300px 1fr;height:100vh}
""",
        media_type="text/css"
    )

@app.get("/ui2.js")
def ui2_js():
    return Response(
        r"""
(function(){
  // API endpoints — NOTA: prompts usa rotta dedicata /ui2/prompts
  const api={
    clients:'/admin/clients',
    accounts:'/admin/accounts',       // lasciamo questo (toggle Bot) se il tuo backend già lo espone
    tokens:'/admin/tokens',
    logs:'/admin/logs',
    prompts:(cid)=>`/ui2/prompts/${cid}`,  // <-- nuove route implementate in questo file
    adminUI:'/admin/ui'
  };

  const state={clients:[],accounts:[],tokens:[],selected:null};
  const $=(s,el=document)=>el.querySelector(s);
  const esc=(s)=> (s??"").replace(/[&<>"]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[m]));

  async function j(u,o={}){const r=await fetch(u,{...o,credentials:'include'});if(!r.ok){const t=await r.text().catch(()=> "");throw new Error(`HTTP ${r.status} ${r.statusText} on ${u}\n${t}`);}return r.json();}

  // Shell
  const root=document.getElementById('app');
  root.innerHTML=`
    <aside class="side">
      <div class="brand">MF.AI — Clienti</div>
      <div class="search"><input id="q" placeholder="Cerca cliente…"></div>
      <div id="list" class="list"><div class="card empty">Carico clienti…</div></div>
    </aside>
    <main class="main">
      <div class="bar">
        <div style="display:flex;align-items:center;gap:8px">
          <div id="crumb" class="crumb">Nessun cliente</div>
          <span id="hint" class="hint"></span>
        </div>
        <div>
          <a href="/admin/ui" target="_blank"><button title="Apri l'Admin classico in una nuova scheda">Admin classico</button></a>
        </div>
      </div>
      <div id="detail" class="content">
        <div class="card empty">Seleziona un cliente dalla lista.</div>
      </div>
    </main>
  `;

  async function boot(){
    try{
      $('#hint').textContent='Carico…';
      const [c,a,t]=await Promise.all([j(api.clients),j(api.accounts),j(api.tokens)]);
      state.clients=c; state.accounts=a; state.tokens=t;
      renderList(); $('#hint').textContent=`Clienti: ${c.length}`;
      $('#q').addEventListener('input',e=>renderList(e.target.value));
    }catch(err){ showFatal(err); console.error(err); }
  }

  function renderList(f=''){
    const box=$('#list'); box.innerHTML='';
    const q=(f||'').trim().toLowerCase();
    const items=state.clients.filter(c=>{const s=`${c.id||''} ${c.name||''} ${c.company||''}`.toLowerCase(); return !q||s.includes(q);});
    for(const c of items){
      const acc=state.accounts.find(a=>a.client_id===c.id);
      const el=document.createElement('div'); el.className='item'+(state.selected===c.id?' active':'');
      el.innerHTML=`<h4>${esc(c.name||c.company||('Cliente #'+c.id))}</h4><div class="meta">${acc?('@'+esc(acc.username)):'—'} · Bot ${acc?.bot_enabled?'ON':'OFF'}</div>`;
      el.onclick=()=>select(c.id); box.appendChild(el);
    }
    if(items.length===0) box.innerHTML='<div class="card empty">Nessun risultato</div>';
  }

  async function select(clientId){
    try{
      state.selected=clientId; renderList($('#q').value||'');
      const c=state.clients.find(x=>x.id===clientId);
      const acc=state.accounts.find(a=>a.client_id===clientId);
      $('#crumb').textContent=c?.name||c?.company||('Cliente #'+clientId);
      $('#hint').textContent='Carico scheda…';

      let prompts=null, promptsErr=null, logs=[];
      try{ prompts=await j(api.prompts(clientId)); }catch(e){ promptsErr=String(e); }
      try{ logs=await j(api.logs+`?client_id=${clientId}&limit=30`);}catch(_e){}

      const toks=state.tokens.filter(t=>t.ig_account_id===acc?.id);
      renderDetail({c,acc,toks,logs,prompts,promptsErr});
      $('#hint').textContent='Pronto';
    }catch(err){ showFatal(err); console.error(err); }
  }

  function headerLine(name){
    return `
      <div class="headerline">
        <div class="title">${esc(name||'Cliente')}</div>
        <div class="group">
          <button id="refresh">Ricarica scheda</button>
          <a href="/admin/ui" target="_blank"><button>Admin classico</button></a>
        </div>
      </div>`;
  }

  function renderDetail({c,acc,toks,logs,prompts,promptsErr}){
    const d=document.getElementById('detail');
    const statusChip = acc?.active ? `<span class="chip ok">Attivo</span>` : `<span class="chip bad">Disattivo</span>`;
    const botChip = acc?.bot_enabled ? `<span id="botchip" class="chip ok">ON</span>` : `<span id="botchip" class="chip bad">OFF</span>`;

    let promptsCard='';
    if(prompts){
      promptsCard=`
        <div class="card">
          <h3>Prompt cliente</h3>
          <div class="row"><input id="greet" type="text" placeholder="Greeting" value="${(prompts?.greeting??'').replaceAll('"','&quot;')}"></div>
          <div class="row"><input id="fallback" type="text" placeholder="Fallback" value="${(prompts?.fallback??'').replaceAll('"','&quot;')}"></div>
          <div class="row"><input id="handoff" type="text" placeholder="Handoff" value="${(prompts?.handoff??'').replaceAll('"','&quot;')}"></div>
          <div class="row"><input id="legal" type="text" placeholder="Legal disclaimer" value="${(prompts?.legal??'').replaceAll('"','&quot;')}"></div>
          <div class="row" style="justify-content:flex-end">
            <span id="ps" class="hint" style="margin-right:8px"></span>
            <button id="savep" class="primary">Salva modifiche</button>
          </div>
        </div>`;
    } else {
      const info = promptsErr ? promptsErr.split('\n')[0] : 'endpoint non raggiungibile';
      promptsCard=`
        <div class="card">
          <h3>Prompt cliente</h3>
          <div class="row">
            <span class="chip neutral">Sezione disabilitata</span>
            <span class="hint">/ui2/prompts/{client_id} non disponibile (${esc(info)}).</span>
          </div>
          <div class="row">
            <button id="retryPrompts">Riprova</button>
            <a href="/admin/ui" target="_blank"><button>Admin classico</button></a>
          </div>
        </div>`;
    }

    d.innerHTML=`
      <div class="card">
        ${headerLine(c?.name||c?.company||('Cliente #'+c.id))}
        <div class="row">
          <div class="kv"><b>Client ID</b> ${String(c.id)}</div>
          <div class="kv"><b>IG</b> ${acc?('@'+acc.username):'—'}</div>
          <div class="kv"><b>IG_USER_ID</b> ${acc?.ig_user_id||'—'}</div>
          <div class="kv"><b>Stato</b> ${statusChip}</div>
        </div>
        <div class="row">
          <div class="group">
            <b>Bot</b>
            <label class="switch">
              <input id="bot" type="checkbox" ${acc?.bot_enabled?'checked':''} ${acc?'':'disabled'}>
              <span class="track"><span class="thumb"></span></span>
            </label>
            ${botChip}
            <span id="bots" class="hint"></span>
          </div>
        </div>
      </div>

      ${promptsCard}

      <div class="card">
        <h3>Token</h3>
        ${toks.length?`<div class="log">${toks.map(t=>`• ${t.long_lived?'LLT':'SLT'} | scade: ${new Date(t.expires_at).toLocaleString()} | active=${t.active}`).join('\n')}</div>`:'<div class="meta">Nessun token per questo account.</div>'}
      </div>

      <div class="card">
        <h3>Ultimi log</h3>
        ${logs?.length?`<div class="log">${logs.map(x=>`[${new Date(x.ts||x.created_at).toLocaleString()}] ${x.direction||''} ${x.payload?JSON.stringify(x.payload):''}`).join('\n')}</div>`:'<div class="meta">Nessun log recente.</div>'}
      </div>
    `;

    // azioni
    const refresh=$('#refresh'); if(refresh){ refresh.onclick=()=>select(c.id); }

    const bot=$('#bot'), bots=$('#bots'), botchip=$('#botchip');
    if(bot&&acc){
      bot.onchange=async()=>{
        try{
          bots.textContent='…';
          await fetch(api.accounts,{method:'PATCH',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({ig_user_id:acc.ig_user_id,bot_enabled:bot.checked})});
          botchip.textContent = bot.checked ? 'ON' : 'OFF';
          botchip.className = 'chip ' + (bot.checked ? 'ok' : 'bad');
          bots.textContent='Salvato';
        }catch(e){
          bots.textContent='Errore';
          bot.checked=!bot.checked; // rollback se fallisce
        }
      };
    }

    const savep=$('#savep'), ps=$('#ps');
    if(savep){
      savep.onclick=async()=>{
        try{
          ps.textContent='…';
          await fetch(api.prompts(c.id),{
            method:'PUT',
            credentials:'include',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({
              greeting:$('#greet').value,
              fallback:$('#fallback').value,
              handoff:$('#handoff').value,
              legal:$('#legal').value
            })
          });
          ps.textContent='Salvato';
        }catch(e){ ps.textContent='Errore'; }
      };
    }
    const retry=$('#retryPrompts'); if(retry){ retry.onclick=()=>select(c.id); }
  }

  function showFatal(msg){
    const app=document.getElementById('app');
    app.innerHTML=`<div style="padding:20px;font-family:system-ui"><h2>⚠️ Errore UI</h2>
    <pre style="white-space:pre-wrap;background:#111;color:#eee;padding:12px;border-radius:8px;border:1px solid #333;max-height:50vh;overflow:auto">${esc(String(msg))}</pre></div>`;
  }

  try { boot(); } catch (e) { showFatal(e); console.error(e); }
})();
""",
        media_type="application/javascript"
    )

# -----------------------------------------------------------
# Endpoint Admin classico (ponte, evita 404)
# -----------------------------------------------------------
@app.get("/admin/ui", response_class=HTMLResponse)
def admin_ui_bridge():
    # pagina ponte: prova a rimandare al vecchio UI (se esiste /ui/clients)
    return """<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>Admin classico</title></head><body style="font-family:system-ui;padding:20px">
<h2>Admin classico</h2>
<p>Se il vecchio pannello è disponibile, lo trovi qui:
  <a href="/ui/clients">/ui/clients</a>
</p>
<p>In alternativa puoi usare la nuova interfaccia: <a href="/ui2">/ui2</a></p>
</body></html>"""

# -----------------------------------------------------------
# Static (facoltativo)
# -----------------------------------------------------------
if os.path.isdir("app/admin_ui/static"):
    app.mount("/static", StaticFiles(directory="app/admin_ui/static"), name="static")

# -----------------------------------------------------------
# Router esterni (import safe)
# -----------------------------------------------------------
# Webhook Meta
try:
    from app.routers.meta_webhook import router as meta_webhook_router
    app.include_router(meta_webhook_router)
except Exception as e:
    print("Meta webhook router non caricato:", e)

# Admin API JSON (clients/accounts/tokens/logs)
try:
    from app.routers import admin_api
    app.include_router(admin_api.router)
except Exception as e:
    print("Admin API router non caricato:", e)

# Admin Prompts JSON (se c'è; ma noi usiamo /ui2/prompts/*)
try:
    from app.routers import admin_prompts
    app.include_router(admin_prompts.router)
except Exception as e:
    print("Admin Prompts router non caricato:", e)

# Admin UI classica (se esiste)
try:
    from app.admin_ui.routes import router as admin_ui_router
    app.include_router(admin_ui_router)
except Exception as e:
    print("Admin UI router non caricato:", e)

# Admin client prompts (overview) — opzionale
try:
    from app.routers import admin_client_prompts
    app.include_router(admin_client_prompts.router)
except Exception as e:
    print("Admin Client Prompts router non caricato:", e)

# Public UI (/c/*) — opzionale
try:
    from app.public_ui.routes import router as public_ui_router  # type: ignore
    app.include_router(public_ui_router)
except Exception as e:
    print("Public UI router non caricato:", e)

# -----------------------------------------------------------
# Templates (Jinja2 opzionali)
# -----------------------------------------------------------
templates = Jinja2Templates(directory="app/templates") if os.path.isdir("app/templates") else None

# -----------------------------------------------------------
# CORS
# -----------------------------------------------------------
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
# Security headers (CSP: solo self; no inline)
# -----------------------------------------------------------
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
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:"
            ),
        }
    )
    return resp

# -----------------------------------------------------------
# API Key guard (per alcune POST/PUT)
# -----------------------------------------------------------
API_KEY = os.getenv("API_KEY", "")
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

async def require_api_key(key: Optional[str] = Depends(api_key_header)) -> None:
    if not API_KEY or key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

# -----------------------------------------------------------
# verify_admin (fallback se modulo assente)
# -----------------------------------------------------------
try:
    from app.security_admin import verify_admin
except Exception:
    async def verify_admin():
        return None

# -----------------------------------------------------------
# SCHEMA SQL
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
        who = (await conn.execute(text("SELECT current_user, current_schema();"))).first()
        print("DB identity:", who)
        for stmt in _split_sql(SCHEMA_SQL):
            await conn.exec_driver_sql(stmt)
        if os.getenv("PUBLIC_SEED_DEMO", "1") == "1":
            await conn.exec_driver_sql("""
            DO $$
            DECLARE cid BIGINT;
            BEGIN
              INSERT INTO mfai_app.clients(name, email)
              VALUES ('Public Demo', 'public.demo@example.local')
              ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
              RETURNING id INTO cid;

              INSERT INTO mfai_app.public_spaces(client_id, slug, title, intro, system_prompt, logo_url, active)
              VALUES (
                cid,
                'dietologa-demo',
                'Dietologa — Demo',
                'Benvenuto nello spazio demo della Dietologa.',
                'Sei una dietologa professionale. Rispondi SEMPRE in italiano, con tono empatico e pratico. Offri esempi concreti e suggerimenti alimentari bilanciati. Se la domanda è clinica, invita a consultare un medico.',
                NULL,
                TRUE
              )
              ON CONFLICT (slug) DO UPDATE
                SET client_id = EXCLUDED.client_id,
                    title = EXCLUDED.title,
                    intro = EXCLUDED.intro,
                    system_prompt = EXCLUDED.system_prompt,
                    active = TRUE;
            END $$;
            """)

# -----------------------------------------------------------
# Routes base
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

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if not templates:
        return HTMLResponse("<!doctype html><html><body>Login non configurato (templates mancanti).</body></html>")
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/db/health")
async def db_health():
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT 'ok'"))
        return {"db": r.scalar_one()}

# --- OAuth Callback Instagram ---
@app.get("/oauth/callback")
async def oauth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code:
        raise HTTPException(status_code=400, detail="Missing ?code in callback")
    return {"status": "ok", "received_code": True, "code_preview": (code[:12] + "..."), "state": state}

# -----------------------------------------------------------
# Modelli I/O
# -----------------------------------------------------------
class SaveTokenPayload(BaseModel):
    token: str = Field(..., min_length=5)
    ig_user_id: str = Field(..., min_length=3)
    username: str = Field(..., min_length=1)
    client_name: str = "Default Client"
    client_email: Optional[str] = None
    expires_at: Optional[datetime] = None  # se None -> +60 giorni

class RefreshTokenPayload(BaseModel):
    ig_user_id: str = Field(..., min_length=3)
    token: str = Field(..., min_length=5)
    expires_in_days: int = Field(default=60, ge=1, le=365)

# -----------------------------------------------------------
# Save token + upsert client/account/token
# -----------------------------------------------------------
@app.post("/save-token", dependencies=[Depends(require_api_key)])
async def save_token(data: SaveTokenPayload):
    try:
        exp = data.expires_at or (datetime.now(timezone.utc) + timedelta(days=60))
        async with engine.begin() as conn:
            # 1) Upsert client
            res = await conn.execute(
                text("""
                    INSERT INTO mfai_app.clients (name, email)
                    VALUES (:name, COALESCE(:email, REPLACE(LOWER(:name),' ','_') || '@example.local'))
                    ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                """),
                {"name": data.client_name, "email": data.client_email},
            )
            client_id = res.scalar_one()

            # 2) Upsert IG account
            res = await conn.execute(
                text("""
                    INSERT INTO mfai_app.instagram_accounts (client_id, ig_user_id, username, active)
                    VALUES (:client_id, :ig_user_id, :username, TRUE)
                    ON CONFLICT (ig_user_id) DO UPDATE
                      SET username = EXCLUDED.username, active = TRUE
                    RETURNING id
                """),
                {"client_id": client_id, "ig_user_id": data.ig_user_id, "username": data.username},
            )
            ig_account_id = res.scalar_one()

            # 3) Disattiva token attivo precedente
            await conn.execute(
                text("UPDATE mfai_app.tokens SET active = FALSE WHERE ig_account_id = :ig AND active = TRUE"),
                {"ig": ig_account_id},
            )

            # 4) Inserisci nuovo token attivo
            await conn.execute(
                text("""
                    INSERT INTO mfai_app.tokens (ig_account_id, access_token, expires_at, long_lived, active)
                    VALUES (:ig_account_id, :token, :expires_at, TRUE, TRUE)
                """),
                {"ig_account_id": ig_account_id, "token": data.token, "expires_at": exp},
            )

            # 5) Log tecnico
            await conn.execute(
                text("INSERT INTO mfai_app.message_logs (ig_account_id, direction, payload) VALUES (:id,'in',:p)"),
                {"id": ig_account_id, "p": f"Saved token (len={len(data.token)})"},
            )

        return {"status": "ok", "client_id": client_id, "ig_account_id": ig_account_id, "expires_at": exp.isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{e.__class__.__name__}: {e}")

# -----------------------------------------------------------
# Utility Token
# -----------------------------------------------------------
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
        await conn.execute(text("UPDATE mfai_app.tokens SET active = FALSE WHERE ig_account_id = :id AND active = TRUE"), {"id": ig_account_id})
        await conn.execute(
            text("INSERT INTO mfai_app.tokens (ig_account_id, access_token, expires_at, long_lived, active) VALUES (:ig, :token, :exp, TRUE, TRUE)"),
            {"ig": ig_account_id, "token": data.token, "exp": exp},
        )
    return {"status": "ok", "ig_user_id": data.ig_user_id, "expires_at": exp.isoformat()}

@app.get("/tokens/expiring")
async def tokens_expiring(days: int = 10):
    threshold = datetime.now(timezone.utc) + timedelta(days=days)
    q = text("""
        SELECT ia.username, ia.ig_user_id, t.id AS token_id, t.expires_at
        FROM mfai_app.tokens t
        JOIN mfai_app.instagram_accounts ia ON ia.id = t.ig_account_id
        WHERE t.active = TRUE AND t.expires_at IS NOT NULL AND t.expires_at <= :threshold
        ORDER BY t.expires_at ASC
        LIMIT 200
    """)
    async with engine.connect() as conn:
        rows = (await conn.execute(q, {"threshold": threshold})).mappings().all()
    return {"items": rows}

# -----------------------------------------------------------
# Admin JSON utili
# -----------------------------------------------------------
@app.get("/admin/clients_list", dependencies=[Depends(verify_admin)])
async def admin_clients_list():
    q = text("""
      SELECT
        c.id,
        c.name,
        c.email,
        COALESCE((SELECT COUNT(*) FROM mfai_app.instagram_accounts ia WHERE ia.client_id = c.id),0) AS ig_accounts,
        COALESCE((SELECT COUNT(*) FROM mfai_app.public_spaces ps WHERE ps.client_id = c.id),0) AS public_spaces
      FROM mfai_app.clients c
      ORDER BY c.id DESC
      LIMIT 500
    """)
    async with engine.connect() as conn:
        rows = (await conn.execute(q)).mappings().all()
    return {"items": rows}

@app.get("/admin/client/{client_id}/overview", dependencies=[Depends(verify_admin)])
async def admin_client_overview(client_id: int):
    async with engine.connect() as conn:
        client = (await conn.execute(text("SELECT id, name, email, created_at FROM mfai_app.clients WHERE id = :cid"),
                                     {"cid": client_id})).mappings().first()
        if not client:
            raise HTTPException(status_code=404, detail="Cliente non trovato")

        ig_accounts = (await conn.execute(text("""
          SELECT id, ig_user_id, username, active, created_at
          FROM mfai_app.instagram_accounts
          WHERE client_id = :cid
          ORDER BY id DESC
        """), {"cid": client_id})).mappings().all()

        spaces = (await conn.execute(text("""
          SELECT id, slug, title, active, updated_at
          FROM mfai_app.public_spaces
          WHERE client_id = :cid
          ORDER BY id DESC
        """), {"cid": client_id})).mappings().all()

        tokens = (await conn.execute(text("""
          SELECT t.ig_account_id, t.expires_at
          FROM mfai_app.tokens t
          WHERE t.active = TRUE
            AND t.ig_account_id IN (SELECT id FROM mfai_app.instagram_accounts WHERE client_id = :cid)
        """), {"cid": client_id})).mappings().all()

    return {"client": client, "ig_accounts": ig_accounts, "public_spaces": spaces, "active_tokens": tokens}

# -----------------------------------------------------------
# Prompts endpoints dedicati per /ui2  (niente 405)
# -----------------------------------------------------------
class ClientPrompts(BaseModel):
    greeting: str = ""
    fallback: str = ""
    handoff: str = ""
    legal: str = ""

@app.get("/ui2/prompts/{client_id}")
async def ui2_get_prompts(client_id: int):
    """Ritorna i 4 prompts come JSON semplice."""
    async with engine.connect() as conn:
        rows = (await conn.execute(text("""
          SELECT key, value
          FROM mfai_app.client_prompts
          WHERE client_id = :cid
        """), {"cid": client_id})).mappings().all()
    data: Dict[str, str] = {r["key"]: r["value"] for r in rows}
    return {
        "greeting": data.get("greeting", ""),
        "fallback": data.get("fallback", ""),
        "handoff":  data.get("handoff", ""),
        "legal":    data.get("legal", ""),
    }

@app.put("/ui2/prompts/{client_id}")
async def ui2_put_prompts(client_id: int, body: ClientPrompts):
    """Upsert dei 4 prompts nel DB."""
    async with engine.begin() as conn:
        for k, v in body.model_dump().items():
            await conn.execute(text("""
              INSERT INTO mfai_app.client_prompts (client_id, key, value)
              VALUES (:cid, :k, :v)
              ON CONFLICT (client_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """), {"cid": client_id, "k": k, "v": v})
    return {"status": "ok"}

# -----------------------------------------------------------
# Static & router opzionali (fine)
# -----------------------------------------------------------
