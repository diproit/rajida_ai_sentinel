# DigiValuer Sentinel 🛡️

**AI/ML Agentic Workflow Service for DigiValuer Workflow Bottlenecks**

DigiValuer Sentinel is an intelligent automation and agentic monitoring platform designed to detect, triage, and expedite operational bottlenecks in property and asset valuation workflows. Powered by async Python, FastAPI, PostgreSQL, Redis/Celery, and Google Gemini via LangChain, Sentinel acts as an autonomous watchdog ensuring valuations flow smoothly without human delay or undetected discrepancies.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    DV[DigiValuer Platform & Webhooks] -->|Valuation Events| API[FastAPI Async API Server]
    API -->|Async Persistence| PG[(PostgreSQL 16\ndigivaluer_sentinel)]
    API -->|Enqueue Triage & Scans| R[(Redis 7 Queue)]
    W[Celery Workers / Poller] -->|Fetch Queue / Scheduled Tasks| R
    W -->|Query Stalled Cases| PG
    W -->|Reasoning & Anomaly Triage| GEMINI[Google Gemini LLM\nLangChain Google GenAI]
    W -->|Action / Alert / Auto-escalate| DV
```

### Core Technologies
- **Backend Framework:** [FastAPI](https://fastapi.tiangolo.com/) (async Python 3.10+)
- **ASGI Server:** [Uvicorn](https://www.uvicorn.org/)
- **Data Modeling & ORM:** [SQLModel](https://sqlmodel.tiangolo.com/) (SQLAlchemy + Pydantic)
- **Database Driver:** [asyncpg](https://github.com/MagicStack/asyncpg) (Async PostgreSQL driver)
- **Database:** PostgreSQL 16
- **Task Queue & Cache:** Redis 7 + [Celery](https://docs.celeryq.dev/)
- **AI / LLM Orchestration:** [LangChain Google GenAI](https://python.langchain.com/docs/integrations/chat/google_generative_ai/) (Gemini 2.0 / 1.5)
- **Configuration & Validation:** [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- **Package & Environment Management:** [uv](https://github.com/astral-sh/uv) (ultra-fast Python package manager)
- **Testing:** [pytest](https://docs.pytest.org/) & [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)

---

## 📂 Project Structure

```text
AIB-Sentinel/
├── .env.example             # Template for environment variables
├── .env                     # Local configuration (ignored by git)
├── .gitignore               # Git ignore rules
├── docker-compose.yml       # Docker services (PostgreSQL & Redis)
├── pyproject.toml           # Project dependencies & tool configurations
├── README.md                # Project documentation & startup guide
├── app/
│   ├── __init__.py          # App package init
│   ├── main.py              # FastAPI app instance, CORS, lifespan, and root routes
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py        # Pydantic Settings loaded from .env
│   │   ├── database.py      # Database re-exports
│   │   └── redis.py         # Async Redis connection manager, pub/sub broadcaster & ping utilities
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py       # SQLModel async engine, sessionmaker, and table initializer
│   │   └── seed.py          # Database seeding script for SLA configs & escalation rules
│   ├── models/
│   │   ├── __init__.py
│   │   ├── agent.py         # CaseSLAConfig, AgentIntervention, EscalationRule, AgentMetrics
│   │   └── valuation.py     # ValuationCase, WorkflowBottleneck, AgentActionLog
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── webhook.py       # Pydantic schema for DigiValuer webhook payloads & responses
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py          # Webhook Bearer token authentication dependency
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── api.py       # Aggregator for v1 routers
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── health.py    # /health, /health/ready, /health/live probes
│   │           ├── webhooks.py  # DigiValuer webhook ingestion (/api/v1/webhooks/digivaluer)
│   │           └── workflows.py # Bottleneck listing and agentic scan triggers
│   ├── routers/
│   │   ├── __init__.py
│   │   └── dashboard.py     # Operations Dashboard API & SSE stream (/api/dashboard/*)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── digivaluer_client.py # DigiValuer API client & mock case simulation
│   │   ├── notifier.py          # Multi-channel notifications (Email, SMS, WhatsApp, Webhooks)
│   │   ├── pause_manager.py     # Redis-backed case monitoring pause/resume state
│   │   ├── sla_evaluator.py     # SLA calculation, cooling-off window & overdue detector
│   │   └── webhook_processor.py # Webhook event dispatcher (state sync, bottleneck auto-resolve)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py              # Google Gemini LLM factory via LangChain
│   │   └── reminder_agent.py    # Context-aware reminder agent with structured outputs
│   ├── workers/
│   │   ├── __init__.py
│   │   └── celery_app.py        # Celery app, scheduled scan tasks & async webhook task
│   └── worker.py                # Core Sentinel worker scan cycle and periodic loop
├── frontend/                    # Operations Lead React + Vite Dashboard
│   ├── index.html               # Single page application entry
│   ├── package.json             # React 18, Vite, Lucide-react, Tailwind CSS
│   ├── vite.config.js           # Dev server config & API reverse proxy
│   ├── src/
│   │   ├── main.jsx             # React DOM root
│   │   ├── App.jsx              # Main Dashboard UI (SSE real-time listener, Bottlenecks, Approvals)
│   │   └── index.css            # Tailwind typography and custom styles
│   └── dist/                    # Compiled SPA bundle mounted at /dashboard/
├── scripts/
│   ├── __init__.py
│   ├── simulate_webhook.py      # CLI tool to dispatch sample DigiValuer webhooks
│   ├── verify_reminder_agent.py # Agent reminder drafting verification script
│   └── verify_dashboard.py      # End-to-end dashboard & intervention approval verification
└── tests/
    ├── conftest.py              # Pytest fixtures and async test client
    ├── test_agent_schema.py     # Schema and seed tests
    ├── test_dashboard.py        # Operations dashboard API endpoint tests
    ├── test_e2e.py              # Complete end-to-end integration test
    ├── test_evaluator.py        # SLA evaluation, cooling-off & client tests
    ├── test_health.py           # Unit & integration tests for health checks
    ├── test_notifier.py         # Email, SMS, WhatsApp & Webhook dispatcher tests
    ├── test_reminder_agent.py   # Reminder drafting agent and tone progression tests
    ├── test_webhooks.py         # DigiValuer webhook ingestion, auth & deduplication tests
    └── test_worker.py           # Background scan and Human-in-the-Loop tests
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Docker & Docker Compose (`docker compose version` >= 2.20)
- Python 3.10+
- `uv` (recommended) or standard `venv` + `pip`

To install `uv` (if not already installed):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Environment Configuration
Copy `.env.example` to `.env` and configure your API keys and endpoints:
```bash
cp .env.example .env
```

Key environment variables:
- `DATABASE_URL`: PostgreSQL connection string (defaults to `postgresql+asyncpg://sentinel:sentinel_secret@localhost:5432/digivaluer_sentinel`)
- `REDIS_URL`: Redis connection string (defaults to `redis://localhost:6379/0`)
- `GEMINI_API_KEY`: Google Gemini API key for AI agent reasoning
- `DIGIVALUER_API_BASE_URL`: Base URL for DigiValuer platform
- `DIGIVALUER_WEBHOOK_SECRET`: Shared secret for authenticating incoming webhooks via `Authorization: Bearer <secret>` (defaults to `dev_webhook_secret_key_2026`)
- `POLLING_INTERVAL_SECONDS`: Background cadence for inspecting active cases

### 3. Spin Up Docker Infrastructure
Launch the complete DigiValuer Sentinel system (`db`, `redis`, `api`, `worker`, `frontend`) with health checks:
```bash
docker compose up -d
```

Verify service status:
```bash
docker compose ps
```
All containers will report running and healthy:
- `digivaluer_sentinel_postgres` (`db`) on port `5432` *(healthy)*
- `digivaluer_sentinel_redis` (`redis`) on port `6379` *(healthy)*
- `digivaluer_sentinel_api` (`api`) on port `8001` *(healthy)*
- `digivaluer_sentinel_worker` (`worker`) recurring background scanning loop
- `digivaluer_sentinel_frontend` (`frontend`) on port `5174`

### 4. Install Dependencies
Using `uv`:
```bash
uv sync --extra dev
```

Or using an existing virtual environment:
```bash
source .venv/bin/activate
uv sync --extra dev
```

### 5. Seed Default Database Configurations
Populate standard SLA stage thresholds and escalation rules:
```bash
python -m app.db.seed
```
*(Or via uv: `uv run python -m app.db.seed`)*

### 6. Start the FastAPI Backend Server
Run the application using Uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```
*(Or via uv: `uv run uvicorn app.main:app --port 8001 --reload`)*

> **Note:** Port 8001 is used by default in `.env` to prevent port collisions if another service is already bound to 8000. You can change `APP_PORT` to 8000 in `.env` if desired.

### 7. Start Celery Background Worker (Optional)
To process agentic background scans and periodic bottleneck checks:
```bash
celery -A app.workers.celery_app worker --loglevel=info
```

### 8. Run DigiValuer Sentinel Scanner

**Manual One-Shot Scan (respects `HUMAN_IN_THE_LOOP` policy):**
```bash
python -m app.worker
```

**Manual One-Shot Scan with Immediate Auto-Dispatch:**
```bash
python -m app.worker --dispatch
```

**Continuous Recurring Background Loop (every 30 minutes):**
```bash
python -m app.worker --loop
```

*(Or trigger on demand via API: `curl -X POST http://localhost:8001/api/v1/workflows/scan-now`)*

### 9. Operations Control Dashboard (React + Vite)

The platform provides a modern Operations Control Dashboard designed for Ops Leads to track workflow bottlenecks, review and approve drafted AI interventions, and monitor delivery telemetry.

**Option A: Development Server (Vite Hot-Reloading)**
```bash
cd frontend
npm install
npm run dev
```
Open **[http://localhost:5174](http://localhost:5174)** in your browser. (The Vite server reverse-proxies `/api` directly to `http://127.0.0.1:8001`).

**Option B: Production Bundle (FastAPI Static Mount)**
The frontend build is pre-compiled inside `frontend/dist` and directly served by the FastAPI backend:
Open **[http://localhost:8001/dashboard/](http://localhost:8001/dashboard/)** in your browser.

**Core Interface Features:**
- **KPI Summary Cards:** Total interventions sent, average response time, turnaround hours saved, active bottleneck counter.
- **Bottleneck Map:** Real-time visualization of delayed cases grouped by stage and assigned officer, progress bars against SLA limits, and one-click "Pause Agent / Resume Monitoring" toggles.
- **Pending Approval Queue:** Human-in-the-Loop review queue for drafted Gemini reminders with "Approve & Send" and "Edit Draft" modal.
- **Intervention History:** Comprehensive dispatch logs across Email, SMS, WhatsApp, and DigiValuer Core webhooks.

---

## 🔍 Verification & Health Checks

### Check Top-Level Health Endpoint
```bash
curl http://localhost:8001/health
```
Response (`200 OK`):
```json
{
  "status": "ok",
  "app": "DigiValuer Sentinel",
  "environment": "development",
  "services": {
    "database": "connected",
    "redis": "connected"
  }
}
```

### Check Deep Readiness Probe
```bash
curl http://localhost:8001/api/v1/health/ready
```
Response (`200 OK`):
```json
{
  "status": "ready",
  "database": "ready",
  "redis": "ready"
}
```

### Webhook Ingestion & Real-Time APIs
- **`POST /api/v1/webhooks/digivaluer`**: Ingests real-time events (`STATUS_CHANGED`, `UNRESPONSIVE_PARTY`, `SLA_DELAY_WARNING`) from DigiValuer (`mekamu_mowheel`). Authenticated via `Authorization: Bearer <DIGIVALUER_WEBHOOK_SECRET>`.
- **`GET /api/dashboard/events`**: Server-Sent Events (SSE) stream broadcasting real-time case updates, bottlenecks, and interventions directly to the Ops Dashboard.

### Dashboard Management APIs
- **`GET /api/dashboard/bottlenecks`**: Aggregates overdue cases grouped by stage and assigned officer, enriched with pause states.
- **`GET /api/dashboard/interventions`**: Returns intervention history with status filters (`DRAFTED`, `APPROVED`, `SENT`, `FAILED`).
- **`POST /api/dashboard/interventions/{id}/approve`**: Approves a drafted reminder and triggers immediate multi-channel delivery.
- **`PUT /api/dashboard/interventions/{id}`**: Allows ops leads to edit drafted reminder content and subject before approval.
- **`POST /api/dashboard/cases/{id}/pause-agent`**: Toggles agent monitoring on or off for a specific case (Redis-persisted).
- **`GET /api/dashboard/metrics`**: Returns aggregate KPI metrics (total reminders sent, avg response time, duration saved).

### Interactive API Documentation
- **Swagger UI:** [http://localhost:8001/docs](http://localhost:8001/docs)
- **ReDoc:** [http://localhost:8001/redoc](http://localhost:8001/redoc)

---

## ⚡ DigiValuer Webhook Integration & Real-Time Event Pipeline

DigiValuer Sentinel provides an event-driven ingestion pipeline allowing the core DigiValuer platform (`mekamu_mowheel`) to push real-time valuation lifecycle events. This eliminates polling delays and allows instant triage of workflow stalls and unresponsive stakeholders.

### 1. Ingestion Endpoint & Authentication
- **Endpoint:** `POST /api/v1/webhooks/digivaluer`
- **Authentication:** Static Bearer token in request header:
  ```http
  Authorization: Bearer dev_webhook_secret_key_2026
  ```
  *(Configured via `DIGIVALUER_WEBHOOK_SECRET` in `.env`)*
- **Idempotency & Deduplication:** Incoming deliveries are deduplicated using Redis `SETNX` on key `sentinel:webhook:event:{event_id}` with a 48-hour expiration. Duplicate event deliveries return `200 OK` (`action_taken: "skipped"`).
- **Asynchronous Task Queue:** Validated events immediately receive a `202 Accepted` response and are enqueued to Celery (`process_digivaluer_webhook_event`), with resilient inline fallback execution if workers are offline.

### 2. DigiValuer Payload Schema
```json
{
  "event_id": "7f9a2b10-6c3e-4d89-9a11-e63f5891d4e0",
  "timestamp": "2026-10-21T10:35:00Z",
  "source_system": "mekamu_mowheel",
  "environment": "production",
  "event_type": "STATUS_CHANGED",
  "severity": "CRITICAL",
  "category": "VALUER_UNRESPONSIVE",
  "application": {
    "id": "c88f9e20-7214-41bd-8c43-4c919d6756ec",
    "application_no": "MK-88A9C12E",
    "status": "VALUATION_AND_INVESTIGATION_PROCESSING",
    "branch_id": "b3e945c2-192a-44e2-bca4-d19e9841f71a",
    "branch_name": "Kandy Branch",
    "created_at": "2026-10-21T08:00:00Z",
    "updated_at": "2026-10-21T08:15:00Z"
  },
  "assigned_party": {
    "role": "VALUER",
    "user_id": "d14f2e50-99c1-4011-82a1-12c8a98b4ef2",
    "name": "Sunil Perera",
    "phone": "0771234567",
    "company_name": "Lanka Valuers Ltd",
    "assigned_at": "2026-10-21T08:15:00Z"
  },
  "metrics": {
    "elapsed_seconds": 7800,
    "sla_threshold_seconds": 7200,
    "delay_seconds": 600
  },
  "details": {
    "previous_status": "DRAFT",
    "new_status": "VALUATION_AND_INVESTIGATION_PROCESSING",
    "trigger_actor": "fo@mekamu.com",
    "message": "Valuer Sunil Perera has not submitted a valuation report within the 2-hour SLA window."
  }
}
```

### 3. Event-Driven Actions Taken by Sentinel
- **`STATUS_CHANGED`**:
  - Updates or creates `ValuationCase` record in PostgreSQL (`case_number = application.application_no`, `status = new_status`).
  - Auto-resolves open `WorkflowBottleneck` records for the previous stage.
  - Automatically marks stale pending reminder drafts (`AgentIntervention`) for that stage as `DISMISSED`.
  - Records an audit log entry in `agent_action_logs`.
  - Broadcasts update via Redis Pub/Sub to trigger live dashboard refresh.
- **`UNRESPONSIVE_PARTY` & `SLA_DELAY_WARNING`**:
  - Sets `ValuationCase.is_stalled = True`.
  - Records a `WorkflowBottleneck` with classification (`category`), severity, and message context.
  - Invokes Google Gemini / AI drafting agent to generate a tailored SMS / email intervention addressed to the valuer/broker (`assigned_party.phone`) calibrated to urgency (`CRITICAL` $\rightarrow$ Escalated, `HIGH` $\rightarrow$ Firm, `MEDIUM/LOW` $\rightarrow$ Gentle).
  - Persists the intervention in `agent_interventions` as `DRAFTED` for operator review (or auto-dispatches if `HUMAN_IN_THE_LOOP=false`).
  - Broadcasts update via Redis Pub/Sub to the Operations Dashboard.

### 4. Real-Time Telemetry & Dashboard Streaming
Sentinel provides a Server-Sent Events (SSE) endpoint:
- **`GET /api/dashboard/events`**: Continuously streams real-time Sentinel events from the Redis `sentinel:events` pub/sub channel.
- The Operations Dashboard (`frontend/src/App.jsx`) connects on mount, displaying instantaneous toast notifications and refreshing KPI summary cards and pending approval queues without requiring manual page reload.

### 5. Simulating Webhooks Locally
Use the bundled CLI simulation script to test webhook delivery against a running Sentinel instance:
```bash
# Simulate an Unresponsive Valuer SLA breach
python scripts/simulate_webhook.py --type UNRESPONSIVE_PARTY --severity CRITICAL --app-no MK-88A9C12E

# Simulate a Status Transition
python scripts/simulate_webhook.py --type STATUS_CHANGED --app-no MK-88A9C12E
```

---

## 🧪 Running Automated Tests

Run the complete test suite (35+ unit, integration, webhook, and E2E tests) with `pytest`:
```bash
pytest
```
*(Or via uv: `uv run pytest -v`)*

### ⚡ Running the Webhook Integration Test Suite
Execute the webhook test suite (`tests/test_webhooks.py`) validating Bearer authentication, Redis deduplication, case synchronization, bottleneck creation, and reminder drafting:
```bash
pytest tests/test_webhooks.py -v
```
*(Or via uv: `uv run pytest tests/test_webhooks.py -v`)*

### 🔄 Running the End-to-End Integration Test
Execute the end-to-end integration test (`tests/test_e2e.py`) validating case injection, worker SLA scanning, PostgreSQL draft generation, API approval, and notification dispatcher calls:
```bash
pytest tests/test_e2e.py -v
```
*(Or via uv: `uv run pytest tests/test_e2e.py -v`)*

### 🤖 Running the Reminder Drafting Agent Verification Script
Run the standalone verification script to test contextual prompt drafting across reminder sequences and verify PostgreSQL database persistence:
```bash
python -m scripts.verify_reminder_agent
```
*(Or via uv: `uv run python -m scripts.verify_reminder_agent`)*

### 📊 Running the Dashboard & Intervention Approval Verification Script
Run the end-to-end verification script testing the dashboard API, pending approval queue, dispatch triggers, and database status transitions:
```bash
PYTHONPATH=. python scripts/verify_dashboard.py
```
*(Or via uv: `uv run python -m scripts.verify_dashboard`)*

---

## 🛠️ Docker Tear-Down
To stop and remove containers and networks:
```bash
docker compose down
```
To also remove persistent volumes:
```bash
docker compose down -v
```
