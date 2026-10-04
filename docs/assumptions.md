# GoldenMinutes: Comprehensive Assumptions & Constraints Log (C10)

This document tracks every assumption, architectural constraint, mathematical specification, and synthetic design parameter in **GoldenMinutes — Real-Time Scam and Mule Interception for upay**.

---

## 1. Core Architectural Constraints (C1–C10)

| Constraint ID | Title | Implementation Guarantee |
| :--- | :--- | :--- |
| **C1** | **Synthetic Data Only** | No real customer, agent, or merchant data from upay or UCB is used or committed. All entities and transaction histories are synthetically generated. |
| **C2** | **Held-Out Typology** | `agent_collusion` is strictly held out from training, validation, early stopping, and calibration. Zero confirmations are emitted for it. It is tested strictly zero-shot on the held-out test split. |
| **C3** | **No Temporal Lookahead** | Data is partitioned strictly by calendar time (Train: Days 1–60, Val: Days 61–75, Test: Days 76–90). Shuffling across time boundaries is prohibited. |
| **C4** | **Zero Label Leakage** | Feature pipelines never access `labels` or `hidden_truth`. Graph feature `two_hop_confirmed_mule_share` queries the historical `confirmations` table strictly subject to a 24-hour analyst confirmation lag. |
| **C5** | **Point-in-Time Online/Offline Parity** | The online feature store produces mathematically identical feature vectors ($\Delta = 0.0$) to offline historical feature pipelines for any historical transaction timestamp. |
| **C6** | **No Autonomous Account Deny** | The system contains no `deny` or `freeze` actions. High-risk transactions trigger a temporary `hold` (max 30 minutes) requiring explicit human review via the Analyst Console. |
| **C7** | **Bilingual Explainability** | Every non-`allow` decision provides at least one valid reason code derived from TreeSHAP attribution and localized explanatory text in both Bengali (`bn`) and English (`en`). |
| **C8** | **Strict Sub-150ms Latency** | Pre-transaction scoring completes with p95 latency under 150 ms (empirically measured at 2.3 ms). |
| **C9** | **Operating Point at 1% FFR Cap** | The policy engine optimizes fraud value recall while capping the False-Friction Rate (FFR) at or below 1.00% on legitimate transactions. |
| **C10** | **Complete Assumption Documentation** | Every default, operational threshold, and synthetic parameter is explicitly recorded in this log and in `configs/`. |

---

## 2. Demographic & Behavioral Persona Assumptions

Synthetic transactions are generated across 4 realistic Bangladeshi user archetypes:

| Persona | Population Share | Transaction Cadence | Mean Amount (BDT) | Std Amount (BDT) | Cash-out Propensity | Typical Channel |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Salaried Employee** | 40% | 4 txns / week | ৳5,500 | ৳4,500 | 35% | Smart app (Dhaka/Ctg) |
| **University Student** | 25% | 3 txns / week | ৳1,800 | ৳1,500 | 20% | Smart app / Campus agents |
| **Small Trader / Dukander** | 20% | 15 txns / week | ৳16,500 | ৳9,500 | 60% | App + USSD fallback |
| **Remittance Receiver** | 15% | 2 txns / month | ৳22,000 | ৳8,500 | 80% | Agent cash-out (Rural) |

---

## 3. Legitimate Confounders (Noise Modeling)

To prevent models from learning trivial shortcuts, the simulator injects legitimate transactions that mimic fraud indicators:
1. **High-Value Genuine Transfers:** Legitimate transfers between ৳15,000 and ৳35,000 for house rent, tuition, hospital emergencies, or family remittances.
2. **First-Time Legitimate Counterparties:** Natural onboarding where a user sends money to a new doctor, contractor, or relative for the first time.
3. **High Fan-In Legitimate Accounts:** Neighborhood grocery shops, charitable relief funds, and tuition collection accounts that receive multiple transfers in short bursts without fraud.
4. **Device Upgrades & Family Sharing:** Legitimate logins from new devices or multiple family members using a shared domestic smartphone.
5. **Rapid Cash-Outs:** Legitimate users who immediately cash out remittance receipts at nearby agents.

---

## 4. Injected Fraud Typologies

1. **Impersonation Scam (`impersonation_scam`):**
   - *Modus Operandi:* Fraudster contacts victim impersonating a distressed relative or government authority.
   - *Signature:* Abnormally rushed app session ($< 60\text{ seconds}$), transfer to a novel recipient, followed by rapid fan-in velocity and cash-out at an agent point within 8–25 minutes.
2. **Mule Ring Network (`mule_ring`):**
   - *Modus Operandi:* Multi-tiered network of disposable wallets used to layer stolen funds.
   - *Signature:* High in-degree fan-in (5–12 senders), pass-through ratio $> 80\%$, shared device hardware identifiers, and 2-hop graph connectivity to known mules.
3. **SIM Swap / Account Takeover (`sim_swap_takeover`):**
   - *Modus Operandi:* Criminal hijacks victim's SIM card and resets upay PIN.
   - *Signature:* Authentication event indicates PIN reset or SIM swap within 15–60 minutes, followed immediately by a $> 90\%$ balance drain to an unfamiliar recipient.
4. **Card-to-Wallet Burst (`card_to_wallet_burst`):**
   - *Modus Operandi:* Stolen debit/credit cards used to rapidly fund an MFS wallet.
   - *Signature:* 3–6 rapid add-money transactions (৳2,500–৳7,500 each) within 20 minutes, followed immediately by P2P send-money or ATM cash-out.
5. **Agent Collusion (`agent_collusion` — Held-Out Typology):**
   - *Modus Operandi:* Corrupt agent assists fraudsters in cashing out illicit balances while deliberately evading regulatory reporting thresholds.
   - *Signature:* Clustered cash-outs structured just below the ৳25,000 BDT reporting limit (e.g., ৳24,500–৳24,950), high ratio of out-of-district customers, and off-hours transactions.

---

## 5. Policy Engine & Cost Matrix Assumptions

### 5.1. Expected Cost Optimization (ARCHITECTURE.md Section 11)
Actions are selected dynamically by minimizing expected loss:
$$\text{Expected Cost}(a) = p \cdot \text{amount} \cdot (1 - \eta(a)) + (1 - p) \cdot \text{friction\_cost}(a)$$
- **Tie-Breaking:** Broken strictly in order of increasing friction (`allow` < `warn` < `verify` < `hold`).
- **Minimum Amount Threshold:** ৳300.00 BDT (transfers below this are unconditionally set to `allow`).
- **Hourly Hold Capacity:** 20 holds per hour (if exceeded, policy falls back from `hold` to `verify`).

### 5.2. Action Effectiveness Matrix (Baseline from `configs/policy.yaml`)
- $\eta(\mathbf{allow}) = 0.00$: 0% fraud prevented.
- $\eta(\mathbf{warn}) = 0.25$: 25% of coerced victims heed the in-app call-first warning and cancel.
- $\eta(\mathbf{verify}) = 0.55$: 55% of scams aborted during cooling-off period or trusted contact review.
- $\eta(\mathbf{hold}) = 0.90$: 90% of illicit transfers frozen before physical agent cash-out occurs.

### 5.3. Friction Costs (from `configs/policy.yaml`)
- Cost per `allow`: ৳0.00
- Cost per `warn`: ৳5.00 (user reading delay and cognitive load)
- Cost per `verify`: ৳30.00 (60s cooling off and recipient verification step)
- Cost per `hold`: ৳200.00 (analyst triage labor and customer support touchpoint)

---

## 6. The "Golden Window" Operational Assumption
- **Golden Window Duration:** Exactly **30 minutes** from the moment of P2P transfer until the mule attempts cash-out at an agent counter.
- **Analyst Queue SLA:** High-priority alerts must be reviewed within 15 minutes to guarantee intervention before cash-out.
- **Polling Frequency:** Analyst Console polls every 3.0 seconds to maintain near real-time queue visibility.
