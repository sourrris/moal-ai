# Project Access Guide (Redis, Database, RabbitMQ, APIs, and Services)

This document explains how to access every major runtime component in this project from your host machine and from inside Docker.

## 1. What this project starts

When you run Docker Compose, these containers are created:

1. `risk-postgres` (PostgreSQL) on host port `5432`
2. `risk-rabbitmq` (RabbitMQ + management UI) on host ports `5672` and `15672`
3. `risk-redis` (Redis) on host port `6379`
4. `risk-ml-inference` (FastAPI) on host port `8001`
5. `risk-api-gateway` (FastAPI) on host port `8000`
6. `risk-event-worker` (FastAPI + queue consumer) on host port `8010`
7. `risk-notification-service` (FastAPI + WebSocket) on host port `8020`
8. `risk-dashboard` (Vite React app) on host port `5173`

## 2. Start and verify the stack

Run from the repository root:

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

Read logs:

```bash
docker compose logs -f api-gateway
docker compose logs -f event-worker
docker compose logs -f notification-service
docker compose logs -f ml-inference
```

## 3. Credentials and defaults

From `.env.example` and init SQL:

1. PostgreSQL database: `risk_monitor`
2. PostgreSQL user/password: `risk` / `risk`
3. JWT secret default: `change-me-in-prod` unless overridden in `.env`
4. Demo login user: `admin`
5. Demo login password: `admin123`
6. RabbitMQ management user/password: `guest` / `guest`

## 4. Access matrix (quick reference)

Primary routed URLs (via local reverse proxy):

1. Dashboard UI: `http://app.localhost`
2. API Gateway: `http://api.localhost`
3. Notification service (status): `http://ws.localhost/v1/notifications/connections`

Direct host ports (bypass reverse proxy):

1. Dashboard UI: `http://localhost:5173`
2. API Gateway: `http://localhost:8000`
3. ML Inference service: `http://localhost:8001`
4. Event Worker health: `http://localhost:8010/health/live`
5. Notification service health: `http://localhost:8020/health/live`
6. RabbitMQ management UI: `http://localhost:15672`
7. PostgreSQL TCP endpoint: `localhost:5432`
8. Redis TCP endpoint: `localhost:6379`

Inside Docker network, service DNS names are:

1. `postgres:5432`
2. `rabbitmq:5672`
3. `redis:6379`
4. `ml-inference:8000`
5. `api-gateway:8000`
6. `event-worker:8010`
7. `notification-service:8020`

## 5. Access PostgreSQL

Host machine access:

```bash
psql "postgresql://risk:risk@localhost:5432/risk_monitor"
```

Container access:

```bash
docker exec -it risk-postgres psql -U risk -d risk_monitor
```

Useful SQL checks:

```sql
\dt
SELECT username, role, created_at FROM users;
SELECT count(*) AS total_events FROM events;
SELECT count(*) AS total_results FROM anomaly_results;
SELECT model_name, model_version, active, updated_at
FROM model_registry
ORDER BY updated_at DESC;
```

Schema tables created on startup:

1. `users`
2. `events`
3. `anomaly_results`
4. `model_registry`

## 6. Access Redis

Host machine access:

```bash
redis-cli -h localhost -p 6379 ping
```

Container access:

```bash
docker exec -it risk-redis redis-cli
```

Useful Redis checks:

```bash
PING
PUBSUB CHANNELS
KEYS processed:*
```

Live alert channel used by notification service:

1. `risk.alerts.live`

Watch live alerts directly from Redis:

```bash
docker exec -it risk-redis redis-cli SUBSCRIBE risk.alerts.live
```

## 7. Access RabbitMQ

Web UI:

1. Open `http://localhost:15672`
2. Login with `guest` / `guest`

AMQP endpoint:

1. `amqp://guest:guest@localhost:5672/` from host
2. `amqp://guest:guest@rabbitmq:5672/` from other containers

Expected topology names:

1. Exchanges: `risk.events.exchange`, `risk.alerts.exchange`, `risk.deadletter.exchange`
2. Queues: `risk.events.queue`, `risk.alerts.queue`, `risk.events.dlq`
3. Routing keys: `risk.events.ingested`, `risk.alerts.raised`

Quick container diagnostics:

```bash
docker exec -it risk-rabbitmq rabbitmq-diagnostics -q ping
docker exec -it risk-rabbitmq rabbitmqctl list_queues name messages consumers
docker exec -it risk-rabbitmq rabbitmqctl list_exchanges name type
```

## 8. Access API Gateway endpoints

Base URL:

1. `http://localhost:8000`

Health:

```bash
curl -s http://localhost:8000/health/live
curl -s http://localhost:8000/health/ready
```

Get JWT token:

```bash
curl -s -X POST http://localhost:8000/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

Store token in shell variable:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r '.access_token')
```

Call protected endpoints:

```bash
curl -s http://localhost:8000/v1/overview/metrics \
  -H "Authorization: Bearer $TOKEN"

curl -s http://localhost:8000/v1/models/active \
  -H "Authorization: Bearer $TOKEN"

curl -s "http://localhost:8000/v1/events?limit=10" \
  -H "Authorization: Bearer $TOKEN"

curl -s "http://localhost:8000/v1/alerts?limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

Ingest a sample event:

```bash
curl -s -X POST http://localhost:8000/v1/events/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id":"tenant-alpha",
    "source":"gateway",
    "event_type":"txn_risk",
    "payload":{"amount":1500,"currency":"USD"},
    "features":[0.12,0.34,0.56,0.78],
    "occurred_at":"2026-01-01T00:00:00Z"
  }'
```

## 9. Access ML Inference service

Service base URL from host:

1. `http://localhost:8001`

Health:

```bash
curl -s http://localhost:8001/health/live
curl -s http://localhost:8001/health/ready
```

Direct inference call:

```bash
curl -s -X POST http://localhost:8001/v1/infer \
  -H "Content-Type: application/json" \
  -d '{"features":[0.12,0.34,0.56,0.78]}'
```

## 10. Access Event Worker

Service base URL from host:

1. `http://localhost:8010`

Health:

```bash
curl -s http://localhost:8010/health/live
curl -s http://localhost:8010/health/ready
```

Worker behavior to know when debugging access:

1. Consumes `risk.events.queue` from RabbitMQ
2. Deduplicates using Redis keys `processed:{event_id}`
3. Writes anomaly results to PostgreSQL
4. Publishes alerts to `risk.alerts.exchange`

## 11. Access Notification Service and WebSocket

Service base URL from host:

1. `http://localhost:8020`

Health and connection count:

```bash
curl -s http://localhost:8020/health/live
curl -s http://localhost:8020/health/ready
curl -s http://localhost:8020/v1/notifications/connections
```

WebSocket endpoint:

1. `ws://localhost:8020/ws/alerts?token=<JWT>`

Test WebSocket stream with `wscat`:

```bash
npx wscat -c "ws://localhost:8020/ws/alerts?token=$TOKEN"
```

The client sends `ping` frames periodically to keep connection alive.

## 12. Access running containers/shells

Open shell in each container:

```bash
docker exec -it risk-api-gateway sh
docker exec -it risk-event-worker sh
docker exec -it risk-ml-inference sh
docker exec -it risk-notification-service sh
docker exec -it risk-postgres sh
docker exec -it risk-rabbitmq sh
docker exec -it risk-redis sh
docker exec -it risk-dashboard sh
```

Inspect environment variables in a container:

```bash
docker exec risk-api-gateway env | sort
docker exec risk-event-worker env | sort
docker exec risk-notification-service env | sort
```

## 13. Inspect persisted data volumes

Named volumes in Compose:

1. `postgres_data` for PostgreSQL files
2. `model_data` for ML model artifacts

Inspect volume metadata:

```bash
docker volume ls
docker volume inspect aegis-ai_postgres_data
docker volume inspect aegis-ai_model_data
```

Note: actual volume names are usually prefixed by the Compose project name (for example `aegis-ai_...`).

## 14. Full end-to-end access check

Run these in order:

1. `docker compose ps` and verify all services are `healthy`/`running`
2. Obtain JWT token from `/v1/auth/token`
3. Ingest one event through `/v1/events/ingest`
4. Query `/v1/events` and `/v1/alerts`
5. Open Redis subscription on `risk.live.alerts` (legacy: `risk.alerts.live`)
6. Open WebSocket on `/ws/alerts?token=...`
7. Confirm `anomaly_results` rows appear in PostgreSQL

## 15. Common access issues

1. `401 Invalid token`: JWT missing/expired or wrong secret in services.
2. WebSocket closes immediately: token not passed as `?token=...`.
3. RabbitMQ login failure from host: use `guest/guest` on localhost.
4. No alerts in UI: check `risk.event.queue` and `risk.alert.queue` message counts in RabbitMQ.
5. DB connection errors: confirm `risk-postgres` healthy and DSN points to `postgres:5432` inside containers, `localhost:5432` from host.
6. Redis timeout: confirm `risk-redis` healthy and reachable on `6379`.

## 16. Relevant source files for access configuration

1. `docker-compose.yml`
2. `.env.example`
3. `backend/libs/common/risk_common/config.py`
4. `backend/libs/common/risk_common/messaging.py`
5. `infra/postgres/init/001_schema.sql`
6. `backend/services/risk/api/app/api/routes_auth.py`
7. `backend/services/risk/notification/app/api/notification_routes.py`
