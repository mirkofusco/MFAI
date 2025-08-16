from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def home():
    return "<h1>MF.AI è attivo ✅</h1><p>Funziona in locale!</p>"

