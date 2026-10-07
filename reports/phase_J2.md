# Phase J2 Report: Prototype Quality & Out-of-Distribution Validation

## Overview
Phase J2 addresses Judge Weaknesses 1 & 2 under Prototype Quality:
1. **Model Loading & Checksum Integrity:** Eliminates silent rules fallbacks, enforces strict SHA-256 checksums, supports graceful degraded mode in dev, and fails loudly in `GM_ENV=prod`.
2. **Public Demo Security (Decision D2 Option a):** Eliminates analyst secrets from public client distribution bundles (`ui/dist`), introduces a sandboxed `public_demo` role with constant-time key comparison, and surfaces a visible Degraded Alert banner in the UI.
3. **Deployment & CI:** Adds a multi-stage production `Dockerfile`, `docker-compose.yml`, `.dockerignore`, and GitHub Actions workflow (`.github/workflows/ci.yml`).
4. **Replay Validation on Independent Organiser Dataset:** Implements `demo/replay_dataset.py` streaming 100,000 transactions through `/v1/score` with point-in-time online feature updates, generating `reports/replay_organiser.json` and `reports/replay_organiser.md`.

---

## 1. Acceptance Criteria Verification

| Criterion | Target | Result | Status |
| :--- | :--- | :--- | :---: |
| **Model Verification & Resolution** | Checksum verification on all model artifacts; cascade resolution (env $\to$ active $\to$ fallback demo assets) | `verify_artifacts()` validates SHA-256; tested in `tests/test_model_loading.py` (5/5 tests passed) | **PASS** |
| **Fail Loud in Production** | `GM_ENV=prod` refuses to boot in degraded mode | Tested and verified in unit tests | **PASS** |
| **Zero Secrets in Client Bundle** | `ui/dist` contains zero analyst keys or environment secrets | Scanned: `grep -rn "demo_analyst_secret_key" ui/dist` returns 0 matches | **PASS** |
| **Degraded State UI Banner** | Dynamic banner displayed when `/health` reports `degraded=true` | Implemented in `Navbar.tsx` with English and Bangla translations | **PASS** |
| **Independent Dataset Replay** | Stream $\ge$100,000 transactions from `goldentimes_synthetic_dataset/transactions.csv` | 100,000 transactions replayed with 0 errors; 82.19% recall, 93.82% value recall, p50 latency 10.40 ms | **PASS** |
| **Regression Suite** | All tests and lint pass | `make lint` and `make test` (pytest + 18 Vitest tests) 100% green | **PASS** |

---

## 2. Replay Performance Summary (Organiser Dataset)
- **Dataset:** `goldentimes_synthetic_dataset/transactions.csv`
- **Scale:** 100,000 transactions
- **Throughput:** 74.6 txns/sec
- **Overall Recall:** 82.19%
- **Value Recall:** 93.82% (৳15,032,030.18 intercepted of ৳16,021,441.53 fraud value)
- **False Friction Rate (FFR):** 12.48%
- **Latency:** Mean 13.32 ms, p50 10.40 ms, p95 22.17 ms, p99 25.71 ms (all well within < 150 ms budget)
- **Per-Scenario Interception Recall:**
  - `mule_account`: 77.41%
  - `mule_ring`: 74.62%
  - `relative_emergency_scam`: 92.51%
  - `agent_collusion`: 79.51%
  - `account_takeover`: 90.60%

---

## 3. Artifacts & Deliverables
- `Dockerfile` & `docker-compose.yml`
- `.github/workflows/ci.yml`
- `src/goldenminutes/models/registry.py` & `models/registry.json`
- `src/goldenminutes/api/deps.py` & `src/goldenminutes/api/service.py`
- `src/goldenminutes/demo/replay_dataset.py` & `Makefile`
- `reports/replay_organiser.json` & `reports/replay_organiser.md`
- `tests/test_model_loading.py` & `tests/test_replay.py`
