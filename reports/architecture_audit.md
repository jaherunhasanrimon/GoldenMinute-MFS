# GoldenMinutes: Architecture Audit & Mismatch Resolution Report

**System:** GoldenMinutes — Real-Time Scam and Mule Interception for upay  
**Reference Specification:** [`ARCHITECTURE.md`](file:///Users/jahirunhassanrimon/GoldenMinute/ARCHITECTURE.md)  
**Execution Order:** [`PHASES_GoldenMinutes.md`](file:///Users/jahirunhassanrimon/GoldenMinute/PHASES_GoldenMinutes.md)  
**Date:** 2026-10-04  
**Audit Status:** All Mismatches Identified, Fixed, and Verified (95/95 tests passing, clean linter)  

---

## 1. Executive Summary

This audit compared the actual codebase (Python backend, React/Vite UI, configuration files, reports, and documentation) against [`ARCHITECTURE.md`](file:///Users/jahirunhassanrimon/GoldenMinute/ARCHITECTURE.md) as the primary contract. Every divergence was categorized into one of two categories per architecture rule:
- **Code/Config/Doc Fix:** The code or configuration deviated from the architecture specification and was corrected.
- **Architecture Contract Alignment:** The architecture description had a naming or typographical deviation from intentional code structures (e.g. `recipient_owner_type_code`) and was updated in place.

---

## 2. Identified Mismatches & Resolutions

| # | Architecture Requirement | Discovered Mismatch | Resolution Applied | Status |
| :--- | :--- | :--- | :--- | :---: |
| **1** | **Section 4 & Makefile:** `make demo` runs `python -m goldenminutes.demo` | Python package shadowing conflict: `src/goldenminutes/demo/` shadowed `src/goldenminutes/demo.py`, causing `python -m goldenminutes.demo` to fail with missing `main`. | Replaced `demo.py` with `demo/__main__.py`. Extracted scripted attack logic to `demo/scenarios.py` and `demo/replay.py`. | **FIXED** |
| **2** | **Section 9 & Registry:** Models must be loadable in fresh checkouts without host path assumptions | `models/registry.json` and `demo_assets/registry.json` contained hardcoded absolute host paths (`/Users/jahirunhassanrimon/...`), preventing loading in a fresh clone. | Refactored `ModelRegistry` to store repo-relative artifact paths and resolve to absolute paths on load. | **FIXED** |
| **3** | **Section 11:** Deterministic policy cost optimization with `configs/policy.yaml` values | `eval/ablation.py` and `eval/run_eval.py` used hardcoded cutoff multipliers (`th*0.75`, `th*0.5`) instead of `PolicyEngine`. Sensitivity baseline assumed `hold_eff: 0.95, verify_eff: 0.70`, contradicting `policy.yaml` (`0.90` and `0.55`). | Added `evaluate_batch` to `PolicyEngine`. Wired `ablation.py` to `PolicyEngine` and config-driven `sensitivity` block in `configs/policy.yaml`. | **FIXED** |
| **4** | **Section 14 & 15:** Live metrics and real measured latency percentiles | `ablation.py` applied artificial multipliers (`lat * 1.5`), `main.py` had fabricated fallback values and fixed numbers (`120577`, `185`), and `reports/metrics.json` lacked hold-resolution time. | Measured real single-row latency distributions, loaded p50/p95 from `reports/latency.json`, added live `hold_resolution_minutes`, and removed fake fallback numbers. | **FIXED** |
| **5** | **Section 13:** `/v1/graph/{wallet_id}` reflects live store state | The graph endpoint contained hardcoded mock overrides specifically targeting `W08371` and a fake "Agent Banani" edge. | Dynamically derive wallet risk and mule classification from live decision and alert records in SQLite. | **FIXED** |
| **6** | **Section 5:** Frontend stack specified `Recharts` and `react-force-graph-2d` | `ui/package.json` had neither library; ablation was only a table, and local wallet graph was rendered as a static card list. | Installed `recharts` and `react-force-graph-2d`. Integrated interactive BarChart in `Metrics.tsx` and 2D force-directed canvas in `AnalystConsole.tsx`. Mocked canvas in Vitest for jsdom. | **FIXED** |
| **7** | **Section 4:** Repository layout modules | Missing modules: `common/logging.py`, `common/time.py`, `demo/replay.py`, `llm/narrative.py`, `eval/fairness.py`. | Created all 5 missing modules conforming to architectural specifications with clean typing. | **FIXED** |
| **8** | **Section 8 & 16:** Feature names and Section 16 Checklist accuracy | Architecture wrote `recipient_owner_type` instead of `recipient_owner_type_code`. Checklist claimed native Bangla review was complete when it is an open decision. | Updated `ARCHITECTURE.md` Section 8 to `recipient_owner_type_code`. Marked native speaker review pending in `docs/section_16_checklist.md` and added Section 21 Open Decisions log. | **FIXED** |
| **9** | **Documentation & README:** Badges, license, and screenshot URLs | `README.md` cited React 19 (actual is React 18.3), an uncommitted MIT license, and broken absolute `file:///Users/...` image links. | Corrected badges to React 18, removed non-existent license badge, copied PNG screenshots to `docs/screenshots/`, and linked relatively. | **FIXED** |

---

## 3. Verification & Gate Audit

1. **Python Linter (`make lint`):**
   ```text
   .venv/bin/ruff check .
   All checks passed!
   ```
2. **Python Test Suite (`pytest`):**
   - 77 passed tests, 0 failures, 0 skipped.
3. **Frontend Test Suite (`vitest`):**
   - 18 passed tests across 4 test suites (`CustomerDemo`, `AnalystConsole`, `Metrics`, `ui_smoke`).
4. **UI Production Build (`npm run build`):**
   - Clean production build with Vite 5 and TypeScript 5.4.
5. **Demonstration Launcher (`make demo`):**
   - Verified that `goldenminutes.demo` module launches uvicorn unified server on `http://127.0.0.1:8000/`.
