"""
Bot de Telegram (Etapa 6): el pegamento entre Telegram y el agente.

Flujo de un mensaje:

    usuario --Telegram--> main.py --agent.responder(chat_id, texto)-->
                            el agente habla con OpenRouter y ejecuta
                            herramientas (catalogo, presupuestos, PDF)
    <-- texto final + rutas de PDF -- main.py responde en el chat y, si
                            el agente genero un PDF, lo adjunta como
                            DOCUMENTO.

Comandos:
    /start        bienvenida (y registra al usuario en la base)
    /nuevo        borra la memoria del chat: arrancamos de cero
    /presupuestos ultimos presupuestos, directo de la base (sin IA)

Lo que NO cambia respecto del bot.py viejo: el mismo formato de logs,
el estado "escribiendo..." (ChatAction.TYPING) y que toda falla de la
IA se responde con un mensaje claro, nunca con un stack trace en el
chat.
"""
import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app import agent, memory, repository
from app.config import LOG_LEVEL, TELEGRAM_BOT_TOKEN

log = logging.getLogger("bot")


def _registrar_desde_update(update: Update) -> int:
    """
    Upsert del usuario en la base y devuelve su chat_id.

    Hace falta ANTES de cualquier presupuesto o mensaje: las dos tablas
    tienen FOREIGN KEY contra usuarios(chat_id) y sin esto todo explota
    con un IntegrityError.
    """
    chat = update.effective_chat
    usuario = update.effective_user
    repository.registrar_usuario(
        chat.id,
        usuario.first_name if usuario else None,
        usuario.username if usuario else None,
    )
    return chat.id


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    _registrar_desde_update(update)
    await update.message.reply_text(
        "¡Hola! Soy el asistente de la Librería UTN.\n"
        "Escribime lo que necesitás: busco artículos y te armo el "
        "presupuesto.\n\n"
        "Comandos:\n"
        "/nuevo - empezar de cero (borra la memoria)\n"
        "/presupuestos - ver tus últimos presupuestos"
    )


async def cmd_nuevo(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Borra la memoria del chat (la tabla mensajes). Los presupuestos
    ya guardados en la base NO se tocan: /presupuestos sigue viéndolos."""
    chat_id = _registrar_desde_update(update)
    borrados = memory.borrar_historial(chat_id)
    log.info("Memoria borrada [%s]: %s mensajes", chat_id, borrados)
    await update.message.reply_text(
        "Listo, memoria borrada ✅ Empezamos de nuevo: ¿qué necesitás?"
    )


async def cmd_presupuestos(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista los últimos presupuestos leyendo DIRECTO de la base: no
    pasa por el modelo, asi no falla aunque la IA esté sin saldo."""
    chat_id = _registrar_desde_update(update)
    preps = repository.listar_presupuestos(chat_id, limite=5)
    if not preps:
        await update.message.reply_text(
            "Todavía no tenés presupuestos. Pedime lo que necesitás y "
            "te armo uno."
        )
        return
    lineas = [
        f"#{p['id']:04d} · {p['estado'].upper()} · ${p['total']:,.2f} · "
        f"{p['creado_en'].strftime('%d/%m/%Y')}"
        for p in preps
    ]
    await update.message.reply_text(
        "Tus últimos presupuestos:\n" + "\n".join(lineas)
    )


async def responder(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Punto de entrada de cada mensaje de texto: va al agente y vuelve
    con la respuesta (y el PDF si el agente lo generó en este turno)."""
    chat_id = _registrar_desde_update(update)
    texto = update.message.text
    log.info(
        "Mensaje recibido [%s] @%s: %s",
        chat_id,
        update.effective_user.username if update.effective_user else "?",
        texto[:80],
    )

    await update.effective_chat.send_action(action=ChatAction.TYPING)

    try:
        texto_respuesta, pdfs = agent.responder(chat_id, texto)
    except agent.ErrorIA as e:
        # el mensaje ya viene pensado para el usuario (agente.py)
        await update.message.reply_text(str(e))
        return
    except Exception:  # noqa: BLE001 - el chat no se cae por un bug nuestro
        log.exception("Fallo inesperado atendiendo a %s", chat_id)
        await update.message.reply_text(
            "Uy, ocurrió un error inesperado. Probá de nuevo en un momento."
        )
        return

    await update.message.reply_text(texto_respuesta)

    # Si el agente generó algún PDF en este turno, lo mandamos como
    # documento (reply_document abre el archivo desde el contenedor:
    # los pdf_path de la base son rutas del contenedor, ej.
    # /app/output/presupuesto_7.pdf).
    for ruta in pdfs:
        archivo = Path(ruta)
        if not archivo.exists():
            log.error("El PDF %s no existe en disco", ruta)
            continue
        log.info("Enviando PDF %s a %s", ruta, chat_id)
        with archivo.open("rb") as f:
            # reply_document usa el nombre del archivo como filename
            await update.message.reply_document(document=f)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en el .env")

    logging.basicConfig(
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        level=LOG_LEVEL,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    log.info("Bot de la Libreria UTN arrancando...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("nuevo", cmd_nuevo))
    app.add_handler(CommandHandler("presupuestos", cmd_presupuestos))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    log.info("Bot listo. Esperando mensajes (long polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
