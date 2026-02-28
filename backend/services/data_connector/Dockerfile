FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/libs/common /app/libs/common
COPY backend/services/data_connector/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt \
    && pip install --no-cache-dir -e /app/libs/common

COPY backend/services/data_connector /app/service
WORKDIR /app/service

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8030"]
