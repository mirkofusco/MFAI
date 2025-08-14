from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="MF.AI - Instagram Assistant")

templates = Jinja2Templates(directory="app/templates")

# Per CORS (nel caso serva per le richieste JS)
#/Users/mirkofusco/Desktop/app/templates/login.html
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Per ricevere il token
class TokenData(BaseModel):
    token: str

@app.post("/token")
async def receive_token(data: TokenData):
    print("Token ricevuto:", data.token)
    # Puoi anche salvarlo nel DB qui
    return JSONResponse(content={"message": "Token ricevuto correttamente."})


from fastapi import Request
from fastapi.responses import JSONResponse

@app.post("/save-token")
async def save_token(request: Request):
    body = await request.json()
    token = body.get("token")
    
    # Salvataggio semplice su file (solo per test)
    with open("access_token.txt", "w") as f:
        f.write(token)

    return JSONResponse(content={"status": "success", "token": token})
