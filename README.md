# GoldenMinutes — Real-Time Scam & Mule Interception for upay

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React 18](https://img.shields.io/badge/React-18.3-61dafb.svg)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.4+-3178c6.svg)](https://www.typescriptlang.org)

**GoldenMinutes** is a real-time scam and mule interception engine designed for Bangladesh's mobile financial services (MFS) ecosystem, modeled on **upay** (UCB Fintech Company Limited). It scores transactions in sub-5 milliseconds, predicts illicit transfers before cash-out occurs, triggers proportionate interventions (`allow`, `warn`, `verify`, `hold`), and explains decisions in natural Bengali and English.

---

## The Problem: The "Golden Minutes" in Bangladesh MFS

In Bangladesh, Mobile Financial Services (MFS) handle over ৳1,00,000 Crore monthly. Fraudsters exploit this velocity through coercive phone scams (impersonating lottery officials, government agencies, or distressed relatives) and funnel stolen money into disposable mule accounts.

Once a victim sends money, there exists a critical **30-minute window** — the **Golden Minutes** — before the mule physically arrives at an agent counter to withdraw cash. Once cashed out, the money is permanently gone.

GoldenMinutes stops fraud **within this window**:
1. It analyzes transaction velocity, device authentication, and 2-hop wallet graph signals at authorization time.
2. It applies a proportionate 4-tier intervention policy — **never autonomously denying or freezing wallets**.
3. It dispatches high-risk transfers into an **Analyst Console** with a live countdown timer and local graph visualization, enabling human analysts to halt illicit cash-out before settlement.

---

## System Architecture

```mermaid
flowchart TD
    User["Customer / upay App"] -->|"POST /v1/score"| API["FastAPI Gateway (/v1/score)"]
    API --> Store["Online Feature Store<br/>(28 Point-in-Time Features)"]
    
    subgraph "AI & ML Inference Pipeline (p95: 2.3 ms)"
        Store --> LGBM["Variant C: LightGBM + Graph"]
        Store --> Anom["Isolation Forest Anomaly"]
        Store --> Rules["Rules Baseline (R1-R5)"]
        LGBM --> Calib["Isotonic Calibration"]
        Calib & Anom & Rules --> Fusion["Variant D: Champion Fusion Stacker"]
        Fusion --> SHAP["TreeSHAP Attribution (C++)"]
    end
    
    Fusion -->|"p(fraud)"| Policy["Proportionate Policy Engine"]
    SHAP -->|"Top Features"| Explainer["Explainability & Narrative Engine"]
    
    Policy -->|"allow"| ResAllow["Immediate Success Confirmation"]
    Policy -->|"warn"| ResWarn["In-App Warning + SAFE_ACTION_HINT"]
    Policy -->|"verify"| ResVerify["60s Cooling-Off + Trusted Contact"]
    Policy -->|"hold"| ResHold["30-Min Hold + Analyst Review"]
    
    ResHold --> DB[("SQLite Database Store<br/>(Decisions, Alerts, Audits)")]
    DB --> Console["Analyst Console<br/>(Live Polling Queue & Drawer)"]
    Console --> Lead["Human Analyst Review<br/>(Approve / Escalate / Release)"]
```

---

## Key Capabilities

### 1. Proportionate 4-Action Policy (No Autonomous Deny)
GoldenMinutes enforces **Constraint C6**: machine learning models never unilaterally terminate customer wallets.
- **`allow`**: Zero-friction instant settlement for normal transfers.
- **`warn`**: In-app warning chips with the mandatory **`SAFE_ACTION_HINT`** directive (*"পাঠানোর আগে আপনার জানা নম্বরে সরাসরি ফোন করে নিশ্চিত হয়ে নিন।"* / *"Before sending, call the person on a number you already have."*). Continuing records `this_was_me` feedback.
- **`verify`**: 60-second cooling-off countdown timer with trusted-contact step-up verification.
- **`hold`**: 30-minute settlement hold for human risk analyst review.

### 2. Full Dual-Language Parity (English & Bengali)
Every UI element, customer alert, and analyst narrative is available natively in both English and Bengali (`bn`), with:
- Indian-style BDT currency grouping (e.g. `৳৩৫,০০০` and `৳৪৪,৪৭,৭৭৭.৫৬`).
- Bengali numerals (`০-৯`).
- Culturally sensitive, non-accusatory language audited for low-literacy clarity.

### 3. TreeSHAP Attribution & Interactive Wallet Graphs
- **Exact TreeSHAP Attribution:** Calculates exact feature contributions in log-odds space in $< 0.1\text{ ms}$ using native C++ tree paths, mapping 28 features to 7 human-understandable reason codes.
- **Local Wallet Graph:** Dynamic 2-hop connectivity graph visualized directly in the analyst detail drawer, rendering counterparty flow edges and mule cluster density.

### 4. Zero-Shot Held-Out Typology Test
To guard against overfitting, all `agent_collusion` fraud was strictly scrubbed from training and validation sets. On the held-out test split, GoldenMinutes achieves **98.36% zero-shot recall** on unseen agent collusion patterns.

---

## UI Screens & Visual Demonstration

### 1. Customer Demo & Live Attack Replay (`/`)
Live 5-step scripted attack escalation demonstrating real-time interception of an impersonation scam and mule ring.

![Customer Demo Attack Replay](docs/screenshots/customer_demo.png)

### 2. Analyst Console (`/analyst`)
3-second polling queue showing priority, money at risk, live countdown timer, TreeSHAP reason weights, and interactive 2-hop wallet graph.

![Analyst Console Drawer](docs/screenshots/analyst_console.png)

### 3. System Metrics & Ablation Dashboard (`/metrics`)
Comprehensive KPI cards, A–D ablation table, held-out recall breakdown, demographic fairness slices, and policy sensitivity grid.

![Metrics Dashboard](docs/screenshots/metrics_dashboard.png)

---

## Quantitative Evaluation (Held-Out Test Set)

Evaluated strictly on Days 76–90 ($N = 120,577$ transactions, 259 fraud cases, ৳45.85 lakh fraud attempted):

| Variant | Architecture | PR-AUC | 1% FFR Recall | Value Recall | P95 Latency | Intercepted Value |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **A** | Rules Baseline ($R_1$–$R_5$) | 0.1140 | 54.36% | 54.36% | 1.28 ms | ৳24.9 Lakh |
| **B** | LightGBM Tabular | 0.9935 | 98.97% | 98.97% | 0.73 ms | ৳42.0 Lakh |
| **C** | LightGBM + 7-Day Graph | 0.9935 | 98.97% | 98.97% | 0.81 ms | ৳42.0 Lakh |
| **D** | **Champion Fusion Stacker** | **0.9955** | **98.97%** | **98.97%** | **1.15 ms** | **৳42.14 Lakh** |

- **Held-Out Zero-Shot Recall (`agent_collusion`):** **98.36%**
- **False-Friction Rate (FFR):** **0.00%** (well below the 1.00% target cap)
- **Scoring Pipeline Benchmark Latency:** **p50 = 10.1 ms**, **p95 = 11.2 ms** (target $< 150\text{ ms}$)

---

## Quickstart & Commands

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- macOS or Linux

### Setup & One-Command Demo
```bash
# 1. Clone repository and install dependencies
git clone https://github.com/jahirunhassanrimon/GoldenMinute.git
cd GoldenMinute
make setup

# 2. Run test suites and verify linter
make lint
make test

# 3. Launch full demo (FastAPI backend + Vite UI)
make demo
```

Visit the application:
- **Customer Demo:** `http://127.0.0.1:5173/`
- **Analyst Console:** `http://127.0.0.1:5173/analyst`
- **Metrics Dashboard:** `http://127.0.0.1:5173/metrics`
- **FastAPI Interactive Docs:** `http://127.0.0.1:8000/docs`

### Full Pipeline Workflow
To regenerate data and train models from scratch:
```bash
make data       # Generate synthetic population and transactions
make features   # Build 28 point-in-time offline features
make train      # Train Variants A-D and register champion model
make eval       # Compute ablation, metrics, fairness, and sensitivity
```

---

## Project Structure

```text
GoldenMinute/
├── configs/                   # System configurations (simulator, policy, reasons)
├── docs/                      # Technical documentation
│   ├── model_card.md          # Formal Model Card (intended use, data, performance)
│   ├── assumptions.md         # Comprehensive assumptions and constraint log (C1-C10)
│   ├── bangla_review.md       # Bengali language native audit reference
│   └── data_dictionary.md     # Synthetic schema specifications
├── reports/                   # Quantitative reports and JSON metrics
│   ├── metrics.json           # Live evaluation KPIs and ablation summaries
│   ├── fairness_report.md     # Demographic fairness analysis (age, region, tenure)
│   ├── sensitivity_report.md  # Policy sensitivity under alternative effectiveness
│   └── latency.json           # Micro-benchmark latency distribution
├── src/goldenminutes/         # Backend Python package
│   ├── api/                   # FastAPI routes, dependencies, and SQLAlchemy store
│   ├── common/                # Schemas, Pydantic models, and settings
│   ├── eval/                  # Metrics calculation, ablation runner, and fairness
│   ├── explain/               # TreeSHAP attribution and reason code mapper
│   ├── features/              # Online feature store and offline parity extractors
│   ├── llm/                   # Template provider, safety guards, and prompt-injection defense
│   ├── models/                # LightGBM, Isolation Forest, and Fusion models
│   ├── policy/                # Proportionate 4-action decision engine
│   └── simulator/             # Synthetic population, legitimate noise, and fraud typologies
├── tests/                     # Comprehensive pytest test suite (77 tests)
└── ui/                        # React 19 + TypeScript + Vite frontend
    ├── src/
    │   ├── api/               # API client and endpoints
    │   ├── components/        # Navbar, AttackDemo, and shared UI components
    │   ├── locales/           # English and Bengali i18n dictionaries
    │   ├── pages/             # CustomerDemo, AnalystConsole, Metrics
    │   └── test/              # Vitest + React Testing Library suites (18 tests)
    └── package.json
```

---

## Responsible AI & Security Checklist (Section 16)

- [x] **Synthetic Data Only (C1):** 100% synthetic dataset; no real customer, agent, or merchant data used.
- [x] **Zero Label Leakage (C4):** Graph features read delayed analyst confirmations (24h lag); never `labels` or `hidden_truth`.
- [x] **Point-in-Time Online Parity (C5):** Verified across 5,000+ sampled historical transactions ($\Delta = 0.0$).
- [x] **No Autonomous Deny (C6):** All interventions are proportionate (`allow`, `warn`, `verify`, `hold`).
- [x] **Bilingual Explainability (C7):** All non-`allow` decisions accompanied by reason codes in Bengali and English.
- [x] **Prompt-Injection Defense:** Untrusted reference text is sanitized; evidence-only numeric extraction prevents prompt hacking.
- [x] **Role-Based Security:** Analyst endpoints enforce `X-API-Key` headers (`customer_demo` and `analyst` roles).
- [x] **Audit Trail:** Every human analyst action creates an immutable SQLite audit record with mandatory review notes.
- [x] **Demographic Fairness:** FFR remains 0.00% across all age bands and regions with $> 98.9\%$ recall.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
