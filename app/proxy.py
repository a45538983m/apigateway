import httpx
from fastapi import HTTPException, Request
from app.config import DRIVER_SERVICE_URL

_client = None

def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client

async def close_client():
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None

async def proxy_request(request: Request, service_prefix: str, path: str):
    base_url = DRIVER_SERVICE_URL
    full_url = f"{base_url}{path}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}

    client = get_client()
    try:
        response = await client.request(
            method=request.method,
            url=full_url,
            headers=headers,
            content=body,
            params=request.query_params,
        )
        return response
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Upstream service error: {str(e)}")