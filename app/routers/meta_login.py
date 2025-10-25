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
        "redirect_uri": REDIRECT_URI,              # verrà URL-encodata da urlencode
        "scope": ",".join(SCOPES),
        "state": "mfai_login_state",               # semplice anti-CSRF demo
    }
    login_url = f"https://www.facebook.com/{GRAPH_VER}/dialog/oauth?{urlencode(params)}"

    return HTMLResponse(f"""
    <html><body style="font-family:system-ui;max-width:760px;margin:40px auto;">
      <h1>MF.AI — Connect with Meta</h1>
      <p>This starts the end-to-end authorization flow required for review.</p>
      <a href="{h(login_url)}">
        <button style="padding:10px 16px;font-size:16px">Continue with Facebook</button>
      </a>
    </body></html>
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
    <html><body style="font-family:system-ui;max-width:920px;margin:30px auto;">
      <h2>✅ Instagram Account Connected Successfully</h2>
      <p><strong>Connection successful!</strong> MF.AI has retrieved your Instagram Business account information.</p>
      <p>Below you can see the details of your connected account. Enter your business name and click "Save token to MF.AI" to complete the setup.</p>
      
      <h3>Summary</h3>
      <pre>{h(json.dumps(summary, indent=2))}</pre>
      
      <form method="post" action="/meta/save" style="margin-top:24px;">
        <input type="hidden" name="payload_json" value='{payload_hidden}' />
        
        <div style="display:flex;flex-direction:column;gap:16px;max-width:600px;">
          
          <div style="display:flex;flex-direction:column;gap:6px;">
            <label style="font-weight:600;font-size:14px;color:#333;">Business Name *</label>
            <input type="text" 
                   name="client_name" 
                   placeholder="e.g. My Business" 
                   required
                   value="{h(ig_username or '')}"
                   style="padding:10px 12px;border-radius:8px;border:1px solid #ccc;font-size:14px;width:100%;">
            <small style="color:#666;font-size:12px;">This name will appear in the MF.AI dashboard</small>
          </div>
          
          <div style="display:flex;flex-direction:column;gap:6px;">
            <label style="font-weight:600;font-size:14px;color:#333;">Email (optional)</label>
            <input type="email" 
                   name="client_email" 
                   placeholder="contact@business.com" 
                   style="padding:10px 12px;border-radius:8px;border:1px solid #ccc;font-size:14px;width:100%;">
          </div>
          
          <button type="submit"
                  style="padding:12px 20px;font-size:16px;background:#10a37f;color:white;border:none;border-radius:8px;cursor:pointer;font-weight:600;margin-top:8px;"
                  title="This will store the Instagram Business token in MF.AI database to enable automated DM replies">
            💾 Save Token to MF.AI Database
          </button>
        </div>
      </form>
      
      <p style="color:#666;margin-top:20px;font-size:14px;">
        The Save action will persist the Page Access Token in MF.AI database to enable automated Instagram DM replies.
      </p>
      
      <p style="margin-top:16px;">
        <a href="/ui2" style="text-decoration:none">
          <button style="padding:8px 16px;background:#f0f0f0;border:1px solid #ccc;border-radius:8px;cursor:pointer;">
            ← Back to Admin Dashboard
          </button>
        </a>
      </p>
    </body></html>
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
