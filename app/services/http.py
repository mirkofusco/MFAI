import httpx

_client = None

def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(8.0, read=30.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )
    return _client

async def close_client():
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
