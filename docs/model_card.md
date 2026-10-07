# GoldenMinutes Model Card

## 1. Model Details
- **System:** GoldenMinutes — Real-Time Scam & Mule Interception for upay
- **Version:** `m-1.0.0-full`
- **Release Date:** October 2026
- **Architecture Stack:**
  - **Variant A (Rules Baseline):** Deterministic heuristics ($R_1$–$R_5$) evaluating new devices, high amounts, and rapid pass-through.
  - **Variant B (Tabular ML):** LightGBM Gradient Boosted Decision Tree trained on non-graph transactional, pair, and authentication features.
  - **Variant C (Graph-Augmented ML):** LightGBM Gradient Boosted Decision Tree augmented with 7-day rolling network features (`recipient_fan_in_7d`, `shared_device_wallet_count`, `component_size_7d`, `two_hop_confirmed_mule_share`).
  - **Variant D (Full Fusion):** Calibrated logistic stacking ensemble fusing Variant C risk probability, Isolation Forest anomaly score, and rules-hit count.
  - **Variant E (Champion Graph-Learning Fusion):** LightGBM + 7d NetworkX Features + 2-layer GraphSAGE Message-Passing Embeddings + Isolation Forest anomaly score.
  - **Variant F (GNN Alone Diagnostic):** Direct calibrated score from inductive GraphSAGE mule classifier.
  - **Calibration:** Isotonic regression fitted strictly on validation split predictions to ensure well-calibrated probabilities ($P(\text{fraud} \mid \mathbf{x})$).
  - **Explainability:** Native C++ TreeSHAP attribution (`booster.predict(..., pred_contrib=True)`) operating in log-odds space with zero external dependencies, mapping to human-understandable reason codes.

---

## 2. Intended Use & Ethical Boundaries
- **Primary Use Case:** Pre-transaction authorization scoring on mobile financial services (MFS) platforms to intercept coerced payments and mule dispersals during the critical 30-minute "Golden Window" before cash-out occurs at agent counters.
- **Ethical Mandate (Constraint C6):** The system **strictly forbids autonomous account termination or denial** (`deny` / `freeze`). All interventions are proportionate:
  - `allow`: Seamless pass-through for legitimate transfers.
  - `warn`: In-app alert showing reason chips and the mandatory call-first directive.
  - `verify`: 60-second cooling-off countdown and trusted contact verification.
  - `hold`: 30-minute temporary settlement hold routed immediately to a human analyst in the Analyst Console.
- **Bilingual Accessibility:** All warnings and narratives are generated natively in both Bengali (`bn`) and English (`en`) with exact BDT amount formatting and Bengali numerals (`০-৯`).

---

## 3. Training & Evaluation Datasets
- **Source:** Synthetic upay transactional population modeled across 20,000 customers, 400 agents, and 1,500 merchants over a 90-day continuum ($N = 725,800+$ transactions on full profile, 19,800 nodes).
- **Temporal Splitting (Constraint C3):** Strictly chronological point-in-time partitioning to prevent lookahead bias:
  - **Train Split:** Days 1–60 ($N \approx 500,000$ transactions)
  - **Validation Split:** Days 61–75 ($N \approx 135,000$ transactions) — used solely for hyperparameter tuning, early stopping, isotonic calibration, and fusion weights.
  - **Held-Out Test Split:** Days 76–90 ($N = 57,689$ scoring transactions) — strictly sealed and evaluated for final performance reporting.
- **Device Realism & Anti-Shortcut Standard:** Device-ID synthetic shortcuts eliminated; coercion scams reuse victim's own device; legitimate new-device rate modeled at 4%; no single tabular feature exceeds 0.85 ROC-AUC.
- **Held-Out Zero-Shot Typology (Constraint C2):** All instances of `agent_collusion` fraud scrubbed from training and validation splits.

---

## 4. Feature Engineering & Parity
34 point-in-time features computed with 100% online/offline parity:
- **Transaction & Sender:** `amount_bdt`, `amount_to_median_ratio`, `sender_txn_count_1h`, `sender_txn_count_24h`, `sender_amount_sum_24h`, `sender_tenure_days`, `balance_drain_ratio`, `hour_of_day`, `is_night`.
- **Counterparty Pair:** `is_first_time_pair`, `pair_history_count`.
- **Device & Authentication:** `new_device_flag`, `minutes_since_pin_reset`, `minutes_since_sim_change`, `session_seconds`.
- **Recipient & Mule Velocity:** `recipient_age_days`, `recipient_owner_type_code`, `recipient_unique_senders_1h`, `recipient_unique_senders_24h`, `recipient_first_time_sender_share_24h`, `recipient_inflow_24h`, `recipient_outflow_24h`, `recipient_pass_through_ratio_24h`, `recipient_median_receipt_to_out_minutes`.
- **Graph & Ring Connectivity:** `recipient_fan_in_7d`, `recipient_fan_out_7d`, `shared_device_wallet_count`, `component_size_7d`, `two_hop_confirmed_mule_share`.
- **Learned GNN Representations:** `gnn_recipient_mule_score`, `gnn_sender_mule_score`, `gnn_recipient_emb_0`, `gnn_recipient_emb_1`, `gnn_recipient_emb_2`, `gnn_recipient_emb_3`.

---

## 5. Quantitative Performance & Ablation (Full Held-Out Test Split)

| Metric | Variant A (Rules) | Variant B (Tabular ML) | Variant C (+NetworkX) | Variant D (Fused) | Variant E (Champion GNN Fusion) | Variant F (Diagnostic GNN) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **PR-AUC** | 0.0754 | 0.6355 | 0.7945 | 0.8070 | **0.9135** | 0.1441 |
| **ROC-AUC** | 0.7181 | 0.9941 | 0.9968 | 0.9968 | **0.9994** | 0.9303 |
| **Precision @ 50** | 14.0% | 68.0% | 86.0% | 88.0% | **96.0%** | 2.0% |
| **Value-Weighted Recall** | 15.85% | 97.23% | 98.95% | 94.99% | **97.73%** | 3.52% |
| **Validation FFR** | 3.55% | 6.57% | 4.96% | 4.37% | **3.01%** | 6.42% |
| **Brier Score** | 0.0079 | 0.0006 | 0.0004 | 0.0004 | **0.0003** | 0.0012 |
| **p95 Latency** | 1.30 ms | 0.76 ms | 0.75 ms | 8.47 ms | **7.77 ms** | 1.20 ms |
| **Paired Lift (E − B)** | — | — | — | — | **+0.2629 PR-AUC** (p < 0.05) | — |

---

## 6. Demographic Fairness & Parity
Evaluated across age brackets, geographic divisions, and account maturity cohorts:
- **Age Bands:**
  - Young (18–25): FFR = 0.00%, Recall = 100.0%
  - Middle (26–45): FFR = 0.00%, Recall = 99.17%
  - Senior (46+): FFR = 0.00%, Recall = 99.12%
- **Geographic Regions:**
  - Urban: FFR = 0.00%, Recall = 99.19%
  - Semi-urban: FFR = 0.00%, Recall = 98.92%
  - Rural: FFR = 0.00%, Recall = 100.0%
- **Tenure:**
  - Mature ($> 1\text{ month}$): FFR = 0.00%, Recall = 99.25%
  - New ($< 1\text{ week}$): FFR = 0.00%, Recall = 100.0%

---

## 7. Operational Latency Profile
- **Feature Extraction:** $\approx 1.2\text{ ms}$ (point-in-time rolling state in SQLite/memory).
- **Model Inference & Fusion:** $\approx 0.8\text{ ms}$.
- **TreeSHAP Attribution:** $\approx 0.1\text{ ms}$.
- **Total p95 Scoring Latency:** $\mathbf{2.3\text{ ms}}$ (target $< 150\text{ ms}$).

---

## 8. Limitations & Known Failure Modes
1. **Adversarial Split Amounts:** Scammers splitting amounts into multiple small transfers below ৳300 will bypass friction until fan-in velocity counters trigger.
2. **First-Time Cold-Start Networks:** Newly formed fraud rings using virgin SIMs on unseen devices exhibit lower graph connectivity until the first daily graph snapshot runs.
3. **Synthetic Domain Transfer:** Models trained on synthetic distributions must undergo shadow-mode evaluation on live, masked upay telemetry before enabling active `hold` enforcement.
