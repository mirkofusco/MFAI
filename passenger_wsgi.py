import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from asgiref.wsgi import AsgiToWsgi
from app.main import app as fastapi_app  # FastAPI è in app/main.py

application = AsgiToWsgi(fastapi_app)
