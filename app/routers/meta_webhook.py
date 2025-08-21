import os, json, hmac, hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.db_session import async_session_maker

router = APIRouter()
VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "changeme")
APP_SECRET = os.environ.get("META_APP_SECRET")
GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v21.0")

@router.get("/webhook/meta")
async def verify(request: Request):
    qp = request.query_params
    if qp.get("hub.mode") == "subscribe" and qp.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(qp.get("hub.challenge", ""), status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")

def verify_signature(request: Request, body: bytes) -> bool:
    sig = request.headers.get("X-Hub-Signature-256")
    if not APP_SECRET or not sig:
        return True
    try:
        _, received = sig.split("=")
        expected = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(received, expected)
    except Exception:
        return False

async def get_active_token(session: AsyncSession, ig_user_id: str) -> str | None:
    q = """
    SELECT token
    FROM mfai_app.tokens
    WHERE active = TRUE AND ig_user_id = :ig_user_id
    ORDER BY id DESC
    LIMIT 1
    """
    res = await session.execute(sql_text(q), {"ig_user_id": ig_user_id})
    row = res.first()
    return row[0] if row else None

async def send_ig_message(ig_user_id: str, recipient_id: str, text_body: str, token: str) -> dict:
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{ig_user_id}/messages"
    payload = {
        "messaging_product": "instagram",
        "recipient": {"id": recipient_id},
        "message": {"text": text_body},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, params={"access_token": token}, json=payload)
        try:
            data = r.json()
        except Exception:
            data = {"status_code": r.status_code, "text": r.text}
        return {"ok": r.status_code == 200, "status": r.status_code, "data": data}

@router.post("/webhook/meta")
async def webhook(request: Request):
    raw = await request.body()
    if not verify_signature(request, raw):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = json.loads(raw.decode("utf-8"))
    events = []

    for entry in payload.get("entry", []):
        ig_user_id = entry.get("id")  # IG business destinatario
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if value.get("messaging_product") == "instagram":
                for msg in value.get("messages", []):
                    ts_ms = msg.get("timestamp")
                    ts = datetime.fromtimestamp(int(ts_ms)/1000, tz=timezone.utc) if ts_ms else None
                    sender_id = msg.get("from")
                    text_body = (msg.get("text") or {}).get("body")
                    events.append({
                        "ts": ts,
                        "ig_user_id": ig_user_id,
                        "sender_id": sender_id,
                        "text": text_body,
                        "raw": value
                    })

    async with async_session_maker() as session:  # type: AsyncSession
        for e in events:
            # Log IN
            payload_text = e["text"] or json.dumps(e["raw"], ensure_ascii=False)
            await session.execute(
                sql_text("""
                    INSERT INTO mfai_app.message_logs (ts, direction, payload, raw_json)
                    VALUES (:ts, 'in', :payload, CAST(:raw_json AS JSONB))
                """),
                {"ts": e["ts"], "payload": payload_text, "raw_json": json.dumps(e["raw"])}
            )

            # Reply
            token = await get_active_token(session, e["ig_user_id"])
            if token:
                reply_text = "Grazie per il messaggio. Ti risponderemo a breve."
                resp = await send_ig_message(e["ig_user_id"], e["sender_id"], reply_text, token)
            else:
                resp = {"ok": False, "status": 0, "data": {"error": "token not found"}}

            # Log OUT
            out_payload = reply_text if resp.get("ok") else f"ERROR {resp.get('status')}"
            await session.execute(
                sql_text("""
                    INSERT INTO mfai_app.message_logs (ts, direction, payload, raw_json)
                    VALUES (now(), 'out', :payload, CAST(:raw_json AS JSONB))
                """),
                {"payload": out_payload, "raw_json": json.dumps(resp)}
            )

        await session.commit()

    return {"status": "ok", "received": len(events)}
