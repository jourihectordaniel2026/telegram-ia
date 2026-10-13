"""
Configuracion central: todo sale del .env, sin excepciones.

Es el unico lugar del proyecto que lee os.getenv(). El resto de los
modulos importan las constantes de aca, asi si algo cambia (por ej. el
puerto de la base) se cambia en un solo lugar.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # carga el .env en las variables de entorno

# Raiz del proyecto. Sirve para guardar los PDF en output/ (Etapa 3)
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

# --- Base de datos -------------------------------------------------------
# En local: localhost:5440 (el puerto que expone docker-compose).
# Adentro de la red de Docker el host se llama "db" y el puerto es 5432;
# docker-compose.yml inyecta DB_HOST/DB_PORT cuando el bot corre en container.
DB_USER = os.getenv("POSTGRES_USER", "libreria")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
DB_NAME = os.getenv("POSTGRES_DB", "libreria")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5440"))

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

if not DB_PASSWORD:
    raise SystemExit("Falta POSTGRES_PASSWORD en el .env")
# Memoria: cuantos mensajes del historial se le pasan al modelo
MAX_HISTORIAL = int(os.getenv("MAX_HISTORIAL", "20"))

# --- Proveedor de IA (agente, Etapa 5) ----------------------------------
# El agente usa el SDK de OpenAI apuntando a OpenRouter (compatible con
# el formato de function-calling). Si mañana cambia el proveedor, solo
# se tocan estas constantes.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-5.5")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))
# Vueltas maximas del loop "modelo decide -> ejecuta -> vuelve al modelo"
# dentro de una sola respuesta. Protege contra un modelo enroscado.
MAX_PASOS = int(os.getenv("MAX_PASOS", "10"))

# --- Bot de Telegram (Etapa 6) -------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# MAX_TOKENS por defecto bajado a 512 para caber en claves con poco crédito
# (el error 402 "can only afford 979" pasa con 1024).
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "512"))