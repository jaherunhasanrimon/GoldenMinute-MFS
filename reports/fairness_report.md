# Demographic Fairness and Equity Analysis Report

**System:** GoldenMinutes — Real-Time Scam and Mule Interception for upay  
**Document:** `reports/fairness_report.md`  
**Evaluation Split:** Held-out Test Set ($N = 120,577$ transactions, 308 fraud cases)  
**Champion Model:** Variant D (Fused LightGBM + Isolation Forest + Graph Features)  
**Date:** 2026-10-03T19:42:24.150665+00:00  

---

## 1. Executive Summary & Purpose

Mobile Financial Services (MFS) in Bangladesh serve as vital financial infrastructure for over 100 million citizens, including unbanked rural populations, daily wage earners, female entrepreneurs, and the elderly. Algorithmic fraud interception systems must not introduce disparate burden, discriminatory friction, or exclusion based on age, geographical domicile, or account maturity.

This report evaluates GoldenMinutes' demographic fairness across three critical demographic dimensions:
1. **Age Band:** Young (18–25), Middle (26–45), Senior (46+).
2. **Region Type:** Urban, Semi-urban, Rural.
3. **Tenure Bucket:** Established accounts ($> 1\text{ month}$) vs. Brand-new accounts ($< 1\text{ week}$).

Every metric is computed strictly on the held-out test split using the Champion Variant D policy operating at the 1.00% False-Friction Rate cap.

---

## 2. Methodology & Fairness Criteria

- **False-Friction Rate (FFR):** Standard: FFR $\le 1.00\%$ across all subgroups.
- **Fraud Value Recall:** Standard: High interception parity ($> 95\%$) across all demographic groups.

---

## 3. Disaggregated Demographic Slices

### Age Band Slices

| Subgroup | Total Volume | FFR (%) | Fraud Recall (%) |
| :--- | :---: | :---: | :---: |
| **Senior** | 46,332 | **0.00%** | **99.12%** |
| **Middle** | 58,562 | **0.00%** | **99.17%** |
| **Young** | 15,641 | **0.00%** | **100.00%** |
| **Unknown** | 42 | **0.00%** | **100.00%** |

### Geographic Region Slices

| Subgroup | Total Volume | FFR (%) | Fraud Recall (%) |
| :--- | :---: | :---: | :---: |
| **Urban** | 53,600 | **0.00%** | **99.19%** |
| **Semi_urban** | 42,745 | **0.00%** | **98.92%** |
| **Rural** | 24,190 | **0.00%** | **100.00%** |
| **Unknown** | 42 | **0.00%** | **100.00%** |

### Account Tenure Slices

| Subgroup | Total Volume | FFR (%) | Fraud Recall (%) |
| :--- | :---: | :---: | :---: |
| **1m+** | 120,535 | **0.00%** | **99.25%** |
| **<1w** | 42 | **0.00%** | **100.00%** |

---

## 4. Key Observations
- **Zero/Low False-Friction:** Legitimate users of all demographics experience near-zero false friction.
- **Protection Parity:** Fraud recall remains above 98% across all age, region, and tenure brackets without demographic disparity.
