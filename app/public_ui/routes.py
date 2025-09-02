# app/public_ui/routes.py
from typing import Any, Dict, Optional
import os
import httpx
from sqlalchemy import text

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.db import engine  # usa lo stesso engine async

router = APIRouter(prefix="/c", tags=["Public UI"])
templates = Jinja2Templates(directory="app/public_ui/templates")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
DEFAULT_PROMPT = "Sei un assistente MF.AI. Rispondi in italiano, breve e chiaro."

class ChatIn(BaseModel):
    user: str = Field(..., min_length=1, description="Messaggio dell'utente")

async def fetch_space(slug: str) -> Optional[Dict[str, Any]]:
    q = text("""
        SELECT id, client_id, slug, title, intro, system_prompt, logo_url, active
        FROM mfai_app.public_spaces
        WHERE slug = :slug AND active = TRUE
        LIMIT 1
    """)
    async with engine.connect() as conn:
        row = (await conn.execute(q, {"slug": slug})).mappings().first()
        return dict(row) if row else None

@router.get("/ping", response_class=HTMLResponse)
async def ping():
    return HTMLResponse("<h1>Public UI: OK</h1>")

@router.get("/{slug}", response_class=HTMLResponse)
async def space(slug: str, request: Request):
    space = await fetch_space(slug)
    if not space:
        raise HTTPException(status_code=404, detail="Spazio non trovato o inattivo")
    return templates.TemplateResponse(
        "space.html",
        {"request": request, "slug": slug, "space": space, "title": space["title"]}
    )

@router.post("/{slug}/chat", response_class=JSONResponse)
async def chat(slug: str, body: ChatIn):
    if not OPENAI_API_KEY:
        return JSONResponse({"reply": "⚠️ OPENAI_API_KEY non impostata nel server."})

    space = await fetch_space(slug)
    system_prompt = (space or {}).get("system_prompt") or DEFAULT_PROMPT

    payload = {
        "model": CHAT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": body.user},
        ],
        "temperature": 0.3,
        "max_tokens": 300,
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        if r.status_code == 401:
            return JSONResponse({"reply": "⚠️ Chiave OpenAI rifiutata (401). Controlla OPENAI_API_KEY."})
        r.raise_for_status()
        data = r.json()
        reply = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        if not reply:
            reply = "Mi dispiace, non ho una risposta al momento."
        return JSONResponse({"reply": reply})
    except httpx.TimeoutException:
        return JSONResponse({"reply": "Tempo scaduto contattando il modello. Riprova."})
    except Exception as e:
        print("Chat error:", repr(e))
        raise HTTPException(status_code=500, detail="Errore interno durante la risposta AI.")
