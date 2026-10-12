"""
Repositorio: TODA las queries del proyecto viven en este archivo.

Reglas del modulo:
- Nada de SQL fuera de aca: el resto de la app (agente, bot, PDF) pide
  datos mediante estas funciones y nunca toca tablas directamente.
- Cada funcion recibe y devuelve datos simples (dict, listas, int, str),
  asi el agente (Etapa 5) los puede usar facilmente.
- Numeros NUMERIC de la base llegan como Decimal; acá los pasamos a float
  para que el agente y el PDF trabajen comodos.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import session_scope

ESTADOS_VALIDOS = ("borrador", "confirmado", "enviado", "anulado")


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
def registrar_usuario(chat_id: int, nombre: str | None, username: str | None) -> None:
    """
    Upsert: crea el usuario si no existe, si no actualiza sus datos.
    Hace falta ANTES de cualquier presupuesto porque presupuestos.chat_id
    tiene FOREIGN KEY contra usuarios(chat_id).
    """
    with session_scope() as s:
        s.execute(
            text("""
                INSERT INTO usuarios (chat_id, nombre, username)
                VALUES (:chat_id, :nombre, :username)
                ON CONFLICT (chat_id) DO UPDATE
                SET nombre = EXCLUDED.nombre, username = EXCLUDED.username
            """),
            {"chat_id": chat_id, "nombre": nombre, "username": username},
        )


# ---------------------------------------------------------------------------
# Catalogo (busqueda sin acentos)
# ---------------------------------------------------------------------------
def buscar_articulos(termino: str, limite: int = 10) -> list[dict]:
    """
    Busca por nombre o marca IGNORANDO acentos y mayusculas.

    Truco: v_catalogo ya trae texto_normalizado = lower(unaccent(nombre+
    marca)), y aca normalizamos TAMBIEN lo que escribe el usuario con
    f_normalizar(). Asi "lapiz" encuentra "Lapiz" y "Lápiz" por igual.
    """
    with session_scope() as s:
        filas = s.execute(
            text("""
                SELECT codigo, nombre, categoria, marca, unidad, precio, stock
                FROM v_catalogo
                WHERE texto_normalizado LIKE '%' || f_normalizar(:termino) || '%'
                ORDER BY nombre
                LIMIT :limite
            """),
            {"termino": termino, "limite": limite},
        ).mappings().all()
    return [dict(f) for f in filas]


def obtener_articulo(codigo: str) -> dict | None:
    """Detalle de un articulo por su codigo exacto (ej. 'ESC-004')."""
    with session_scope() as s:
        fila = s.execute(
            text("""
                SELECT codigo, nombre, categoria, marca, unidad,
                       precio::float AS precio, stock
                FROM v_catalogo
                WHERE codigo = :codigo
            """),
            {"codigo": codigo},
        ).mappings().first()
    return dict(fila) if fila else None


# ---------------------------------------------------------------------------
# Presupuestos (CRUD)
# ---------------------------------------------------------------------------
def crear_presupuesto(chat_id: int, cliente_nombre: str | None = None) -> int:
    """Crea un presupuesto en estado 'borrador' y devuelve su id."""
    with session_scope() as s:
        presupuesto_id = s.execute(
            text("""
                INSERT INTO presupuestos (chat_id, cliente_nombre)
                VALUES (:chat_id, :cliente_nombre)
                RETURNING id
            """),
            {"chat_id": chat_id, "cliente_nombre": cliente_nombre},
        ).scalar_one()
    return presupuesto_id


def agregar_item(presupuesto_id: int, codigo: str, cantidad: int = 1) -> None:
    """
    Agrega un articulo al presupuesto. Si ya estaba, SUMA la cantidad.
    Copia el precio vigente del articulo (precio_unitario): el precio del
    presupuesto no cambia aunque el catalogo se actualice despues.
    """
    if cantidad < 1:
        raise ValueError("La cantidad tiene que ser 1 o mas")
    with session_scope() as s:
        precio = s.execute(
            text("SELECT precio FROM articulos WHERE codigo = :codigo AND activo"),
            {"codigo": codigo},
        ).scalar_one_or_none()
        if precio is None:
            raise ValueError(f"No existe el articulo '{codigo}' (o esta inactivo)")

        ya_esta = s.execute(
            text("""
                UPDATE presupuesto_items
                SET cantidad = cantidad + :cantidad
                WHERE presupuesto_id = :pid AND articulo_codigo = :codigo
            """),
            {"pid": presupuesto_id, "codigo": codigo, "cantidad": cantidad},
        ).rowcount
        if not ya_esta:
            s.execute(
                text("""
                    INSERT INTO presupuesto_items
                        (presupuesto_id, articulo_codigo, cantidad, precio_unitario)
                    VALUES (:pid, :codigo, :cantidad, :precio)
                """),
                {"pid": presupuesto_id, "codigo": codigo,
                 "cantidad": cantidad, "precio": precio},
            )
        _recalcular_totales(s, presupuesto_id)


def quitar_item(presupuesto_id: int, codigo: str) -> None:
    """Borra un articulo del presupuesto y recalcula los totales."""
    with session_scope() as s:
        s.execute(
            text("""
                DELETE FROM presupuesto_items
                WHERE presupuesto_id = :pid AND articulo_codigo = :codigo
            """),
            {"pid": presupuesto_id, "codigo": codigo},
        )
        _recalcular_totales(s, presupuesto_id)


def _recalcular_totales(s: Session, presupuesto_id: int) -> None:
    """
    Subtotal = suma de (cantidad x precio_unitario) de SUS items.
    Total = subtotal - descuento. Todo en UNA query (UPDATE ... FROM).
    """
    s.execute(
        text("""
            UPDATE presupuestos p SET
                subtotal = i.sub,
                total = i.sub - p.descuento,
                actualizado_en = now()
            FROM (SELECT COALESCE(SUM(cantidad * precio_unitario), 0) AS sub
                  FROM presupuesto_items
                  WHERE presupuesto_id = :pid) i
            WHERE p.id = :pid
        """),
        {"pid": presupuesto_id},
    )


def obtener_presupuesto(presupuesto_id: int) -> dict | None:
    """Cabecera + items de un presupuesto, listo para armar el PDF."""
    with session_scope() as s:
        cab = s.execute(
            text("""
                SELECT id, chat_id, cliente_nombre, estado,
                       descuento::float AS descuento,
                       subtotal::float AS subtotal,
                       total::float AS total, pdf_path, creado_en
                FROM presupuestos
                WHERE id = :pid
            """),
            {"pid": presupuesto_id},
        ).mappings().first()
        if cab is None:
            return None
        items = s.execute(
            text("""
                SELECT i.articulo_codigo AS codigo, a.nombre,
                       i.cantidad, i.precio_unitario::float AS precio_unitario,
                       (i.cantidad * i.precio_unitario)::float AS importe
                FROM presupuesto_items i
                JOIN articulos a ON a.codigo = i.articulo_codigo
                WHERE i.presupuesto_id = :pid
                ORDER BY i.id
            """),
            {"pid": presupuesto_id},
        ).mappings().all()

    presupuesto = dict(cab)
    presupuesto["items"] = [dict(i) for i in items]
    return presupuesto


def listar_presupuestos(chat_id: int, limite: int = 10) -> list[dict]:
    """Los ultimos presupuestos de un usuario (para /presupuestos)."""
    with session_scope() as s:
        filas = s.execute(
            text("""
                SELECT id, cliente_nombre, estado,
                       total::float AS total, creado_en
                FROM presupuestos
                WHERE chat_id = :chat_id
                ORDER BY id DESC
                LIMIT :limite
            """),
            {"chat_id": chat_id, "limite": limite},
        ).mappings().all()
    return [dict(f) for f in filas]


def cambiar_estado(presupuesto_id: int, estado: str) -> None:
    """Valida el estado contra la lista permitida ANTES de escribir."""
    if estado not in ESTADOS_VALIDOS:
        raise ValueError(f"Estado invalido: '{estado}'. Valores: {ESTADOS_VALIDOS}")
    with session_scope() as s:
        s.execute(
            text("""
                UPDATE presupuestos
                SET estado = :estado, actualizado_en = now()
                WHERE id = :pid
            """),
            {"pid": presupuesto_id, "estado": estado},
        )


def aplicar_descuento(presupuesto_id: int, monto: float) -> None:
    """
    Setea el descuento del presupuesto (monto FIJO en pesos, no %) y
    recalcula el total: total = subtotal - descuento (mira
    _recalcular_totales).

    Valida contra el subtotal: un descuento mayor dejaria el total en
    negativo, cosa que el PDF mostraria sin sentido.
    """
    if monto < 0:
        raise ValueError("El descuento no puede ser negativo")
    with session_scope() as s:
        subtotal = s.execute(
            text("SELECT subtotal FROM presupuestos WHERE id = :pid"),
            {"pid": presupuesto_id},
        ).scalar_one_or_none()
        if subtotal is None:
            raise ValueError(f"No existe el presupuesto {presupuesto_id}")
        if monto > float(subtotal):
            raise ValueError(
                f"El descuento (${monto:,.2f}) no puede superar el subtotal "
                f"(${float(subtotal):,.2f})"
            )
        s.execute(
            text("""
                UPDATE presupuestos
                SET descuento = :monto, actualizado_en = now()
                WHERE id = :pid
            """),
            {"pid": presupuesto_id, "monto": monto},
        )
        _recalcular_totales(s, presupuesto_id)


def guardar_pdf_path(presupuesto_id: int, ruta: str) -> None:
    """Guarda donde quedo el PDF generado (lo usa el envio de Telegram)."""
    with session_scope() as s:
        s.execute(
            text("UPDATE presupuestos SET pdf_path = :ruta WHERE id = :pid"),
            {"pid": presupuesto_id, "ruta": ruta},
        )