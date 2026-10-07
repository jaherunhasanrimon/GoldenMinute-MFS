# Phase 1: Graph Learning Lift & Network Intelligence Evaluation

**Date:** 2026-10-07 05:19 UTC  
**Dataset Profile:** `full` | **Model Version:** `m-1.0.0-full`  
**Bootstrap Resamples:** 1000 paired iterations | **Coverage:** 95% Confidence Intervals

## Executive Summary

- **Tabular Shortcut Invariant (Criterion 1):** PASSED. Highest tabular single-feature ROC-AUC is `balance_drain_ratio` at **0.8486** (Strictly <= 0.85 threshold; previous shortcut `new_device_flag` reduced to **0.6460**).
- **Graph Learning Lift (E − B):** ΔPR-AUC = **+0.2629** [95% CI: `+0.1472`, `+0.3787`].
- **GNN Incremental Lift over NetworkX (E − C):** ΔPR-AUC = **+0.1073** [95% CI: `+0.0333`, `+0.1876`].
- **NetworkX Graph Lift over Tabular (C − B):** ΔPR-AUC = **+0.1556** [95% CI: `+0.0616`, `+0.2628`].
- **Graph Rewiring Sensitivity:** PR-AUC drops from **0.9008** to **0.2251** (Δ = **-0.6757**) when topological edges are randomized.

**Acceptance Criterion 3 Verdict:** **PASS — Statistically Significant Graph Lift Confirmed**.

---

## 1. Variant Comparison & Paired Differences

| Comparison | Metric | Mean Diff | 95% CI Lower | 95% CI Upper | Statistically Significant? |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **E − B (Full Graph Lift)** | PR-AUC | +0.2629 | +0.1472 | +0.3787 | Yes (p < 0.05) |
| **E − B (Full Graph Lift)** | Recall @ 1% FFR | +0.4510 | +0.3214 | +0.5867 | Yes (p < 0.05) |
| **E − B (Full Graph Lift)** | Value Recall | +0.4411 | +0.3015 | +0.5849 | Yes (p < 0.05) |
| **E − C (GNN over NetworkX)** | PR-AUC | +0.1073 | +0.0333 | +0.1876 | Yes (p < 0.05) |
| **E − C (GNN over NetworkX)** | Recall @ 1% FFR | +0.2250 | +0.1029 | +0.3405 | Yes (p < 0.05) |
| **E − C (GNN over NetworkX)** | Value Recall | +0.2513 | +0.1257 | +0.3946 | Yes (p < 0.05) |
| **C − B (NetworkX over Tabular)** | PR-AUC | +0.1556 | +0.0616 | +0.2628 | Yes (p < 0.05) |
| **C − B (NetworkX over Tabular)** | Recall @ 1% FFR | +0.2260 | +0.1159 | +0.3519 | Yes (p < 0.05) |
| **C − B (NetworkX over Tabular)** | Value Recall | +0.1899 | +0.0341 | +0.3477 | Yes (p < 0.05) |

---

## 2. Typology-Level Graph Lift Breakdown

| Typology | Comparison | ΔPR-AUC (Mean) | 95% CI Lower | 95% CI Upper | ΔRecall @ 1% FFR |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `card_to_wallet_burst` | E − B | +0.7693 | +0.5000 | +0.9091 | +1.0000 |
| `card_to_wallet_burst` | E − C | +0.6109 | +0.0000 | +0.8571 | +0.0000 |
| `impersonation_scam` | E − B | -0.0098 | -0.2310 | +0.2152 | +0.1479 |
| `impersonation_scam` | E − C | -0.0032 | -0.1757 | +0.1422 | +0.1469 |
| `mule_ring` | E − B | +0.7433 | +0.5529 | +0.9047 | +0.8937 |
| `mule_ring` | E − C | +0.2829 | +0.1053 | +0.4745 | +0.3150 |
| `sim_swap_takeover` | E − B | +0.2003 | +0.0702 | +0.3733 | +0.3163 |
| `sim_swap_takeover` | E − C | +0.1096 | +0.0140 | +0.2274 | +0.2266 |

---

## 3. Feature-Group Permutation Importance

Measures mean PR-AUC drop when all features in a group are permuted across test instances (higher drop = higher reliance):

| Feature Group | Features Count | Mean PR-AUC Drop | Std Dev | Importance Share |
| :--- | :---: | :---: | :---: | :---: |
| **`sender`** | 8 | 0.5670 | ±0.0357 | 29.2% |
| **`gnn`** | 6 | 0.5634 | ±0.0149 | 29.0% |
| **`pair`** | 2 | 0.4785 | ±0.0315 | 24.7% |
| **`device_auth`** | 4 | 0.2516 | ±0.0326 | 13.0% |
| **`recipient`** | 9 | 0.0740 | ±0.0077 | 3.8% |
| **`graph`** | 5 | 0.0066 | ±0.0036 | 0.3% |

---

## 4. Graph Topology Rewiring Test

To verify that the model's performance relies on true topological relations (rather than marginal distribution shifts), we randomly rewire edges across graph and GNN features while preserving all tabular signals:

- **Baseline PR-AUC (Intact Graph):** `0.9008`
- **Rewired PR-AUC (Perturbed Graph):** `0.2251`
- **Performance Collapse:** `-0.6757`
- **Topology Dependency Confirmed:** `YES`
