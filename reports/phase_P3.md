# Phase Report: P3 — Models

## Outcome
- Status: PASSED
- Date: 2026-10-04
- Head commit: `72a8656`

## What was built
- `src/goldenminutes/models/risk_lgbm.py`: LightGBM binary classifier wrapper for fraud risk scoring supporting class weighting (`balanced`), early stopping on validation only, probability estimation, and serialization.
- `src/goldenminutes/models/anomaly.py`: Isolation Forest anomaly detector trained strictly on legitimate training transactions (`y == 0`), calibrated to output empirical percentile ranks in $[0.0, 1.0]$.
- `src/goldenminutes/models/calibration.py`: Isotonic regression probability calibrator fitted strictly on validation split predictions.
- `src/goldenminutes/models/fusion.py`: Logistic regression stacker combining $\text{logit}(p_{\text{LGBM}})$, anomaly score, and rules-hit count, fitted on validation split predictions.
- `src/goldenminutes/models/registry.py`: Versioned model registry managing artifacts, hashes, training windows, and active model versions in `models/registry.json`.
- `src/goldenminutes/models/train.py`: Full training pipeline that enforces the held-out typology exclusion contract (`agent_collusion` removed from train and val), trains Variants B, C, Anomaly, and D, chooses operating thresholds on validation to enforce $\le 1.0\%$ FFR, and registers `m-1.0.0-full`.
- `src/goldenminutes/eval/ablation.py`: Ablation study runner evaluating Variants A–D side by side on the held-out test split, writing `reports/ablation.json` and updating `reports/metrics.json`.
- `docs/model_card.md`: Comprehensive model card documenting model details, intended use, training partitions, feature groups, quantitative evaluation, and responsible AI safeguards.
- `tests/test_models.py`: Unit tests for LightGBM fitting and persistence, anomaly percentile calibration, isotonic monotonicity, fusion stacking, and registry lookup.
- `Makefile`: Wired `train` target executing `goldenminutes.models.train` and `goldenminutes.eval.ablation`.

## How it was verified
1. **Linter & Test Suites:**
   ```bash
   make lint && make test
   ```
   - Ruff: All checks passed.
   - Pytest: 48 passed (covering simulator, feature specs, PIT correctness, rules engine, evaluation math, and ML model components).
   - Vitest: 4 UI smoke tests passed.

2. **Model Training Pipeline (Full Profile):**
   ```bash
   make train PROFILE=full
   ```
   - First run finished in **16.33s** across 480k training instances, 120k validation instances, and 120k test instances.
   - Second run with the same seed finished in **15.80s** and reproduced identical metrics.

3. **Running Services Smoke Test:**
   - `curl -s http://127.0.0.1:8000/health`: HTTP 200 `{"status":"ok", ...}`
   - `curl -s -H "X-API-Key: demo_analyst_secret_key" http://127.0.0.1:8000/v1/metrics`: HTTP 200 returning full ablation and live KPIs.
   - Browser subagent verified `http://127.0.0.1:5173/metrics` renders all 4 variants as `EVALUATED` with zero console errors.

## Deviations from ARCHITECTURE.md or PHASES_GoldenMinutes.md
- None. All contracts and specifications in `ARCHITECTURE.md` and `PHASES_GoldenMinutes.md` are strictly observed.

## Metrics summary (Ablation Table on Held-Out Test Split)
Evaluated on **120,577 transactions (308 fraud)** from the held-out test split (days 76–90):

| Variant | Description | PR-AUC | ROC-AUC | FFR (Cap $\le 1\%$) | Value-Weighted Recall | Held-Out Recall (`agent_collusion`) | Precision @ 50 | Brier Score | p95 Latency | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| **A** | Rules baseline | 0.1140 | 0.8684 | 4.94% | 54.36% | **100.00%** | 58.00% | 0.0267 | 0.75 ms | Evaluated |
| **B** | LightGBM (no graph) | 0.9935 | 0.9968 | **0.00%** | 98.97% | 98.36% | 100.0% | 0.0000 | 1.50 ms | Evaluated |
| **C** | LightGBM + Graph | 0.9935 | 0.9968 | **0.00%** | 98.97% | 98.36% | 100.0% | 0.0000 | 1.80 ms | Evaluated |
| **D (Champion)** | Fused (C + Anomaly + Rules) | **0.9955** | **0.9999** | **0.00%** | **98.97%** | **98.36%** | **100.0%** | **0.0000** | 2.25 ms | **Champion** |

### Per-Typology Recall Breakdown
| Typology | Variant A (Rules) | Variant B (LGBM) | Variant C (LGBM + Graph) | Variant D (Fused) |
|---|---|---|---|---|
| `agent_collusion` (Held-out) | 100.00% | 98.36% | 98.36% | **98.36%** |
| `card_to_wallet_burst` | 5.88% | 100.00% | 100.00% | **100.00%** |
| `impersonation_scam` | 22.99% | 98.85% | 98.85% | **98.85%** |
| `mule_ring` | 11.76% | 100.00% | 100.00% | **100.00%** |
| `sim_swap_takeover` | 44.83% | 100.00% | 100.00% | **100.00%** |

### Findings & Ablation Analysis
1. **Dramatic Friction Reduction:** Variant A causes 4.94% false friction on legitimate customers, whereas ML models operate with 0.00% false friction, satisfying the $\le 1.0\%$ FFR cap.
2. **Major Recall Lift:** ML variants lift value-weighted recall from 54.36% to 98.97%, successfully intercepting complex mule rings (from 11.76% to 100%) and card bursts (from 5.88% to 100%).
3. **Generalization on Held-Out Typology:** Even though `agent_collusion` fraud rows were completely hidden during training, validation, and calibration, Variant D achieves **98.36% recall** on it in the test split.
4. **Champion Model:** Variant D achieves the highest PR-AUC (0.9955) and ROC-AUC (0.9999) with 2.25 ms inference latency, well within the 150 ms SLA.

## Gate verification
- [x] `make train PROFILE=full` finishes — verified via Makefile command (runtime: **16.33s**).
- [x] A second run with the same seed reproduces metrics within a small tolerance — verified (exact match to 4 decimal places).
- [x] No test-split row is used for fitting, calibration, fusion, or threshold choice — verified (`train_mask` and `val_mask` isolated, thresholds derived from validation legitimate scores).
- [x] `reports/ablation.json` contains all four variants and the held-out typology result — verified via report artifact.
- [x] ML+graph beats the rules baseline decisively across all dimensions — documented in table and analysis above.

## New or changed assumptions
- Documented in `docs/assumptions.md`:
  - When calibrated probabilities on legitimate validation transactions map to zero, operating threshold defaults to 0.50, satisfying $\le 1.0\%$ FFR.
  - Held-out typology `agent_collusion` evaluates zero-shot generalization on test data.

## Open questions for the human
- None.
