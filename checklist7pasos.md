# 📋 Checklist de Seguimiento: App de IA para Librería

## 🗄️ Etapa 1 — Estructura y base de datos
- [x] Crear `db/schema.sql` (tablas: categorias, articulos, usuarios, presupuestos, presupuesto_items, mensajes, memoria_usuario + vista `v_catalogo`).
- [x] Crear `db/seed.sql` e insertar el catálogo inicial de la librería.
- [x] Modificar `docker-compose.yml` para añadir el servicio de base de datos (`postgres:16`) y `Adminer`.
- [x] 🧪 **Verificación:** Ejecutar `docker compose up -d` y realizar una query de prueba con `psql` desde la terminal para confirmar que las tablas y la vista existen.

## 🔌 Etapa 2 — Conexión y repositorio
- [x] Crear `app/config.py` para las variables de entorno.
- [x] Crear `app/db.py` para inicializar el engine de SQLAlchemy.
- [x] Crear `app/repository.py` con las funciones CRUD de presupuestos y la función de búsqueda de artículos que ignore acentos.
- [x] 🧪 **Verificación:** Correr un script rápido o query de prueba que use el repositorio y devuelva artículos reales de la base de datos.

## 📄 Etapa 3 — PDF
- [x] Crear `app/pdf_generator.py` utilizando ReportLab.
- [x] Diseñar el layout del PDF: encabezado, número, fecha, cliente, ítems, subtotales, total y validez.
- [x] Configurar el guardado automático de los archivos generados en la carpeta `output/`.
- [x] 🧪 **Verificación:** Generar un PDF de prueba mediante script y abrirlo para revisar el diseño visual.

## 🧠 Etapa 4 — Memory
- [x] Crear `app/memory.py` para la persistencia del chat.
- [x] Desarrollar la función para guardar cada mensaje en la tabla `mensajes` usando el formato JSONB.
- [x] Desarrollar la función para recuperar el historial de chat filtrando por `chat_id`.
- [x] 🧪 **Verificación:** Enviar un par de mensajes de prueba y confirmar que impacten correctamente en la tabla correspondiente.

## 🤖 Etapa 5 — El agente (El corazón del TP)
- [x] Crear `app/prompts.py` con las instrucciones del sistema para el comportamiento del agente de la librería.
- [x] Crear `app/tools.py` con las definiciones en formato JSON de las ~10 herramientas que usará el modelo.
- [x] Crear `app/agent.py` implementando el loop de ejecución (Modelo decide tool ➔ Se ejecuta ➔ El resultado vuelve al modelo ➔ Repite hasta la respuesta final).
- [x] 🧪 **Verificación:** Ejecutar una consola de prueba local (sin Telegram) escribiendo *"necesito 5 cuadernos A4"* y verificar en los logs que las tools se disparen de manera lógica.

## 🤖 Etapa 6 — Bot de Telegram
- [x] Crear `app/main.py` para inicializar el flujo del bot de Telegram.
- [x] Configurar los comandos principales: `/start`, `/nuevo` y `/presupuestos`.
- [x] Implementar el reenvío de mensajes del usuario hacia el módulo del agente.
- [x] Integrar la generación y el envío automático del PDF como documento al chat de Telegram.
- [x] Reutilizar la lógica existente de logging, estados ("escribiendo...") y control de errores.
- [x] 🧪 **Verificación:** Levantar el entorno con `docker compose --profile bot up -d --build` y simular un pedido completo desde la app de Telegram.

## 🏁 Etapa 7 — Cierre
- [x] Probar todo el flujo de inicio a fin siguiendo el ejemplo exacto provisto en la consigna de la diplomatura.
- [x] Redactar el archivo `README.md` detallando las instrucciones de instalación y uso.
- [x] Ejecutar `git init`, añadir los archivos del proyecto y realizar el commit final de entrega.
