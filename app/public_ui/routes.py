# app/public_ui/routes.py
from typing import Any, Dict
import os
import httpx

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

router = APIRouter(prefix="/c", tags=["Public UI"])
templates = Jinja2Templates(directory="app/public_ui/templates")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

# Config minimale degli spazi (in futuro verrà da DB)
SPACES: Dict[str, Dict[str, Any]] = {
    "dietologa-demo": {
        "title": "Dietologa — Demo",
        "intro": "Benvenuto nello spazio demo della Dietologa.",
        "system_prompt": (
            "Sei una dietologa professionale. Rispondi SEMPRE in italiano, "
            "in modo chiaro, empatico e pratico. Offri esempi concreti."
        ),
    }
}
DEFAULT_PROMPT = (
    "Sei un assistente MF.AI. Rispondi sempre in italiano in modo breve, chiaro e utile."
)

class ChatIn(BaseModel):
    user: str = Field(..., min_length=1, description="Messaggio dell'utente")

class ChatOut(BaseModel):
    reply: str

@router.get("/ping", response_class=HTMLResponse)
async def ping():
    return HTMLResponse("<h1>Public UI: OK</h1>")

@router.get("/{slug}", response_class=HTMLResponse)
async def space(slug: str, request: Request):
    space = SPACES.get(slug, {"title": f"Spazio: {slug}", "intro": "Spazio generico.", "system_prompt": DEFAULT_PROMPT})
    return templates.TemplateResponse(
        "space.html",
        {"request": request, "slug": slug, "space": space, "title": space["title"]}
    )

@router.post("/{slug}/chat", response_class=JSONResponse)
async def chat(slug: str, body: ChatIn):
    """Endpoint JSON per la chat pubblica."""
    if not OPENAI_API_KEY:
        return JSONResponse({"reply": "⚠️ OPENAI_API_KEY non impostata nel server."})

    space = SPACES.get(slug, {"system_prompt": DEFAULT_PROMPT})
    system_prompt = space.get("system_prompt", DEFAULT_PROMPT)

    # Chiamiamo OpenAI Chat Completions (via HTTPX) per evitare dipendenze extra
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
        # Log server side e risposta generica
        print("Chat error:", repr(e))
        raise HTTPException(status_code=500, detail="Errore interno durante la risposta AI.")
