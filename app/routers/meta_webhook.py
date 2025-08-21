import os, json, hmac, hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

# useremo la sessione standard creata al punto 2
from app.db_session import async_session_maker

router = APIRouter()
VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "changeme")
APP_SECRET = os.environ.get("META_APP_SECRET")

@router.get("/webhook/meta")
async def verify(request: Request):
    qp = request.query_params
    if qp.get("hub.mode") == "subscribe" and qp.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(qp.get("hub.challenge", ""), status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")

def verify_signature(request: Request, body: bytes) -> bool:
    sig = request.headers.get("X-Hub-Signature-256")
    if not APP_SECRET or not sig:
        return True  # in sviluppo accetta tutto
    try:
        _, received = sig.split("=")
        expected = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(received, expected)
    except Exception:
        return False

@router.post("/webhook/meta")
async def webhook(request: Request):
    raw = await request.body()
    if not verify_signature(request, raw):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = json.loads(raw.decode("utf-8"))
    events = []

    for entry in payload.get("entry", []):
        ig_business_id = entry.get("id")  # destinatario (IG business)
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if value.get("messaging_product") == "instagram":
                for msg in value.get("messages", []):
                    ts_ms = msg.get("timestamp")
                    ts = datetime.fromtimestamp(int(ts_ms)/1000, tz=timezone.utc) if ts_ms else None
                    events.append({
                        "ts": ts,
                        "sender_id": msg.get("from"),
                        "recipient_id": ig_business_id,
                        "text": (msg.get("text") or {}).get("body"),
                        "raw_json": value
                    })

    async with async_session_maker() as session:  # type: AsyncSession
        for e in events:
            await session.execute(
                sql_text("""
                    INSERT INTO mfai_app.message_logs (ts, sender_id, recipient_id, text, raw_json)
                    VALUES (:ts, :sender_id, :recipient_id, :text, CAST(:raw_json AS JSONB))
                """),
                {
                    "ts": e["ts"],
                    "sender_id": e["sender_id"],
                    "recipient_id": e["recipient_id"],
                    "text": e["text"],
                    "raw_json": json.dumps(e["raw_json"]),
                }
            )
        await session.commit()

    return {"status": "ok", "received": len(events)}
