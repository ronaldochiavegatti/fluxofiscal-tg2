FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Consome as três filas (ADR-0003). A concorrência real por fila entra na
# US-18, quando houver tarefa que justifique perfis diferentes.
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "-Q", "ocr,llm,manutencao"]
