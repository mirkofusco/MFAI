from app.routers.meta_webhook import router as meta_webhook_router
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.routers import admin_api
app.include_router(admin_api.router)


app = FastAPI(title="MF.AI")
app.include_router(admin_api.router)


app.include_router(meta_webhook_router)

templates = Jinja2Templates(directory="app/templates")

# CORS aperto per ora (poi lo chiudiamo ai tuoi domini)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"ok": True, "app": "MF.AI"}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

class TokenData(BaseModel):
    token: str

@app.post("/token")
async def receive_token(data: TokenData):
    return JSONResponse(content={"message": "Token ricevuto correttamente."})

@app.post("/save-token")
async def save_token(request: Request):
    body = await request.json()
    token = body.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Token mancante")
    with open("access_token.txt", "w") as f:
        f.write(token)
    return JSONResponse(content={"status": "success"})
