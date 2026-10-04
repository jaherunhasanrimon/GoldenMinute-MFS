# GoldenMinutes: PHASES.md (data-ready web app build plan)

> Companion to `ARCHITECTURE.md`. `ARCHITECTURE.md` says **what and why**. This file says **order and gates**.
> If they conflict on design, `ARCHITECTURE.md` wins. On sequencing, this file wins. Report the conflict and fix the wrong file.
> Effort tags (S, M, L) are relative sizes, not time estimates.

## Status tracker

| Phase | Name | Size | Status |
|---|---|---|---|
| P0 | Scaffold and walking skeleton | S | ☑ |
| P1 | Dataset onboarding, simulator compatibility and validation | M | ☑ |
| P2 | Features, rules baseline, eval harness | L | ☑ |
| P3 | Models | M | ☑ |
| P4 | Policy, online state, API | L | ☐ |
| P5 | Explainability and narrative | M | ☐ |
| P6 | Web UI | L | ☐ |
| P7 | Hardening and demo readiness | M | ☐ |

Tick a phase only after its gate passes **and** the human replies `approved P<n>`.

---

## How the agent runs a phase

1. **Announce:** state the phase id, task list, and prerequisites.
2. **Check prerequisites:** re-run the previous phase's gate commands. If they fail, fix that first.
3. **Do the tasks in order.** Commit after each task: `P<n>.<task>: <summary>`.
4. **Run the gate.** Every command and check in the gate must pass. Never weaken, skip, or delete a test to make it pass.
5. **Update docs:** tick the tracker, update `docs/assumptions.md` and `docs/data_dictionary.md`, and edit `ARCHITECTURE.md` if any contract changed (same commit).
6. **Write `reports/phase_P<n>.md`** using the template below, and summarize it in chat.
7. **STOP.** Do not begin the next phase until the human approves.

### Stop and ask the human when

Stop when a requirement is ambiguous, a Hard Constraint (C1–C10) would be affected, a dependency outside the stack is needed, a test must change to pass, the supplied dataset conflicts with an architecture contract in a material way, or the result contradicts an expectation (for example, ML+graph does not beat the rules baseline).

Be honest about failures. Never tune on the test split.

## Kickoff prompt

```text
Read ARCHITECTURE.md and PHASES.md fully. Execute Phase P<N> only, following the
protocol in PHASES.md. Do not start the next phase. When the gate passes, write
reports/phase_P<N>.md and stop.
```

## Phase report template

```markdown
# Phase P<N> report

## Built

## How to run it (exact commands)

## Gate results (paste command output)

## Deviations from the plan, and why

## New or changed assumptions

## Open questions for the human
```

---

# Web-app rules (apply to every phase)

- **Always runnable.** At the end of every phase, `make api` and `make ui` start cleanly, `GET /health` returns 200, and the UI loads.
- **Backend:** FastAPI with a `create_app()` factory on port 8000, CORS for `http://localhost:5173`, OpenAPI at `/docs`, config from env, structured logs with a request ID.
- **Frontend:** Vite, React, TypeScript, Tailwind CSS, React Router, on port 5173. One API client in `ui/src/api/`. All strings in `ui/src/locales/` (`en`, `bn`). Bangla font via `@fontsource/noto-sans-bengali` so it works offline. Every data view has loading, empty, and error states.
- **Updates:** poll the API every 3 seconds on the analyst queue. No websockets.
- **Stubs:** an endpoint not yet implemented returns fixture data with header `X-GM-Stub: 1`. The UI shows a small `demo data` badge when it sees that header.
- **Honesty labels:** scripted attack runs are labeled `Illustrative scenario (synthetic)`. Headline metrics come **only** from the held-out test split.
- **Demo keys:** `VITE_CUSTOMER_KEY` and `VITE_ANALYST_KEY` are demo-only, not production auth.

## Decisions and contract additions fixed in this file

Apply each addition to `ARCHITECTURE.md` in the phase shown, in the same commit that introduces it.

| Addition | Where in ARCHITECTURE.md | Phase |
|---|---|---|
| Tailwind CSS, React Router, Vitest + React Testing Library, optional `openapi-typescript` | Section 5 | P0 |
| Auth: header `X-API-Key` with roles `customer_demo` and `analyst`, keys from env | Sections 13 and 16 | P0 |
| `confirmations` table (`wallet_id`, `confirmed_at`, `source`) simulating analyst confirmations with a lag and a detection rate. Never emitted for the held-out typology. | Section 6 | P1 |
| `two_hop_confirmed_mule_share` reads `confirmations`, never `labels` | Sections 8 and 18 | P2 |
| Graph component features use the **previous day's snapshot** | Section 8 | P2 |
| Optional `reference` field on `ScoreRequest` (string, max 140 chars), treated as untrusted free text | Section 13 | P5 |
| `POST /v1/simulate/reset` (demo only) | Section 13 | P4 |
| `GET /v1/demo/accounts` (demo only, disabled when `GM_ENV=prod`) | Section 13 | P6 |

---

# P0: Scaffold and walking skeleton (S)

**Goal:** a wired repo and a web app that runs end to end on stub data, so the UI and API can be built in parallel.

## Tasks

1. Create the repository layout from `ARCHITECTURE.md` Section 4. Add `pyproject.toml`, `.env.example`, `Makefile`, `.gitignore` (`data/`, `models/`, `.env`, `node_modules/`, `*.db`) and `CLAUDE.md` with one line telling the agent to read `ARCHITECTURE.md` and `PHASES.md` first.
2. `common/config.py`: load YAML configs and env, validate with Pydantic, and expose `GM_SEED`.
3. `common/schemas.py`: Pydantic models for every request/response in Section 13.
4. `api/main.py`: `create_app()`, request-ID middleware, error shape, CORS, `X-API-Key` role check, `/health`, and stubs for every `/v1` endpoint with `X-GM-Stub: 1`.
5. `ui/`: Vite + React + TypeScript + Tailwind + Router. Three routes (`/`, `/analyst`, `/metrics`) against stub data. Add `en`/`bn` toggle, Bangla font, and demo-data badge.
6. Tests: endpoint contract smoke tests, config loader, role-check tests, and UI smoke tests.
7. Wire `make setup`, `make lint`, `make test`, `make api`, and `make ui`.

## Gate

- `make setup && make lint && make test` pass.
- `make api`: `GET /health` returns 200 and `/docs` lists every `/v1` endpoint.
- `make ui`: all three pages render, language toggle works, and demo-data badge shows.
- P0 architecture additions above are written into `ARCHITECTURE.md`.

---

# P1: Dataset onboarding, simulator compatibility and validation (M)

**Goal:** turn the already-generated synthetic dataset into a clean, reproducible canonical input for GoldenMinutes while preserving the simulator contracts from the architecture.

> The repository may already contain a ZIP/CSV synthetic dataset. Treat it as a **bootstrap/source dataset**, not as a reason to bypass validation or the canonical simulator contract.

## Tasks

1. `configs/simulator.yaml`: define `small` and `full` profiles, seed, persona parameters, seasonality, typology parameters, confirmation lag/detection rate, and `agent_collusion` as held out.
2. Add a dataset intake step that discovers the supplied synthetic data under the repository's documented data location. If a ZIP exists, unpack it without modifying the source archive.
3. Normalize source data into the canonical entities required by `ARCHITECTURE.md`: customers, wallets (customer/agent/merchant), agents, devices/device links, transactions, cash-outs, relationships, auth events, labels and hidden truth as separate logical artifacts.
4. Preserve raw source data under `data/raw_source/`. Never edit the source files in place.
5. Build a compatibility/normalization layer so source CSV column names can map into the canonical schema. Record every mapping and any dropped/derived field in `docs/data_dictionary.md`.
6. Enforce the architecture contract that model features must not read `labels` or `hidden_truth`. If the supplied raw transactions contain fraud labels, create a sanitized canonical transaction artifact without labels and keep truth in a separate ground-truth store.
7. Implement or retain the simulator modules:
   - `simulator/population.py`
   - `simulator/behavior.py`
   - `simulator/typologies/impersonation_scam.py`
   - `simulator/typologies/mule_ring.py`
   - `simulator/typologies/sim_swap_takeover.py`
   - `simulator/typologies/card_to_wallet_burst.py`
   - `simulator/typologies/agent_collusion.py`
8. Ensure legitimate confounders exist: legitimate large sends to new recipients, high fan-in merchants/billers, normal cash-out delays from minutes to days, and normal device changes.
9. Emit `confirmations` for every typology except the held-out `agent_collusion` typology.
10. `simulator/generate.py`: produce reproducible Parquet under `data/raw/<profile>/` and `reports/sim_summary.json`.
11. Add validation tests for referential integrity, monotone timestamps per wallet, deterministic generation, schema compatibility, leakage separation, and non-trivial overlap between normal and fraud behavior.
12. Write `docs/data_dictionary.md` and `docs/assumptions.md` with every mapping, injected pattern and parameter.
13. If the supplied dataset does not satisfy the final P1 gate, create a corrected canonical generated profile rather than silently weakening the gate. Report the deviation explicitly.

## Gate

- `make data PROFILE=small` succeeds in a reproducible local run.
- `make data PROFILE=full` succeeds and runtime is recorded.
- Fraud share is roughly `0.2–0.6%` on `full` (`0.2–1.0%` on `small`), unless `ARCHITECTURE.md` explicitly says otherwise.
- Each typology has at least 300 positive transactions on `full` and at least 30 on `small`.
- Same seed produces identical output hashes.
- Wallet timestamps are monotone.
- Foreign keys are valid.
- Labels and hidden truth are not present in model-input transaction features.
- Legitimate confounders are present.
- No single raw column reaches AUC above `0.85` for fraud.
- `reports/sim_summary.json`, `docs/assumptions.md`, and `docs/data_dictionary.md` are reviewed by the human.

**Pitfall:** do not make fraud obviously detectable by one raw field such as amount, hour, account age, or device ID.

---

# P2: Features, rules baseline, eval harness (L)

**Goal:** point-in-time-correct features, a deterministic baseline, and the evaluation machinery.

## Tasks

1. `features/specs.py`: single source of truth for every feature: name, group, dtype, window, definition.
2. `features/offline.py`: vectorized batch builder. No per-row Python loops over the full dataset. Write `data/processed/<profile>/features.parquet` with a `split` column: days 1–60 train, 61–75 validation, 76–90 test.
3. Build transaction/sender features such as:
   - amount vs personal norm
   - new recipient
   - sender velocity
   - time since PIN/device change
   - behavioral deviation
4. Build recipient/mule features such as:
   - unique senders in 24h/7d
   - first-time sender ratio
   - incoming volume and amount
   - average cash-out delay
   - rapid cash-out ratio
   - pass-through ratio
   - shared device/agent counts
   - transaction velocity
5. Graph features: degree-style features via time-window joins. Component features via daily snapshots with NetworkX on a suspicious subgraph only, using the previous day's snapshot. `two_hop_confirmed_mule_share` uses `confirmations` with `confirmed_at <= ts`.
6. `rules/baseline.py`: implement rules R1–R5 from Section 9 with thresholds in `configs/models.yaml`.
7. `eval/metrics.py`: FFR, value-weighted recall at FFR cap, precision at K, per-typology recall, Brier score, ECE, bootstrap intervals.
8. `eval/run_eval.py`: run variant A and write `reports/metrics.json` matching `MetricsResponse`.
9. Tests: point-in-time correctness, leakage prevention, rules unit tests, and toy metric tests.

## Gate

- `make features PROFILE=full` finishes; runtime is recorded.
- Point-in-time and leakage tests pass.
- `make eval` writes variant A metrics, including held-out typology recall.
- Human reads the baseline numbers; they should show the rules are useful but not necessarily unbeatable.

**Pitfall:** do not rebuild graph features hourly. Use daily snapshots.

---

# P3: Models (M)

**Goal:** the ablation: variants A (rules), B (LightGBM, no graph), C (LightGBM + graph), D (C + anomaly, fused).

## Tasks

1. `models/risk_lgbm.py`: class weighting, early stopping on validation only. Train B and C.
2. `models/anomaly.py`: Isolation Forest trained on legitimate training rows and scored as a percentile rank.
3. `models/calibration.py`: isotonic calibration fitted on validation only.
4. `models/fusion.py`: logistic stacker on validation predictions using `logit(p_lgbm)`, anomaly score, and rules-hit count.
5. Remove the held-out typology's fraud rows from train, validation, and calibration. Keep them in test.
6. `models/registry.py` and `models/train.py`: version string, config hash, training window, and metrics in `models/registry.json`.
7. `eval/ablation.py`: produce `reports/ablation.json` with PR-AUC, value-weighted recall at FFR cap, precision at K, held-out typology recall, calibration, and p95 inference time.
8. Start `docs/model_card.md`.

## Gate

- `make train PROFILE=full` finishes.
- A second run with the same seed reproduces metrics within a small tolerance.
- No test-split row is used for fitting, calibration, fusion, or threshold choice.
- `reports/ablation.json` contains all four variants and the held-out typology result.
- Report whatever the ablation shows. If ML+graph does not beat the rules baseline, stop and ask the human before changing anything.

**Pitfall:** thresholds are chosen on validation and then applied to test. Never the reverse.

---

# P4: Policy, online state, API (L)

**Goal:** a real scoring API that replaces every stub.

## Tasks

1. `policy/engine.py` and `policy/cost.py`: implement Section 11 exactly: hard rules, minimum amount, expected-cost choice, hold-capacity fallback to `verify`, no `deny`, alert priority and deadline logic.
2. `features/online.py`: rolling state keyed on event time, not wall-clock. Warm from history until `GM_WARMUP_CUTOFF` and implement `update(event)` and `features(txn)`. Recompute graph snapshots at simulated day boundaries.
3. `api/store.py`: SQLite via SQLAlchemy for decisions, alerts, analyst actions, feedback, and audit rows.
4. Replace stubs for `/v1/score`, `/v1/alerts`, `/v1/alerts/{id}`, `/v1/alerts/{id}/decision`, `/v1/feedback`, `/v1/graph/{wallet_id}`, `/v1/metrics`, `/v1/simulate/attack`, and `POST /v1/simulate/reset`.
5. Analyst endpoints require the analyst role. Every analyst action creates an audit record.
6. Measure p50 and p95 latency over 1,000 requests and write `reports/latency.json`.
7. Tests: contracts, error shapes, roles, alert lifecycle, feedback persistence, and online/offline parity on at least 5,000 sampled transactions including first-ever transactions and wallets with no history.

## Gate

- No endpoint returns `X-GM-Stub`.
- Online/offline parity passes.
- p95 latency is recorded; target is under 150 ms.
- Human can POST `/v1/score` from `/docs` with a test transaction and receive a plausible action, reasons, and an alert when action is `hold`.

---

# P5: Explainability and narrative (M)

**Goal:** every decision explains itself in Bangla and English, and the LLM path is safe.

## Tasks

1. `explain/shap_explainer.py` and `explain/reasons.py`: map top positive SHAP contributors to reason codes through `configs/reasons.yaml`. Every feature must map to a code.
2. `llm/template_provider.py`: analyst summary and customer warning in `bn` and `en`, including `SAFE_ACTION_HINT`.
3. `llm/guards.py`: evidence-only input, reason-code constraints, exact numbers, length/language checks, and template fallback.
4. `llm/provider.py`: `NarrativeProvider` interface and optional `LLMProvider` stub controlled by `GM_LLM_PROVIDER`. No network access unless the human enables it.
5. Add optional `reference` to `ScoreRequest` and treat it as untrusted free text.
6. Wire narratives into `/v1/score` and `/v1/alerts/{id}`.
7. Create `docs/bangla_review.md` for native-speaker review.

## Gate

- Every non-`allow` response has a reason code and both `bn` and `en` text.
- Guard tests pass, including prompt-injection testing via hostile `reference` text.
- Template provider covers every reason code in both languages.
- Human receives `docs/bangla_review.md`.

---

# P6: Web UI (L)

**Goal:** the three screens and the live attack demo, on real data.

## Tasks

### 6.1 App shell and demo accounts
Layout, navigation, persisted `en`/`bn` toggle, and `GET /v1/demo/accounts` with clearly synthetic sender/recipient options.

### 6.2 Customer demo (`/`)
Send-money form with sender, recipient/new number, and amount. Result:
- `allow`: success message.
- `warn`: reason chips, call-first hint, Cancel/Continue; continuing records `this_was_me`.
- `verify`: short cooling-off countdown and clearly simulated trusted-contact confirmation.
- `hold`: review status, target time, and `this was me` feedback.

### 6.3 Analyst console (`/analyst`)
Poll every 3 seconds. Show priority, money at risk, score, status, and live time-left countdown. Detail drawer includes score, reasons, local wallet graph, narrative, key evidence, audit trail, and approve/release/escalate actions. Release requires a note.

### 6.4 Metrics (`/metrics`)
KPI cards, ablation chart (A–D), held-out typology table, fairness slices, sensitivity table, latency card, and footer: `Synthetic data, held-out test split`.

### 6.5 Attack demo and polish
`Run attack` calls `/v1/simulate/attack` and animates scripted steps. `Reset demo` resets the scenario. Scenario should use a fresh recipient wallet and several prior-history victims so the network signal builds and action escalates. Label it `Illustrative scenario (synthetic)`.

Add loading, empty, error states, responsive layout, accessible labels/focus states, and BDT formatting with Bengali digits in `bn`.

## Tests

Vitest + React Testing Library for every page against a mocked API. Add a backend test asserting the scenario reaches at least `verify` by its last step.

## Gate

- Demo steps 1–5 run in the browser against the real API with no manual fixes.
- Bangla and English both display correctly.
- No console errors.
- UI tests pass.

**Rule:** if the scenario does not escalate, fix the scenario's wallets and amounts. Do not change the policy or model just to fit the demo.

---

# P7: Hardening and demo readiness (M)

**Goal:** a robust, honest, one-command demo.

## Tasks

1. Fairness slices by age band, region type, and tenure bucket plus policy sensitivity grid.
2. Finish `docs/model_card.md` and `docs/assumptions.md`. Write `README.md` with problem, architecture, run steps, screenshots, and known limits.
3. `make demo`: build UI, serve it from FastAPI static files, warm state, and print URLs/demo script.
4. Optional demo safety net: small `demo_assets/` bundle with trained model, sample accounts and scenario; include only if under about 25 MB.
5. Walk the Section 16 checklist in `ARCHITECTURE.md`.
6. Final regression from a clean checkout: lint, tests, UI tests, full data generation, training, and evaluation.

## Gate

- Fresh clone with a new virtual environment runs `make setup && make demo` successfully.
- Section 16 checklist is complete or every exception is justified in writing.
- Human rehearses the 3-minute demo and signs off.

---

# Global Definition of Done (every phase)

- `make lint` and `make test` pass with no skipped or weakened tests.
- No hard-coded thresholds, costs, or strings outside `configs/` and `locales/`.
- Docs updated, tracker ticked, phase report written.
- App still runs: `make api`, `make ui`.
- No data, models, secrets, or `.env` committed.

# Cut list (if time runs short)

Cut in this order:

1. Stretch items: GNN, adaptive fraudster, SMS/voice, real LLM provider, Docker, Postgres.
2. Sensitivity grid beyond a minimal 3×3.
3. Variant D (anomaly fusion).
4. Graph component features (keep degree-style graph features).
5. Verify UI step (keep warn and hold).
6. Metrics charts (keep tables).

**Never cut:** P0–P2, B vs C ablation, held-out typology test, `/v1/score` and alerts, customer warning and analyst console, reason codes, human review for `hold`, and synthetic-only data.

# Optional parallel plan for three people

After P0 passes:

| Person | Phases | Notes |
|---|---|---|
| 1: Data and ML | P1, P2, P3 | Owns dataset onboarding, simulator, features, models and ablation |
| 2: Backend | P4, P5 | Starts with dummy model and policy engine, then integrates after P3 |
| 3: Frontend | P6 | Builds against P0 stubs and shared schemas |

Any contract change is one commit touching `common/schemas.py`, `ARCHITECTURE.md` Section 13, and UI types, and must be announced to all three. Merge the tracks at the P4 gate.
