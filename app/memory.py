"""
Memoria del chat: el historial vive en la tabla `mensajes` (JSONB).

A diferencia del dict en memoria del bot.py viejo, esta memoria
SOBREVIVE a reinicios del contenedor y se puede inspeccionar desde
Adminer (http://localhost:8080).

`contenido` guarda el mensaje COMPLETO en formato de proveedor
{"role": ..., "content": ...} como JSONB, asi recuperar_historial()
devuelve exactamente lo que el modelo espera recibir (Etapa 5).
"""
import json

from sqlalchemy import text

from app.config import MAX_HISTORIAL
from app.db import session_scope


def guardar_mensaje(chat_id: int, role: str, contenido: str) -> None:
    """
    Guarda un mensaje del chat. role: 'user' o 'assistant' (el mismo
    CHECK que puso el schema en la columna rol).
    """
    if role not in ("user", "assistant"):
        raise ValueError(f"Role invalido: '{role}'")
    mensaje = {"role": role, "content": contenido}
    with session_scope() as s:
        s.execute(
            text("""
                INSERT INTO mensajes (chat_id, rol, contenido)
                VALUES (:chat_id, :role, CAST(:contenido AS jsonb))
            """),
            {
                "chat_id": chat_id,
                "role": role,
                # json.dumps con ensure_ascii=False para que "á/ñ" se
                # guarden tal cual y no como \u00e1
                "contenido": json.dumps(mensaje, ensure_ascii=False),
            },
        )


def recuperar_historial(chat_id: int, limite: int = MAX_HISTORIAL) -> list[dict]:
    """
    Los ultimos `limite` mensajes del chat, en orden cronologico, como
    lista de dicts [{"role": ..., "content": ...}] lista para mandarle
    al modelo.

    Trucos de JSONB en la query:
      contenido->>'role'    extrae un campo como TEXTO (->> en vez de ->)
      ORDER BY id DESC      traemos los ultimos...
      ...LIMIT y .reverse() ...pero los devolvemos del mas viejo al mas nuevo
    El while inicial descarta que el historial arranque en 'assistant':
    los proveedores exigen que la primera entrada sea 'user'.
    """
    with session_scope() as s:
        filas = s.execute(
            text("""
                SELECT contenido->>'role' AS role,
                       contenido->>'content' AS content
                FROM mensajes
                WHERE chat_id = :chat_id
                  AND contenido->>'role' IN ('user', 'assistant')
                ORDER BY id DESC
                LIMIT :limite
            """),
            {"chat_id": chat_id, "limite": limite},
        ).mappings().all()

    historial = [dict(f) for f in filas]
    historial.reverse()  # del mas viejo al mas nuevo

    while historial and historial[0]["role"] != "user":
        historial.pop(0)
    return historial


def borrar_historial(chat_id: int) -> int:
    """Borra todos los mensajes del chat (lo usa /clear). Devuelve cuantos."""
    with session_scope() as s:
        borrados = s.execute(
            text("DELETE FROM mensajes WHERE chat_id = :chat_id"),
            {"chat_id": chat_id},
        ).rowcount
    return borrados