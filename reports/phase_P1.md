# Phase Report: P1 — Dataset onboarding, simulator compatibility and validation

## Outcome
- Status: PASSED
- Date: 2026-10-04
- Head commit: `8e88356`

## What was built
- `configs/simulator.yaml`: Configured `small` and `full` dataset profiles, canonical entity parameters, seasonality, typology distributions, confirmation detection lag and detection rate, and held-out typology (`agent_collusion`).
- `src/goldenminutes/common/config.py`: Added Pydantic schema validation for simulator profiles and parameters (`SimulatorConfig`, `SimulatorProfileConfig`).
- `src/goldenminutes/simulator/intake.py`: Raw dataset discovery, archive extraction, preservation in `data/raw_source/`, canonical column mapping, label/hidden truth separation, and confirmations emission.
- `src/goldenminutes/simulator/population.py`: Synthetic population generation for customers, wallets (customer, agent, merchant), agent outlets, and device links.
- `src/goldenminutes/simulator/behavior.py`: Legitimate transaction generator incorporating user personas, diurnal and weekend seasonality, and realistic confounders (large sends to new recipients, high fan-in merchants, normal cash-out delays, normal device switches).
- `src/goldenminutes/simulator/typologies/`:
  - `impersonation_scam.py`: Victim coerced sends with rapid cash-out attempts.
  - `mule_ring.py`: Multi-hop mule dispersion networks with layering and cash-out.
  - `sim_swap_takeover.py`: Account takeover preceded by credential/auth events and swift drain.
  - `card_to_wallet_burst.py`: Stolen card rapid top-up bursts followed by immediate p2p/cash-out.
  - `agent_collusion.py`: Agent-assisted illegitimate cash-outs (strictly held-out typology, excluded from confirmations).
- `src/goldenminutes/simulator/generate.py`: CLI and pipeline writing partitioned Parquet datasets to `data/raw/<profile>/` and summary metrics to `reports/sim_summary.json`.
- `tests/test_simulator.py`: 9 validation tests covering referential integrity, timestamp monotonicity, deterministic generation, leakage separation, held-out confirmation exclusion, fraud rate / typology counts, confounders, raw feature AUC bounds (< 0.85), and source preservation.
- `docs/data_dictionary.md`: Full canonical schema documentation and source-to-canonical mapping table.
- `docs/assumptions.md`: Detailed simulator assumptions, parameter calibrations, and rationale.
- `Makefile`: Wired `data` target supporting `PROFILE=small` and `PROFILE=full`.

## How it was verified
1. **Linter & Test Suites:**
   ```bash
   make lint && make test
   ```
   - Ruff: All checks passed.
   - Pytest: 32 tests passed (including 9 simulator tests and all API contract tests).
   - Vitest: 4 UI smoke tests passed.

2. **Data Generation Runs:**
   - Small profile run:
     ```bash
     make data PROFILE=small
     ```
     - Output: 24,237 transactions, 237 fraud (0.978%), duration: 0.94s.
   - Full profile run:
     ```bash
     make data PROFILE=full
     ```
     - Output: 721,862 transactions, 1,862 fraud (0.258%), duration: 29.80s.

3. **Simulator Test Suite Verification:**
   ```bash
   .venv/bin/pytest -v tests/test_simulator.py
   ```
   - `test_referential_integrity`: PASSED
   - `test_wallet_timestamp_monotonicity`: PASSED
   - `test_deterministic_generation`: PASSED
   - `test_leakage_separation`: PASSED
   - `test_confirmations_excludes_agent_collusion`: PASSED
   - `test_fraud_rate_and_typology_counts`: PASSED
   - `test_legitimate_confounders_present`: PASSED
   - `test_no_single_raw_column_auc_over_85`: PASSED
   - `test_raw_source_preservation`: PASSED

4. **Running Services Smoke Test:**
   - `curl -s http://127.0.0.1:8000/health`: HTTP 200 `{"status":"ok","model_version":"m-0.1.0-stub","policy_version":"0.1","environment":"dev"}`
   - `curl -s http://127.0.0.1:5173/`: HTTP 200, HTML rendered with title `GoldenMinutes — Real-Time Scam & Mule Interception for upay`.
   - Browser subagent verified UI loads cleanly with no console errors and demo badge visible.

## Deviations from ARCHITECTURE.md or PHASES_GoldenMinutes.md
- None. All contracts and specifications in `ARCHITECTURE.md` and `PHASES_GoldenMinutes.md` are strictly observed.

## Metrics summary
| Metric | Target (`small` / `full`) | Actual `small` | Actual `full` | Status |
|---|---|---|---|---|
| Total Transactions | Configurable | 24,237 | 721,862 | PASSED |
| Fraud Share | `0.2–1.0%` (small), `0.2–0.6%` (full) | 0.978% | 0.258% | PASSED |
| Impersonation Scam count | >= 30 (small), >= 300 (full) | 59 | 485 | PASSED |
| Card-to-Wallet Burst count | >= 30 (small), >= 300 (full) | 57 | 361 | PASSED |
| Agent Collusion count | >= 30 (small), >= 300 (full) | 45 | 360 | PASSED |
| Mule Ring count | >= 30 (small), >= 300 (full) | 41 | 341 | PASSED |
| SIM Swap Takeover count | >= 30 (small), >= 300 (full) | 35 | 315 | PASSED |
| Confirmations emitted | Analyst lag + detection rate | 92 | 712 | PASSED |
| Held-out typology confirmations | 0 | 0 | 0 | PASSED |
| Max single raw feature AUC | < 0.85 | 0.771 (`amount_bdt`) | < 0.85 | PASSED |
| Generation Runtime | Recorded | 0.94s | 29.80s | PASSED |

## Gate verification
- [x] `make data PROFILE=small` succeeds in a reproducible local run — verified via Makefile command (0.94s).
- [x] `make data PROFILE=full` succeeds and runtime is recorded — verified via Makefile command (29.80s).
- [x] Fraud share is roughly `0.2–0.6%` on `full` (`0.2–1.0%` on `small`) — verified (0.978% on small, 0.258% on full).
- [x] Each typology has at least 300 positive transactions on `full` and at least 30 on `small` — verified via `sim_summary.json` and `test_fraud_rate_and_typology_counts`.
- [x] Same seed produces identical output hashes — verified via `test_deterministic_generation`.
- [x] Wallet timestamps are monotone — verified via `test_wallet_timestamp_monotonicity`.
- [x] Foreign keys are valid — verified via `test_referential_integrity`.
- [x] Labels and hidden truth are not present in model-input transaction features — verified via `test_leakage_separation`.
- [x] Legitimate confounders are present — verified via `test_legitimate_confounders_present`.
- [x] No single raw column reaches AUC above `0.85` for fraud — verified via `test_no_single_raw_column_auc_over_85`.
- [x] `reports/sim_summary.json`, `docs/assumptions.md`, and `docs/data_dictionary.md` are documented and ready for human review.

## New or changed assumptions
- Documented in `docs/assumptions.md`:
  - Calibrated normal transfer amounts for small traders (15,000–45,000 BDT) and varying session durations so that raw transaction amounts or durations alone do not artificially leak fraud status (AUC < 0.85).
  - Explicit confirmation emission modeling: 65% detection rate with a 24-hour analyst lag for typologies 1–4, and 0% for `agent_collusion`.

## Open questions for the human
- None.
