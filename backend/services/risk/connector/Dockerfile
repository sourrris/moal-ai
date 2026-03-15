FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/libs/common /app/libs/common
COPY backend/services/risk/requirements.base.txt /app/services/risk/requirements.base.txt
COPY backend/services/risk/connector/requirements.txt /app/services/risk/connector/requirements.txt
COPY aegis-connectors/python /app/aegis-connectors/python
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/services/risk/connector/requirements.txt \
    && pip install --no-cache-dir -e /app/libs/common \
    && pip uninstall --yes setuptools wheel

COPY backend/services/risk/connector /app/service
WORKDIR /app/service

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8030"]
