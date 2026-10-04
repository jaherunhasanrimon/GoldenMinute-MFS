# Policy Engine Sensitivity and Economic Impact Report

**System:** GoldenMinutes — Real-Time Scam and Mule Interception for upay  
**Document:** `reports/sensitivity_report.md`  
**Dataset:** Held-out Test Split ($N = 120,577$ transactions, 308 fraud cases)  
**Policy Version:** 0.1  
**Date:** 2026-10-04  

---

## 1. Executive Summary

A real-world anti-scam intervention policy operates under uncertainty regarding human behavior:
- How often does a customer heed an in-app warning (`warn`)?
- What proportion of coerced victims cancel a payment during cooling-off verification (`verify`)?
- What proportion of cash-outs are prevented when an analyst places a temporary hold (`hold`)?

This sensitivity analysis evaluates GoldenMinutes across three scenarios: conservative, baseline (from `configs/policy.yaml`), and optimistic.

---

## 2. Effectiveness & Friction Matrix (from configs/policy.yaml)

| Action | Baseline Effectiveness | Baseline Friction Cost (BDT) | Description |
| :--- | :---: | :---: | :--- |
| **`allow`** | 0.00 (0%) | ৳0.00 | Pass-through with zero friction |
| **`warn`** | 0.25 (25%) | ৳5.00 | In-app warning with call-first directive |
| **`verify`** | 0.55 (55%) | ৳30.00 | Cooling-off timer and trusted-contact step |
| **`hold`** | 0.90 (90%) | ৳200.00 | 30-minute analyst review golden window |

---

## 3. Financial Interception Results

| Scenario | Hold Eff | Verify Eff | Total Intercepted BDT |
| :--- | :---: | :---: | :---: |
| **Conservative** | 0.75 | 0.40 | **৳3,511,403.34** |
| **Baseline** | 0.90 | 0.55 | **৳4,213,684.01** |
| **Optimistic** | 0.98 | 0.70 | **৳4,588,233.70** |

---

## 4. Operational Recommendations for upay
1. **Deploy Baseline Thresholds:** Maintain baseline effectiveness targets from `configs/policy.yaml`.
2. **Golden Window SLA:** Ensure analyst queue review latency $< 15\text{ minutes}$ (within the 30-minute cash-out deadline).
