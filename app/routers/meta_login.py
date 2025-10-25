# app/routers/meta_login.py
# ------------------------------------------------------------
# Meta Login flow — OAuth -> long-lived user token -> Page + IG
# Pagina di successo con "Save token to MF.AI" che salva via /save-token
# ------------------------------------------------------------
import os
import html
import json
from typing import Dict, Any, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()

GRAPH_VER = "v21.0"
META_APP_ID = os.getenv("META_APP_ID")
META_APP_SECRET = os.getenv("META_APP_SECRET")
REDIRECT_URI = os.getenv(
    "META_REDIRECT_URI",
    "https://mid-ranna-soluzionidigitaliroma-f8d1ef2a.koyeb.app/meta/callback",
)

# Salvataggio interno
API_KEY = os.getenv("API_KEY", "").strip()
BASE_URL = os.getenv("BASE_URL", "").strip()  # opzionale (se vuoto usa path locali)

# === SCOPI CORRETTI (rimosso instagram_business_basic che è invalido) ===
SCOPES = [
    "instagram_basic",
    "pages_show_list",
    "pages_manage_metadata",
    "instagram_manage_messages",
    # "pages_messaging",      # scommenta se invii messaggi via Pagina
    # "business_management",  # scommenta se gestisci asset Business
]

def h(s: Any) -> str:
    return html.escape(str(s), quote=True)

@router.get("/meta/login", response_class=HTMLResponse)
async def meta_login():
    if not META_APP_ID or not META_APP_SECRET:
        return HTMLResponse("<h3>Missing META_APP_ID or META_APP_SECRET</h3>", status_code=500)

    params = {
        "client_id": META_APP_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": ",".join(SCOPES),
        "state": "mfai_login_state",
    }
    login_url = f"https://www.facebook.com/{GRAPH_VER}/dialog/oauth?{urlencode(params)}"

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>MF.AI — Connetti Instagram</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .container {{
                background: white;
                border-radius: 20px;
                padding: 48px 40px;
                max-width: 480px;
                width: 100%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
            }}
            .logo {{
                width: 120px;
                height: 120px;
                margin: 0 auto 24px;
                border-radius: 30px;
                object-fit: contain;
                box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
            }}
            h1 {{
                font-size: 28px;
                color: #1a1a1a;
                margin-bottom: 12px;
                font-weight: 700;
            }}
            p {{
                color: #666;
                font-size: 16px;
                line-height: 1.6;
                margin-bottom: 32px;
            }}
            .btn {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 16px 32px;
                font-size: 16px;
                font-weight: 600;
                border-radius: 12px;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                transition: transform 0.2s, box-shadow 0.2s;
                box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            }}
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
            }}
            .btn:active {{
                transform: translateY(0);
            }}
            .features {{
                margin-top: 32px;
                padding-top: 32px;
                border-top: 1px solid #e0e0e0;
                text-align: left;
            }}
            .feature {{
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 16px;
                color: #555;
                font-size: 14px;
            }}
            .feature::before {{
                content: "✓";
                background: #667eea;
                color: white;
                width: 24px;
                height: 24px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                flex-shrink: 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <img src="https://soluzionidigitali.roma.it/mfai.png" alt="MF.AI Logo" class="logo">
            <h1>Connetti Instagram</h1>
            <p>Autorizza MF.AI ad accedere al tuo account Instagram Business per automatizzare le risposte ai messaggi.</p>
            
            <a href="{h(login_url)}" class="btn">
                Continua con Facebook
            </a>
            
            <div class="features">
                <div class="feature">Risposte automatiche ai DM</div>
                <div class="feature">Gestione commenti intelligente</div>
                <div class="feature">Dashboard di monitoraggio</div>
            </div>
        </div>
    </body>
    </html>
    """)

@router.get("/meta/callback", response_class=HTMLResponse)
async def meta_callback(request: Request):
    # 1) Code exchange
    code = request.query_params.get("code")
    error = request.query_params.get("error")
    error_desc = request.query_params.get("error_description")
    if error:
        return HTMLResponse(f"<h3>Login error</h3><pre>{h(error)}: {h(error_desc or '')}</pre>", status_code=400)
    if not code:
        return HTMLResponse("<h3>Missing ?code</h3>", status_code=400)

    async with httpx.AsyncClient(timeout=25.0) as client:
        # short-lived user token
        token_resp = await client.get(
            f"https://graph.facebook.com/{GRAPH_VER}/oauth/access_token",
            params={
                "client_id": META_APP_ID,
                "redirect_uri": REDIRECT_URI,
                "client_secret": META_APP_SECRET,
                "code": code,
            },
        )
        token_data = token_resp.json()
        if "access_token" not in token_data:
            return HTMLResponse(f"<h3>Token error</h3><pre>{h(token_resp.text[:2000])}</pre>", status_code=400)
        user_access_token = token_data["access_token"]

        # 2) Long-lived user token
        ll_resp = await client.get(
            f"https://graph.facebook.com/{GRAPH_VER}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": META_APP_ID,
                "client_secret": META_APP_SECRET,
                "fb_exchange_token": user_access_token,
            },
        )
        ll_data = ll_resp.json()
        long_lived_user_token = ll_data.get("access_token", user_access_token)

        # 3) Pages + IG linkage
        pages_resp = await client.get(
            f"https://graph.facebook.com/{GRAPH_VER}/me/accounts",
            params={
                "access_token": long_lived_user_token,
                "fields": "id,name,access_token,instagram_business_account",
            },
        )
        pages_data = pages_resp.json()
        if "data" not in pages_data or not pages_data["data"]:
            return HTMLResponse("<h3>No Pages found for this user</h3>", status_code=400)

        selected_page: Optional[Dict[str, Any]] = None
        for p in pages_data["data"]:
            if p.get("instagram_business_account"):
                selected_page = p
                break
        if not selected_page:
            selected_page = pages_data["data"][0]

        page_id = selected_page["id"]
        page_name = selected_page.get("name", "")
        page_access_token = selected_page.get("access_token", "")

        # 4) IG User ID dalla Page (se necessario)
        if selected_page.get("instagram_business_account", {}).get("id"):
            ig_user_id = selected_page["instagram_business_account"]["id"]
        else:
            page_detail_resp = await client.get(
                f"https://graph.facebook.com/{GRAPH_VER}/{page_id}",
                params={
                    "access_token": long_lived_user_token,
                    "fields": "instagram_business_account",
                },
            )
            page_detail = page_detail_resp.json()
            iba = page_detail.get("instagram_business_account")
            ig_user_id = iba.get("id") if iba else None

        # 5) IG username (best effort)
        ig_username: Optional[str] = None
        if ig_user_id and page_access_token:
            try:
                igq = await client.get(
                    f"https://graph.facebook.com/{GRAPH_VER}/{ig_user_id}",
                    params={"access_token": page_access_token, "fields": "username"},
                )
                igd = igq.json()
                ig_username = igd.get("username")
            except Exception:
                ig_username = None

    summary = {
        "page_id": page_id,
        "page_name": page_name,
        "ig_user_id": ig_user_id,
        "ig_username": ig_username,
        "page_access_token": "***hidden***",
        "long_lived_user_token": (long_lived_user_token[:20] + "..."),
    }

    # Hidden payload per /meta/save
    payload_hidden = h(json.dumps({
        "page_id": page_id,
        "ig_user_id": ig_user_id,
        "ig_username": ig_username or "unknown",
        "page_access_token": page_access_token,
    }))

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>MF.AI — Connessione riuscita</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 920px;
                margin: 40px auto;
                background: white;
                border-radius: 20px;
                padding: 40px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }}
            .header {{
                text-align: center;
                margin-bottom: 32px;
            }}
            .logo-small {{
                width: 60px;
                height: 60px;
                margin: 0 auto 16px;
                display: block;
                border-radius: 12px;
            }}
            .success-icon {{
                width: 80px;
                height: 80px;
                background: #10b981;
                border-radius: 50%;
                margin: 0 auto 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 40px;
                color: white;
            }}
            h2 {{
                text-align: center;
                color: #1a1a1a;
                margin-bottom: 16px;
                font-size: 28px;
            }}
            .summary {{
                background: #f8f9fa;
                border-radius: 12px;
                padding: 20px;
                margin: 24px 0;
                font-family: 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                overflow-x: auto;
            }}
            .form-section {{
                margin: 32px 0;
                padding: 24px;
                background: #f8f9fa;
                border-radius: 12px;
            }}
            .form-section h3 {{
                margin-bottom: 16px;
                color: #1a1a1a;
            }}
            .input-group {{
                display: flex;
                gap: 12px;
                flex-wrap: wrap;
                margin-bottom: 16px;
            }}
            input[type="text"],
            input[type="email"] {{
                flex: 1;
                min-width: 200px;
                padding: 12px 16px;
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                font-size: 14px;
                transition: border-color 0.2s;
            }}
            input:focus {{
                outline: none;
                border-color: #667eea;
            }}
            .btn {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 14px 28px;
                font-size: 16px;
                font-weight: 600;
                border-radius: 10px;
                cursor: pointer;
                transition: transform 0.2s;
            }}
            .btn:hover {{
                transform: translateY(-2px);
            }}
            .btn-secondary {{
                background: #6b7280;
                margin-left: 12px;
            }}
            .note {{
                color: #666;
                font-size: 14px;
                margin-top: 16px;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img src="https://soluzionidigitali.roma.it/mfai.png" alt="MF.AI Logo" class="logo-small">
                <div class="success-icon">✓</div>
                <h2>Connessione riuscita!</h2>
                <p style="color:#666;">
                    Token e account Instagram recuperati correttamente.
                </p>
            </div>

            <h3 style="margin-bottom:12px;">Riepilogo</h3>
            <pre class="summary">{h(json.dumps(summary, indent=2))}</pre>

            <form method="post" action="/meta/save" class="form-section">
                <h3>Salva il token in MF.AI</h3>
                <input type="hidden" name="payload_json" value='{payload_hidden}' />
                <div class="input-group">
                    <input type="text" name="client_name" placeholder="Nome cliente *" required>
                    <input type="email" name="client_email" placeholder="Email cliente (opzionale)">
                </div>
                <button type="submit" class="btn">Salva token</button>
                <a href="/ui2"><button type="button" class="btn btn-secondary">Torna alla dashboard</button></a>
            </form>

            <p class="note">
                Il token verrà salvato in modo sicuro nel database.
            </p>
        </div>
    </body>
    </html>
    """)

@router.post("/meta/save", response_class=HTMLResponse)
async def meta_save(
    request: Request,
    payload_json: str = Form(...),
    client_name: Optional[str] = Form(None),
    client_email: Optional[str] = Form(None),
):
    if not API_KEY:
        return HTMLResponse("<h3>Missing API_KEY env var</h3>", status_code=500)
    try:
        payload = json.loads(payload_json)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    ig_user_id = payload.get("ig_user_id")
    page_access_token = payload.get("page_access_token")
    ig_username = payload.get("ig_username") or "unknown"
    if not ig_user_id or not page_access_token:
        raise HTTPException(status_code=400, detail="Missing ig_user_id or page_access_token")

    body = {
        "token": page_access_token,
        "ig_user_id": ig_user_id,
        "username": ig_username,
        "client_name": (client_name or "Default Client"),
        "client_email": (client_email or None),
    }

    # Costruisci la target URL: usa BASE_URL se presente, altrimenti l'origin della richiesta
    origin = f"{request.url.scheme}://{request.url.netloc}"
    target_url = f"{(BASE_URL or origin).rstrip('/')}/save-token"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(target_url, json=body, headers={"x-api-key": API_KEY})
        if resp.status_code >= 400:
            return HTMLResponse(
                f"<h3>Save failed</h3><pre>Status: {resp.status_code}\n{h(resp.text[:1000])}</pre>",
                status_code=500,
            )
    except Exception as e:
        return HTMLResponse(f"<h3>Save failed</h3><pre>{h(e)}</pre>", status_code=500)

    return RedirectResponse(url="/ui2?ok=token_refreshed", status_code=302)