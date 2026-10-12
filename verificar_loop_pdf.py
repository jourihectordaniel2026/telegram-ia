"""
Verificacion del tramo final del loop (generar_pdf) SIN depender del
saldo de la API: el cliente de OpenAI se reemplaza por un guion de
respuestas falsas que pide generar_pdf y despues responde texto.

Cubre exactamente los tramos que la verificacion en vivo no alcanzo a
probar (llego el 402 de OpenRouter a mitad del turno 3):
  1. tools.ejecutar("generar_pdf") -> PDF en disco + pdf_path en la base
  2. agent.responder() junta la ruta del PDF y la devuelve
  3. la memoria persiste user/assistant en la tabla mensajes

Sale con codigo 0 si todo OK.
"""
import json
import logging
import os
import sys
from types import SimpleNamespace

from sqlalchemy import text

from app import agent, memory, repository, tools
from app.db import session_scope

CHAT_ID = 777_777_008  # otro id de prueba, distinto al de probar_agente.py


class ClienteFalso:
    """Reemplaza a OpenAI: devuelve las respuestas del guion en orden."""

    def __init__(self, guion: list):
        self._guion = list(guion)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        # el SDK real recibe messages/tools; el guion solo necesita avanzar
        if not self._guion:
            raise AssertionError("el guion se quedo sin respuestas: el loop pidio mas llamadas de las esperadas")
        mensaje = self._guion.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=mensaje)])


def _limpiar() -> None:
    with session_scope() as s:
        s.execute(text("DELETE FROM mensajes WHERE chat_id = :c"), {"c": CHAT_ID})
        s.execute(text("DELETE FROM presupuestos WHERE chat_id = :c"), {"c": CHAT_ID})
        s.execute(text("DELETE FROM usuarios WHERE chat_id = :c"), {"c": CHAT_ID})


def _tool_call(nombre: str, argumentos: dict) -> SimpleNamespace:
    """Un tool_call como el que arma el SDK de OpenAI real."""
    return SimpleNamespace(
        id=f"call_{nombre}",
        function=SimpleNamespace(
            name=nombre,
            arguments=json.dumps(argumentos, ensure_ascii=False),
        ),
        type="function",
    )


def _main() -> int:
    logging.basicConfig(
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        level=logging.INFO,
    )
    fallos: list[str] = []

    _limpiar()
    repository.registrar_usuario(CHAT_ID, "Prueba PDF loop", None)

    # --- Fase 1: la herramienta sola contra la base real -----------------
    pid = repository.crear_presupuesto(CHAT_ID)
    repository.agregar_item(pid, "CUA-001", 5)
    r = tools.ejecutar("generar_pdf", {"presupuesto_id": pid})
    print(f"tools.ejecutar -> {r}")
    if "error" in r:
        fallos.append(f"generar_pdf devolvio error: {r['error']}")
    else:
        if not os.path.exists(r["pdf_path"]):
            fallos.append(f"el PDF no existe: {r['pdf_path']}")
        else:
            print(f"PDF en disco: {r['pdf_path']} ({os.path.getsize(r['pdf_path'])} bytes)")
        p = repository.obtener_presupuesto(pid)
        if p["pdf_path"] != r["pdf_path"]:
            fallos.append(f"pdf_path no persistido (base={p['pdf_path']})")

    # errores utiles del dispatcher (sin cortar nada)
    err = tools.ejecutar("generar_pdf", {"presupuesto_id": 999999})
    print(f"presupuesto inexistente -> {err}")
    if "error" not in err:
        fallos.append("generar_pdf sobre id inexistente deberia devolver error")

    # --- Fase 2: el loop completo con cliente simulado -------------------
    guion = [
        # paso 1: el "modelo" pide generar el PDF
        SimpleNamespace(
            content=None,
            tool_calls=[_tool_call("generar_pdf", {"presupuesto_id": pid})],
        ),
        # paso 2: el "modelo" da la respuesta final
        SimpleNamespace(content="Listo, te armé el PDF del presupuesto #{}.".format(pid), tool_calls=None),
    ]
    agent._cliente = ClienteFalso(guion)  # inyectamos el doble antes del loop
    try:
        texto, pdfs = agent.responder(CHAT_ID, "listo, generá el PDF")
    finally:
        agent._cliente = None  # nunca dejar el doble colgado

    print(f"responder() -> texto={texto!r} pdfs={pdfs}")
    if not pdfs:
        fallos.append("agent.responder no devolvio ninguna ruta de PDF")
    elif not os.path.exists(pdfs[0]):
        fallos.append(f"la ruta devuelta no existe en disco: {pdfs[0]}")

    historial = memory.recuperar_historial(CHAT_ID, limite=50)
    roles = [m["role"] for m in historial]
    print(f"historial = {roles}")
    if roles != ["user", "assistant"]:
        fallos.append(f"historial inesperado: {roles}")
    # el historial NO debe arrastrar los tool calls intermedios
    if "tool" in roles:
        fallos.append("los mensajes 'tool' no deben persistirse en la tabla")

    # --- Limpieza ---------------------------------------------------------
    for ruta in pdfs:
        if os.path.exists(ruta):
            os.remove(ruta)
    _limpiar()
    print("datos de prueba borrados (la base quedo como estaba)")

    if fallos:
        print("\nVERIFICACION FALLIDA:")
        for f in fallos:
            print(f"  - {f}")
        return 1
    print("\nVERIFICACION OK: generar_pdf, coleccion de rutas en el loop y memoria.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
