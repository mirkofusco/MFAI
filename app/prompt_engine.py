# prompt_engine.py

from openai import OpenAI
import os
from dotenv import load_dotenv

# Carica le variabili dal file .env
load_dotenv()

# Recupera la chiave API da .env
api_key = os.getenv("OPENAI_API_KEY")

# Istanza del client OpenAI
client = OpenAI(api_key=api_key)

def get_gpt_reply(user_message: str) -> str:
    """
    Invia il messaggio dell'utente al modello GPT e restituisce la risposta.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # modello consigliato
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        return f"[ERRORE GPT] {str(e)}"


async def build_system_prompt(session, client_id: int | None, base_system: str) -> str:
    """Se il client ha ai_prompt, prefissa il system con quelle istruzioni."""
    try:
        from sqlalchemy import select
        from app.models import Client  # Client nel file models.py
        if client_id is None:
            return base_system
        res = await session.execute(select(Client).where(Client.id == client_id))
        c = res.scalar_one_or_none()
        if c and getattr(c, "ai_prompt", None):
            ap = (c.ai_prompt or "").strip()
            if ap:
                return ap + "\n\n" + base_system
    except Exception:
        # Se qualcosa va storto, non bloccare: usa il base_system
        pass
    return base_system
