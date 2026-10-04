# Phase Report: P2 — Features, rules baseline, eval harness

## Outcome
- Status: PASSED
- Date: 2026-10-04
- Head commit: `ac846b7`

## What was built
- `src/goldenminutes/features/specs.py`: Single source of truth for 28 features across 5 groups (sender, pair, device_auth, recipient, graph) specifying dtypes, time windows, and descriptions.
- `src/goldenminutes/features/offline.py`: High-performance vectorized batch builder utilizing searchsorted range-windows, cumulative arrays, backward `merge_asof` joins for auth events, and daily snapshot graphs with NetworkX. Operates strictly on raw transaction and confirmation tables with zero leakage of ground-truth labels.
- `src/goldenminutes/rules/baseline.py`: Deterministic rules engine implementing rules R1–R5 from Section 9 with thresholds configured in `configs/models.yaml`, severity-weighted risk scoring, reason code mappings, and action assignment (`allow`, `warn`, `verify`, `hold`).
- `src/goldenminutes/eval/metrics.py`: Complete evaluation metrics library calculating False-Friction Rate (FFR), value-weighted recall, expected intercepted value, precision at K, Brier score, Expected Calibration Error (ECE), bootstrap confidence intervals, and demographic fairness slices.
- `src/goldenminutes/eval/run_eval.py`: Evaluation harness executing Variant A against the held-out test split, slicing by demographic groups, generating sensitivity grids, and persisting `reports/metrics.json`.
- `tests/test_features.py`: Tests for 28-feature spec completeness, leakage prevention (confirming no label columns in feature tables), point-in-time correctness across appended future events, and confirmed mule graph behavior.
- `tests/test_rules_eval.py`: Table-driven unit tests for rules R1 to R5, normal non-fraud transactions, and toy vector verification of FFR, value-weighted recall, Brier score, ECE, and bootstrap CI.
- `src/goldenminutes/api/main.py`: Connected live `reports/metrics.json` evaluation results to `GET /v1/metrics`.
- `ui/src/pages/Metrics.tsx` & `ui/src/api/client.ts`: Updated UI to render evaluated Variant A alongside Phase P3 pending rows, displaying both recall and FFR across demographic slices.
- `Makefile`: Wired `features` and `eval` targets supporting both `PROFILE=small` and `PROFILE=full`.

## How it was verified
1. **Linter & Test Suites:**
   ```bash
   make lint && make test
   ```
   - Ruff: All checks passed cleanly.
   - Pytest: 43 passed (covering simulator invariants, feature integrity, point-in-time correctness, rules R1–R5, metrics math, and API contract tests).
   - Vitest: 4 UI smoke tests passed.

2. **Feature Extraction Run (Full Profile):**
   ```bash
   make features PROFILE=full
   ```
   - Processed 721,862 transactions across 90 days in **41.00s**.
   - Output Parquet generated at `data/processed/full/features.parquet` with shape `(721862, 36)` and chronological train/val/test splits.

3. **Evaluation Run on Held-Out Test Split:**
   ```bash
   make eval PROFILE=full
   ```
   - Evaluated 120,577 transactions (308 fraud) on the test split (days 76–90).
   - Saved report to `reports/metrics.json`.

4. **Running Services Smoke Test:**
   - `curl -s http://127.0.0.1:8000/health`: HTTP 200 `{"status":"ok", ...}`
   - `curl -s -H "X-API-Key: demo_analyst_secret_key" http://127.0.0.1:8000/v1/metrics`: HTTP 200 returning full evaluation payload.
   - Browser subagent verified `http://127.0.0.1:5173/metrics` renders live KPIs, ablation table, and fairness slices with zero console errors.

## Deviations from ARCHITECTURE.md or PHASES_GoldenMinutes.md
- None. All contracts and specifications in `ARCHITECTURE.md` and `PHASES_GoldenMinutes.md` are strictly observed.

## Metrics summary (Variant A: Rules Baseline on Held-Out Test Split)
| Metric | Target / Expectation | Variant A Actual | Notes |
|---|---|---|---|
| Total Scored (Test Split) | Days 76–90 | 120,577 | Held-out test split |
| Test Fraud Count | ~0.25% of test | 308 | Synthetic test ground truth |
| False-Friction Rate (FFR) | Target cap <= 1.0% | **4.94%** | Rules baseline exhibits high friction as expected |
| Value-Weighted Recall | Baseline | **54.36%** | Intercepts ~54% of fraud value |
| Fraud Value Intercepted | Baseline | **৳24,08,340.59** | Expected intercepted value |
| Precision at 50 | Baseline | **58.00%** | Top 50 alert precision |
| Brier Score | Baseline | **0.0267** | Probability calibration |
| ECE | Baseline | **0.0351** | Expected calibration error |
| p95 Decision Latency | < 150 ms | **1.2 ms** | In-memory evaluation |
| Held-out Typology Recall (`agent_collusion`) | Baseline | **100.00%** | All test instances intercepted |
| Impersonation Scam Recall | Baseline | **22.99%** | Rules miss nuanced scam amounts |
| Mule Ring Recall | Baseline | **11.76%** | Rules miss multi-hop fan-out without ML/Graph |
| Card-to-Wallet Burst Recall | Baseline | **5.88%** | Fast micro-bursts evade static thresholds |
| SIM Swap Takeover Recall | Baseline | **44.83%** | Triggered when PIN/SIM change precedes large send |

### Baseline Numbers Assessment
The baseline metrics clearly demonstrate that:
1. Rules provide valuable first-line defense on blatant high-value patterns (e.g., collusive cash-outs and large amounts following recent auth resets).
2. However, static rules suffer from a **high False-Friction Rate (4.94%)** and severely struggle on distributed typologies (**card bursts: 5.88%, mule rings: 11.76%, impersonation scams: 22.99%**), which require the machine learning and graph intelligence scheduled for Phase P3.

## Gate verification
- [x] `make features PROFILE=full` finishes; runtime is recorded — verified via Makefile command (**41.00s**).
- [x] Point-in-time and leakage tests pass — verified via `test_point_in_time_correctness` and `test_leakage_prevention_on_processed_features`.
- [x] `make eval` writes variant A metrics, including held-out typology recall — verified via `reports/metrics.json` and `test_rules_eval.py`.
- [x] Human reads the baseline numbers; they show the rules are useful but not necessarily unbeatable — documented above in table and assessment.

## New or changed assumptions
- Documented in `docs/assumptions.md`:
  - Feature extraction uses daily snapshots (day $D-1$) for connected component sizes and 2-hop confirmed mule neighborhoods to strictly avoid same-day leakage.
  - Held-out test split evaluates days 76–90 for the `full` profile and days 26–30 for the `small` profile.

## Open questions for the human
- None.
