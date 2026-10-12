"""
Verificacion de la Etapa 2: usa app/repository.py contra la base REAL.

Se puede correr desde la raiz del proyecto (en Windows/macOS local puede
fallar el import de psycopg2 por el antivirus; en Docker anda siempre):

  docker compose --profile bot run --rm --no-deps \
    -v <ruta-app>:/app/app:ro -e DB_HOST=db -e DB_PORT=5432 \
    --entrypoint python bot verificar_etapa2.py

Cada paso imprime OK o explota con assert. Al final borra los datos de
prueba que creo, asi la base queda como estaba.
"""
from app import repository as repo

CHAT_PRUEBA = 999999999  # chat_id inventado, no es de nadie real


def main() -> None:
    # 1. Usuario (upsert) ------------------------------------------------
    repo.registrar_usuario(CHAT_PRUEBA, "Prueba Etapa 2", "prueba")
    repo.registrar_usuario(CHAT_PRUEBA, "Prueba Etapa 2 v2", "prueba")
    print("OK  registrar_usuario (upsert x2)")

    # 2. Busqueda sin acentos ni mayusculas ------------------------------
    r1 = repo.buscar_articulos("lapiz")          # sin acento, minuscula
    r2 = repo.buscar_articulos("LAPIZ")          # sin acento, mayuscula
    r3 = repo.buscar_articulos("cuaderno A4")
    assert any("Lápiz" in a["nombre"] for a in r1), f"lapiz -> {r1}"
    assert any("Lápiz" in a["nombre"] for a in r2), f"LAPIZ -> {r2}"
    assert r3, "cuaderno A4 no devolvio nada"
    print(f"OK  buscar_articulos: 'lapiz'={len(r1)} | 'LAPIZ'={len(r2)} "
          f"| 'cuaderno A4'={len(r3)} | ej: {r1[0]['codigo']} {r1[0]['nombre']}")

    # 3. Detalle por codigo ---------------------------------------------
    art = repo.obtener_articulo("ESC-004")
    assert art and isinstance(art["precio"], float), art
    print(f"OK  obtener_articulo ESC-004 -> {art['nombre']} ${art['precio']}")

    # 4. Presupuesto: crear, agregar items, sumar cantidades -------------
    pid = repo.crear_presupuesto(CHAT_PRUEBA, "Cliente de prueba")
    repo.agregar_item(pid, "ESC-004", 5)   # 5 lapices
    repo.agregar_item(pid, "ESC-004", 2)   # +2 => deben quedar 7 en UNA linea
    p = repo.obtener_presupuesto(pid)
    assert p["cliente_nombre"] == "Cliente de prueba"
    assert len(p["items"]) == 1, p["items"]
    assert p["items"][0]["cantidad"] == 7, p["items"][0]

    esperado = round(7 * art["precio"], 2)
    assert round(p["subtotal"], 2) == esperado, (p["subtotal"], esperado)
    assert round(p["total"], 2) == esperado, (p["total"], esperado)
    assert p["estado"] == "borrador"
    print(f"OK  agregar_item x2 -> 1 linea con cant=7 | subtotal=total=${esperado}")

    # 5. Totales con descuento ------------------------------------------
    with repo.session_scope() as s:
        from sqlalchemy import text
        s.execute(text("UPDATE presupuestos SET descuento = 10 WHERE id = :pid"),
                  {"pid": pid})
    repo.agregar_item(pid, "ESC-004", 1)   # recalcula con descuento
    p = repo.obtener_presupuesto(pid)
    assert round(p["subtotal"], 2) == round(8 * art["precio"], 2), p
    assert round(p["total"], 2) == round(p["subtotal"] - 10, 2), p
    print(f"OK  _recalcular_totales con descuento -> subtotal={p['subtotal']} "
          f"total={p['total']}")

    # 6. Quitar item ------------------------------------------------------
    repo.quitar_item(pid, "ESC-004")
    p = repo.obtener_presupuesto(pid)
    assert p["items"] == [] and p["subtotal"] == 0, p
    print(f"OK  quitar_item -> items=[] subtotal={p['subtotal']}")

    # 7. Errores manejados con ValueError ---------------------------------
    try:
        repo.agregar_item(pid, "NO-EXISTE", 1)
        raise AssertionError("debia fallar por codigo inexistente")
    except ValueError as e:
        print(f"OK  ValueError por codigo inexistente: {e}")
    try:
        repo.cambiar_estado(pid, "reventado")
        raise AssertionError("debia fallar por estado invalido")
    except ValueError as e:
        print(f"OK  ValueError por estado invalido: {e}")

    # 8. Estados, pdf_path y listado --------------------------------------
    repo.cambiar_estado(pid, "confirmado")
    repo.guardar_pdf_path(pid, f"output/presupuesto_{pid}.pdf")
    p = repo.obtener_presupuesto(pid)
    assert p["estado"] == "confirmado" and p["pdf_path"].endswith(".pdf"), p

    repo.agregar_item(pid, "ESC-004", 3)
    lista = repo.listar_presupuestos(CHAT_PRUEBA)
    assert any(x["id"] == pid for x in lista), lista
    print(f"OK  estado/pdf/listado -> estado={p['estado']} "
          f"| listado de {CHAT_PRUEBA}: {len(lista)} presupuesto(s)")

    # 9. Limpieza: la base queda como estaba -------------------------------
    with repo.session_scope() as s:
        from sqlalchemy import text
        s.execute(text("DELETE FROM presupuestos WHERE chat_id = :c"),
                  {"c": CHAT_PRUEBA})
        s.execute(text("DELETE FROM usuarios WHERE chat_id = :c"),
                  {"c": CHAT_PRUEBA})
    quedan = repo.listar_presupuestos(CHAT_PRUEBA)
    assert quedan == [], quedan
    print("OK  limpieza: datos de prueba borrados")

    print("\nETAPA 2 VERIFICADA: 9/9 checks OK")


if __name__ == "__main__":
    main()
