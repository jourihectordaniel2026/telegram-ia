"""
Herramientas del agente: definiciones (lo que el MODELO lee) y
ejecucion (lo que corre contra nuestra base).

Dos mitades que van juntas:

  HERRAMIENTAS -> lista JSON en formato function-calling. El modelo la
                  recibe en cada llamada y decide cual usar y con que
                  argumentos. La "description" es TODO lo que el modelo
                  sabe de la herramienta: ahi se explica cuando usarla.
  EJECUTORES   -> dict nombre -> funcion de Python real. ejecutar()
                  toma la llamada del modelo y la ejecuta.

Reglas del modulo (las mismas que repository):
- Ninguna herramienta escribe SQL: van todas por repository/pdf_generator.
- Ningun error corta el chat: se devuelve {"error": "mensaje"} en
  espanol y el modelo se lo traslada al cliente.
- Los resultados son dict/list simples; los Decimal y datetime que la
  base devuelve los convierte serializar() (los proveedores exigen texto).
"""
import json
import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app import pdf_generator, repository

log = logging.getLogger("agente.tools")

# ---------------------------------------------------------------------------
# 1) Definiciones: lo que el MODELO lee
# ---------------------------------------------------------------------------
HERRAMIENTAS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_articulos",
            "description": (
                "Busca articulos del catalogo por nombre o marca ignorando "
                "acentos y mayusculas ('lapiz' encuentra 'Lapiz' y 'Lápiz'). "
                "Devuelve codigo, nombre, categoria, precio y stock. Usala "
                "ANTES de agregar un articulo a un presupuesto para conocer "
                "su codigo exacto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "termino": {
                        "type": "string",
                        "description": "Texto a buscar, ej. 'cuaderno A4'",
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Maximo de resultados a devolver (por defecto 10)",
                    },
                },
                "required": ["termino"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_articulo",
            "description": (
                "Detalle de UN articulo por su codigo exacto, ej. 'CUA-001'. "
                "Devuelve precio y stock actuales."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "codigo": {
                        "type": "string",
                        "description": "Codigo exacto del articulo, ej. 'CUA-001'",
                    },
                },
                "required": ["codigo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crear_presupuesto",
            "description": (
                "Crea un presupuesto nuevo en estado 'borrador' y devuelve su "
                "numero. Hacelo ANTES de agregar items. Usa el chat_id que el "
                "sistema te inyecta en el ultimo mensaje; nunca lo pidas al "
                "cliente ni lo inventes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "integer",
                        "description": "chat_id del usuario (el que te dio el sistema)",
                    },
                    "cliente_nombre": {
                        "type": "string",
                        "description": "Nombre del cliente si lo dijo; si no, no lo pases",
                    },
                },
                "required": ["chat_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agregar_item",
            "description": (
                "Agrega un articulo al presupuesto (si ya estaba, SUMA la "
                "cantidad) y recalcula subtotal y total. Requiere el numero de "
                "presupuesto y el codigo del articulo (conseguilo con "
                "buscar_articulos)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "presupuesto_id": {
                        "type": "integer",
                        "description": "Numero de presupuesto devuelto por crear_presupuesto",
                    },
                    "codigo": {
                        "type": "string",
                        "description": "Codigo del articulo, ej. 'CUA-001'",
                    },
                    "cantidad": {
                        "type": "integer",
                        "description": "Unidades a agregar, minimo 1 (por defecto 1)",
                    },
                },
                "required": ["presupuesto_id", "codigo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quitar_item",
            "description": (
                "Elimina un articulo del presupuesto y recalcula subtotal y "
                "total. Falla si el articulo no estaba."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "presupuesto_id": {"type": "integer", "description": "Numero de presupuesto"},
                    "codigo": {"type": "string", "description": "Codigo del articulo a quitar"},
                },
                "required": ["presupuesto_id", "codigo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_presupuesto",
            "description": (
                "Cabecera e items del presupuesto: estado, cliente, subtotal, "
                "descuento, total y la lista de articulos con sus importes. "
                "Usala para mostrarle al cliente que lleva antes de confirmar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "presupuesto_id": {"type": "integer", "description": "Numero de presupuesto"},
                },
                "required": ["presupuesto_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_presupuestos",
            "description": (
                "Ultimos presupuestos del cliente (numero, estado, total, "
                "fecha). Util para el comando /presupuestos o para recuperar "
                "el presupuesto en curso."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "integer",
                        "description": "chat_id del usuario (el que te dio el sistema)",
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Maximo de presupuestos a devolver (por defecto 10)",
                    },
                },
                "required": ["chat_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aplicar_descuento",
            "description": (
                "Setea un descuento FIJO en pesos (no porcentaje) sobre el "
                "presupuesto y recalcula el total. No puede superar el "
                "subtotal. Usalo solo si el cliente pide un descuento."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "presupuesto_id": {"type": "integer", "description": "Numero de presupuesto"},
                    "monto": {
                        "type": "number",
                        "description": "Descuento en pesos, ej. 150",
                    },
                },
                "required": ["presupuesto_id", "monto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cambiar_estado",
            "description": (
                "Cambia el estado de un presupuesto. Marca 'confirmado' cuando "
                "el cliente acepta el pedido y 'enviado' cuando ya se paso el "
                "PDF. Otros valores: 'borrador', 'anulado'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "presupuesto_id": {"type": "integer", "description": "Numero de presupuesto"},
                    "estado": {
                        "type": "string",
                        "enum": ["borrador", "confirmado", "enviado", "anulado"],
                        "description": "Estado nuevo",
                    },
                },
                "required": ["presupuesto_id", "estado"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generar_pdf",
            "description": (
                "Genera el PDF del presupuesto en output/, guarda la ruta en "
                "la base y la devuelve. El presupuesto debe tener al menos un "
                "item. Usala cuando el cliente CONFIRME el pedido."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "presupuesto_id": {"type": "integer", "description": "Numero de presupuesto"},
                },
                "required": ["presupuesto_id"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# 2) Implementaciones: lo que se ejecuta
# ---------------------------------------------------------------------------
def _o_error(presupuesto_id: int) -> dict:
    """Trae el presupuesto o lanza un error claro (vuelve como {"error"})."""
    presupuesto = repository.obtener_presupuesto(presupuesto_id)
    if presupuesto is None:
        raise ValueError(
            f"No existe el presupuesto #{presupuesto_id}. "
            "Puede que no se haya creado: usá crear_presupuesto primero."
        )
    return presupuesto


def _crear_presupuesto(chat_id: int, cliente_nombre: str | None = None) -> dict:
    pid = repository.crear_presupuesto(chat_id, cliente_nombre)
    return {
        "presupuesto_id": pid,
        "estado": "borrador",
        "mensaje": f"Presupuesto #{pid} creado. Ahora agregá items con agregar_item.",
    }


def _agregar_item(presupuesto_id: int, codigo: str, cantidad: int = 1) -> dict:
    _o_error(presupuesto_id)
    repository.agregar_item(presupuesto_id, codigo, cantidad)
    p = repository.obtener_presupuesto(presupuesto_id)
    return {
        "presupuesto_id": presupuesto_id,
        "items": len(p["items"]),
        "subtotal": p["subtotal"],
        "total": p["total"],
        "mensaje": f"Agregado {cantidad} x {codigo}. Total actual: ${p['total']:,.2f}.",
    }


def _quitar_item(presupuesto_id: int, codigo: str) -> dict:
    p = _o_error(presupuesto_id)
    if not any(i["codigo"] == codigo for i in p["items"]):
        raise ValueError(
            f"El articulo {codigo} no esta en el presupuesto #{presupuesto_id}."
        )
    repository.quitar_item(presupuesto_id, codigo)
    p = repository.obtener_presupuesto(presupuesto_id)
    return {
        "presupuesto_id": presupuesto_id,
        "items": len(p["items"]),
        "subtotal": p["subtotal"],
        "total": p["total"],
        "mensaje": f"Quitado {codigo}. Total actual: ${p['total']:,.2f}.",
    }


def _aplicar_descuento(presupuesto_id: int, monto: float) -> dict:
    _o_error(presupuesto_id)
    repository.aplicar_descuento(presupuesto_id, monto)
    p = repository.obtener_presupuesto(presupuesto_id)
    return {
        "presupuesto_id": presupuesto_id,
        "descuento": p["descuento"],
        "total": p["total"],
        "mensaje": f"Descuento de ${monto:,.2f} aplicado. Total: ${p['total']:,.2f}.",
    }


def _cambiar_estado(presupuesto_id: int, estado: str) -> dict:
    _o_error(presupuesto_id)
    repository.cambiar_estado(presupuesto_id, estado)
    return {
        "presupuesto_id": presupuesto_id,
        "estado": estado,
        "mensaje": f"Presupuesto #{presupuesto_id} paso a '{estado}'.",
    }


def _generar_pdf(presupuesto_id: int) -> dict:
    p = _o_error(presupuesto_id)
    if not p["items"]:
        raise ValueError(
            f"El presupuesto #{presupuesto_id} no tiene items: "
            "primero agregá articulos con agregar_item."
        )
    ruta = pdf_generator.generar_pdf(p)
    repository.guardar_pdf_path(presupuesto_id, str(ruta))
    return {
        "presupuesto_id": presupuesto_id,
        "pdf_path": str(ruta),
        "total": p["total"],
        "mensaje": f"PDF generado en {ruta}.",
    }


# ---------------------------------------------------------------------------
# 3) Puente entre ambas mitades
# ---------------------------------------------------------------------------
EJECUTORES = {
    "buscar_articulos": repository.buscar_articulos,
    "obtener_articulo": repository.obtener_articulo,
    "crear_presupuesto": _crear_presupuesto,
    "agregar_item": _agregar_item,
    "quitar_item": _quitar_item,
    "obtener_presupuesto": repository.obtener_presupuesto,
    "listar_presupuestos": repository.listar_presupuestos,
    "aplicar_descuento": _aplicar_descuento,
    "cambiar_estado": _cambiar_estado,
    "generar_pdf": _generar_pdf,
}


def ejecutar(nombre: str, argumentos: dict):
    """
    Ejecuta la herramienta que eligio el modelo.

    NADA de esto corta el chat: cualquier fallo (argumentos malos,
    articulo inexistente, base caida...) vuelve como {"error": ...}
    para que el modelo se lo explique al cliente y, si hace falta,
    reintente con otros argumentos.
    """
    funcion = EJECUTORES.get(nombre)
    if funcion is None:
        disponibles = ", ".join(sorted(EJECUTORES))
        return {"error": f"Herramienta '{nombre}' inexistente. Disponibles: {disponibles}"}
    try:
        return funcion(**argumentos)
    except TypeError as e:
        # argumento faltante, de mas, o tipo incorrecto (cantida="cinco")
        return {"error": f"Argumentos invalidos para '{nombre}': {e}"}
    except ValueError as e:
        # errores de negocio con mensaje pensado (repository / wrappers)
        return {"error": str(e)}
    except IntegrityError:
        # la mas comun: chat_id que no existe en usuarios (FK)
        return {
            "error": (
                "El chat_id no corresponde a un usuario registrado: "
                "primero debe iniciar con /start."
            )
        }
    except Exception as e:  # noqa: BLE001 - el error va al modelo, no al usuario
        log.exception("Fallo la herramienta %s(%s)", nombre, argumentos)
        return {"error": f"Error interno al ejecutar '{nombre}': {e}"}


def _a_json(obj):
    """Conversion final para json.dumps: Decimal y datetime no son JSON."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


def serializar(datos) -> str:
    """
    dict/list -> texto JSON para mandarle al proveedor (que exige texto).

    ensure_ascii=False para que "á/ñ" queden legibles, igual que en
    memory.py (el mismo truco, por la misma razon).
    """
    return json.dumps(datos, ensure_ascii=False, default=_a_json)
