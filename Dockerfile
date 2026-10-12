FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Las dependencias primero: asi la capa se cachea y solo se reinstala
# cuando cambia requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# El paquete completo: el bot corre como `python -m app.main`, asi que
# necesita todo app/ (config, db, repository, memory, tools, agent,
# prompts, pdf_generator).
COPY app/ app/

CMD ["python", "-u", "-m", "app.main"]
