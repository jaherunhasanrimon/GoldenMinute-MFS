# Phase P0 report: Scaffold and walking skeleton

## Built
- **Repository layout & tooling**: Section 4 structure initialized with Python 3.13 / virtualenv, `pyproject.toml`, `.env.example`, `CLAUDE.md`, `.gitignore`, and `Makefile`.
- **Configuration subsystem** (`src/goldenminutes/common/config.py`):
  - YAML configuration loaders for `configs/simulator.yaml`, `configs/features.yaml`, `configs/models.yaml`, `configs/policy.yaml`, and `configs/reasons.yaml`.
  - Pydantic models for type-safe validation of simulator profiles, policy parameters, models, and bilingual reason codes.
  - Pydantic Settings for environment variables (`GM_ENV`, `GM_DB_URL`, `GM_MODEL_DIR`, `GM_LLM_PROVIDER`, `GM_SEED`, `GM_CUSTOMER_KEY`, `GM_ANALYST_KEY`).
  - Module-level export of `GM_SEED`.
- **API Contracts & Schemas** (`src/goldenminutes/common/schemas.py`):
  - Complete Pydantic models for every Section 13 API request/response: `ScoreRequest`, `ScoreResponse`, `AlertListResponse`, `AlertDetailResponse`, `AlertDecisionRequest`, `AlertDecisionResponse`, `FeedbackRequest`, `FeedbackResponse`, `GraphResponse`, `MetricsResponse`, `SimulateAttackRequest`, `SimulateAttackResponse`, `SimulateResetResponse`, `DemoAccountsResponse`, `HealthResponse`.
  - Standardized error shape `{ "error": { "code", "message", "details" } }`.
- **Serving layer** (`src/goldenminutes/api/main.py`, `deps.py`):
  - `create_app()` FastAPI application factory with OpenAPI documentation at `/docs`.
  - Request-ID middleware generating/propagating `X-Request-ID` and measuring processing latency in `X-Process-Time`.
  - CORS middleware configured for `http://localhost:5173` and `http://127.0.0.1:5173`.
  - Role-based authentication via `X-API-Key` header with roles `customer_demo` and `analyst`.
  - `GET /health` endpoint returning liveness and system version metadata.
  - Fixture stubs for all 10 `/v1` endpoints with `X-GM-Stub: 1` header.
- **Frontend web application** (`ui/`):
  - Vite + React 18 + TypeScript + Tailwind CSS + React Router setup.
  - Three distinct routes:
    - `/`: Customer demo screen with interactive send-money simulation and proportionate action card (`allow`, `warn`, `verify`, `hold`).
    - `/analyst`: Analyst console with 3-second live polling, priority ranking, money-at-risk aggregation, filtering, and alert detail drawer with investigation actions.
    - `/metrics`: Metrics and evaluation dashboard displaying headline KPIs, full ablation comparison table (Variants A–D), fairness demographic slices, and held-out typology recall.
  - Bilingual localization (`en`/`bn`) with offline Bangla typography via `@fontsource/noto-sans-bengali`.
  - Dynamic `demo data` indicator in top navigation bar reacting to `X-GM-Stub: 1` backend header.
- **Test suite**:
  - 23 backend unit and contract tests in `tests/test_config.py`, `tests/test_auth_roles.py`, `tests/test_api_contracts.py`.
  - 4 Vitest + React Testing Library UI smoke tests in `ui/src/test/ui_smoke.test.tsx` verifying route rendering, navigation, demo-data badge, and language toggle.
- **Documentation**:
  - `ARCHITECTURE.md` updated with P0 additions (Tailwind CSS, React Router, Vitest, and `X-API-Key` authentication roles in Sections 5, 13, and 16).
  - `docs/assumptions.md`, `docs/data_dictionary.md`, and `docs/model_card.md` created.

## How to run it (exact commands)

### Setup & Tests
```bash
make setup
make lint
make test
```

### Running Backend API
```bash
make api
# Server starts on http://localhost:8000
# OpenAPI documentation available at http://localhost:8000/docs
# Health check: curl http://localhost:8000/health
```

### Running Frontend UI
```bash
make ui
# Vite dev server starts on http://localhost:5173
```

## Gate results (paste command output)

### Command: `make setup && make lint && make test`
```text
.venv/bin/pip install --upgrade pip
Requirement already satisfied: pip in ./.venv/lib/python3.13/site-packages (26.2.1)
.venv/bin/pip install -e ".[dev]"
Obtaining file:///Users/jahirunhassanrimon/GoldenMinute
  Installing build dependencies ... done
  Checking if build backend supports build_editable ... done
  Getting requirements to build editable ... done
  Preparing editable metadata (pyproject.toml) ... done
Requirement already satisfied: fastapi>=0.110.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: uvicorn>=0.28.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: pydantic>=2.6.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: pydantic-settings>=2.2.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: pyyaml>=6.0.1 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: python-multipart>=0.0.9 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: httpx>=0.27.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: pandas>=2.2.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: numpy>=1.26.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: pyarrow>=15.0.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: scikit-learn>=1.4.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: networkx>=3.2.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: sqlalchemy>=2.0.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: pytest>=8.0.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: pytest-asyncio>=0.23.0 in ./.venv/lib/python3.13/site-packages
Requirement already satisfied: ruff>=0.3.0 in ./.venv/lib/python3.13/site-packages
Building wheels for collected packages: goldenminutes
  Building editable for goldenminutes (pyproject.toml) ... done
Successfully installed goldenminutes-0.1.0

up to date, audited 337 packages in 3s
101 packages are looking for funding
  run `npm fund` for details

.venv/bin/ruff check .
All checks passed!

.venv/bin/pytest tests
.......................                                                  [100%]
23 passed, 2 warnings in 0.33s

> goldenminutes-ui@0.1.0 test:run
> vitest run

 RUN  v1.6.1 /Users/jahirunhassanrimon/GoldenMinute/ui

 ✓ src/test/ui_smoke.test.tsx (4)
   ✓ GoldenMinutes UI Smoke Tests (4)
     ✓ renders navbar, branding, and demo-data badge
     ✓ renders customer demo screen by default
     ✓ toggles language between Bangla and English
     ✓ navigates to analyst console and metrics pages

 Test Files  1 passed (1)
      Tests  4 passed (4)
   Duration  1.12s
```

### Health & OpenAPI Verification (`make api`)
- `GET /health` returned `200 OK`:
  `{"status":"ok","model_version":"m-0.1.0-stub","policy_version":"0.1","environment":"dev"}`
- `GET /openapi.json` verified all expected paths:
  `['/health', '/v1/alerts', '/v1/alerts/{alert_id}', '/v1/alerts/{alert_id}/decision', '/v1/demo/accounts', '/v1/feedback', '/v1/graph/{wallet_id}', '/v1/metrics', '/v1/score', '/v1/simulate/attack', '/v1/simulate/reset']`

### Browser UI Verification (`make ui`)
- Verified in browser with subagent and automated recording (`ui_verification_p0`).
- Customer demo screen, analyst console with live polling, and metrics ablation table render without errors.
- Dynamic `demo data` indicator is visible.
- Language toggle switches between English and Bangla seamlessly.

## Deviations from the plan, and why
- **None**: All P0 tasks were executed strictly in the order prescribed by `PHASES.md` without modifying any P1+ modules or skipping tests.

## New or changed assumptions
- Added `VITE_CUSTOMER_KEY` and `VITE_ANALYST_KEY` corresponding to `GM_CUSTOMER_KEY` and `GM_ANALYST_KEY` for prototype frontend authentication.
- Added `X-GM-Stub: 1` header detection to frontend API client to dynamically toggle the demo-data badge.
- Added mock demo accounts endpoint `/v1/demo/accounts` in stub mode providing preconfigured synthetic sender and recipient options for rapid testing.

## Open questions for the human
1. In P1, should the dataset intake script primarily ingest the supplied `goldentimes_synthetic_dataset/` CSV directory directly or also retain the synthetic generator pipeline for creating additional small/full profiles? (The current design supports both).
2. For the held-out typology, `ARCHITECTURE.md` designates `agent_collusion` while `goldentimes_synthetic_dataset` contains `heldout_card_to_wallet_burst.csv`. We will follow `ARCHITECTURE.md`'s contract (`agent_collusion` as the primary held-out typology), but please confirm if you would like `card_to_wallet_burst` evaluated as an additional held-out case.
