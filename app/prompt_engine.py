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
