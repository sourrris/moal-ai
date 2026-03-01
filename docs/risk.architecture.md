# Real-Time AI Risk Monitoring System

## 1) High-Level Architecture

```mermaid
graph TD
    U[Clients / Partners] --> AG[API Gateway\nFastAPI + JWT]
    AG -->|Persist event| PG[(PostgreSQL)]
    AG -->|Publish event| RMQ[(RabbitMQ)]

    RMQ -->|risk.event.queue| EW[Event Worker\nFastAPI Worker Runtime]
    EW -->|ML inference request| ML[ML Inference Service\nTensorFlow]
    EW -->|Persist anomaly result| PG
    EW -->|Publish alert| RMQ

    RMQ -->|risk.alert.queue| NS[Notification Service\nFastAPI + WebSocket]
    NS -->|Publish alert| REDIS[(Redis Pub/Sub)]
    REDIS -->|Fan-out| NS
    NS -->|WebSocket stream| FE[React Dashboard]

    AG -. model management .-> ML
```

## 2) Service Responsibilities

### API Gateway (FastAPI)
- JWT authentication (`/v1/auth/token`).
- Event ingestion REST endpoint (`/v1/events/ingest`).
- Idempotent insert on `events.event_id` primary key.
- Publishes accepted events to RabbitMQ exchange.
- Proxies model management APIs to ML service.
- Health checks: `/health/live`, `/health/ready`.

### Event Worker
- Consumes ingested events from RabbitMQ.
- Calls ML service for anomaly scoring.
- Writes results to `anomaly_results`, updates event status.
- Publishes anomaly alerts to alert exchange.
- Retry strategy with header `x-retry-count`.
- Dead-letter routing after max retries.
- Idempotency via Redis key (`processed:{event_id}`).
- Health checks: `/health/live`, `/health/ready`.

### ML Inference Service
- TensorFlow autoencoder-based inference (`/v1/infer`).
- Model training endpoint (`/v1/models/train`).
- Model activation and active-model lookup.
- Versioned model persistence in `/models`.
- Dynamic threshold from validation reconstruction error quantile.
- Health checks: `/health/live`, `/health/ready`.

### WebSocket Notification Service
- Consumes alert messages from RabbitMQ.
- Publishes alert payloads to Redis channel (`risk.live.alerts`).
- Subscribes Redis Pub/Sub channel and broadcasts over WebSocket.
- Authenticated WebSocket endpoint (`/ws/risk-stream?channels=alerts,metrics&token=...`).
- Health checks: `/health/live`, `/health/ready`.

## 3) Data Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant AG as API Gateway
    participant R as RabbitMQ
    participant W as Event Worker
    participant ML as ML Service
    participant DB as PostgreSQL
    participant N as Notification Service
    participant RS as Redis Pub/Sub
    participant UI as React Dashboard

    C->>AG: POST /v1/events/ingest (JWT)
    AG->>DB: INSERT events (ON CONFLICT DO NOTHING)
    AG->>R: Publish EventEnvelope

    R->>W: Deliver event
    W->>ML: POST /v1/infer
    ML-->>W: anomaly_score + threshold + is_anomaly
    W->>DB: INSERT anomaly_results + UPDATE events.status

    alt is_anomaly == true
        W->>R: Publish AlertMessage
        R->>N: Deliver alert
        N->>RS: Publish alert channel
        RS->>N: Subscribed message
        N-->>UI: WebSocket push
    end

    alt processing failure
        W->>W: Increment x-retry-count and republish
        W->>R: Send to DLX after max retries
    end
```

## 4) Database Schema

```mermaid
erDiagram
    users {
      bigint id PK
      varchar username UK
      text password_hash
      varchar role
      timestamptz created_at
    }

    events {
      uuid event_id PK
      varchar tenant_id
      varchar source
      varchar event_type
      jsonb payload
      float_array features
      varchar status
      varchar submitted_by
      timestamptz occurred_at
      timestamptz ingested_at
    }

    anomaly_results {
      bigint id PK
      uuid event_id FK
      varchar model_name
      varchar model_version
      float anomaly_score
      float threshold
      bool is_anomaly
      timestamptz processed_at
    }

    model_registry {
      bigint id PK
      varchar model_name
      varchar model_version
      jsonb metadata
      bool active
      timestamptz updated_at
    }

    events ||--o{ anomaly_results : has
```

## 5) Reliability and Idempotency

- Ingestion idempotency: primary key on `events.event_id`.
- Processing idempotency: Redis `processed:{event_id}` cache.
- Retry control: Rabbit message header `x-retry-count`.
- Dead letter: exhausted events moved to `risk.events.dlq` via DLX exchange.
- Manual acknowledgment after deterministic handling.

## 6) Horizontal Scalability

- API Gateway: stateless, scale behind L4/L7 load balancer.
- Event Worker: scale consumer replicas by queue depth/lag.
- ML Service: scale inference replicas; pin CPU/GPU pools separately.
- Notification Service: scale WebSocket nodes with Redis Pub/Sub fan-out.
- RabbitMQ: quorum queues for durability in production.
- PostgreSQL: read replicas for analytics; partition `events` by time/tenant.

## 7) Potential Bottlenecks

- ML inference latency under burst load.
- PostgreSQL write contention on hot tenants.
- WebSocket fan-out throughput on single notification instance.
- RabbitMQ queue lag if worker autoscaling is conservative.

## 8) Mitigation Strategies

- Batch inference or async micro-batching in ML service.
- Separate hot/cold storage, and partitioned indexes.
- Autoscale workers by queue depth and processing latency SLO.
- Redis Cluster and sharded WS nodes for 10k+ clients.
- Backpressure + circuit breakers for dependent services.
