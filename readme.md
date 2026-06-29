# 🚨 AI Incident Commander — AI-Powered RCA Agent for Slack

> Slack Agent Builder Challenge 2026 · Track: **New Slack Agent**

Incident Commander is an AI agent that lives inside Slack and autonomously investigates production incidents. When an alert fires, it collects evidence across your stack (GitHub, logs, Jira), generates a root-cause hypothesis, validates it through a multi-step evaluation engine, and only then surfaces a confidence-scored RCA to an on-call engineer for one-click approval.

Most incident bots create a ticket. This one tells you _why_ before it does.

**Ship plan:** Full product in 7 days — sequenced build with demo reliability, not a reduced MVP.

**Stack:** Python 3.11+ · LangGraph · Bolt for Python · FastAPI · Pydantic · OpenAI (primary LLM) · Google Gemini (fallback)

---

## Build Status (7-day ship)

- [x] **Day 1:** Bolt app running in Slack sandbox (Socket Mode or HTTP events)
- [x] **Day 2:** LangGraph investigation pipeline end-to-end (mock evidence)
- [x] **Day 3:** GitHub + Datadog integration clients live
- [x] **Day 4:** Jira + Real-Time Search API live
- [x] **Day 5:** Full eval engine; all three test scenarios passing (`pytest`)
- [x] **Day 6:** PagerDuty webhook + Block Kit approval actions
- [ ] **Day 7:** Demo video recorded; judge sandbox access granted — see [`docs/HACKATHON_SUBMISSION.md`](docs/HACKATHON_SUBMISSION.md)

**Hackathon build note:** Investigation state defaults to a **JSON file** on disk (`.investigation_store.json`) so Approve/Reject survive process restarts without PostgreSQL. Set `DATABASE_URL` to use PostgreSQL persistence (Alembic migrations in `alembic/versions/`). Set `DEMO_MODE=true` in `.env` for predictable hackathon demos.

---

## Demo

> 📹 [3-minute demo video — link here]

**Recommended demo path (Assistant-first — shows Slack AI + RTS):**

1. Open **Incident Commander** in the Slack **Assistant** panel (sidebar).
2. Click **Redis pool exhaustion** or type `checkout-service latency spike`.
3. Watch Assistant loading status → RCA card in `#incidents` → Approve.

**Fallback:** `/incident checkout-service latency spike` (slash command; RTS uses cached token if Assistant was opened recently).

Set `DEMO_MODE=true` in `.env` before recording or judging. Full checklist: [`docs/HACKATHON_SUBMISSION.md`](docs/HACKATHON_SUBMISSION.md).

**Demo service names** (fixture-backed scenarios with predictable outcomes):

| Service | Assistant / slash example | Expected outcome |
| ------- | ------------------------- | ---------------- |
| `checkout-service` | `checkout-service latency spike` | RCA surfaced (~87% confidence) |
| `payment-service` | `payment-service null deploy regression` | Blocked by Eval 1 (low coverage) |
| `auth-service` | `auth-service flaky integration test failure` | Blocked by false-alarm guard |

Other service names return an error unless live GitHub/Datadog evidence is configured. Stick to the three names above for judging and recording.

```
Assistant prompt / suggested prompt  ──or──  /incident checkout-service latency spike
       │                        │ (PagerDuty webhook also supported)
       └────────────────────────┘
                    │
                    ▼
AI Incident Commander wakes up in #incidents
"Investigating checkout-service latency spike..."
       │
       ▼
Evidence collected: 4 recent commits · 3 error log clusters · 1 prior incident match
       │
       ▼
Root Cause Candidate: Redis connection pool exhaustion (commit abc123 · 14 min ago)
Confidence Score: 87%  [Evidence: ████████░░]  [Grounding: ████████░░]  [Consistency: █████████░]
       │
       ▼
[✅ Approve & Create Jira]   [❌ Reject]   [🔍 Show Evidence]
       │
       ▼
Jira ticket created with full RCA, evidence links, and timeline
```

---

## Architecture

```
                        ┌─────────────────────┐
  PagerDuty / Webhook   │        Slack         │
  ─────────────────►    │  #incidents channel  │
  (FastAPI route)       └────────┬────────────┘
                                 │  Bolt (slash cmd / Block Kit actions)
                                 ▼
                    ┌────────────────────────┐
                    │  Investigation Graph   │
                    │  (LangGraph StateGraph)│
                    └────────┬───────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ GitHub   │  │ Datadog  │  │  Jira    │
        │  client  │  │  client  │  │  client  │
        └──────────┘  └──────────┘  └──────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │ + Real-Time Search API
                             ▼   (#incidents · 90 days)
                    ┌────────────────────┐
                    │   RCA Generator    │
                    │   (LLM node)       │
                    └────────┬───────────┘
                             │
                             ▼
                    ┌────────────────────────────┐
                    │     Evaluation Engine      │
                    ├────────────────────────────┤
                    │ ✓ Evidence Coverage Check  │
                    │ ✓ False-Alarm Guard        │
                    │ ✓ Hallucination Validator  │
                    │ ✓ Consistency Scorer       │
                    └────────┬───────────────────┘
                             │
                             ▼
                    ┌────────────────────┐
                    │  Human Approval    │
                    │  (Slack Block Kit) │
                    └────────┬───────────┘
                             │
                             ▼
                    ┌────────────────────┐
                    │  Jira Ticket       │
                    │  (on approve only) │
                    └────────────────────┘
```

### LangGraph flow

The investigation pipeline is a `StateGraph` with typed state (`InvestigationState`). Nodes run sequentially; evidence collection fans out inside the collect node via `asyncio.gather`.

```
START → collect_evidence → synthesize_rca → run_evals → [route]
                                                          ├─ block → END
                                                          └─ surface_rca → END
                                                                    │
                                                          (human approve/reject via Bolt)
```

| Node | Responsibility |
| ---- | -------------- |
| `collect_evidence` | Parallel calls to GitHub, Datadog, Jira clients + RTS API |
| `synthesize_rca` | LLM structured output → `RcaHypothesis` (Pydantic) |
| `run_evals` | Coverage → false-alarm guard → grounding → consistency; compute confidence |
| `surface_rca` | Mark investigation ready; Block Kit card posted by `slack/investigation_runner.py` |
| `block` | Post blocked reason; no Jira ticket |

---

## Technologies Used

| Technology | Role |
| ---------- | ---- |
| **LangGraph** | Investigation agent orchestration (`StateGraph`, conditional routing) |
| **LangChain** | LLM adapter, structured output, prompt templates, provider fallback |
| **OpenAI** | Primary LLM (`langchain-openai` — RCA synthesis, grounding validator) |
| **Google Gemini** | Fallback LLM (`langchain-google-genai` — used when OpenAI fails or rate-limits) |
| **PostgreSQL** | Optional investigation persistence and eval audit trail |
| **SQLAlchemy + Alembic** | ORM, migrations, connection pooling |
| **Bolt for Python** | Slack slash commands, interactivity, Block Kit actions |
| **FastAPI** | PagerDuty webhook + Slack HTTP events (production) |
| **Pydantic** | RCA schema, evidence bundles, eval results, settings |
| **slack-sdk** | RTS API (`assistant.search.context`), Web API calls |
| **MCP (Python SDK)** | GitHub commit evidence via in-repo FastMCP server (`mcp/github_server.py`) |
| **structlog** | Structured JSON logging |
| **pytest** | Eval scenario tests + unit tests |

---

## How It Works

### 1. Trigger

Two entry points, same LangGraph pipeline:

- **PagerDuty webhook (primary)** — `POST /webhooks/pagerduty` on FastAPI. Parses the incident payload and invokes `investigation_graph.ainvoke(...)`.
- **`/incident <service> <description>` slash command (fallback)** — Bolt handler in `slack/handlers/slash.py`. Reliable live trigger for demos and judging.

Both paths converge on the same graph. In-flight investigations are stored in the **investigation store** (JSON file by default, PostgreSQL when `DATABASE_URL` is set) so **Approve**, **Reject**, and **Show Evidence** work after async evidence collection completes.

### 2. Evidence Collection

The `collect_evidence` node fans out in parallel:

- **GitHub client** — commits from the past 2 hours via an in-repo **FastMCP** server (`mcp/github_server.py`); falls back to direct REST if MCP fails. Set `GITHUB_USE_MCP=false` to skip MCP.
- **Datadog client** — error rate spikes, log clusters, and APM traces via direct REST (`httpx`).
- **Jira client** — past incident tickets; creates the RCA ticket on human approval
- **RTS API** (`search/rts.py`) — searches `#incidents` for prior context. Background investigations use `conversations.history` (bot token). The RTS `assistant.search.context` API is used when a Slack `action_token` is available from a message event.

All results are assembled into an `EvidenceBundle` (Pydantic model).

### 3. RCA Generation

The `synthesize_rca` node calls the LLM with structured output validation:

```json
{
  "root_cause_candidate": "Redis connection pool exhaustion",
  "supporting_commit": "abc123",
  "commit_age_minutes": 14,
  "affected_service": "checkout-service",
  "prior_incident_match": "INC-2041"
}
```

Prompts live in `src/ai_incident_commander/prompts/` (version-controlled, not inline strings).

### LLM provider strategy

| Priority | Provider | Package | Default model |
| -------- | -------- | ------- | ------------- |
| **Primary** | OpenAI | `langchain-openai` | `gpt-4.1` |
| **Fallback** | Google Gemini | `langchain-google-genai` | `gemini-2.0-flash` |

All LLM calls go through `llm/adapter.py` — a single adapter that:

1. Attempts the primary OpenAI model with structured output (Pydantic schema)
2. On retryable failure (timeout, 429, 5xx), falls back to Google Gemini
3. Logs provider used, latency, and failure reason via structlog (never logs API keys)

```python
# langchain pattern: primary.with_fallbacks([fallback])
primary = ChatOpenAI(model=settings.openai_model, temperature=0)
fallback = ChatGoogleGenerativeAI(model=settings.google_model, temperature=0)
llm = primary.with_fallbacks([fallback])
```

Grounding validation can use cheaper models via `OPENAI_GROUNDING_MODEL` / `GOOGLE_GROUNDING_MODEL`. All LLM calls log token usage and an approximate `estimated_cost_usd` via structlog.

Grounding validator and consistency scorer always use `temperature=0`.

### 4. Evaluation Engine

The `run_evals` node runs checks before any RCA reaches a human. A failed eval blocks the RCA or penalizes confidence — the agent never self-approves.

**Eval 1 — Evidence Coverage**
Checks that the RCA cites at minimum one commit, one log cluster, and one deployment or prior incident. Returns a float in `[0.0, 1.0]`. If `evidence_coverage < 0.6`, the graph routes to `block`.

**False-alarm guard (deterministic)**
Before any LLM eval runs, blocks investigations where evidence is test-only (flaky CI retries) and the alert description signals a false alarm. Also blocks when the alert cites production failure terms with no matching evidence.

**Eval 2 — Hallucination Validator**
A separate LLM call with strict grounding (`temperature=0`). Given only raw evidence, does the cited root cause appear? Outputs `grounding_score` of `0.0` (ungrounded) or `1.0` (grounded) with a citation. Ungrounded blocks ticket creation.

**Eval 3 — Consistency Scorer**
Re-runs `synthesize_rca` once and compares the root cause to the graph's first synthesis (`baseline_rca`). `consistency` is a float in `[0.0, 1.0]` (1.0 = identical root causes). Divergence penalizes confidence and is surfaced to the reviewer.

**Confidence score — deterministic formula, not LLM-generated:**

```
confidence = (evidence_coverage × 0.4) + (grounding_score × 0.4) + (consistency × 0.2)
```

All component scores are floats in `[0.0, 1.0]`. UI displays as percentages (e.g. `0.87` → `87%`).

### 5. Human Approval

The scored RCA is posted as a Slack Block Kit card with three actions:

- **Approve & Create Jira** — creates a fully-populated ticket with RCA, evidence links, timeline, and confidence breakdown
- **Reject** — closes the investigation; reason is logged for trend analysis
- **Show Evidence** — expands raw evidence inline without leaving Slack

No ticket is created without explicit human approval.

---

## Evaluation Results (Test Scenarios)

| Scenario | Evidence Coverage | Grounding | Consistency | Confidence | Outcome |
| -------- | ----------------- | --------- | ----------- | ---------- | ------- |
| Redis pool exhaustion | 100% | Grounded | 95% | **87%** | Surfaced for approval |
| Null deploy (no root cause) | 40% | N/A | — | — | **Blocked by Eval 1** |
| Flaky test false alarm | 60% | N/A | — | — | **Blocked by false-alarm guard** |

The third row is what matters: the system caught a test-only false alarm before it reached a human (no grounding LLM call).

Run locally: `pytest tests/test_evals.py -v`

---

## 7-Day Build Plan

| Day | Goal | Exit criteria |
| --- | ---- | ------------- |
| **1** | Skeleton that runs | Bolt `/incident` posts to `#incidents` in sandbox |
| **2** | LangGraph pipeline (mock) | Graph produces Block Kit RCA card with fixture evidence |
| **3** | GitHub + Datadog live | Real commit and log data in `EvidenceBundle` |
| **4** | Jira + RTS live | RCA cites a real prior incident ID from sandbox history |
| **5** | Evaluation engine | All three `test_evals.py` scenarios pass |
| **6** | Triggers + UI + PagerDuty | Both entry points work; Approve creates Jira ticket |
| **7** | Demo hardening | Video recorded; judges invited; no new features after noon |

---

## Demo Sandbox

Judges will not have access to your GitHub org or Datadog account. Pre-seed the sandbox workspace before recording:

- **GitHub** — a demo repo with a known suspect commit tied to the Redis pool exhaustion scenario
- **Datadog** — monitors or saved views that return predictable error clusters for `checkout-service`
- **`#incidents`** — 2–3 prior incident threads for RTS to match (e.g. a prior Redis exhaustion post referencing `INC-2041`)
- **Jira** — a project with historical incident tickets aligned to the seeded scenarios

Show PagerDuty auto-trigger in the demo video; use `/incident` as the reliable fallback during live judging.

### Sandbox setup

1. Join the [Slack Developer Program](https://api.slack.com/developer-program) and provision a developer sandbox
2. Payment method may be required for identity verification (not charged for sandbox)
3. Invite judges: `slackhack@salesforce.com`, `testing@devpost.com`

---

## Setup

### Prerequisites

- Python 3.11+
- Slack **developer sandbox** with next-gen platform enabled
- Slack app created via [api.slack.com](https://api.slack.com/apps) (manifest in `manifest.json`) — **no Slack CLI required**
- API keys: GitHub, Jira, Datadog, OpenAI, Google AI
- PostgreSQL 15+ **optional** — omit `DATABASE_URL` to use the JSON file store (`.investigation_store.json`); use Docker Compose or a managed DB for full audit-trail persistence

### Installation

```bash
# Clone the repo
git clone https://github.com/your-username/ai-incident-commander
cd ai-incident-commander

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install package in editable mode (required for src/ layout)
pip install -e .

# Install dependencies (exact versions pinned in requirements.txt)
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Fill in tokens — see Environment Variables below

# Run database migrations (only when DATABASE_URL is set and PostgreSQL is running)
# Skip this step if you omit DATABASE_URL — the app uses .investigation_store.json instead.
alembic upgrade head

# Run tests
pytest tests/ -v

# Start locally (FastAPI + Bolt Socket Mode)
python -m ai_incident_commander.server.main
```

### Docker (local development)

Runs the app with **hot reload** and a **PostgreSQL 16** container. Slack tokens and API keys still come from your `.env` file on the host.

```bash
cp .env.example .env
# Fill in SLACK_*, OPENAI_*, GOOGLE_*, integration tokens, etc.

docker compose up --build
```

| Service | URL |
| ------- | --- |
| App (health) | http://localhost:8000/health |
| PostgreSQL | Internal to compose network; host port `5439` for local tools |

Useful commands:

```bash
docker compose up --build          # start app + db
docker compose up -d db              # postgres only (run app on host with venv)
docker compose exec app pytest -v    # run tests inside container
docker compose down -v               # stop and remove volumes
```

`DATABASE_URL` inside the `app` container is set by `docker-compose.yml` to point at the `db` service. When running **without** Docker, use `localhost` instead:

```env
DATABASE_URL=postgresql+asyncpg://incident:incident@localhost:5439/incident_commander
```

After Alembic migrations are added:

```bash
docker compose exec app alembic upgrade head
```

### Installation (without Docker)

### Create the Slack app (one-time)

1. Open [api.slack.com/apps/new](https://api.slack.com/apps/new) → **From an app manifest**
2. Select your **developer sandbox** workspace
3. Paste contents of `manifest.json` → **Create** → **Install to Workspace**
4. Copy **Bot Token** (`xoxb-...`) and **App-Level Token** (`xapp-...` with `connections:write`) into `.env`
5. Create `#incidents` channel and invite the bot (or rely on `chat:write.public` in `manifest.json` to post without a manual invite)

### Environment Variables

Copy `.env.example` to `.env`. All variables below are referenced at runtime:

```env
# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...          # Socket Mode
SLACK_SIGNING_SECRET=...          # HTTP events mode (production)

# LLM — primary: OpenAI, fallback: Google Gemini
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1
OPENAI_GROUNDING_MODEL=gpt-4.1-mini   # optional; falls back to OPENAI_MODEL
GOOGLE_API_KEY=...
GOOGLE_MODEL=gemini-2.0-flash
GOOGLE_GROUNDING_MODEL=gemini-2.0-flash  # optional; falls back to GOOGLE_MODEL

# Database (optional — omit for JSON file store)
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5439/incident_commander

# GitHub
GITHUB_TOKEN=ghp_...
GITHUB_REPO_OWNER=your-github-username
GITHUB_REPO_NAME=your-demo-repo
GITHUB_USE_MCP=true

# Jira
JIRA_API_TOKEN=...
JIRA_EMAIL=you@example.com
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_PROJECT_KEY=SCRUM
JIRA_ISSUE_TYPE=Task

# Datadog
DATADOG_API_KEY=...
DATADOG_APP_KEY=...
DATADOG_SITE=datadoghq.com        # or ap1.datadoghq.com
DATADOG_LOG_INDEX=main

# Evidence collection
EVIDENCE_LOOKBACK_HOURS=2

# Evidence compaction (LLM token budget)
EVIDENCE_FIELD_MAX_CHARS=500
EVIDENCE_PROMPT_TOKEN_BUDGET=6000
CHARS_PER_TOKEN_ESTIMATE=4

# App
INCIDENTS_CHANNEL_ID=C...
PAGERDUTY_WEBHOOK_SECRET=...       # required for /webhooks/pagerduty
LOG_LEVEL=info
```

### Socket Mode vs HTTP events

**Local development (recommended):** Socket Mode with `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN`. FastAPI starts immediately; Socket Mode connects in a background thread — wait for `slack_socket_ready` in logs before running `/incident`.

**Slack scopes (`manifest.json`):** `assistant:write` requires the `assistant_view` feature block (declared in `features`). It enables AI assistant surfaces and RTS `action_token` flows. `search:read.public` is required by Slack for `assistant.search.context` on bot tokens. Background investigations fall back to `conversations.history` when no `action_token` is available.

**Production HTTP mode:** Set `SLACK_SIGNING_SECRET` and point Slack **Event Subscriptions** and **Interactivity** to `https://<host>/slack/events`. Do **not** also point the slash command Request URL at HTTP while using Socket Mode for buttons — approvals will miss the in-process store.

Startup validates Slack tokens, `INCIDENTS_CHANNEL_ID`, at least one LLM key, and configured integration credentials before the app accepts traffic.

### Python dependencies

Pinned in `requirements.txt`. Core stack:

| Package | Purpose |
| ------- | ------- |
| `langgraph` | Investigation `StateGraph` orchestration |
| `langchain-core` | LLM abstractions, structured output |
| `langchain-openai` | Primary LLM — OpenAI (`ChatOpenAI`) |
| `langchain-google-genai` | Fallback LLM — Google Gemini |
| `sqlalchemy` | PostgreSQL ORM (async sessions) |
| `asyncpg` | Async PostgreSQL driver |
| `alembic` | Database migrations (versioned, reversible) |
| `slack-bolt` | Slack event handlers, slash commands, Block Kit |
| `slack-sdk` | Web API + RTS (`assistant.search.context`) |
| `fastapi` | PagerDuty webhook + Slack HTTP events |
| `uvicorn` | ASGI server |
| `pydantic` | Models for RCA, evidence, eval results, settings |
| `pydantic-settings` | `.env` loading |
| `httpx` | Async HTTP for GitHub / Jira / Datadog clients |
| `structlog` | Structured JSON logging |
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support (`asyncio_mode = "auto"` set in `pyproject.toml`) |

### PostgreSQL schema (overview)

| Table | Purpose |
| ----- | ------- |
| `investigations` | One row per incident run (service, description, status, Slack thread ref) |
| `evidence_snapshots` | Serialized `EvidenceBundle` at collection time |
| `rca_hypotheses` | Structured RCA output + confidence score |
| `eval_results` | Per-eval verdict, score, and explanation (audit trail) |
| `approval_actions` | Approve / reject / show-evidence events with timestamps |

Migrations live in `alembic/versions/` — never modify schema by hand.

### MCP integration

GitHub commit evidence uses the **Model Context Protocol** via an in-repo FastMCP server:

```
GitHubClient.get_recent_commits()
  → fetch_recent_commits_mcp()  [stdio]
  → ai_incident_commander.mcp.github_server:list_recent_commits
  → fetch_recent_commits_http()  (shared REST implementation)
```

- **Server:** `src/ai_incident_commander/mcp/github_server.py` — exposes `list_recent_commits` tool
- **Client:** `src/ai_incident_commander/mcp/client.py` — spawns the server over stdio and calls tools
- **Config:** `GITHUB_USE_MCP=true` (default). Set to `false` for direct REST only.
- **Fallback:** If the MCP subprocess fails, `GitHubClient` automatically retries via `httpx`.

Datadog, Jira, and Slack RTS use direct REST for now; the same MCP pattern can be extended later.

```python
from ai_incident_commander.integrations.github import GitHubClient

commits = await GitHubClient(settings).get_recent_commits("checkout-service")
```

### Deploy (Railway / Render)

```bash
# Production: HTTP events (no Socket Mode)
# Set SLACK_SIGNING_SECRET; configure Request URL → https://<host>/slack/events
# Attach PostgreSQL add-on; set DATABASE_URL

alembic upgrade head
uvicorn ai_incident_commander.server.main:api --host 0.0.0.0 --port $PORT
```

See `Dockerfile` and `docker-compose.yml` for deploy scaffolding.

---

## Project Structure

```
ai-incident-commander/
├── src/ai_incident_commander/
│   ├── agents/
│   │   ├── graph.py              # LangGraph StateGraph definition
│   │   ├── investigation.py      # Node implementations (collect, synthesize, surface)
│   │   └── evaluator.py          # Orchestrates all three evals
│   ├── evals/
│   │   ├── coverage.py           # Eval 1 — evidence coverage
│   │   ├── grounding.py          # Eval 2 — hallucination check
│   │   └── consistency.py        # Eval 3 — dual-run consistency
│   ├── llm/
│   │   ├── adapter.py            # OpenAI primary + Google Gemini fallback
│   │   ├── evidence_context.py   # Evidence compaction and token budgets
│   │   ├── pricing.py            # Approximate USD cost estimates
│   │   └── usage.py              # Per-call and per-investigation token logging
│   ├── db/
│   │   ├── session.py              # Async SQLAlchemy session factory
│   │   ├── models.py             # ORM models (investigations, evals, approvals)
│   │   └── repository.py         # Investigation CRUD
│   ├── integrations/
│   │   ├── credentials.py        # Startup credential validation
│   │   ├── github.py             # Commits via MCP (with REST fallback)
│   │   ├── github_mcp.py         # MCP wrapper for GitHub commits
│   │   ├── datadog.py            # Logs, error clusters, APM
│   │   └── jira.py               # Past incidents + ticket creation
│   ├── mcp/
│   │   ├── client.py             # Stdio MCP client helper
│   │   └── github_server.py      # FastMCP server for GitHub commits
│   ├── search/
│   │   └── rts.py                # Real-Time Search API wrapper
│   ├── models/
│   │   ├── evidence.py           # EvidenceBundle
│   │   ├── rca.py                # RcaHypothesis + confidence formula
│   │   └── eval_result.py        # Per-eval explainable results
│   ├── slack/
│   │   ├── app.py                # Bolt App init + handler registration
│   │   ├── handlers/
│   │   │   ├── slash.py          # /incident command handler
│   │   │   └── actions.py        # Block Kit actions (Approve / Reject / Show Evidence)
│   │   └── views/
│   │       └── approval.py       # Block Kit RCA card builder
│   ├── server/
│   │   ├── main.py               # FastAPI + Bolt Socket Mode / HTTP events
│   │   └── routes/
│   │       └── pagerduty.py      # PagerDuty webhook → graph invoke
│   ├── config.py                 # Pydantic Settings (env vars)
│   ├── constants.py              # Eval thresholds, confidence weights
│   └── prompts/
│       ├── rca_synthesis.md
│       └── grounding_validator.md
├── alembic/                      # Database migrations
│   └── versions/
├── tests/
│   ├── conftest.py               # Shared fixtures and store isolation
│   ├── test_evals.py             # All 3 scenarios from README
│   └── fixtures.py               # Mock evidence bundles
├── manifest.json                 # Slack app manifest (api.slack.com) — scopes, slash commands, events
├── pyproject.toml                # Package config; makes src/ layout importable
├── requirements.txt
├── Dockerfile                    # Local dev image (used by docker compose)
├── docker-compose.yml            # App + PostgreSQL for local development
└── .dockerignore
```

---

## Roadmap (Post-Hackathon)

- **Auto-remediation mode** — for high-confidence, known-pattern incidents, skip approval and auto-rollback
- **Runbook matching** — surface the relevant runbook steps alongside the RCA
- **Trend analysis** — identify recurring root causes across incidents over time
- **On-call handoff digest** — end-of-shift summary of all investigations and their outcomes

---

## Team

| Name | Role |
| ---- | ---- |
| Tamilarasu Ravi | Builder |

---

## Hackathon Submission

See **[`docs/HACKATHON_SUBMISSION.md`](docs/HACKATHON_SUBMISSION.md)** for the full checklist (video, judge invites, manifest reinstall).

- **Track:** New Slack Agent
- **Agent Builder alignment:** [`docs/AGENT_BUILDER.md`](docs/AGENT_BUILDER.md)
- **Sandbox:** https://YOUR-WORKSPACE.slack.com _(update with your workspace URL)_
- **Judge access:** `slackhack@salesforce.com` and `testing@devpost.com` invited to the sandbox workspace
- **Demo video:** [YouTube/Loom link] (~3 minutes, working project footage required)
- **Architecture diagram:** See [Architecture](#architecture) above (export a visual version for Devpost if needed)
- **Slack App ID:** A0XXXXXXX _(Organizations / Marketplace track only — not required for New Slack Agent)_

### Devpost pitch

> AI Incident Commander is a Slack-native investigation agent that autonomously gathers evidence from GitHub, logs, and past incidents via MCP and Real-Time Search, generates a root-cause hypothesis with LangGraph, and validates it through a three-stage evaluation engine before any human sees it. Unlike alerting bots that only create tickets, it surfaces a confidence-scored RCA with explicit grounding checks — blocking hallucinated root causes before they reach on-call engineers.

### Demo video script (~3 min)

| Time | Beat |
| ---- | ---- |
| 0:00–0:30 | Problem: alert fires, engineer opens 4 tabs, RCA takes 45+ minutes |
| 0:30–1:00 | Open **Assistant** → trigger `checkout-service latency spike` |
| 1:00–1:45 | Evidence (MCP commits, logs, prior incident via **RTS**) |
| 1:45–2:15 | RCA card with confidence breakdown |
| 2:15–2:45 | Assistant: flaky scenario → false-alarm guard blocks |
| 2:45–3:00 | Approve → Jira ticket; human-in-the-loop closing |

Record in your sandbox workspace, not localhost-only.

---

## License

MIT

---

_Built for the [Slack Agent Builder Challenge 2026](https://slackhack.devpost.com)_
