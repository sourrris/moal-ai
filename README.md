# Real-Time AI Risk Monitoring System

Production-grade distributed scaffold for real-time AI risk monitoring with FastAPI microservices, RabbitMQ event routing, Redis Pub/Sub WebSocket streaming, PostgreSQL persistence, TensorFlow anomaly detection, and React dashboard.

## Stack
- Backend: Python 3.11+, FastAPI, PostgreSQL, RabbitMQ, Redis, TensorFlow
- Frontend: React + TypeScript + Recharts + WebSocket client
- Infra: Docker + Docker Compose

## Services
- API Gateway: Auth, ingestion, model management proxy
- Event Worker: Consumes events, calls ML inference, persists results, emits alerts
- ML Inference: TensorFlow autoencoder train/infer + model version activation
- Notification Service: Rabbit alert consumer + Redis Pub/Sub + WebSocket fan-out
- Dashboard: React live monitoring UI

## Quick Start
1. Copy `.env.example` to `.env` and set secrets.
2. Run:

```bash
docker compose up --build
```

3. Open dashboard at `http://localhost:5173`.
4. RabbitMQ management at `http://localhost:15672` (`guest/guest`).

## Default Demo Credentials
- username: `admin`
- password: `admin123`

## Docs
- Architecture and diagrams: `docs/architecture.md`
- Folder structure: `docs/folder-structure.md`

## Key Production Patterns Included
- Event-driven microservices via RabbitMQ
- Redis Pub/Sub-based real-time streaming
- JWT authentication
- Idempotent ingestion and processing controls
- Retry + dead-letter queue handling
- Structured JSON logging
- Health checks for orchestration
