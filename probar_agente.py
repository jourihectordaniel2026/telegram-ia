"""
Verificacion de la Etapa 5: consola de prueba del agente, SIN Telegram.

Uso:
    python probar_agente.py                     # flujo completo (3 turnos)
    python probar_agente.py "otro mensaje"      # solo el primer turno

Flujo (sigue el ejemplo de la consigna: "necesito 5 cuadernos A4"):
  turno 1  pedido           -> el modelo debe buscar en el catalogo
                               (hay 2 cuadernos A4: puede preguntar cual)
  turno 2  aclaracion       -> con el codigo claro, debe crear el
                               presupuesto y agregar las 5 unidades
  turno 3  confirmacion     -> generar el PDF y devolver la ruta

Verifica en cada paso que las herramientas se disparen de forma logica
y que todo impacte en la base. Borra todo lo que creo: la base queda
como estaba. Sale con codigo 0 si todo OK, 1 si algo fallo.
"""
import logging
import os
import sys

from sqlalchemy import text

from app import agent, memory, repository
from app.db import session_scope

# chat_id de prueba: no existe en Telegram, no puede chocar con nadie
CHAT_ID = 777_777_007

TURNO_1 = "necesito 5 cuadernos A4"
TURNO_2 = "Los rayados, por favor."
TURNO_3 = "Perfecto, confirmo el pedido. Generá el PDF por favor."


def _limpiar() -> None:
    """Borra presupuestos (items en cascada), mensajes y el usuario de prueba."""
    with session_scope() as s:
        s.execute(text("DELETE FROM mensajes WHERE chat_id = :c"), {"c": CHAT_ID})
        s.execute(text("DELETE FROM presupuestos WHERE chat_id = :c"), {"c": CHAT_ID})
        s.execute(text("DELETE FROM usuarios WHERE chat_id = :c"), {"c": CHAT_ID})


def _preguntar(texto: str) -> tuple[str, list[str]]:
    """Un turno contra el agente real, con el mismo manejo de error que main.py."""
    print(f"\n>>> Usuario: {texto}")
    try:
        respuesta, pdfs = agent.responder(CHAT_ID, texto)
    except agent.ErrorIA as e:
        print(f"FAIL (ErrorIA): {e}")
        raise SystemExit(1) from e
    print(f"<<< Asistente: {respuesta}")
    return respuesta, pdfs


def _verificar_presupuesto(fallos: list[str], cant_esperada: int) -> dict | None:
    """Lee el presupuesto de la base y chequea items/total. Devuelve el dict."""
    preps = repository.listar_presupuestos(CHAT_ID)
    if len(preps) != 1:
        fallos.append(f"se esperaba 1 presupuesto y hay {len(preps)}")
        return None
    p = repository.obtener_presupuesto(preps[0]["id"])
    cant = sum(i["cantidad"] for i in p["items"])
    print(
        f"DB: presupuesto #{p['id']} estado={p['estado']} items={len(p['items'])} "
        f"cantidad_total={cant} subtotal={p['subtotal']} total={p['total']}"
    )
    for i in p["items"]:
        print(
            f"     - {i['cantidad']} x {i['codigo']} {i['nombre']} "
            f"@ {i['precio_unitario']} = {i['importe']}"
        )
    if cant != cant_esperada:
        fallos.append(f"se esperaban {cant_esperada} unidades en total, hay {cant}")
    return p


def _main() -> int:
    logging.basicConfig(
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    _limpiar()
    repository.registrar_usuario(CHAT_ID, "Prueba Etapa 5", "prueba_etapa5")

    fallos: list[str] = []
    pdfs_finales: list[str] = []

    # --- Turno 1: el pedido (puede quedar en el aire si pregunta) --------
    _, pdfs1 = _preguntar(sys.argv[1] if len(sys.argv) > 1 else TURNO_1)
    if pdfs1:
        fallos.append(f"en el turno 1 no deberia generarse un PDF y hubo: {pdfs1}")

    if len(sys.argv) > 1:
        # modo mensaje propio: un solo turno, sin asumir flujo
        _limpiar()
        print("DB: datos de prueba borrados")
        print("VERIFICACION OK (turno unico, ver logs arriba).")
        return 0

    # --- Turno 2: aclara que quiere los rayados -> debe armar todo -------
    _, pdfs2 = _preguntar(TURNO_2)
    if pdfs2:
        fallos.append(f"en el turno 2 no deberia generarse un PDF y hubo: {pdfs2}")
    p = _verificar_presupuesto(fallos, cant_esperada=5)
    if p and len(p["items"]) != 1:
        fallos.append(
            f"se esperaba 1 solo item (CUA-001 x5) y hay {len(p['items'])}"
        )

    # --- Turno 3: confirmacion -> PDF ------------------------------------
    _, pdfs3 = _preguntar(TURNO_3)
    pdfs_finales = pdfs3
    if not pdfs3:
        fallos.append("el asistente no llamo a generar_pdf en el turno 3")
    for ruta in pdfs3:
        if not os.path.exists(ruta):
            fallos.append(f"el PDF no existe en disco: {ruta}")
        else:
            print(f"DB: PDF OK -> {ruta} ({os.path.getsize(ruta)} bytes)")
    if p:
        p_final = repository.obtener_presupuesto(p["id"])
        if not p_final["pdf_path"]:
            fallos.append("pdf_path no quedo guardado en la base")
        else:
            print(f"DB: pdf_path persistido = {p_final['pdf_path']}")

    historial = memory.recuperar_historial(CHAT_ID, limite=50)
    roles = [m["role"] for m in historial]
    print(f"\nDB: historial guardado = {roles}")
    if roles != ["user", "assistant", "user", "assistant", "user", "assistant"]:
        fallos.append(f"historial inesperado: {roles}")

    # --- Limpieza --------------------------------------------------------
    for ruta in pdfs_finales:
        if os.path.exists(ruta):
            os.remove(ruta)
    _limpiar()
    print("DB: datos de prueba borrados (la base quedo como estaba)")

    if fallos:
        print("\nVERIFICACION FALLIDA:")
        for f in fallos:
            print(f"  - {f}")
        return 1
    print(
        "\nVERIFICACION OK: busqueda -> presupuesto -> items -> PDF, "
        "con datos en la base, PDF en disco e historial persistido."
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
