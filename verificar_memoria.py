"""
Verificacion de la Etapa 4: app/memory.py contra la base REAL.

Se corre DOS veces (fase "guardar" y fase "recuperar") en contenedores
DISTINTOS: si la segunda fase ve el historial que guardo la primera, la
memoria sobrevive a reinicios, que es justamente lo que hay que probar.

  docker compose --profile bot run --rm --no-deps ... \
    --entrypoint python bot verificar_memoria.py guardar
  docker compose --profile bot run --rm --no-deps ... \
    --entrypoint python bot verificar_memoria.py recuperar
"""
import sys

from app import memory
from app import repository as repo
from app.config import MAX_HISTORIAL
from app.db import session_scope
from sqlalchemy import text

CHAT = 999999998


def fase_guardar() -> None:
    # mensajes.chat_id tiene FOREIGN KEY contra usuarios: hay que dar de
    # alta el usuario ANTES de guardar nada (el mismo upsert que usara el bot)
    repo.registrar_usuario(CHAT, "Prueba Memoria", "prueba")
    memory.borrar_historial(CHAT)

    # Mensajes con acentos yñ para probar el ensure_ascii=False
    mensajes = [
        ("user", "Hola, ¿tienen cuadernos A4?"),
        ("assistant", "¡Sí! Tenemos CUA-002 Cuaderno A4 100 hojas ($3.200)."),
        ("user", "Dame 2 por favor"),
        ("assistant", "Listo, agregué 2 unidades al presupuesto."),
    ]
    for role, contenido in mensajes:
        memory.guardar_mensaje(CHAT, role, contenido)

    # Un rol invalido tiene que rechazarse
    try:
        memory.guardar_mensaje(CHAT, "system", "no deberia guardarse")
        raise AssertionError("debia rechazar role 'system'")
    except ValueError as e:
        print("OK  ValueError por role invalido:", e)

    # Confirmamos en la tabla cruda (lo que veria Adminer)
    with session_scope() as s:
        fila = s.execute(
            text("""
                SELECT rol, contenido->>'content' AS contenido,
                       pg_typeof(contenido)::text AS tipo
                FROM mensajes WHERE chat_id = :c ORDER BY id DESC LIMIT 1
            """),
            {"c": CHAT},
        ).first()
    assert fila is not None
    assert fila[2] == "jsonb", f"tipo real: {fila[2]}"
    assert "2 unidades" in fila[1], fila
    print(f"OK  4 mensajes guardados | ultima fila: rol={fila[0]} "
          f"contenido={fila[1][:30]!r}... | tipo={fila[2]}")
    print("FASE 1 LISTA: contenedor termino; la memoria quedo en la base")


def fase_recuperar() -> None:
    historial = memory.recuperar_historial(CHAT)
    assert len(historial) == 4, historial
    assert historial[0] == {
        "role": "user",
        "content": "Hola, ¿tienen cuadernos A4?",
    }, historial[0]
    assert historial[1]["role"] == "assistant"
    assert historial[-1]["content"].endswith("unidades al presupuesto.")
    # Acentos intactos (nada de \u00e1)
    assert "cuadernos" in historial[0]["content"]
    print("OK  historial recupero los 4 mensajes en orden, acentos intactos")
    print("OK  SOBREVIVE AL REINICIO: 2 contenedores distintos, misma memoria")

    # Limite: pedir menos devuelve los ultimos N (la ventana es messages
    # 3 y 4: 'Dame 2 por favor' + 'Listo...')
    corto = memory.recuperar_historial(CHAT, limite=2)
    assert len(corto) == 2 and corto[0]["role"] == "user", corto
    assert corto[0]["content"] == "Dame 2 por favor", corto
    assert corto[1]["role"] == "assistant", corto
    print("OK  limite=2 -> ultimos 2 mensajes en orden cronologico")

    # Historial que arranca en 'assistant' se descarta (los proveedores
    # exigen que la primera entrada sea 'user')
    memory.guardar_mensaje(CHAT, "user", "mensaje suelto viejo")
    # borramos solo el user dejando un assistant colgado al principio:
    with session_scope() as s:
        s.execute(
            text("""
                DELETE FROM mensajes WHERE chat_id = :c
                AND contenido->>'content' = 'mensaje suelto viejo'
            """),
            {"c": CHAT},
        )
    memory.guardar_mensaje(CHAT, "assistant", "assistant colgado al inicio")
    # limite=1 deja SOLO el assistant colgado: sin el while inicial el
    # historial arrancaria en 'assistant' y el proveedor rechazaria el request
    raro = memory.recuperar_historial(CHAT, limite=1)
    assert raro == [], raro
    raro3 = memory.recuperar_historial(CHAT, limite=3)
    assert raro3[0]["role"] == "user", raro3[0]
    print("OK  historial colgado en 'assistant' se limpia al recuperar")

    # Limpieza: quedan 5 mensajes (4 del dialogo + el assistant colgado;
    # el 'mensaje suelto viejo' ya se borro a mano en el test anterior)
    borrados = memory.borrar_historial(CHAT)
    assert borrados == 5, borrados
    assert memory.recuperar_historial(CHAT) == []
    with session_scope() as s:
        s.execute(text("DELETE FROM usuarios WHERE chat_id = :c"), {"c": CHAT})
    print(f"OK  limpieza: {borrados} mensajes borrados, base como estaba")

    print(f"\nETAPA 4 VERIFICADA (MAX_HISTORIAL={MAX_HISTORIAL})")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("guardar", "recuperar"):
        raise SystemExit("uso: python verificar_memoria.py guardar|recuperar")
    if sys.argv[1] == "guardar":
        fase_guardar()
    else:
        fase_recuperar()
