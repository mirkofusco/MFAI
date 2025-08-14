from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import requests

router = APIRouter()

# ✅ Pagina pubblica per connettere l'account Instagram
@router.get("/connect", response_class=HTMLResponse)
async def connect():
    app_id = "INSERISCI_APP_ID"  # <-- metti qui il tuo Instagram App ID
    redirect_uri = "http://localhost:8000/connected"

    url = (
        f"https://api.instagram.com/oauth/authorize"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=user_profile,user_media"
        f"&response_type=code"
    )

    html_content = f"""
    <html>
        <head><title>Connetti Instagram</title></head>
        <body style="font-family: Arial; text-align: center; padding-top: 100px">
            <h1>🔗 Connetti il tuo account Instagram</h1>
            <a href="{url}" style="font-size: 18px;">Autorizza via Instagram</a>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ✅ Rotta che riceve il codice da Instagram dopo il login
@router.get("/connected")
async def connected(request: Request):
    code = request.query_params.get("code")

    if not code:
        return {"error": "Codice mancante"}

    app_id = "INSERISCI_APP_ID"      # <-- stesso App ID
    app_secret = "INSERISCI_APP_SECRET"  # <-- metti il tuo App Secret
    redirect_uri = "http://localhost:8000/connected"

    # Richiesta a Instagram per ottenere lo short_lived_token
    token_url = "https://api.instagram.com/oauth/access_token"
    payload = {
        "client_id": app_id,
        "client_secret": app_secret,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code": code,
    }

    response = requests.post(token_url, data=payload)
    data = response.json()

    if "access_token" not in data:
        return {"error": "Errore nel recupero del token", "dettaglio": data}

    access_token = data["access_token"]
    user_id = data["user_id"]  # ⚠️ NON è lo username Instagram visibile

    # Invia il token al backend per salvarlo nel database
    update_response = requests.post(
        "http://localhost:8000/admin/update-token",
        params={
            "instagram_username": str(user_id),  # al momento usiamo l'user_id
            "short_token": access_token,
        }
    )

    if update_response.status_code != 200:
        return {"error": "Errore nel salvataggio del token", "dettaglio": update_response.json()}

    # Redireziona ad una pagina di successo
    return RedirectResponse(url="/success")
