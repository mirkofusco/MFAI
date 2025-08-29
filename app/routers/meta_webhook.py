import os, json, hmac, hashlib, logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.db_session import async_session_maker

router = APIRouter()
VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "changeme")
APP_SECRET   = os.environ.get("META_APP_SECRET", "")
GRAPH_VER    = os.environ.get("META_GRAPH_VERSION", "v23.0")  # aggiorno default

@router.get("/webhook/meta")
async def meta_verify(request: Request):
    qp = request.query_params
    if qp.get("hub.mode") == "subscribe" and qp.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(qp.get("hub.challenge", ""), status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")

def _valid_sig(sig_header: str | None, body: bytes) -> bool:
    if not APP_SECRET:  # in dev non bloccare
        return True
    if not sig_header or not sig_header.startswith("sha256="):
        return False
    received = sig_header.split("=", 1)[1]
    expected = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received, expected)

async def _get_active_token(session: AsyncSession, ig_user_id: str) -> str | None:
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

async def _send_ig_text(ig_user_id: str, recipient_id: str, text_body: str, token: str) -> dict:
    # Send API per Instagram: recipient.id + message.text
    url = f"https://graph.facebook.com/{GRAPH_VER}/{ig_user_id}/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message":   {"text": text_body},
        "messaging_type": "RESPONSE",
        "messaging_product": "instagram",
    }
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.post(url, params={"access_token": token}, json=payload)
        try:
            data = r.json()
        except Exception:
            data = {"status_code": r.status_code, "text": r.text}
        return {"ok": r.status_code == 200, "status": r.status_code, "data": data}

@router.post("/webhook/meta")
async def meta_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("x-hub-signature-256") or request.headers.get("X-Hub-Signature-256")
    if not _valid_sig(sig, raw):
        # in produzione puoi fare raise 401
        return JSONResponse({"status": "invalid_signature"}, 200)

    text = raw.decode("utf-8", errors="ignore")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        logging.warning("Webhook non-JSON, body=%s", text[:500])
        return JSONResponse({"status": "ignored_non_json"}, 200)

    logging.info("WEBHOOK EVENT: %s", text[:1000])

    events: list[dict] = []

    # A) Test console Meta: {"field":"messages" | "messaging_seen", "value":{...}}
    if isinstance(payload.get("field"), str):
        field = payload["field"]
        v = payload.get("value", {}) or {}
        if field == "messages":
            sender_id    = (v.get("sender") or {}).get("id")
            recipient_id = (v.get("recipient") or {}).get("id")
            msg_text     = (v.get("message") or {}).get("text")
            # in test non abbiamo un ig_user_id reale: usa recipient_id come placeholder
            events.append({
                "ts": datetime.now(timezone.utc),
                "ig_user_id": recipient_id or "",
                "sender_id": sender_id,
                "text": msg_text,
                "raw": payload,
                "test_event": True,
            })
        elif field == "messaging_seen":
            # non rispondiamo ai "seen"
            return {"status": "ok", "received": 0}

    # B) Formato Instagram Messaging “entry/changes/...”
    for e in (payload.get("entry") or []):
        ig_user_id = e.get("id") or ""  # IG business destinatario
        for ch in (e.get("changes") or []):
            val = ch.get("value") or {}
            if val.get("messaging_product") == "instagram":
                # messaggi in arrivo
                for m in (val.get("messages") or []):
                    ts_ms     = m.get("timestamp")
                    ts        = datetime.fromtimestamp(int(ts_ms)/1000, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)
                    sender_id = m.get("from")
                    # alcuni payload usano {"text":{"body":...}}, altri {"text":"..."}
                    text_obj  = m.get("text")
                    msg_text  = text_obj.get("body") if isinstance(text_obj, dict) else text_obj
                    events.append({
                        "ts": ts, "ig_user_id": ig_user_id, "sender_id": sender_id,
                        "text": msg_text, "raw": val, "test_event": False
                    })

        # C) Formato “entry/messaging” stile Messenger (alcuni ambienti/dev)
        for m in (e.get("messaging") or []):
            sender_id = (m.get("sender") or {}).get("id")
            msg       = m.get("message") or {}
            msg_text  = msg.get("text")
            events.append({
                "ts": datetime.now(timezone.utc), "ig_user_id": ig_user_id,
                "sender_id": sender_id, "text": msg_text, "raw": m, "test_event": False
            })

    # Nessun evento parsato: OK 200 per evitare retry
    if not events:
        return {"status": "ok", "received": 0}

    async with async_session_maker() as session:  # type: AsyncSession
        for ev in events:
            # log IN
            payload_text = ev["text"] or json.dumps(ev["raw"], ensure_ascii=False)
            await session.execute(
                sql_text("""
                    INSERT INTO mfai_app.message_logs (ts, direction, payload, raw_json)
                    VALUES (:ts, 'in', :payload, CAST(:raw_json AS JSONB))
                """),
                {"ts": ev["ts"], "payload": payload_text, "raw_json": json.dumps(ev["raw"])}
            )

            # invio risposta solo se NON è un test e abbiamo token
            out_resp = {"ok": False, "status": 0, "data": {"info": "skipped"}}
            out_payload = "skipped"
            if not ev.get("test_event") and ev.get("sender_id"):
                token = await _get_active_token(session, ev["ig_user_id"])
                if token:
                    reply = "Grazie per il messaggio. Ti risponderemo a breve."
                    out_resp = await _send_ig_text(ev["ig_user_id"], ev["sender_id"], reply, token)
                    out_payload = reply if out_resp.get("ok") else f"ERROR {out_resp.get('status')}"
                else:
                    out_payload = "ERROR no_active_token"

            await session.execute(
                sql_text("""
                    INSERT INTO mfai_app.message_logs (ts, direction, payload, raw_json)
                    VALUES (now(), 'out', :payload, CAST(:raw_json AS JSONB))
                """),
                {"payload": out_payload, "raw_json": json.dumps(out_resp)}
            )
        await session.commit()

    return {"status": "ok", "received": len(events)}
