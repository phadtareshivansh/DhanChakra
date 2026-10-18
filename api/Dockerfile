FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY tests/ ./tests/

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8000} --reload"]