import os
from openai import AsyncOpenAI
from app.services.http import get_client

FAST_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "220"))

_client = AsyncOpenAI(http_client=get_client())

async def ai_reply(messages):
    stream = await _client.chat.completions.create(
        model=FAST_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=MAX_TOKENS,
        stream=True,
    )
    buf = []
    async for ev in stream:
        delta = ev.choices[0].delta.get("content", "")
        if not delta:
            continue
        buf.append(delta)
        txt = "".join(buf)
        if any(txt.endswith(p) for p in (".", "!", "?", "…")) and len(txt) >= 60:
            break
    return "".join(buf).strip()
