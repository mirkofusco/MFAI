import os
from app.services.http import get_client

GRAPH_URL = "https://graph.facebook.com/v21.0/me/messages"
PAGE_TOKEN = os.getenv("PAGE_TOKEN", "")

def _headers():
    return {"Authorization": f"Bearer {PAGE_TOKEN}"}

async def send_typing(ig_psid: str):
    payload = {"recipient": {"id": ig_psid}, "sender_action": "typing_on"}
    await get_client().post(GRAPH_URL, json=payload, headers=_headers())

async def send_text(ig_psid: str, text: str):
    payload = {"recipient": {"id": ig_psid}, "message": {"text": text}}
    await get_client().post(GRAPH_URL, json=payload, headers=_headers())
