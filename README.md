# moal-ai

Self-hosted user behavior anomaly detection for security teams.

## What It Does

moal-ai monitors user behavior events (auth logs, API calls, session activity) and detects anomalies using a TensorFlow autoencoder trained on real behavioral features like login patterns, request rates, geo-distance, and device novelty.

Think lightweight, self-hosted UEBA (User and Entity Behavior Analytics) for startups and small security teams who can't afford Exabeam or Securonix.

## Stack

- Backend: Python 3.11+, FastAPI, PostgreSQL, TensorFlow
- Frontend: React + TypeScript + Vite
- Infra: Docker Compose

## Quick Start

```bash
docker compose up -d --build
```

Services:
- Dashboard: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`

## Local Development

```bash
./scripts/local/setup.sh   # One-time install & bootstrap
./scripts/local/start.sh   # Start all services
./scripts/local/stop.sh    # Stop all services
```

## Default Credentials

- username: `admin`
- password: `admin123`

## Architecture

```
Client
  |
FastAPI (single service)
  |- POST /api/events/ingest  -> Feature engineering -> ML scoring -> DB
  |- GET  /api/events         -> List behavior events
  |- GET  /api/alerts         -> List flagged events
  |- POST /auth/token         -> JWT auth
  |- GET  /api/models/active  -> Model metadata
  |
PostgreSQL (5 tables)
  - users, behavior_events, anomaly_results, alerts, model_registry
  |
TensorFlow Autoencoder
  - Trains on real behavioral features
  - Scores anomalies synchronously
  |
React Dashboard
  - Overview, Alerts, Events, Models, Login
```

## Behavior Event Data Model

Events describe user behavior, not transactions:
- Auth logs (logins, failures, new devices)
- API calls (request patterns, rates)
- Session activity (duration, source IPs, user agents)

Real features for the autoencoder:
- Hour/day of week (cyclical encoding)
- Failed auth ratio, session duration, request rate
- Device fingerprint novelty, geo distance
- Source IP frequency
