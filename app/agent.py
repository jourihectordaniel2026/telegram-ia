"""
El agente de la libreria (Etapa 5): el loop de tool-calling.

A diferencia del bot.py viejo -que hacia "una pregunta, una respuesta"-,
aca el MODELO decide: puede pedir una o mas herramientas (buscar, crear
presupuesto, agregar items, generar PDF...) antes de dar la respuesta
final.

    usuario ---> [modelo] --tool_calls--> ejecutamos la herramienta
               <-- resultado (JSON) <--    (repository / pdf_generator)
               ... se repite ...
               [modelo] -- solo texto --> respuesta final al usuario

Reglas del loop:
- Cada vuelta es UNA llamada a la API; MAX_PASOS (config) la limita
  para que un modelo enroscado no genere un loop infinito.
- La memoria vive en la tabla `mensajes` (memory.py) y sobrevive a
  reinicios, pero SOLO se guardan los mensajes user/assistant
  definitivos: los pasos intermedios de herramientas viven unicamente
  en la lista `mensajes` de ESTA llamada (la tabla ademas tiene un
  CHECK que solo admite esos dos roles).
- Si la API falla se lanza ErrorIA con un mensaje apto para el usuario
  y NO se guarda nada (mismo criterio que bot.py).
"""
import json
import logging

from openai import APIConnectionError, APIStatusError, OpenAI

from app import memory
from app.config import MAX_PASOS, MAX_TOKENS, OPENROUTER_API_KEY, OPENROUTER_MODEL
from app.prompts import armar_historial
from app.tools import HERRAMIENTAS, ejecutar, serializar

log = logging.getLogger("agente")

BASE_URL_OPENROUTER = "https://openrouter.ai/api/v1"


class ErrorIA(Exception):
    """Fallo al consultar la IA. El mensaje ya esta pensado para el usuario."""


_cliente: OpenAI | None = None


def _obtener_cliente() -> OpenAI:
    """Cliente unico (singleton): crear uno por mensaje abre conexion nueva."""
    global _cliente
    if _cliente is None:
        if not OPENROUTER_API_KEY:
            raise ErrorIA(
                "Falta OPENROUTER_API_KEY en el .env (se obtiene en "
                "openrouter.ai/keys)."
            )
        _cliente = OpenAI(api_key=OPENROUTER_API_KEY, base_url=BASE_URL_OPENROUTER)
    return _cliente


def responder(chat_id: int, texto_usuario: str) -> tuple[str, list[str]]:
    """
    Procesa UN mensaje del usuario.

    Devuelve (respuesta_final, rutas_de_pdf). La lista de PDFs queda
    vacia salvo que el modelo haya llamado a generar_pdf en ESTE turno
    (la usa main.py en la Etapa 6 para mandar el documento a Telegram).
    """
    log.info("Mensaje recibido [%s]: %s", chat_id, texto_usuario[:80])

    # El mensaje nuevo se agrega EN MEMORIA todavia: si la llamada a la
    # IA falla no queda un 'user' colgado en la base sin respuesta.
    historial = memory.recuperar_historial(chat_id)
    historial.append({"role": "user", "content": texto_usuario})
    mensajes = armar_historial(historial, chat_id)

    cliente = _obtener_cliente()
    pdfs: list[str] = []

    for paso in range(1, MAX_PASOS + 1):
        try:
            r = cliente.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=mensajes,
                tools=HERRAMIENTAS,
                max_tokens=MAX_TOKENS,
            )
        except APIStatusError as e:
            log.exception("OpenRouter devolvio un error")
            if e.status_code in (401, 403):
                raise ErrorIA(
                    "OpenRouter rechazó la clave. Revisá OPENROUTER_API_KEY "
                    "en el .env."
                ) from e
            if e.status_code == 402:
                # Ojo: 402 no siempre es "sin saldo". Si el cuerpo habla de
                # in_flight_budget, es un limite TEMPORAL por uso reciente
                # (lleva Retry-After) y basta con esperar un poco.
                if "in_flight" in str(e).lower():
                    raise ErrorIA(
                        "El proveedor está limitando las consultas por uso "
                        "reciente. Esperá un par de minutos y probá de nuevo."
                    ) from e
                raise ErrorIA(
                    "OpenRouter no tiene saldo para ese modelo. Cargá créditos "
                    "en openrouter.ai/credits."
                ) from e
            if e.status_code == 429:
                raise ErrorIA(
                    "Se agotó el límite de pedidos a la IA. Probá de nuevo "
                    "en un momento."
                ) from e
            if e.status_code == 400:
                raise ErrorIA(
                    "El proveedor rechazó el pedido (error 400). Revisá el "
                    "modelo configurado en OPENROUTER_MODEL."
                ) from e
            raise ErrorIA(
                f"Uy, falló la consulta a la IA (error {e.status_code}). "
                "Probá de nuevo en un momento."
            ) from e
        except APIConnectionError as e:
            log.exception("No se pudo conectar con OpenRouter")
            raise ErrorIA(
                "No pude conectar con la IA. Revisá la conexión e intentá "
                "otra vez."
            ) from e

        mensaje = r.choices[0].message
        # Se agrega el mensaje COMPLETO (con sus tool_calls) para que el
        # proveedor vea que le respondemos a esa peticion concreta.
        mensajes.append(mensaje)

        # Sin tool_calls = el modelo termino: eso es la respuesta final.
        if not mensaje.tool_calls:
            texto = (mensaje.content or "").strip()
            if not texto:
                raise ErrorIA("La IA devolvió una respuesta vacía.")
            memory.guardar_mensaje(chat_id, "user", texto_usuario)
            memory.guardar_mensaje(chat_id, "assistant", texto)
            log.info("Respuesta [%s] en %s paso(s): %s", chat_id, paso, texto[:80])
            return texto, list(dict.fromkeys(pdfs))

        for llamada in mensaje.tool_calls:
            nombre = llamada.function.name
            try:
                argumentos = json.loads(llamada.function.arguments or "{}")
            except json.JSONDecodeError:
                resultado = {"error": f"Argumentos ilegibles para '{nombre}'"}
            else:
                log.info("tool [%s] paso %s: %s %s", chat_id, paso, nombre, argumentos)
                resultado = ejecutar(nombre, argumentos)
                if (
                    nombre == "generar_pdf"
                    and isinstance(resultado, dict)
                    and resultado.get("pdf_path")
                ):
                    pdfs.append(resultado["pdf_path"])
            contenido = serializar(resultado)
            log.info("  -> %s", contenido[:400])
            # Cada tool_call se responde con un mensaje role="tool" que
            # lleva el mismo id: asi el proveedor lo ata a su peticion.
            mensajes.append(
                {"role": "tool", "tool_call_id": llamada.id, "content": contenido}
            )

    raise ErrorIA(
        f"Llevé {MAX_PASOS} pasos sin llegar a una respuesta. "
        "Probá de nuevo con una consulta más corta."
    )
