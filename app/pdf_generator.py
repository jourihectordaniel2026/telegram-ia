"""
Generacion del PDF del presupuesto con ReportLab.

Diseño: encabezado con datos de la libreria, datos del presupuesto y del
cliente, tabla de items con importes, y bloque de totales + validez.
Los PDF se guardan en output/ (crear_dir los crea si no existe).
"""
from datetime import timedelta
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from app.config import OUTPUT_DIR

# Colores y fuentes del documento
AZUL = colors.HexColor("#1f4e79")
GRIS = colors.HexColor("#f2f2f2")
MARGEN = 2 * cm
VALIDEZ_DIAS = 7


def _encabezado(c: canvas.Canvas, ancho: float, alto: float) -> float:
    """Barra superior con nombre y datos de contacto. Devuelve la Y
    donde empieza el contenido (reportlab mide desde ABAJO)."""
    c.setFillColor(AZUL)
    c.rect(0, alto - 2.2 * cm, ancho, 2.2 * cm, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(MARGEN, alto - 1.3 * cm, "Libreria UTN")
    c.setFont("Helvetica", 9)
    c.drawString(MARGEN, alto - 1.8 * cm,
                 "Av. Universidad 1234 - Tel (011) 4444-5555 - libreria@utn.edu.ar")
    return alto - 3.0 * cm


def _datos_presupuesto(c: canvas.Canvas, y: float, presupuesto: dict) -> float:
    """Numero, fecha, cliente y estado, en dos columnas."""
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(MARGEN, y, f"Presupuesto N° {presupuesto['id']:04d}")

    # Fecha y validez a la derecha
    fecha = presupuesto["creado_en"].strftime("%d/%m/%Y")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.black)
    c.drawRightString(ancho := A4[0] - MARGEN, y, f"Fecha: {fecha}")
    vence = (presupuesto["creado_en"] + timedelta(days=VALIDEZ_DIAS))
    c.drawRightString(ancho, y - 0.45 * cm,
                      f"Válido hasta: {vence.strftime('%d/%m/%Y')}")

    y -= 1.2 * cm
    c.setFont("Helvetica", 9)
    cliente = presupuesto.get("cliente_nombre") or "Consumidor final"
    c.drawString(MARGEN, y, f"Cliente: {cliente}")
    c.drawString(MARGEN, y - 0.45 * cm, f"Estado: {presupuesto['estado'].upper()}")
    return y - 1.2 * cm


def _tabla_items(c: canvas.Canvas, y: float, items: list[dict]) -> float:
    """Tabla codigo | descripcion | cantidad | precio | importe."""
    # Columnas: codigo y descripcion a la izquierda; cant, precio e
    # importe ALINEADOS A LA DERECHA (los numeros se leen mejor asi).
    # cant y precio llevan ~0.6cm de aire para que un precio ancho
    # ($18,500.00) no se pegue a la cantidad.
    cols = [MARGEN, MARGEN + 2.2 * cm, MARGEN + 10.5 * cm,
            MARGEN + 13.0 * cm, A4[0] - MARGEN]

    # Fila de encabezado
    c.setFillColor(AZUL)
    c.rect(MARGEN, y - 0.5 * cm, A4[0] - 2 * MARGEN, 0.6 * cm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    y_txt = y - 0.35 * cm
    c.drawString(cols[0], y_txt, "Codigo")
    c.drawString(cols[1] + 0.1 * cm, y_txt, "Descripcion")
    c.drawRightString(cols[2], y_txt, "Cant.")
    c.drawRightString(cols[3], y_txt, "Precio")
    c.drawRightString(cols[4] - 0.1 * cm, y_txt, "Importe")
    y -= 0.8 * cm

    # Filas con rayado alternado
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    for i, item in enumerate(items):
        if i % 2 == 0:
            c.setFillColor(GRIS)
            c.rect(MARGEN, y - 0.35 * cm, A4[0] - 2 * MARGEN, 0.55 * cm,
                   fill=1, stroke=0)
            c.setFillColor(colors.black)
        c.drawString(cols[0], y - 0.1 * cm, item["codigo"])
        c.drawString(cols[1] + 0.1 * cm, y - 0.1 * cm, item["nombre"][:45])
        # Cant. y Precio alineados a la derecha, igual que sus encabezados
        c.drawRightString(cols[2], y - 0.1 * cm, str(item["cantidad"]))
        c.drawRightString(cols[3], y - 0.1 * cm,
                          f"${item['precio_unitario']:,.2f}")
        c.drawRightString(cols[4] - 0.1 * cm, y - 0.1 * cm,
                          f"${item['importe']:,.2f}")
        y -= 0.55 * cm

    # Linea de cierre
    c.setFillColor(colors.black)
    c.line(MARGEN, y, A4[0] - MARGEN, y)
    return y - 0.6 * cm


def _totales(c: canvas.Canvas, y: float, presupuesto: dict) -> float:
    """Subtotal, descuento y TOTAL (resaltado)."""
    x_texto = A4[0] - MARGEN - 5 * cm
    x_valor = A4[0] - MARGEN - 0.1 * cm  # 1mm de aire contra el borde

    c.setFont("Helvetica", 10)
    c.setFillColor(colors.black)
    c.drawString(x_texto, y, "Subtotal:")
    c.drawRightString(x_valor, y, f"${presupuesto['subtotal']:,.2f}")
    y -= 0.55 * cm
    c.drawString(x_texto, y, "Descuento:")
    c.drawRightString(x_valor, y, f"-${presupuesto['descuento']:,.2f}")
    y -= 0.9 * cm

    # Total en caja azul
    c.setFillColor(AZUL)
    c.rect(x_texto - 0.3 * cm, y - 0.25 * cm, x_valor - x_texto + 0.3 * cm,
           0.8 * cm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_texto, y, "TOTAL")
    c.drawRightString(x_valor, y, f"${presupuesto['total']:,.2f}")
    return y - 1.6 * cm


def generar_pdf(presupuesto: dict) -> Path:
    """
    Genera output/presupuesto_<id>.pdf y devuelve la ruta.

    presupuesto: el dict que devuelve repository.obtener_presupuesto(),
    o sea cabecera + items (cada item con codigo, nombre, cantidad,
    precio_unitario e importe).
    """
    OUTPUT_DIR.mkdir(exist_ok=True)  # crea output/ si no existe
    ruta = OUTPUT_DIR / f"presupuesto_{presupuesto['id']}.pdf"

    c = canvas.Canvas(str(ruta), pagesize=A4)
    ancho, alto = A4
    c.setTitle(f"Presupuesto {presupuesto['id']}")

    y = _encabezado(c, ancho, alto)
    y = _datos_presupuesto(c, y, presupuesto)
    y = _tabla_items(c, y, presupuesto["items"])
    y = _totales(c, y, presupuesto)

    # Pie: validez y observaciones
    c.setFillColor(colors.grey)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(MARGEN, y,
                 f"Presupuesto valido por {VALIDEZ_DIAS} dias. "
                 "Precios sujetos a variacion sin previo aviso.")
    c.drawString(MARGEN, y - 0.4 * cm,
                 "Gracias por su consulta. No incluye IVA.")

    c.showPage()  # cierra la pagina (sin esto el PDF sale en blanco)
    c.save()
    return ruta