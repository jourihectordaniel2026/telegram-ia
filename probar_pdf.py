"""
Genera un PDF de prueba de la Etapa 3 con datos REALES de la base.

Crea un presupuesto temporal con varios articulos del catalogo, genera
el PDF con app/pdf_generator.py y lo borra de la base (el archivo en
output/ queda para revisar el diseño).
"""
from app import repository as repo
from app.pdf_generator import generar_pdf

CHAT_PRUEBA = 999999999


def main() -> None:
    repo.registrar_usuario(CHAT_PRUEBA, "Prueba PDF", "prueba")

    pid = repo.crear_presupuesto(CHAT_PRUEBA, "Facundo Prueba (Etapa 3)")

    # Descuento ANTES de los items: total = subtotal - descuento se
    # recalcula en cada agregar_item, asi el PDF queda consistente
    from sqlalchemy import text
    with repo.session_scope() as s:
        s.execute(text("UPDATE presupuestos SET descuento = 150 WHERE id = :pid"),
                  {"pid": pid})

    # Varios articulos reales del catalogo
    repo.agregar_item(pid, "ESC-004", 5)    # lapiz grafito HB
    repo.agregar_item(pid, "ESC-005", 3)    # lapiz 2B dibujo
    articulo = repo.obtener_articulo("ESC-004")
    assert articulo is not None
    print("articulos encontrados:", articulo["codigo"], articulo["nombre"])

    # Buscar un cuaderno y una mochila para que la tabla tenga renglones
    for termino, cant in (("cuaderno", 4), ("mochila", 1), ("resma", 2)):
        resultados = repo.buscar_articulos(termino, limite=1)
        if resultados:
            repo.agregar_item(pid, resultados[0]["codigo"], cant)
            print(f"  + {resultados[0]['codigo']} x{cant}: "
                  f"{resultados[0]['nombre']}")

    presupuesto = repo.obtener_presupuesto(pid)
    assert presupuesto is not None
    assert len(presupuesto["items"]) >= 3, presupuesto["items"]
    print(f"presupuesto {pid}: {len(presupuesto['items'])} items | "
          f"subtotal={presupuesto['subtotal']} total={presupuesto['total']}")

    ruta = generar_pdf(presupuesto)
    print("PDF generado:", ruta)

    # Limpieza en la base (el PDF queda en output/ para revisar)
    with repo.session_scope() as s:
        s.execute(text("DELETE FROM presupuestos WHERE chat_id = :c"),
                  {"c": CHAT_PRUEBA})
        s.execute(text("DELETE FROM usuarios WHERE chat_id = :c"),
                  {"c": CHAT_PRUEBA})
    print("base limpia, listo")


if __name__ == "__main__":
    main()
