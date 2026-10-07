# GoldenMinutes — Post-Judging Implementation Phases

> **Status:** Plan APPROVED 2026-10-07. **Phase 1 COMPLETE** — full-profile training, evaluation, paired bootstrap, test suites (101/101 tests), and linter passing.
> Decisions applied: D1 = accept metric drop; D2 = option (a); Q2 = self-contained GraphSAGE.
> **Source of feedback:** `GoldenMinutes_Judging_Feedback_One_by_One.pdf` (overall 74.67/100, 3 judges).
> **Companion contract:** `ARCHITECTURE.md`. Each phase lists the exact `ARCHITECTURE.md` sections it would change.
> Those edits happen **only once that phase is approved and in progress**, in the same change as the code.
> **Execution rule:** one phase per work session. Stop after each phase. Wait for "approved, proceed to next phase".

### Phase 1 progress log (2026-10-07)
| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Data realism (device-ID shortcut) | ✅ Done | `impersonation_scam.py` + behavior.py updated; device shortcut eliminated |
| 2 | Graph feature fix (P2P subgraph) | ✅ Done | `features/graph.py` created; merchant/agent hubs excluded |
| 3 | GNN model (`models/gnn.py`) | ✅ Done | MuleGraphSAGE 2-layer; `embedding_store.py` point-in-time |
| 4 | Variants E + F; champion selection | ✅ Done | `ablation.py` A–F; champion = E (PR-AUC 0.9135); F = diagnostic |
| 5 | Lift analysis (`eval/lift.py`) | ✅ Done | Paired bootstrap (1,000 resamples), E-B lift +0.2629 [0.1472, 0.3787] |
| 6 | Evaluation population fix (F6) | ✅ Done | Primary = `send_money`; other types reported separately |
| 7 | Reason codes + UI updates | ✅ Done | `NETWORK_MULE_NEIGHBORHOOD` added; Metrics.tsx A–F + CI panel |
| 8 | macOS BLAS segfault fix | ✅ Done | `OMP_NUM_THREADS=1` in Makefile + `gnn.py`; `import lightgbm` before torch |
| 9 | ARCHITECTURE.md updated | ✅ Done | §5 GNN active; §8 GNN features; §9 E/F variants; fusion calibration note |
| 10 | Full-profile pipeline & verification | ✅ Done | All 83 Python tests + 18 Vitest UI tests (101/101) passing; `make lint` clean |


---

## 0. Baseline: what I found in the repo (evidence for every phase below)

I checked these before planning. The test suite passes today (77 pytest tests). The numbers come from
`data/processed/full/features.parquet`, `reports/metrics.json` and the source files linked here.

| # | Finding | Evidence | Affects |
|---|---|---|---|
| F1 | **One feature nearly gives away the label.** `new_device_flag` alone scores ROC-AUC **0.985**. 1,857 of 1,862 fraud rows (99.7%) have `new_device_flag=1`, compared with 2.8% of legit rows. The cause is that every typology makes up device IDs (`DEV_V_*`, `DEV_M_*`, `DEV_BURST_*`, `DEV_COLLUDE_*`) that are never written to `device_links`. | `simulator/typologies/*.py` (e.g. `impersonation_scam.py:52`); single-feature AUC scan | Phases 1, 5, 6 |
| F2 | **Graph features add no lift.** Variant B (no graph) and Variant C (+graph) match to 4 decimals: PR-AUC 0.9935, recall 98.97%, same per-typology recall. | `reports/metrics.json → ablation_table` | Phase 1 |
| F3 | **Graph features as built carry almost no signal.** `component_size_7d` averages about 17,000 (one giant component, because merchant and agent hubs connect everyone). `two_hop_confirmed_mule_share` has AUC 0.52 (mean 0.0135 for legit vs 0.0132 for fraud). The spec says "suspicious transaction subgraph", but the code builds the **full** transfer graph. | `features/offline.py:355-394`, `features/online.py:124-170` | Phase 1 |
| F4 | **There is no graph learning.** "Graph intelligence" is 5 hand-made NetworkX statistics. `ARCHITECTURE.md §5` calls GNN "a stretch goal only". `torch` is not installed. `features/graph.py` is listed in `§4` but does not exist (graph logic is inline in `offline.py` and `online.py`). | `pyproject.toml`, `ARCHITECTURE.md §4, §5, §19` | Phase 1 |
| F5 | **No lift statistics.** `eval/metrics.py` has `compute_bootstrap_ci`, but the ablation never uses it. There is no paired delta, no feature-group permutation importance, and no confidence interval on B→C. | `eval/ablation.py`, `eval/metrics.py:104` | Phase 1 |
| F6 | **Evaluation scores transaction types the API never scores.** The test split includes `cash_out` (561 fraud) and `add_money_card` (295 fraud) rows. `/v1/score` only takes send-money requests. | crosstab of `type × is_fraud` | Phase 1 |
| F7 | **Model-loading bug (the one Judge 1 flagged), root cause.** The committed `models/registry.json` has `active_version: m-1.0.0-full`, but `models/*` is gitignored, so a fresh clone has no `.joblib` files. `get_active_metadata()` still returns metadata (not `None`), so the `demo_assets/` fallback in `service.py:62-72` **never runs**. Each artifact load is skipped quietly by `Path(...).exists()` (`service.py:87-94`). The service then scores with **rules only** (`service.py:177`) while `/health` still reports `m-1.0.0-full`. `GM_MODEL_DIR` is defined but never read. | `models/registry.json`, `.gitignore`, `api/service.py:53-97`, `models/registry.py:15,39` | Phase 2 |
| F8 | **No hosted demo.** There is no Dockerfile or deploy config. CORS is hard-coded to `localhost:5173`. `main.py` can already serve `ui/dist` as static files (`main.py:550`), so a single-container deploy is possible. | repo tree, `api/main.py:81-90` | Phase 2 |
| F9 | **An independent dataset is available but unused.** The organiser dataset in `goldentimes_synthetic_dataset/` (500k txns, 150 mule rings, 265k relationship edges, 6 scenarios, 3.9% fraud) has an intake path (`simulator/intake.py`, `generate.py --source bootstrap`). The models are never evaluated on it. | `DATASET_README.md`, `generate.py:69` | Phases 2, 5 |
| F10 | **Shared keys, and the analyst key ships to the browser.** `ui/src/api/client.ts:7-8` reads the analyst key from `VITE_ANALYST_KEY` (falling back to a hard-coded default) and bakes it into the JS bundle, so anyone who loads the UI has analyst rights. Every audit entry records `analyst_id="analyst_demo"` (`main.py:283`). Keys are compared with plain `==` (`deps.py:25`). | `client.ts`, `deps.py`, `main.py:283` | Phase 3 (and a risk for Phase 2, see §D2) |
| F11 | **Fairness result is empty of meaning.** FFR is 0.00% in every slice. That is a side effect of F1 (the model is near-perfect), not evidence of fairness. | `reports/fairness_report.md`, `metrics.json` | Phase 3 |
| F12 | **All scoring state lives in one process.** `OnlineFeatureStore` keeps rolling windows and graph edges in Python dicts. `PolicyEngine` keeps hold capacity in memory. `get_service()` is a process singleton. The database is a SQLite file. Two scoring replicas would compute **different features** for the same request. | `features/online.py`, `policy/engine.py:76-118`, `api/service.py:328`, `api/store.py:139` | Phase 4 |
| F13 | **Savings and friction are not measured.** `expected intercepted value` is `amount × effectiveness[action]`, an assumption, measured only on the project's own easy data. Customer friction is never measured in minutes of delay or BDT delayed. | `eval/metrics.py:48`, `policy.yaml` | Phase 5 |
| F14 | **The adaptive fraudster was never built.** `ARCHITECTURE.md §7` lists it as a stretch goal. The code has no adversarial or evasion typologies. | grep `adversar|adaptive` → none | Phase 6 |
| F15 | **Problem claims have no sources.** The README says "৳1,00,000 Crore monthly" and "30-minute window" with no citations. | `README.md:14-16` | Phase 7 |
| F16 | **Docs contradict each other.** README p95 is given as 2.3 ms (diagram), 11.2 ms (text) and 1.15 ms (table). "React 19" vs "React 18" badge. `PHASES.md` and `PHASES_GoldenMinutes.md` are byte-identical duplicates. Brier = 0.0 on B/C/D is a sign of F1. | `README.md`, root dir | Phases 1, 2 |

---

## 1. Phase order and dependency flags

| Order | Phase | Criterion (score) | Why here |
|---|---|---|---|
| 1 | **AI/ML Depth: real graph learning + measured lift** | AI/ML Depth (73.4%) | User priority |
| 2 | **Prototype Quality: fix model loading, public demo, replay validation** | Prototype Quality (68.9%) | User priority |
| 3 | Responsible AI & Security: per-user auth + validated safeguards | 60.0% | Lowest remaining score |
| 4 | Scalability & Integration: shared state, graph DB, multi-replica proof | 66.7% | Next lowest |
| 5 | Business/Customer Impact: measured loss prevented + friction cost | 76.6% | Next lowest |
| 6 | Innovation: adversarial scams + golden-window time-to-cash-out model | 76.7% | Next lowest |
| 7 | Problem Relevance: primary-source validation | 85.0% | Highest score; not in your list, so I put it last |

I did **not** reorder anything. These are the dependency issues I found and how the plan handles them. I need
your decision on D1 and D2.

> [!IMPORTANT]
> **D1. Phase 1 has to fix the data before it can show any lift (scope expansion, not a reorder).**
> F1 means Variant B is already near-perfect (PR-AUC 0.99), so *no* graph model can show measurable lift on this
> data. Phase 1 therefore starts by removing the simulator's device-ID shortcut and the giant-component artefact.
> **Consequence:** the headline numbers in README and pitch (98.97% recall, 0% FFR, 98.36% held-out) **will drop**,
> probably by a lot. The new numbers will be honest and will hold up when judges ask about them. Please confirm you
> accept this.

> [!WARNING]
> **D2. Phase 2 (public demo) ships before Phase 3 (per-user auth).**
> Because of F10, a public URL would publish the analyst key inside the JS bundle. That puts the exact weakness
> Judge 1 flagged on display. Options:
> - **(a) Recommended. Keep the order** and add a stopgap in Phase 2. The public build ships **without** the analyst
>   key. Analyst views run in a read-only "sandbox" role with per-visitor demo state reset and rate limiting. The full
>   fix lands in Phase 3.
> - **(b)** Move a minimal per-user login from Phase 3 into Phase 2. Phase 3 would then cover hardening and validation only.
> - **(c)** Delay publishing the URL until Phase 3 is done.

> [!NOTE]
> **D3. These dependencies support the current order (no change needed).**
> - Phase 3's "validated in a production-like setting" needs the Phase 2 deployment to test against.
> - Phase 3's fairness re-run only means something after the Phase 1 data fix (F11).
> - Phase 5's impact numbers need Phase 1's honest data and Phase 2's replay harness.
> - Phase 1 puts GNN embeddings behind an `EmbeddingStore` interface, so Phase 4 can move them to Redis or a graph DB
>   without touching model code.
> - Phase 3 adds Alembic migrations, so Phase 4's move from SQLite to Postgres is a config change, not a rewrite.

> [!CAUTION]
> **D4. "Real MFS transactions" cannot be met under the current hard constraint C1** ("Synthetic data only. No real
> personal data, ever." in `ARCHITECTURE.md §2`). The plan covers the gap as far as C1 allows:
> 1. Replay on an **independently generated** dataset (the organiser data, F9).
> 2. Optionally, **PaySim**, a public synthetic mobile-money dataset calibrated on real African MFS logs (licence and
>    download need your OK).
> 3. A **shadow-mode replay harness** that an MFS partner could point at governed data.
>
> README will say clearly that this is not validation on real data.

---

## Phase 1 — AI/ML Depth: real graph learning and measured wallet-link lift

**Objective.** Replace "graph intelligence = NetworkX counts" with a real graph-learning model. Then prove, with
confidence intervals, whether wallet-link signals improve detection over the tabular baseline. If they don't, say so.

**Judge weakness addressed.**
- AI/ML Depth, **Judge 2**: "advanced graph learning/GNN is not actually implemented."
- AI/ML Depth, **Judge 1**: "Show whether wallet links improve detection."
- AI/ML Depth, **Judge 3**: mentions the graph layer is "NetworkX-graafeigenschappen" (NetworkX graph features).

**Root cause in the codebase.**
- F4: there is no learned graph model. `§5` treats GNN as a stretch goal.
- F1: the `new_device_flag` shortcut in every typology generator makes the tabular model near-perfect, so no added
  signal can show up.
- F3: graph snapshots use every transfer edge, including merchant and agent hubs. That gives a giant component
  (~17k nodes) and a diluted 2-hop mule share.
- F5: the ablation compares point estimates only. There are no paired CIs and no group importance.
- F6: the evaluation population (cash_out and add_money_card rows) doesn't match the population the API scores.

**Proposed technical changes.**
1. **Data realism (prerequisite, see D1).**
   - Typology generators reuse the victim's **own** registered device for coercion scams (impersonation, relative
     emergency). That is what happens in reality: the victim is talked into sending from their own phone.
   - New-device signals stay only for `sim_swap_takeover`, and only with probability < 1.
   - About 3–5% of legit transfers get a new device (phone upgrades).
   - Every fraud device is written to `device_links` with a realistic `first_seen_at`.
   - Assumptions recorded in `docs/assumptions.md`.
2. **Fix the existing graph features.** Build snapshots on a *P2P transfer subgraph*: exclude edges to wallets whose
   `owner_type ∈ {merchant, agent}` and biller hubs. Add wallet–device and wallet–cash-out-agent edges as separate
   relations. Recompute `component_size_7d` and `two_hop_confirmed_mule_share`. Move the shared logic into a new
   `features/graph.py` (the file `§4` already promises) so offline and online use one implementation.
3. **GNN model (`models/gnn.py`).**
   - **Model:** a 2-layer **GraphSAGE** (mean aggregator) in PyTorch. Node features are per-wallet aggregates: tenure,
     in/out counts and amounts, median receipt-to-cash-out time, device fan-out. The graph is heterogeneous, with
     wallet→wallet transfer, wallet–device and wallet–agent relations collapsed to typed edges.
   - **Task:** node classification `is_mule`, trained semi-supervised on **`confirmations` only**
     (`confirmed_at ≤ snapshot_end`), never on `labels` or `hidden_truth`. This keeps leakage rule C8 and the §18
     leakage test intact. `hidden_truth` is used in evaluation only.
   - **Point-in-time:** embeddings and scores are computed per daily snapshot covering D-7…D-1. That is the same
     discipline `component_size_7d` already follows, so a request on day D reads day D-1's table.
   - **Outputs, as new graph features:** `gnn_recipient_mule_score` and `gnn_sender_mule_score`, plus a small
     embedding (4–8 PCA dims of the 32-dim hidden layer) for the tree model.
   - **Serving:** `EmbeddingStore` interface with a Parquet/in-memory backend now and Redis in Phase 4. The online path
     is a dictionary lookup, so latency barely changes. New wallets (cold start) get an inductive 1-hop mean
     aggregation, or a learned default.
4. **New Variant E** = LightGBM + fixed graph features + GNN outputs (+ anomaly via fusion, as Variant D does today).
   Variant F = GNN score alone, as a diagnostic. Ablation table becomes **A, B, C, D, E (+F)**.
5. **Lift analysis (`eval/lift.py`, wired into `make eval`).**
   - Paired bootstrap (≥1,000 resamples, same rows across variants) of ΔPR-AUC, Δrecall@1%FFR and Δvalue-recall for
     **C−B**, **E−C**, **E−B**, with 95% CIs.
   - Every metric reported per typology. Mule-ring and impersonation are where graph signal should matter most.
   - **Feature-group permutation importance** (sender / pair / device / recipient / graph / GNN).
   - **Graph-perturbation sanity check:** randomly rewire edges in the test snapshot. GNN lift should disappear,
     which shows the model really uses graph structure.
   - Output: `reports/lift.json` and `reports/lift_report.md`.
6. **Evaluation population fix (F6).** Primary metrics only on the transaction types `/v1/score` accepts. Other types
   reported separately.
7. **Explainability.** New reason code `NETWORK_MULE_NEIGHBORHOOD` in `configs/reasons.yaml` (en + bn; the bn text is
   flagged for native-speaker review). SHAP keeps working because GNN outputs are inputs to LightGBM.
8. **Docs.** README, `docs/model_card.md` and the metrics UI ablation table updated with the new honest numbers and
   CIs. The B=C claim is removed. The three conflicting README latency figures are reconciled (F16).

**Files/modules likely affected.**
- `simulator/typologies/{impersonation_scam,mule_ring,sim_swap_takeover,card_to_wallet_burst,agent_collusion}.py`, `simulator/behavior.py`, `configs/simulator.yaml`
- `features/graph.py` (new), `features/offline.py`, `features/online.py`, `features/specs.py`, `configs/features.yaml`
- `models/gnn.py` (new), `models/embedding_store.py` (new), `models/train.py`, `models/registry.py`, `configs/models.yaml`
- `eval/ablation.py`, `eval/lift.py` (new), `eval/run_eval.py`, `eval/metrics.py`
- `api/service.py` (Variant E as the active champion), `explain/reasons.py`, `configs/reasons.yaml`
- `ui/src/pages/Metrics.tsx` (variants E/F + CI columns), `ui/src/locales/*.json`
- `pyproject.toml` (`torch` CPU build; optional `torch_geometric` — see open question Q2)
- `tests/test_gnn.py`, `tests/test_lift.py` (new); `tests/test_features.py`, `tests/test_parity.py`, `tests/test_simulator.py` (extended)
- `docs/assumptions.md`, `docs/model_card.md`, `README.md`, `demo_assets/` (retrained small bundle)

**Acceptance criteria (objective).**
1. **The shortcut is gone:** no single feature has ROC-AUC > 0.85 on the `full` test split. Shown by a committed
   single-feature AUC scan in `reports/lift.json` and enforced by a test on the `small` profile.
2. **Real graph learning exists:** `models/gnn.py` trains a message-passing model. Tests prove:
   - (a) seeded determinism;
   - (b) training reads only `confirmations` with `confirmed_at ≤ snapshot_end`, never `labels` or `hidden_truth`
     (the leakage test is extended);
   - (c) a future edge does not change a past embedding (point-in-time);
   - (d) online/offline parity for the GNN features within tolerance.
3. **Lift is quantified:** `reports/lift_report.md` shows paired-bootstrap 95% CIs for C−B, E−C and E−B overall and
   per typology, plus group permutation importance and the rewiring sanity check.
   **Pass condition:** the E−B ΔPR-AUC CI excludes 0 overall **or** on at least one graph-native typology (mule_ring,
   impersonation_scam). **If not,** the "graph intelligence improves detection" claim is removed from README and pitch
   and the negative result is reported. Either way the judge's question gets an evidence-based answer.
4. **Latency budget held:** p95 `/v1/score` < 150 ms in `benchmarks/benchmark_latency.py` with Variant E active.
5. **Regression:** `make test` and `make lint` green. Existing contract tests unchanged or only extended.

**Estimated effort.** **L**, about 4–6 focused days. Data regeneration plus GNN training on `full` is the long pole.

**Dependencies / risks.**
- Retraining on `full` changes every headline metric (D1).
- The GNN may show *small* lift on synthetic data. The acceptance criteria allow reporting that honestly.
- PyTorch on Python 3.13 / macOS: CPU wheels exist. `torch_geometric` adds install friction, so the default plan is a
  self-contained GraphSAGE using `torch.sparse` (Q2).
- Docker image size grows by about 200 MB (CPU torch). This matters for the Phase 2 hosting choice.
- Bangla text for the new reason code needs native review (`docs/bangla_review.md`).

**Architecture change required?** **Yes.**

---

## Phase 2 — Prototype Quality: fix model loading, publish a demo, replay on independent data

**Objective.** A fresh clone, or the public URL, loads the champion model for sure (or fails loudly). Judges get a
working hosted demo link. Detection is validated by replaying an independently generated dataset through the real
API path.

**Judge weakness addressed.**
- Prototype Quality, **Judge 1**: "no public link was provided. Share a working demo link and fix model loading."
- Prototype Quality, **Judge 2**: "remains a synthetic-data prototype rather than a live MFS deployment."

**Root cause in the codebase.**
- F7: the committed `models/registry.json` points to `m-1.0.0-full`, whose artifacts are gitignored. The
  `demo_assets/` fallback is skipped because metadata exists. The artifact checks fail quietly, so the API runs
  rules-only while `/health` reports a model version. `active_version` is hard-coded in `service.py:53`.
  `GM_MODEL_DIR` is never used.
- F8: there is no container or deploy config, and CORS is pinned to localhost.
- F9: the organiser dataset is never used for evaluation.

**Proposed technical changes.**
1. **Model loading, fail-loud and verifiable.**
   - Registry resolves from `GM_MODEL_DIR`.
   - Resolution order: env-pinned version → active version **whose artifacts all exist and pass their checksums** →
     `demo_assets` bundle → explicit `degraded` mode.
   - SHA-256 checksums are written into registry metadata at train time and checked at load time.
   - Remove the hard-coded `active_version`. Stop committing an `active_version` that points to gitignored artifacts.
   - `/health` gains `models_loaded: bool`, `degraded: bool`, `artifact_source: registry|demo_assets|none`. The UI shows
     a visible banner when degraded.
   - `GM_ENV=prod` refuses to start in degraded mode.
2. **Fresh-clone test.** A CI job clones the repo into a temp dir, runs `make setup`, starts the API, and asserts
   `/health.degraded == false` and that a known-risky request gets a model-based score (not the rules fallback).
3. **GitHub Actions CI:** lint, pytest, vitest, fresh-clone test, Docker build.
4. **Single-container deploy.** Multi-stage `Dockerfile` (build `ui/dist` → slim Python runtime with the demo model
   bundle; FastAPI already serves the SPA). `docker-compose.yml` for local use. Env-driven CORS. A deploy manifest for
   the chosen host (Q1).
5. **Public-demo safety stopgap (D2 option a).** Public build excludes `VITE_ANALYST_KEY`. A `public_demo` role gets
   read-only analyst views plus attack replay. Per-visitor demo state reset. Simple rate limit. "Synthetic data"
   banner (already in `Navbar.tsx`).
6. **Replay validation harness (`demo/replay_dataset.py`, `make replay`).**
   - Ingest the organiser dataset via `simulator/intake.py`.
   - Build features with the *online* store.
   - Stream transactions in timestamp order through the real `/v1/score` HTTP path (or in-process `TestClient`).
   - Write `reports/replay_<dataset>.json/md`: recall, value-recall and FFR at the operating point; per-scenario recall
     (including scenarios our simulator never generated, e.g. `relative_emergency_scam`, `account_takeover`);
     latency distribution; decision mix.
   - The models are **not** retrained on this data, so it's a true out-of-distribution test.
   - Optional PaySim replay (D4).
7. **Docs.** README gets the public URL, a "Validation beyond our own simulator" section, and a corrected quick-start.
   Duplicate `PHASES_GoldenMinutes.md` deleted or marked as a mirror (F16).

**Files/modules likely affected.**
- `models/registry.py`, `api/service.py`, `api/main.py` (`/health`, CORS), `common/config.py`, `common/schemas.py` (`HealthResponse`)
- `api/deps.py` (`public_demo` role), `ui/src/api/client.ts`, `ui/src/components/Navbar.tsx` (degraded banner)
- `demo/replay_dataset.py` (new), `simulator/intake.py`, `Makefile`
- `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.github/workflows/ci.yml`, host manifest (all new)
- `models/registry.json`, `demo_assets/registry.json`, `.gitignore`, `.env.example`
- `tests/test_model_loading.py`, `tests/test_replay.py` (new), `tests/test_api_contracts.py` (health fields)

**Acceptance criteria (objective).**
1. **Model loading fixed:**
   - Fresh-clone CI job passes: `/health` returns `models_loaded=true, degraded=false`.
   - A unit test reproduces the old bug (registry points to missing artifacts) and asserts the bundle fallback is used,
     or a loud error when `GM_ENV=prod`.
   - A tampered artifact (checksum mismatch) is rejected.
2. **Public demo:** a working HTTPS URL. A scripted smoke test (Playwright or httpx) against **the deployed URL**
   passes: health, normal send → `allow`, attack replay → `hold`, alert visible in the analyst view, metrics page
   renders. Screenshot or recording saved in `docs/`.
3. **No analyst secret in the public bundle:** CI greps `ui/dist` and fails if `VITE_ANALYST_KEY` or the analyst key
   value appears.
4. **Replay validation:** `reports/replay_organiser.md` exists with per-scenario recall, FFR and latency from
   streaming ≥100k organiser transactions through the scoring path, with zero errors. Results are reported honestly
   even if lower than on our own data.
5. CI green on `main`.

**Estimated effort.** **M**, about 2–4 days. Replay schema mapping is the main unknown.

**Dependencies / risks.**
- Needs Phase 1's retrained `demo_assets` bundle (otherwise we publish the old shortcut model).
- Hosting choice affects image size and cold start (torch from Phase 1): Q1.
- Public URL before per-user auth: D2.
- Organiser dataset licence or terms for public reports: confirm (Q4).

**Architecture change required?** **Yes**, deployment topology and health contract only. Scoring logic is unchanged.

---

## Phase 3 — Responsible AI & Security: individual logins and validated safeguards

**Objective.** Every reviewer has a personal, secure login. Every analyst action can be traced to a person in a
tamper-evident audit log. Fairness and prompt-injection safeguards are tested against the deployed system, not only
in unit tests.

**Judge weakness addressed.**
- Responsible AI & Security, **Judge 1**: "shared access keys weaken protection. Give each reviewer a secure
  personal login."
- Responsible AI & Security, **Judge 2**: "these safeguards have not yet been validated in production."

**Root cause in the codebase.**
- F10: two global keys (`GM_CUSTOMER_KEY`, `GM_ANALYST_KEY`), the analyst key compiled into the frontend, the
  hard-coded `analyst_id="analyst_demo"`, and key comparison that isn't constant-time.
- F11: fairness "0% FFR everywhere" is an artefact of F1.
- Prompt-injection tests (`tests/test_narrative_guards.py`) only run in-process against the template provider.

**Proposed technical changes.**
1. **Identity:**
   - `users` table with argon2id password hashes and roles `analyst`, `senior_analyst`, `admin`, `customer_demo`.
   - `POST /v1/auth/login` issues short-lived JWT access tokens plus refresh tokens in **httpOnly, Secure, SameSite**
     cookies, with logout and token revocation.
   - Optional OIDC hook (Q5).
   - Account lockout after N failures. Login rate-limited.
2. **Service-to-service auth:** the `/v1/score` caller (an MFS core system) uses **hashed, named, per-client API keys**
   (`api_clients` table, rotation, constant-time compare). The shared customer key is removed.
3. **Authorization:**
   - `analyst_id` comes from the token in every `record_analyst_action` call.
   - **Four-eyes rule:** releasing a hold above a configurable amount needs a `senior_analyst`.
4. **Audit integrity:** `audit_logs` gets a hash chain (`prev_hash`, `entry_hash`), a verification command, and
   append-only enforcement in the store layer. Logins, failed logins and role changes are audited too.
5. **Frontend:** login page, auth context, removal of all `VITE_*_KEY` usage, per-user display in the analyst console.
6. **Migrations:** introduce Alembic, so the schema change works on SQLite now and Postgres in Phase 4.
7. **Validation in a production-like setting (against the Phase 2 deployment):**
   - **OWASP ZAP baseline scan** of the deployed URL in CI.
   - **Auth test matrix** (wrong role, expired token, replayed refresh, lockout).
   - **Expanded red-team corpus:** ≥50 prompt-injection payloads in English, Bangla and mixed script, sent through the
     *deployed* `/v1/score` `reference` field. Each must leave score, action and narrative facts unchanged.
   - **Fairness re-run** on Phase 1's honest data with bootstrap CIs on FFR and recall per slice. Gaps above the
     threshold are flagged (not hidden).
   - Results in `reports/security_validation.md`.

**Files/modules likely affected.**
- `api/deps.py`, `api/main.py`, `api/store.py` (`users`, `api_clients`, `refresh_tokens`, audit hash chain), `api/auth.py` (new)
- `common/config.py`, `common/schemas.py`, `.env.example`, `alembic/` (new)
- `eval/fairness.py`, `tests/test_auth_roles.py`, `tests/test_auth_login.py`, `tests/test_audit_chain.py`, `tests/redteam/` (new)
- `ui/src/api/client.ts`, `ui/src/pages/Login.tsx` (new), `ui/src/App.tsx`, `ui/src/pages/AnalystConsole.tsx`, locales
- `.github/workflows/ci.yml` (ZAP job), `docs/model_card.md`, `README.md` Section 16 checklist

**Acceptance criteria (objective).**
1. No shared secret in the repo or the UI bundle. CI grep is green. `GM_ANALYST_KEY` and `VITE_*_KEY` are removed.
2. Two seeded analysts log in separately. Each analyst action's audit row carries the right `user_id`. Tests cover
   this.
3. The audit hash-chain check passes. A test that changes any row makes it fail.
4. The four-eyes test passes: a junior analyst gets 403 on a high-value release.
5. ZAP baseline on the deployed URL shows **no High findings**. Medium findings are fixed or documented.
6. The red-team corpus passes 100% against the deployed instance.
7. `reports/fairness_report.md` regenerated with CIs on honest data.

**Estimated effort.** **M–L**, about 3–5 days.

**Dependencies / risks.** Needs the Phase 2 deployment to validate against. A cookie-based session needs CORS and
CSRF handled correctly on the hosted origin. OIDC is optional, to avoid an external IdP dependency in the demo.

**Architecture change required?** **Yes.**

---

## Phase 4 — Scalability & Integration: shared state, graph database, multi-replica proof

**Objective.** Show that N scoring replicas share one source of truth for features, holds and decisions. Run graph
work on graph infrastructure. Show a realistic MFS integration surface.

**Judge weakness addressed.**
- Scalability & Integration, **Judge 1**: "needs shared data for larger use. Test several scoring servers using the
  same data."
- Scalability & Integration, **Judge 2**: "large-scale performance and integration with actual MFS infrastructure
  have not been demonstrated."
- Scalability & Integration, **Judge 3**: "graph computations... should scale to dedicated graph databases."

**Root cause in the codebase.** F12. Rolling windows, pair history, device links and graph edges live in Python
dicts inside `OnlineFeatureStore`. Hold capacity is an in-memory list in `PolicyEngine`. The service is a process
singleton. Storage is a SQLite file. The graph is rebuilt in NetworkX per process.

**Proposed technical changes.**
1. **Postgres** for decisions, alerts, audit and users (already SQLAlchemy; switch via `GM_DB_URL` + Alembic).
2. **Redis online feature state:**
   - Sorted sets per wallet for 1h/24h/7d windows, sets for pair history and device links.
   - An atomic Lua script for "read features + append event", so concurrent replicas stay consistent.
   - A shared hold-capacity counter (sliding-window `INCR` with TTL).
   - `OnlineFeatureStore` becomes an interface with `InMemory` (tests/demo) and `Redis` backends.
   - The existing parity test runs against both.
3. **Graph database (Neo4j Community or Memgraph, Q3):**
   - Holds the wallet/device/agent graph.
   - Powers `/v1/graph/{wallet_id}` with Cypher 2-hop queries.
   - Runs the nightly snapshot export for Phase 1's GNN job.
   - GNN embeddings are published to Redis through `EmbeddingStore`. The hot path never queries the graph DB
     synchronously (latency).
4. **Integration surface:**
   - An event-ingestion consumer (Redpanda/Kafka topic `mfs.transactions`) that updates feature state from the MFS
     ledger stream.
   - A synchronous pre-authorization `/v1/score` contract with idempotency keys and timeout and fail-open semantics,
     documented.
   - A **mock MFS core adapter** that plays the ledger and calls score at authorization.
   - A shadow-mode flag (score, log, no customer action).
   - Documented as "integration-ready". Not claimed as integrated with upay.
5. **Multi-replica proof:**
   - `docker-compose.scale.yml` with 3 API replicas behind nginx + Postgres + Redis + graph DB.
   - Cross-replica consistency test: send the fan-in burst to replica 1, score on replica 3, and assert identical
     features to single-node.
   - k6/Locust load test, with the report in `reports/scale_test.md`.

**Files/modules likely affected.**
- `features/online.py` (refactored into an interface), `features/online_redis.py` (new), `policy/engine.py`, `api/service.py`, `api/store.py`, `api/main.py` (graph endpoint)
- `models/embedding_store.py` (Redis backend), `graph/neo4j_repo.py` (new), `ingest/consumer.py`, `integration/mock_core.py` (new)
- `docker-compose.scale.yml`, `deploy/nginx.conf`, `benchmarks/loadtest/` (new), `.env.example`, `pyproject.toml` (`redis`, `psycopg`, `neo4j`)
- `tests/test_parity.py` (both backends), `tests/test_multi_replica.py` (new, runs in compose CI job)

**Acceptance criteria (objective).**
1. The cross-replica test passes: features computed on any replica match single-node values exactly (tolerance as in
   the existing parity test). The hold-capacity cap holds globally across replicas.
2. Load test with 3 replicas: sustained ≥ X req/s (target agreed in Q6, e.g. 500 rps on a laptop-class host) with
   p95 < 150 ms and 0 errors. Throughput scaling from 1→3 replicas reported.
3. `/v1/graph/{wallet_id}` served from the graph DB, and the p95 of the 2-hop query reported.
4. The mock core adapter replays ≥100k transactions through ingestion + score in shadow mode with zero lost events
   (idempotency test).
5. Single-node `make demo` still works with in-memory backends (no regression for judges).

**Estimated effort.** **XL**, about 6–9 days. This is the largest phase. I can split it into 4a (Postgres + Redis +
replicas) and 4b (graph DB + ingestion) if you prefer.

**Dependencies / risks.** Redis Lua window logic must match offline semantics exactly (the parity risk). Running a
graph DB on the public host may need a paid tier, so the public demo may stay single-node while the scale proof runs
in CI or compose (Q1/Q3).

**Architecture change required?** **Yes**, and it's the largest one.

---

## Phase 5 — Business/Customer Impact: measured loss prevented and friction cost

**Objective.** Replace assumed savings with measured, replay-based loss-prevention numbers that have uncertainty
bounds. Quantify the cost of unnecessary delays to legitimate customers.

**Judge weakness addressed.**
- Business/Customer Impact, **Judge 1**: "claimed savings need testing. Measure losses prevented and unnecessary
  payment delays."
- Business/Customer Impact, **Judge 2**: "impact has not yet been demonstrated with real MFS transactions or
  customers."

**Root cause in the codebase.**
- F13: `compute_expected_intercepted_value` multiplies the amount by an assumed `effectiveness[action]`.
- Friction is a flat BDT number in `policy.yaml`. No metric counts delay minutes, delayed legit value or analyst
  workload.
- Measured only on F1-inflated data.

**Proposed technical changes.**
1. **Time-aware loss model (`eval/impact.py`).** Use each fraud case's actual simulated **cash-out timestamp**. A hold
   prevents loss only if analyst resolution (from the capacity queue simulation) happens *before* cash-out. Warn and
   verify use configurable abandonment rates with a sensitivity range. Output: *money actually saved vs. money that
   escaped while waiting in queue*.
2. **Customer friction metrics:**
   - Count of legit customers delayed, per action.
   - Total and p95 **delay minutes** (warn ≈ seconds, verify = cooling-off, hold = queue time until release).
   - **Legit BDT delayed**.
   - Repeat-friction rate (the same customer hit more than once in 30 days).
   - Estimated drop-off cost.
3. **Analyst workload simulation:** alerts/hour vs `hold_capacity_per_hour`, queue wait, "late" alert share. Ties to
   Judge 1's Problem Relevance note to "check the response time needed by fraud teams".
4. **Net-benefit curve:** saved BDT − friction cost − analyst cost across operating thresholds, with bootstrap CIs.
   Run on (a) our simulator, (b) the organiser replay (Phase 2), (c) PaySim if approved.
5. **UI:** a Metrics-page "Impact" section with saved vs escaped, delay distribution and the net-benefit curve.
6. **Assumption ledger:** every rate comes from `configs/policy.yaml` and is listed in `docs/assumptions.md`.

**Files/modules likely affected.** `eval/impact.py` (new), `eval/run_eval.py`, `eval/metrics.py`,
`configs/policy.yaml`, `ui/src/pages/Metrics.tsx`, locales, `api/main.py` (`/v1/metrics` fields),
`common/schemas.py`, `reports/impact_report.md`, `docs/assumptions.md`, `tests/test_impact.py`.

**Acceptance criteria (objective).**
1. `reports/impact_report.md` reports, for each dataset, with 95% CIs: BDT saved before cash-out, BDT escaped,
   legit customers delayed, p50/p95 delay minutes, legit BDT delayed, alerts/hour vs capacity, and the net benefit at
   the chosen operating point.
2. A test shows a hold resolved *after* the simulated cash-out counts as **not** saved.
3. The sensitivity grid shows whether the conclusion (net benefit > 0) holds across the configured effectiveness and
   abandonment ranges. Regions where it doesn't are stated explicitly.
4. README replaces "৳42 Lakh intercepted" with the measured, CI-bounded figure and its assumptions.

**Estimated effort.** **M**, about 2–3 days.

**Dependencies / risks.** Needs Phase 1 (honest data) and Phase 2 (replay harness). The organiser dataset's cash-out
linkage quality limits accuracy there. Still no real-customer validation (D4).

**Architecture change required?** **No** structural change. The doc update is limited to `§15` (new metric rows),
which I'll make together with the code so the two docs stay in step.

---

## Phase 6 — Innovation: harder-to-detect scams and a golden-window cash-out model

**Objective.** Stress-test detection against adaptive and evasive fraud. Add one technique specific to this problem
that goes beyond the established LightGBM/IForest/SHAP stack.

**Judge weakness addressed.**
- Innovation, **Judge 1**: "Test scams that are harder to spot."
- Innovation, **Judge 2**: "most underlying AI techniques are established."

**Root cause in the codebase.**
- F14: the adaptive fraudster is still a stretch item. Typologies are fixed and static.
- The golden window is a fixed 30 minutes in `policy.yaml`. Urgency in `policy/engine.py` uses
  `minutes_since_first_inflow`, not a predicted cash-out time.

**Proposed technical changes.**
1. **Adversarial typology suite** (`simulator/typologies/adversarial/`), each with a "strength" knob:
   - **Threshold-aware structuring:** amounts split just below the R1–R5 thresholds.
   - **Aged mules:** mule wallets pre-aged for 30–90 days with benign activity before use.
   - **Slow cash-out:** mules wait past the golden window.
   - **Deep chains:** 3–5 hop layering, which defeats 2-hop features.
   - **Merchant mimicry:** mules disguised as small merchants.
   - **Clean-device coercion:** no device or auth anomaly (follows from the Phase 1 realism fix).
2. **Adaptive fraudster loop:** after each simulated week, the attacker moves its strategy away from whatever got
   flagged (bandit over evasion tactics). Track recall decay over rounds, with and without weekly retraining.
3. **Robustness report:** recall and value-recall vs attack strength for Variants A, B, C and E. Shows whether the GNN
   degrades more gracefully than rules and tabular models (especially on deep chains).
4. **Golden-window time-to-cash-out model.** A survival model predicts *minutes until the recipient cashes out*
   (LightGBM with a survival objective or discrete-time hazard, on recipient and graph features). Alert priority
   becomes `p × amount × P(cash-out within analyst SLA)`, replacing the fixed-window urgency. The fixed rule stays
   available as a fallback.
5. **Innovation narrative in README:** recipient-side graph learning + survival-based golden-window triage +
   proportionate actions + Bangla explanations, backed by the robustness evidence.

**Files/modules likely affected.** `simulator/typologies/adversarial/*.py` (new), `simulator/generate.py`,
`configs/simulator.yaml`, `models/cashout_survival.py` (new), `models/train.py`, `policy/engine.py`,
`configs/policy.yaml`, `eval/robustness.py` (new), `reports/robustness_report.md`, `ui/src/pages/Metrics.tsx`,
`ui/src/pages/AnalystConsole.tsx` (predicted time-to-cash-out), tests.

**Acceptance criteria (objective).**
1. ≥5 adversarial typologies with tests (reproducible by seed, labelled, never in training when evaluated as held-out).
2. `reports/robustness_report.md`: recall vs attack-strength curves for A/B/C/E with CIs, plus a recall-decay curve
   for the adaptive loop.
3. Survival model C-index reported on test. The **priority-ranking A/B test** in the capacity simulation (fixed-window
   vs survival urgency) reports BDT saved before cash-out at equal analyst capacity. The new method is adopted only if
   it's better (CI excludes 0). Otherwise it's documented as a negative result.
4. All existing tests are green, and latency is still within budget.

**Estimated effort.** **M–L**, about 3–5 days.

**Dependencies / risks.** Depends on Phase 1 (GNN, realistic data) and Phase 5 (capacity/queue simulation reused for
the priority A/B test). The survival model may not beat the fixed window on synthetic data. The acceptance criteria
allow for that.

**Architecture change required?** **Yes (conditional).** `§7` always changes (adversarial typologies). `§11`
changes only if the survival urgency is adopted (criterion 3).

---

## Phase 7 — Problem Relevance: primary-source validation

**Objective.** Back every problem claim with citable primary sources and answer Judge 1's question about fraud-team
response times.

**Judge weakness addressed.**
- Problem Relevance, **Judge 2**: "real-world problem claims still need stronger primary-source validation."
- Problem Relevance, **Judge 1**: "Check the response time needed by fraud teams."

**Root cause in the codebase.** F15. The README's market-size and 30-minute claims have no citations.
`docs/assumptions.md` documents simulator assumptions, not problem evidence.

**Proposed technical changes.**
1. **`docs/problem_evidence.md`** with citations to primary sources (to be verified during the phase, not assumed):
   Bangladesh Bank MFS monthly statistics, BFIU annual reports on MFS-related suspicious transactions, Bangladesh Bank
   MFS regulations (transaction limits), BTRC and police/CID public statements on MFS fraud, and published
   industry/academic studies on mule cash-out latency.
2. **Golden-window justification:** compare cited cash-out latency evidence with our simulator distribution and the
   organiser dataset (average linked cash-out delay 247 minutes). Adjust `configs/simulator.yaml` and
   `golden_window_minutes` if the evidence disagrees.
3. **Mentor/partner validation template:** a short structured questionnaire for upay mentors (response-time SLA,
   typology prevalence ranking). The answers are recorded as evidence once given.
4. README claims rewritten with inline citations. Any claim we can't source is removed or labelled as an estimate.

**Files/modules likely affected.** `docs/problem_evidence.md` (new), `README.md`, `docs/assumptions.md`, possibly
`configs/simulator.yaml` and `configs/policy.yaml`.

**Acceptance criteria (objective).** Every quantitative problem claim in README has an inline citation to a primary
source or is labelled as an estimate. `docs/problem_evidence.md` lists ≥5 primary sources with access dates. The
golden-window value is justified by cited evidence or flagged as an assumption.

**Estimated effort.** **S**, about 0.5–1 day.

**Dependencies / risks.** Some Bangladesh Bank and BFIU documents are PDFs that may be hard to fetch. Mentor answers
depend on availability.

**Architecture change required?** **No** (the `§1` problem statement wording may get citations; the design doesn't
change).

---

## 2. `ARCHITECTURE.md` alignment register

> These edits are **not** made yet. Each is applied only when its phase is approved and underway, in the same change
> as the code, per `ARCHITECTURE.md §0` rule ("if the code and this file disagree... update this file in the same
> change").

| Phase | `ARCHITECTURE.md` section | Change required |
|---|---|---|
| 1 | §2 C8 / §18 leakage | Add: GNN training labels come only from `confirmations` with `confirmed_at ≤ snapshot_end`. GNN features added to the leakage and parity tests. |
| 1 | §3 diagram | Add a "Graph snapshot + GNN embedding job (daily, D-1)" node feeding the offline and online feature layers. Add an `EmbeddingStore`. |
| 1 | §4 layout | `features/graph.py` becomes real (shared snapshot logic). Add `models/gnn.py`, `models/embedding_store.py`, `eval/lift.py`. |
| 1 | §5 tech stack | Graph row: "NetworkX (snapshot features) + PyTorch GraphSAGE (learned embeddings)". Remove "GNN is a stretch goal only". |
| 1 | §7 simulator | Device realism: coercion typologies use the victim's own device; legit new-device rate; all fraud devices in `device_links`. New sanity invariant: no single feature AUC > 0.85. |
| 1 | §8 features | Graph snapshots built on the P2P subgraph (merchant/agent hubs excluded). Add `gnn_recipient_mule_score`, `gnn_sender_mule_score`, `gnn_emb_*`. |
| 1 | §9 models | Add Variant E (C + GNN, fused) and diagnostic Variant F (GNN only). Describe the GNN task, labels and training window. Champion becomes E if acceptance criterion 3 passes. |
| 1 | §10 reasons | Add `NETWORK_MULE_NEIGHBORHOOD`. |
| 1 | §15 eval | Ablation becomes A–F with paired-bootstrap ΔCIs, group permutation importance, edge-rewiring check. Primary population = scored transaction types. |
| 1 | §19 build plan | Remove GNN from Stretch. Add a reference to this file for post-judging phases. |
| 2 | §13 API | `/health` adds `models_loaded`, `degraded`, `artifact_source`. Add a `public_demo` role (stopgap, removed in Phase 3). |
| 2 | §9 registry | Artifact checksums, `GM_MODEL_DIR` resolution order, fail-loud rule in `GM_ENV=prod`. |
| 2 | §17 env/Makefile | `GM_CORS_ORIGINS`, `make replay`, `make docker`. Dockerfile and CI described. |
| 2 | §18 testing | Add the fresh-clone test, bundle-secret scan and replay test. |
| 2 | §20 demo script | Use the public URL. Add a "validation beyond our simulator" step. |
| 3 | §6 data model | Add `users`, `api_clients`, `refresh_tokens`. `audit_logs` gains `prev_hash`, `entry_hash`. `analyst_actions.analyst_id` must be a real user. |
| 3 | §13 auth | Replace the `X-API-Key` shared-role scheme with per-user JWT sessions (UI) + hashed per-client API keys (`/v1/score`). Add the four-eyes rule. Remove the `public_demo` stopgap. |
| 3 | §14 frontend | Add a login screen and auth context. No secrets in the bundle. |
| 3 | §16 checklist | Rewrite the role-based-access line. Add ZAP, red-team corpus and audit-chain items. |
| 3 | §17 env | Remove `GM_ANALYST_KEY`, `GM_CUSTOMER_KEY`, `VITE_*_KEY`. Add `GM_JWT_SECRET`, token TTLs, lockout settings. |
| 4 | §3 diagram | Load balancer → N API replicas → Redis (online state, embeddings, hold counter) + Postgres + graph DB. Event ingestion consumer. Mock MFS core. |
| 4 | §5 tech stack | Storage row: Postgres (SQLite for local/dev). Add Redis, the graph DB, and the message bus. |
| 4 | §8 features | Online state lives in Redis. Atomic read+update semantics defined. |
| 4 | §11 policy | Hold capacity is a global shared counter. |
| 4 | §13 API | Idempotency key and fail-open/timeout semantics for `/v1/score`. Shadow mode. `/v1/graph` backed by the graph DB. |
| 4 | §21 open decisions | Close "SQLite or Postgres". |
| 5 | §15 eval | Add rows: BDT saved before cash-out, BDT escaped, delay minutes, legit BDT delayed, repeat friction, analyst load, net-benefit curve. (Doc-only, no structural change.) |
| 6 | §7 simulator | The adaptive fraudster and adversarial typology suite move from stretch to core. |
| 6 | §11 policy (conditional) | Urgency uses the predicted P(cash-out within SLA), with the fixed window as fallback. Only if Phase 6 criterion 3 passes. |
| 7 | §1 (optional) | Add citations to the problem statement. No design change. |

---

## 3. Open questions (decisions needed before or during the relevant phase)

| ID | Phase | Question | My default if you don't specify |
|---|---|---|---|
| **D1** | 1 | Accept that headline metrics will drop once the data shortcut is removed? | Yes, proceed |
| **D2** | 2 | Public demo before per-user auth: option (a) stopgap, (b) pull login forward, (c) delay URL? | (a) |
| Q1 | 2 | Hosting target: Render, Fly.io, Google Cloud Run, or Hugging Face Spaces (Docker)? | Cloud Run or Fly.io (container, free/low tier) |
| Q2 | 1 | GNN implementation: self-contained PyTorch GraphSAGE (`torch.sparse`), or PyTorch Geometric? | Self-contained (fewer install risks) |
| Q3 | 4 | Graph DB: Neo4j Community or Memgraph? | Neo4j Community |
| Q4 | 2, 5 | May we publish replay results on the organiser dataset? May we download PaySim (Kaggle account needed)? | Organiser: yes. PaySim: skip unless approved |
| Q5 | 3 | Do we need OIDC (Google/Microsoft login), or are local accounts enough? | Local accounts + optional OIDC hook |
| Q6 | 4 | Throughput target for the scale test? | 500 rps across 3 replicas on a laptop-class host |
| Q7 | 4 | Split Phase 4 into 4a/4b? | Yes, split |

---

## 4. Phase gate checklist (applied at the end of every phase)

1. All acceptance criteria for the phase are shown with commands run, report files and test output.
2. `make test` and `make lint` are green.
3. `ARCHITECTURE.md` rows for this phase (§2 above) are applied and match the code.
4. README, model card and assumptions are updated only where the phase touched them.
5. A phase report is written to `reports/phase_J<N>.md` (J = post-judging series, so it doesn't clash with the
   existing `phase_P*.md`).
6. **Stop.** Wait for "approved, proceed to next phase".
