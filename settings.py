# settings.py
import os
from dotenv import load_dotenv

load_dotenv()

# Obrigatório
TOKEN = os.getenv("DISCORD_TOKEN")

# Operação (opcional via env)
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
try:
    LOOP_MINUTES = int(os.getenv("LOOP_MINUTES", "1440"))
except ValueError:
    LOOP_MINUTES = 1440

# Web dashboard (segurança: por padrão só localhost; em Docker use WEB_HOST=0.0.0.0 com cuidado)
WEB_ENABLED = os.getenv("WEB_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
try:
    WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
except ValueError:
    WEB_PORT = 8080
# Se definido, /api/stats exige header: Authorization: Bearer <segredo>
WEB_API_SECRET = os.getenv("WEB_API_SECRET", "").strip() or None
