import httpx
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.auth import decode_access_token, create_access_token
from app.proxy import proxy_request, close_client
from app.config import DRIVER_SERVICE_URL
import app.models as models

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

app = FastAPI(title="API Gateway")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

@app.on_event("shutdown")
async def shutdown():
    await close_client()

# ---------- Публичные ----------
@app.post("/auth/register")
@limiter.limit("5/minute")
async def register(request: Request, user_data: models.UserRegister):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{DRIVER_SERVICE_URL}/drivers", json=user_data.dict())
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

@app.post("/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, form: models.LoginForm):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{DRIVER_SERVICE_URL}/auth/verify", json={"phone": form.phone, "password": form.password})
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user_data = resp.json()
    token = create_access_token({"sub": user_data["user_id"], "role": user_data.get("role", "driver")})
    return {"access_token": token, "token_type": "bearer"}

# ---------- Защищённые ----------
@app.get("/drivers/{driver_id}")
@limiter.limit("100/minute")
async def get_driver(request: Request, driver_id: str, user=Depends(get_current_user)):
    if user.get("sub") != driver_id and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    response = await proxy_request(request, "drivers", f"/{driver_id}")
    return Response(content=response.content, status_code=response.status_code,
                    headers=dict(response.headers), media_type=response.headers.get("content-type"))

@app.post("/drivers/{driver_id}/vehicles")
@limiter.limit("50/minute")
async def add_vehicle(request: Request, driver_id: str, user=Depends(get_current_user)):
    if user.get("sub") != driver_id and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    response = await proxy_request(request, "drivers", f"/{driver_id}/vehicles")
    return Response(content=response.content, status_code=response.status_code,
                    headers=dict(response.headers), media_type=response.headers.get("content-type"))

@app.get("/drivers")
@limiter.limit("100/minute")
async def list_drivers(request: Request, user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    response = await proxy_request(request, "drivers", "")
    return Response(content=response.content, status_code=response.status_code,
                    headers=dict(response.headers), media_type=response.headers.get("content-type"))

@app.patch("/drivers/{driver_id}")
@limiter.limit("50/minute")
async def update_driver(request: Request, driver_id: str, user=Depends(get_current_user)):
    if user.get("sub") != driver_id and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    response = await proxy_request(request, "drivers", f"/{driver_id}")
    return Response(content=response.content, status_code=response.status_code,
                    headers=dict(response.headers), media_type=response.headers.get("content-type"))

@app.delete("/drivers/{driver_id}")
@limiter.limit("20/minute")
async def delete_driver(request: Request, driver_id: str, user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    response = await proxy_request(request, "drivers", f"/{driver_id}")
    return Response(content=response.content, status_code=response.status_code,
                    headers=dict(response.headers), media_type=response.headers.get("content-type"))

@app.get("/vehicles/{vehicle_id}")
@limiter.limit("100/minute")
async def get_vehicle(request: Request, vehicle_id: str, user=Depends(get_current_user)):
    response = await proxy_request(request, "vehicles", f"/{vehicle_id}")
    return Response(content=response.content, status_code=response.status_code,
                    headers=dict(response.headers), media_type=response.headers.get("content-type"))

@app.patch("/vehicles/{vehicle_id}")
@limiter.limit("50/minute")
async def update_vehicle(request: Request, vehicle_id: str, user=Depends(get_current_user)):
    response = await proxy_request(request, "vehicles", f"/{vehicle_id}")
    return Response(content=response.content, status_code=response.status_code,
                    headers=dict(response.headers), media_type=response.headers.get("content-type"))

@app.delete("/vehicles/{vehicle_id}")
@limiter.limit("20/minute")
async def delete_vehicle(request: Request, vehicle_id: str, user=Depends(get_current_user)):
    response = await proxy_request(request, "vehicles", f"/{vehicle_id}")
    return Response(content=response.content, status_code=response.status_code,
                    headers=dict(response.headers), media_type=response.headers.get("content-type"))

@app.put("/drivers/{driver_id}/status")
@limiter.limit("30/minute")
async def update_driver_status(request: Request, driver_id: str, user=Depends(get_current_user)):
    if user.get("sub") != driver_id:
        raise HTTPException(status_code=403, detail="You can only change your own status")
    response = await proxy_request(request, "drivers", f"/{driver_id}/status")
    return Response(content=response.content, status_code=response.status_code,
                    headers=dict(response.headers), media_type=response.headers.get("content-type"))

@app.get("/health")
async def health():
    return {"status": "ok"}