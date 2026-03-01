# Engineering Folder Structure

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
│   │           ├── schemas_v2.py
│   │           └── security.py
│   ├── services
│   │   └── risk
│   │       ├── api
│   │       ├── worker
│   │       ├── ml
│   │       ├── notification
│   │       ├── connector
│   │       ├── enrichment
│   │       └── metrics
│   └── tests
├── frontend
│   └── dashboard
│       ├── package.json
│       ├── vite.config.ts
│       └── src
│           ├── app
│           ├── entities
│           ├── features
│           │   ├── access-auth.content
│           │   ├── alert-monitor.content
│           │   ├── event-stream.content
│           │   ├── model-management.content
│           │   ├── platform-settings.content
│           │   └── risk-dashboard.content
│           ├── shared
│           └── widgets
├── infra
│   ├── postgres
│   ├── reverse-proxy
│   └── eks
├── scripts
│   ├── local
│   ├── dev.start.sh
│   ├── dev.reset.sh
│   ├── dev.seed.sh
│   └── prod.build.sh
├── docs
│   ├── engineering.naming-convention.md
│   ├── engineering.naming-audit.md
│   ├── engineering.folder-structure.md
│   └── risk.architecture.md
└── docker-compose.yml
```
