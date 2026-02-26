# Folder Structure

```text
.
├── backend
│   ├── libs
│   │   └── common
│   │       ├── pyproject.toml
│   │       └── risk_common
│   │           ├── config.py
│   │           ├── logging.py
│   │           ├── messaging.py
│   │           ├── schemas.py
│   │           └── security.py
│   └── services
│       ├── api_gateway
│       │   ├── Dockerfile
│       │   ├── requirements.txt
│       │   └── app
│       │       ├── api
│       │       ├── application
│       │       ├── domain
│       │       ├── infrastructure
│       │       └── main.py
│       ├── event_worker
│       │   ├── Dockerfile
│       │   ├── requirements.txt
│       │   └── app
│       │       ├── api
│       │       ├── application
│       │       ├── domain
│       │       ├── infrastructure
│       │       └── main.py
│       ├── ml_inference
│       │   ├── Dockerfile
│       │   ├── requirements.txt
│       │   └── app
│       │       ├── api
│       │       ├── application
│       │       ├── domain
│       │       ├── infrastructure
│       │       └── main.py
│       └── notification_service
│           ├── Dockerfile
│           ├── requirements.txt
│           └── app
│               ├── api
│               ├── application
│               ├── domain
│               ├── infrastructure
│               └── main.py
├── frontend
│   └── dashboard
│       ├── Dockerfile
│       ├── package.json
│       ├── src
│       │   ├── components
│       │   ├── hooks
│       │   ├── services
│       │   ├── types
│       │   ├── App.tsx
│       │   ├── main.tsx
│       │   └── styles.css
│       └── vite.config.ts
├── infra
│   └── postgres
│       └── init
│           └── 001_schema.sql
├── docs
│   ├── architecture.md
│   └── folder-structure.md
├── docker-compose.yml
└── .env.example
```
