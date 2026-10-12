# Asistente de la Librería UTN — Bot de Telegram con IA

Sistema completo de 7 etapas: agente conversacional con function-calling, búsqueda en catálogo, presupuestos persistentes en PostgreSQL, generación de PDF y memoria que sobrevive a reinicios.

## 📋 Resumen de etapas

| Etapa | Qué entrega |
|-------|-------------|
| 1 | Base de datos PostgreSQL + schema (categorías, artículos, usuarios, presupuestos, items, mensajes, memoria) + Adminer |
| 2 | Conexión SQLAlchemy + repositorio (búsqueda sin acentos, CRUD de presupuestos) |
| 3 | Generación de PDF con ReportLab (encabezado, tabla de items, totales, validez) |
| 4 | Memoria persistente en tabla `mensajes` (JSONB) — sobrevive a reinicios |
| 5 | **Agente**: loop de tool-calling con OpenAI SDK apuntando a OpenRouter (10 herramientas) |
| 6 | **Bot Telegram**: `/start`, `/nuevo`, `/presupuestos`, envío automático de PDF |
| 7 | Este README + entrega en Git |

## 🚀 Instalación y puesta en marcha

### Requisitos
- Docker Desktop (con el demonio corriendo)
- Claves en `.env` (ver sección **Variables de entorno**)

### 1. Clonar y configurar
```bash
git clone <este-repositorio>
cd Telegram-IA
cp .env.example .env
# Editar .env con tus claves reales (ver abajo)
```

### 2. Levantar todo
```bash
docker compose --profile bot up -d --build
```

El `--profile bot` es obligatorio: el servicio `bot` está declarado con `profiles: ["bot"]`.

### 3. Verificar
```bash
docker compose ps                    # los tres contenedores: "running"
docker compose logs -f bot           # logs en vivo (Ctrl+C para salir)
# Deberías ver: "Bot listo. Esperando mensajes (long polling)..."
```

### 4. Probar en Telegram
Buscá tu bot en Telegram y mandale:
- `/start` — bienvenida + registra tu usuario en la base
- `"necesito 5 cuadernos A4"` — el agente busca, pregunta cuál (hay 2), arma el presupuesto y genera el PDF
- `/presupuestos` — lista tus últimos presupuestos (lee directo de la base, sin IA)
- `/nuevo` — borra la memoria del chat (los presupuestos guardados no se tocan)

### 5. Detener
```bash
docker compose --profile bot down
```
Los datos de PostgreSQL **sobreviven** gracias al volumen `pgdata`.

### Adminer (interfaz web de la base)
```bash
# http://localhost:8080
# Sistema: PostgreSQL | Servidor: db | Usuario: libreria | Base: libreria | Contraseña: la de POSTGRES_PASSWORD
```

## 🔧 Variables de entorno (`.env`)

| Variable | Requerida | Qué hace |
|----------|-----------|----------|
| `TELEGRAM_BOT_TOKEN` | **Sí** | Token de @BotFather (`/newbot`) |
| `OPENROUTER_API_KEY` | **Sí*** | Clave de OpenRouter (openrouter.ai/keys) |
| `ANTHROPIC_API_KEY` | * | Clave de Anthropic (console.anthropic.com) — alternativa a OpenRouter |
| `PROVEEDOR` | No | `auto` (default), `openrouter`, `anthropic` |
| `OPENROUTER_MODEL` | No | Default: `anthropic/claude-sonnet-5.5` |
| `CLAUDE_MODEL` | No | Default: `claude-sonnet-5-5` |
| `MAX_TOKENS` | No | Default: 1024 |
| `MAX_HISTORIAL` | No | Default: 20 (mensajes que se le pasan al modelo) |
| `MAX_PASOS` | No | Default: 10 (vueltas máximas del loop tool-calling) |
| `POSTGRES_PASSWORD` | **Sí** | Contraseña de la base (usa la misma en `.env` y `docker-compose.yml`) |
| `DB_HOST` / `DB_PORT` | No | Inyectados por docker-compose al contenedor (`db:5432`) |
| `LOG_LEVEL` | No | `INFO` (default), `DEBUG`, `WARNING` |

> \* **Al menos una** de `OPENROUTER_API_KEY` u `ANTHROPIC_API_KEY` es obligatoria. El bot usa OpenRouter por defecto si hay clave; si no, Anthropic.

**Ejemplo `.env`:**
```env
TELEGRAM_BOT_TOKEN=123456789:ABC-DEF...
OPENROUTER_API_KEY=sk-or-v1-...
PROVEEDOR=auto
POSTGRES_PASSWORD=libreria-dev
```

## 🤖 Comandos del bot

| Comando | Descripción |
|---------|-------------|
| `/start` | Bienvenida + registra tu usuario en la base (necesario por FOREIGN KEY) |
| `/nuevo` | Borra la memoria de la conversación (`mensajes`); los presupuestos **no** se borran |
| `/presupuestos` | Lista los últimos 10 presupuestos leyendo directo de la base (funciona aunque la IA esté sin saldo) |
| *Cualquier texto* | Lo procesa el agente: busca en catálogo, crea/actualiza presupuesto, genera PDF si confirmás |

## 🏗️ Arquitectura (código)

```
app/
├── main.py            # Bot Telegram: handlers + envío de PDF
├── agent.py           # Loop tool-calling: modelo decide → ejecuta → vuelve al modelo
├── tools.py           # 10 herramientas (definiciones JSON + dispatcher)
├── prompts.py         # SYSTEM_PROMPT + armar_historial()
├── memory.py          # Persistencia en tabla mensajes (JSONB)
├── repository.py      # TODO el SQL: buscar, CRUD presupuestos, items, descuento
├── pdf_generator.py   # ReportLab → output/presupuesto_<id>.pdf
├── config.py          # Único lugar que lee os.getenv()
└── db.py              # Engine SQLAlchemy + session_scope
```

**Flujo de un mensaje:**
```
Usuario (Telegram)
    ↓
main.responder() — registra usuario, estado "escribiendo..."
    ↓
agent.responder(chat_id, texto)
    ├─ Recupera historial de la tabla mensajes (JSONB)
    ├─ Arma messages con system prompt + chat_id inyectado
    ├─ Loop: OpenRouter decide tool_calls → tools.ejecutar() → resultado
    └─ Hasta respuesta final (sin tool_calls)
    ↓
main.py: reply_text(respuesta) + reply_document(PDF) si se generó
```

## 🛠️ Herramientas del agente (10)

| Herramienta | Para qué sirve |
|-------------|----------------|
| `buscar_articulos` | Busca en `v_catalogo` ignorando acentos/mayúsculas |
| `obtener_articulo` | Detalle de un artículo por código exacto |
| `crear_presupuesto` | Crea presupuesto en borrador (necesita `chat_id`) |
| `agregar_item` | Agrega ítem (si existe, suma cantidad) + recalcula totales |
| `quitar_item` | Elimina ítem + recalcula |
| `obtener_presupuesto` | Cabecera + items + totales (para mostrar al cliente) |
| `listar_presupuestos` | Últimos N presupuestos del usuario |
| `aplicar_descuento` | Descuento fijo en pesos (valida contra subtotal) |
| `cambiar_estado` | `borrador` → `confirmado` → `enviado` / `anulado` |
| `generar_pdf` | Genera PDF en `output/`, guarda ruta en la base |

## 📊 Base de datos (tablas principales)

- `usuarios` — `chat_id` PK, nombre, username
- `categorias` / `articulos` — catálogo (72 artículos de seed)
- `presupuestos` — cabecera (estado, descuento, subtotal, total, pdf_path)
- `presupuesto_items` — líneas (cantidad, precio_unitario copiado al momento)
- `mensajes` — historial persistente (`contenido` JSONB con `role`/`content`)
- `memoria_usuario` — clave/valor por usuario (no usado por el agente actual)
- `v_catalogo` — vista con `texto_normalizado` (lower + unaccent) para búsqueda

## 🧪 Pruebas automatizadas (sin Telegram ni créditos)

```bash
# Etapa 2: repositorio + búsqueda
docker compose --profile bot run --rm -e DB_HOST=db -e DB_PORT=5432 -v "$(pwd):/work" -w /work bot python verificar_etapa2.py

# Etapa 3: PDF real
docker compose --profile bot run --rm -e DB_HOST=db -e DB_PORT=5432 -v "$(pwd):/work" -w /work bot python probar_pdf.py

# Etapa 4: memoria (2 contenedores = persistencia real)
docker compose --profile bot run --rm -e DB_HOST=db -e DB_PORT=5432 -v "$(pwd):/work" -w /work bot python verificar_memoria.py

# Etapa 5: agente completo (necesita créditos OpenRouter para turnos 1-2)
docker compose --profile bot run --rm -e DB_HOST=db -e DB_PORT=5432 -v "$(pwd):/work" -w /work bot python probar_agente.py

# Etapa 5: tramo generar_pdf (cliente OpenAI simulado, sin créditos)
docker compose --profile bot run --rm -e DB_HOST=db -e DB_PORT=5432 -v "$(pwd):/work" -w /work bot python verificar_loop_pdf.py

# Etapa 6: handlers del bot (updates falsos, cliente simulado)
docker compose --profile bot run --rm -e DB_HOST=db -e DB_PORT=5432 -v "$(pwd):/work" -w /work bot python verificar_main.py
```

> **Nota:** `probar_agente.py` (Etapa 5 completa) necesita saldo en OpenRouter. Las otras usan cliente simulado y corren sin créditos.

## 📁 Archivos de salida

- PDFs generados: `output/presupuesto_<id>.pdf` (se sirven desde el contenedor al mandar `reply_document`)
- Logs: stdout del contenedor (`docker compose logs -f bot`)

## ⚠️ Limitaciones conocidas

1. **Créditos OpenRouter/Anthropic**: sin saldo, el agente responde "El proveedor está limitando las consultas". Los comandos `/start`, `/nuevo`, `/presupuestos` funcionan igual.
2. **Stock**: el agente consulta stock disponible pero **no lo descuenta** al confirmar (pedido de mejora futuro).
3. **Un solo contenedor de bot**: si escalás horizontalmente, la memoria en tabla `mensajes` sigue funcionando (es compartida), pero el long polling de `python-telegram-bot` no está preparado para múltiples instancias sin webhook.

## 📦 Entrega (Git)

```bash
git init
git add .
git commit -m "Entrega TP: Asistente Librería UTN — 7 etapas

- PostgreSQL + Adminer (docker-compose)
- SQLAlchemy + repositorio con búsqueda sin acentos
- PDF ReportLab con layout completo
- Memoria persistente en mensajes (JSONB)
- Agente tool-calling (10 herramientas) con OpenAI SDK → OpenRouter
- Bot Telegram: /start /nuevo /presupuestos + envío PDF
- Tests automatizados por etapa

🤖 Generated with Codebuff"
```

---

**Desarrollado para la Diplomatura en IA — Trabajo Práctico Integrador**  
Librería UTN · 2026