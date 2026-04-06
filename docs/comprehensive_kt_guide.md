# Aegis AI - Comprehensive Knowledge Transfer (KT) Guide

## 1. System Overview

Aegis AI is a production-grade distributed real-time AI risk monitoring system. Its primary purpose is to ingest events, perform machine-learning-based anomaly detection, and distribute risk alerts in real-time to a React dashboard.

It is built heavily on an event-driven microservices architecture using:
- **FastAPI** for HTTP/REST services.
- **RabbitMQ** for reliable message queuing and event routing.
- **PostgreSQL** for persistent storage of events, alert states, and model metadata.
- **Redis Pub/Sub & WebSockets** for live fan-out of metrics and alerts to connected UI clients.
- **TensorFlow** for unsupervised anomaly detection (Autoencoder).
- **React + Vite + Tailwind** for the dashboard UI.

---

## 2. Backend Internals: The Lifecycle of a Risk Event

When an event enters the system, it flows through a series of specialized microservices.

### A. API Gateway (Ingestion & Auth)
- **Role:** The entry point for all external traffic.
- **Auth:** Uses JWT (JSON Web Tokens) with a tenant-aware mechanism. Standard RS256 JWKS authentication is supported.
- **Flow:** Clients HTTP `POST` events to `/v1/events/ingest`.
- **Action:** The Gateway persists the event to PostgreSQL idempotently (ignoring conflicts on `event_id`), and publishes an `EventEnvelope` to the `risk.event.queue` in RabbitMQ.

### B. Event Worker
- **Role:** Asynchronous consumer that handles heavy lifting and external calls so the API gateway is not blocked.
- **Flow:** Consumes events from `risk.event.queue`.
- **Action:** 
  1. It calls the **ML Inference Service** (`POST /v1/infer`) with event features.
  2. Receives an `anomaly_score`, `threshold`, and an `is_anomaly` flag.
  3. Writes the `anomaly_results` back to PostgreSQL and updates the overall event status.
  4. **Alerting:** If `is_anomaly == true`, it publishes an `AlertMessage` to the `risk.alert.queue` in RabbitMQ.
- **Reliability:** Features dead-letter routing (DLX) and a retry mechanism tracked via an `x-retry-count` header. It also uses Redis constraints cache `processed:{event_id}` to ensure processing idempotency.

### C. ML Inference Service
- **Role:** Specialized predictive service running TensorFlow autoencoder models.
- **Action:** Evaluates the input features. The threshold for anomalies is dynamically computed from the validation reconstruction error quantile during the model training phase.
- **Capabilities:** Manages multiple versions of models, tracking "active" models via the `model_registry` table.

### D. Notification Service & Metrics Aggregator
- **Notification Service:** Consumes `AlertMessage` from RabbitMQ and pushes it into a Redis Pub/Sub channel (`risk.live.alerts`). Any connected WebSocket client (like the Dashboard) receives these alerts instantly.
- **Metrics Aggregator:** A separate worker computes 1-minute and 1-hour rollup metrics from the database and streams live aggregate metrics via WebSocket.
- **Feature Enrichment & Data Connectors:** Scheduled background tasks pull contextual risk data (OFAC, FATF, FX rates) from the internet. This enriched data gives operators more context around why an event is flagged.

---

## 3. Frontend Dashboard Walkthrough

The React dashboard visualizes the live risk landscape. We performed an automated walkthrough to capture the UI behavior, which is embedded below.

### UI Recording
The recording shows the flow from Authentication through exploring the Alerts, Events, and Models tabs.

![Aegis AI Dashboard Walkthrough Video](file:///Users/sourrrish/.gemini/antigravity/brain/34f0c4bb-ddeb-4686-a1b7-f00539954882/aegis_ai_kt_walkthrough_1773568629819.webp)

### Key Views
1. **Login State:** Shows standard authentication. Username and Password inputs are protected. Once signed in, a secure JWT is persisted in cookies/local storage.
2. **Overview/Risk Dashboard:** The main landing page. Summarizes live events, displaying real-time ingest rates and anomaly percentages pushed via WebSocket from the Metrics Aggregator.
3. **Alerts Monitor:** Shows a stream of events that crossed the anomaly threshold. Users can acknowledge or investigate these alerts further.
4. **Event Stream:** A live feed of all ingested events (anomalous and benign).
5. **Model Management:** Exposes the states from the ML Inference service's active/inactive repository, allowing administrators to audit model versions.

---

## 5. Control Plane & Tenant Operations Walkthrough

Aegis AI also includes a dedicated **Control Plane** for managing global operations and individual tenant workspaces. This separates the high-volume streaming data (handled by the gateways) from the management and configuration data.

### A. Control Plane Backend Services
1. **Control API (`/backend/services/risk/control_plane`)**: 
   - A FastAPI service that securely exposes endpoints for configuring tenant rules, routing strategies, anomaly thresholds, and enabling/disabling intelligence feed connectors.
   - It maintains an audit log of all configuration changes globally.
2. **Alert Router (`/backend/services/risk/alert_router`)**:
   - Acts as the egress layer. It listens to RabbitMQ for internally processed alerts and routes them to external tenant destinations (e.g., Slack, Email, Webhooks) based on the configurations managed by the Control API.

### B. UI Walkthroughs
The platform exposes two specialized React applications for control plane operations.

#### 1. Control Ops Console (Global Management)
- **Role:** Centralized operating surface for system administrators.
- **Features:** 
  - Allows operators to manage the lifecycle of tenants across the system.
  - Controls the global intelligence feeds (`Connectors` tab), enabling them cluster-wide.
  - Monitors global alert delivery and logs across all routing instances.
  - **Screenshot:**
    ![Control Ops Operations Overview](/Users/sourrrish/.gemini/antigravity/brain/34f0c4bb-ddeb-4686-a1b7-f00539954882/control_ops_connectors_1773569038199.png)

#### 2. Control Tenant Console (Workspace Management)
- **Role:** Dedicated environment for a specific tenant (e.g., `tenant-alpha`).
- **Features:**
  - **Overview:** Summarizes configuration version, default thresholds, active models, and reconciliation mismatch flags.
  - **Risk & Model Policy:** Fine-tunes the exact TensorFlow model serving the tenant, and overrides system-default anomaly thresholds.
  - **Alert Routing:** Directs anomalous events to the tenant's chosen endpoints.
  - **Test Lab:** A secure sandbox for administrators to craft mock JSON events and simulate pipeline scoring deterministically.
  - **Screenshot:**
    ![Control Tenant Workspace Overview](/Users/sourrrish/.gemini/antigravity/brain/34f0c4bb-ddeb-4686-a1b7-f00539954882/control_tenant_overview_1773569125535.png)

### Control & Tenant Recording
A full interactive flow of exploring the global Control Ops console, followed by entering the dedicated Tenant workspace setup, is recorded below:

![Control and Tenant Console Walkthrough Video](/Users/sourrrish/.gemini/antigravity/brain/34f0c4bb-ddeb-4686-a1b7-f00539954882/control_and_tenant_ops_walkthrough_1773568941275.webp)

---

## 6. Key Architectural Takeaways

- **Decoupled by Design:** The heavy calculation (ML) is decoupled from the ingestion pathway, ensuring that bursts of external API traffic don't immediately crash the ML service and are safely queued in RabbitMQ.
- **Control Plane Isolation:** Managing tenant state and routing configurations happens in completely isolated services (Control API and Ops frontends), protecting the hot-path ingestion nodes.
- **Real-Time Push:** Instead of the frontend polling PostgreSQL every few seconds, Redis Pub/Sub combined with FastAPI WebSockets provides instant UI updates with low overhead.
- **Resilience:** Events are retried natively using RabbitMQ headers. Poison pills eventually hit the Dead Letter Queue (DLQ), ensuring the pipeline stays unblocked. Idempotency is rigorously enforced, preventing duplicate events from triggering duplicate alerts or scores.
