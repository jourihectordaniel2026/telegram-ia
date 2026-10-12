"""
Verificacion de la Etapa 6: los handlers del bot SIN Telegram ni IA.

Usa updates falsos (con los mismos atributos que python-telegram-bot)
y un cliente OpenAI simulado, asi se prueba el pegamento completo sin
depender del saldo de la API:

  /start       -> registra al usuario (FK) y responde la bienvenida
  mensaje      -> va al agente, que genera un PDF de verdad, y main.py
                  lo manda como DOCUMENTO (capturado por el fake)
  /presupuestos -> lista el presupuesto creado, leyendo de la base
  /nuevo       -> borra la memoria

La verificacion EN VIVO (docker compose --profile bot up -d --build +
mensaje desde la app de Telegram) la hace el usuario.
"""
import asyncio
import json
import logging
import os
import sys
from types import SimpleNamespace

from sqlalchemy import text

from app import agent, main, memory, repository
from app.db import session_scope

CHAT_ID = 777777010  # id de prueba: no existe en Telegram


class FakeMessage:
    """Captura las respuestas del bot en vez de mandarlas a Telegram."""

    def __init__(self, texto=None):
        self.text = texto
        self.textos: list[str] = []
        self.documentos: list[str] = []

    async def reply_text(self, texto, **_):
        self.textos.append(texto)
        print(f"    <- reply_text: {texto[:90]}")

    async def reply_document(self, document, **_):
        nombre = getattr(document, "name", "?")
        self.documentos.append(nombre)
        print(f"    <- reply_document: {nombre}")


class FakeChat:
    def __init__(self, chat_id):
        self.id = chat_id
        self.acciones = []

    async def send_action(self, action):
        self.acciones.append(action)


class ClienteFalso:
    """Reemplaza a OpenAI: devuelve las respuestas del guion en orden."""

    def __init__(self, guion: list):
        self._guion = list(guion)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **_kwargs):
        if not self._guion:
            raise AssertionError("el guion se quedo sin respuestas: el loop pidio mas llamadas")
        return SimpleNamespace(choices=[SimpleNamespace(message=self._guion.pop(0))])


def _update(texto=None):
    return SimpleNamespace(
        message=FakeMessage(texto),
        effective_chat=FakeChat(CHAT_ID),
        effective_user=SimpleNamespace(id=1, first_name="Prueba", username="prueba_etapa6"),
    )


def _tool_call(nombre: str, argumentos: dict):
    return SimpleNamespace(
        id=f"call_{nombre}",
        function=SimpleNamespace(name=nombre, arguments=json.dumps(argumentos)),
        type="function",
    )


def _limpiar() -> None:
    with session_scope() as s:
        s.execute(text("DELETE FROM mensajes WHERE chat_id=:c"), {"c": CHAT_ID})
        s.execute(text("DELETE FROM presupuestos WHERE chat_id=:c"), {"c": CHAT_ID})
        s.execute(text("DELETE FROM usuarios WHERE chat_id=:c"), {"c": CHAT_ID})


def _hay_usuario() -> int:
    with session_scope() as s:
        return s.execute(
            text("SELECT count(*) FROM usuarios WHERE chat_id=:c"), {"c": CHAT_ID}
        ).scalar_one()


def _main() -> int:
    logging.basicConfig(
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        level=logging.INFO,
    )
    fallos: list[str] = []
    _limpiar()

    # --- /start: bienvenida + registro en la base ------------------------
    print("\n== /start ==")
    u = _update()
    asyncio.run(main.cmd_start(u, None))
    if not u.message.textos or "Librer" not in u.message.textos[0]:
        fallos.append("/start no respondio la bienvenida")
    if _hay_usuario() != 1:
        fallos.append("/start no dejo el usuario registrado (necesario para las FK)")

    # --- /presupuestos vacio ---------------------------------------------
    print("\n== /presupuestos (vacio) ==")
    u = _update()
    asyncio.run(main.cmd_presupuestos(u, None))
    if not u.message.textos or "Todav" not in u.message.textos[0]:
        fallos.append("/presupuestos sin datos no aviso que no hay nada")

    # --- mensaje -> agente (cliente simulado) -> PDF real ----------------
    pid = repository.crear_presupuesto(CHAT_ID, "Prueba Etapa 6")
    repository.agregar_item(pid, "CUA-001", 5)
    guion = [
        # paso 1: el "modelo" pide generar el PDF
        SimpleNamespace(content=None, tool_calls=[_tool_call("generar_pdf", {"presupuesto_id": pid})]),
        # paso 2: respuesta final
        SimpleNamespace(
            content=f"Listo, te generé el PDF del presupuesto #{pid}.",
            tool_calls=None,
        ),
    ]
    agent._cliente = ClienteFalso(guion)
    try:
        print("\n== mensaje de texto: 'confirmo, generá el PDF' ==")
        u = _update("Perfecto, confirmo. Generá el PDF.")
        asyncio.run(main.responder(u, None))
    finally:
        agent._cliente = None  # nunca dejar el doble colgado

    if not u.message.textos or "PDF" not in u.message.textos[0]:
        fallos.append("responder no mando el texto final del agente")
    if not u.effective_chat.acciones:
        fallos.append("responder no mostro el estado 'escribiendo...'")
    if len(u.message.documentos) != 1:
        fallos.append(f"responder deberia mandar 1 documento, mando {len(u.message.documentos)}")
    else:
        doc = u.message.documentos[0]
        if not doc.endswith(".pdf") or not os.path.exists(doc):
            fallos.append(f"el documento no es un PDF en disco: {doc}")
        else:
            print(f"    PDF enviado: {doc} ({os.path.getsize(doc)} bytes)")
    p = repository.obtener_presupuesto(pid)
    if not p["pdf_path"]:
        fallos.append("pdf_path no quedo persistido en la base")

    # --- /presupuestos con datos -----------------------------------------
    print("\n== /presupuestos (con 1) ==")
    u = _update()
    asyncio.run(main.cmd_presupuestos(u, None))
    if not u.message.textos or f"#{pid:04d}" not in u.message.textos[0]:
        fallos.append("/presupuestos no listo el presupuesto creado")

    # --- /nuevo borra la memoria ------------------------------------------
    print("\n== /nuevo ==")
    roles_antes = [m["role"] for m in memory.recuperar_historial(CHAT_ID, 50)]
    print(f"    historial antes: {roles_antes}")
    if not roles_antes:
        fallos.append("el agente no dejo historial en la base (falta verificar /nuevo)")
    u = _update()
    asyncio.run(main.cmd_nuevo(u, None))
    if memory.recuperar_historial(CHAT_ID, 50):
        fallos.append("/nuevo no borro la memoria del chat")

    # --- limpieza ----------------------------------------------------------
    if p["pdf_path"] and os.path.exists(p["pdf_path"]):
        os.remove(p["pdf_path"])
    _limpiar()
    print("datos de prueba borrados (la base quedo como estaba)")

    if fallos:
        print("\nVERIFICACION FALLIDA:")
        for f in fallos:
            print(f"  - {f}")
        return 1
    print(
        "\nVERIFICACION OK: bienvenida, registro FK, respuesta del agente, "
        "PDF como documento, /presupuestos y /nuevo."
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
