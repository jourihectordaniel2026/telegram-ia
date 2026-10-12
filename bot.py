"""
Bot de Telegram que responde con IA (modelos Claude).

Flujo: el usuario manda un mensaje -> lo reenviamos al proveedor de IA
junto con el historial de la conversacion -> la respuesta vuelve al chat.

El proveedor lo decide el .env, sin tocar codigo:
  - OPENROUTER_API_KEY presente  -> usa OpenRouter
  - si no, ANTHROPIC_API_KEY      -> usa la API oficial de Anthropic
Se puede forzar con PROVEEDOR=anthropic u OPENROUTER.

La conversacion se guarda en memoria (un dict por chat), asi que se pierde
si el contenedor se reinicia. Para el TP eso esta bien.
"""

import logging
import os
from collections import defaultdict

import anthropic
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Configuracion: todo sale del .env (docker-compose se lo pasa al contenedor)
# ---------------------------------------------------------------------------
load_dotenv()

if not os.getenv("TELEGRAM_BOT_TOKEN"):
    raise SystemExit("Falta TELEGRAM_BOT_TOKEN en el .env")
if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENROUTER_API_KEY")):
    raise SystemExit(
        "Falta una clave de IA en el .env: cargá ANTHROPIC_API_KEY u OPENROUTER_API_KEY"
    )

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))
MAX_HISTORIAL = int(os.getenv("MAX_HISTORIAL", "20"))  # mensajes que se recuerdan

MODELO_ANTHROPIC = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
MODELO_OPENROUTER = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-5.5")

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    (
        "Sos el asistente virtual de una libreria universitaria. "
        "Respondes en espanol, de forma breve, clara y amable. "
        "Si te preguntan por precios o stock, aclará que esos datos "
        "se confirman en el local."
    ),
)


def _elegir_proveedor() -> str:
    """auto: OpenRouter si hay clave, si no Anthropic."""
    if os.getenv("PROVEEDOR", "auto").lower() in ("anthropic", "openrouter"):
        return os.environ["PROVEEDOR"].lower()
    return "openrouter" if OPENROUTER_API_KEY else "anthropic"


PROVEEDOR = _elegir_proveedor()
MODELO = MODELO_OPENROUTER if PROVEEDOR == "openrouter" else MODELO_ANTHROPIC

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=LOG_LEVEL,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

claude = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# historial[chat_id] = [{"role": "user"|"assistant", "content": "..."}, ...]
historial: dict[int, list[dict]] = defaultdict(list)


class ErrorIA(Exception):
    """Fallo al consultar la IA. El mensaje ya esta pensado para el usuario."""


def _recortar(mensajes: list[dict]) -> list[dict]:
    """Deja los ultimos MAX_HISTORIAL mensajes y arranca en un mensaje 'user'."""
    recorte = mensajes[-MAX_HISTORIAL:]
    while recorte and recorte[0]["role"] != "user":
        recorte.pop(0)
    return recorte or mensajes[-1:]


async def _preguntar(textos: list[dict]) -> str:
    """Manda la conversacion al proveedor activo y devuelve la respuesta."""
    if PROVEEDOR == "openrouter":
        return await _preguntar_openrouter(textos)
    return await _preguntar_anthropic(textos)


async def _preguntar_anthropic(textos: list[dict]) -> str:
    try:
        respuesta = await claude.messages.create(
            model=MODELO_ANTHROPIC,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=textos,
        )
    except anthropic.APIStatusError as e:
        log.exception("La API de Anthropic devolvio un error")
        if "credit" in str(e).lower():
            raise ErrorIA(
                "La cuenta de Anthropic no tiene saldo. Cargá créditos en "
                "console.anthropic.com (Plans & Billing)."
            ) from e
        raise ErrorIA(
            f"Uy, fallo la consulta a la IA (error {e.status_code}). "
            "Probá de nuevo en un momento."
        ) from e
    except anthropic.APIConnectionError as e:
        log.exception("No se pudo conectar con la API de Anthropic")
        raise ErrorIA(
            "No pude conectar con la IA. Revisá la conexión e intentá otra vez."
        ) from e

    texto = "".join(
        bloque.text for bloque in respuesta.content if bloque.type == "text"
    ).strip()
    if not texto:
        raise ErrorIA("La IA devolvio una respuesta vacia.")
    return texto


async def _preguntar_openrouter(textos: list[dict]) -> str:
    mensajes = [{"role": "system", "content": SYSTEM_PROMPT}, *textos]
    try:
        async with httpx.AsyncClient(timeout=90) as cliente:
            r = await cliente.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={
                    "model": MODELO_OPENROUTER,
                    "max_tokens": MAX_TOKENS,
                    "messages": mensajes,
                },
            )
            r.raise_for_status()
            datos = r.json()
    except httpx.HTTPStatusError as e:
        codigo = e.response.status_code
        log.exception("OpenRouter devolvio un error")
        if codigo in (401, 403):
            raise ErrorIA(
                "OpenRouter rechazó la clave. Revisá OPENROUTER_API_KEY en el .env."
            ) from e
        if codigo == 402:
            raise ErrorIA(
                "OpenRouter no tiene saldo para ese modelo. Cargá créditos en "
                "openrouter.ai/credits."
            ) from e
        raise ErrorIA(
            f"Uy, fallo la consulta a la IA (error {codigo}). "
            "Probá de nuevo en un momento."
        ) from e
    except httpx.HTTPError as e:
        log.exception("No se pudo conectar con OpenRouter")
        raise ErrorIA(
            "No pude conectar con la IA. Revisá la conexión e intentá otra vez."
        ) from e

    texto = (datos["choices"][0]["message"]["content"] or "").strip()
    if not texto:
        raise ErrorIA("La IA devolvio una respuesta vacia.")
    return texto


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hola! Soy el asistente de la Libreria UTN.\n"
        "Escribime cualquier consulta y te respondo.\n\n"
        "Comandos: /start reinicia este mensaje, /clear borra la memoria."
    )


async def cmd_clear(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    historial.pop(update.effective_chat.id, None)
    await update.message.reply_text("Listo, memoria borrada. ¿En que te ayudo?")


async def responder(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Punto de entrada de cada mensaje de texto del usuario."""
    chat_id = update.effective_chat.id
    texto_usuario = update.message.text
    log.info(
        "Mensaje recibido [%s] @%s: %s",
        chat_id,
        update.effective_user.username if update.effective_user else "?",
        texto_usuario[:80],
    )
    historial[chat_id].append({"role": "user", "content": texto_usuario})
    mensajes = _recortar(historial[chat_id])

    await update.message.chat.send_action(action=ChatAction.TYPING)

    try:
        texto = await _preguntar(mensajes)
    except ErrorIA as e:
        historial[chat_id].pop()  # sacamos el mensaje que no se pudo responder
        await update.message.reply_text(str(e))
        return

    historial[chat_id].append({"role": "assistant", "content": texto})
    await update.message.reply_text(texto)
    log.info("Respuesta enviada via %s [%s]: %s", PROVEEDOR, chat_id, texto[:80])


def main() -> None:
    log.info("Proveedor de IA: %s | modelo: %s", PROVEEDOR, MODELO)
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    log.info("Bot listo. Esperando mensajes (long polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
