# Phase P4 Completion Report: Policy, Online State, and Real API

## 1. Executive Summary

Phase P4 has successfully replaced all mock and stub behaviors across the GoldenMinutes backend with real, production-ready implementations:
1. **Policy Engine (`goldenminutes.policy.engine`, `cost.py`)**: Implements Section 11 expected-cost optimization ($E[\text{cost}(a)] = p \cdot \text{amount} \cdot (1 - \text{eff}_a) + (1-p) \cdot \text{fric}_a$), hard blocklist rules, 300 BDT minimum intervention threshold, hold capacity fallback (20/hr to `verify`), strictly zero `deny` responses, and golden window priority and deadline calculation.
2. **Online Feature Store (`goldenminutes.features.online`)**: Event-time state tracking per wallet, device, and pair. Provides sub-millisecond point-in-time feature extraction matching vectorized offline feature calculations with 100% mathematical parity.
3. **Persistent SQLite Store (`goldenminutes.api.store`)**: SQLAlchemy models and thread-safe CRUD for decisions, priority-sorted alerts, analyst actions (approve/release/escalate with mandatory notes for release), customer/analyst feedback, and immutable operational audit logs.
4. **Real Section 13 API (`goldenminutes.api.main`, `service.py`)**: Live endpoints for `/v1/score`, `/v1/alerts`, `/v1/alerts/{id}`, `/v1/alerts/{id}/decision`, `/v1/feedback`, `/v1/graph/{wallet_id}`, `/v1/metrics`, `/v1/simulate/attack`, and `POST /v1/simulate/reset`. The legacy `X-GM-Stub` header is completely removed from all responses.
5. **Latency Benchmark (`benchmarks/benchmark_latency.py`, `reports/latency.json`)**: Measured over 1,000 sequential live scoring requests: **p50 = 10.14 ms**, **p95 = 11.21 ms**, easily beating the strict 150 ms threshold by >13x.

---

## 2. Policy Engine & Expected Cost Evaluation

Configured strictly per `configs/policy.yaml` and `ARCHITECTURE.md` Section 11:

$$\text{expected\_cost}(a) = p \cdot \text{amount} \cdot (1 - \text{effectiveness}[a]) + (1 - p) \cdot \text{friction\_cost}[a]$$

- **Configured Actions**: `[allow, warn, verify, hold]`
- **Effectiveness Assumptions**: `allow: 0.0`, `warn: 0.25`, `verify: 0.55`, `hold: 0.90`
- **Friction Costs (BDT)**: `allow: 0`, `warn: 5`, `verify: 30`, `hold: 200`
- **Intervention Threshold**: Amounts $< 300$ BDT always result in `allow`.
- **Hold Capacity Fallback**: If $\ge 20$ holds have been initiated in the past hour, fallback automatically triggers `verify`.
- **Priority & Deadline**:
  $$\text{urgency} = \text{clip}\left(1 - \frac{\text{time\_left}}{30}, 0, 1\right)$$
  $$\text{priority} = p \cdot \text{amount} \cdot (1 + \text{urgency})$$
  Status is set to `late` if funds are cashed out before alert evaluation.

---

## 3. Online vs. Offline Parity Verification

Tested via `tests/test_parity.py` against both brand-new/unseen wallets and 5,000+ sampled transactions from canonical dataset:

| Feature Name | Offline vs Online Parity | Max Discrepancy |
|---|---|---|
| `amount_to_median_ratio` | Identical | $0.000000$ |
| `sender_txn_count_1h` | Identical | $0$ |
| `sender_txn_count_24h` | Identical | $0$ |
| `sender_amount_sum_24h` | Identical | $0.000000$ |
| `sender_tenure_days` | Identical | $0.000000$ |
| `balance_drain_ratio` | Identical | $0.000000$ |
| `hour_of_day` | Identical | $0$ |
| `is_night` | Identical | $0$ |
| `is_first_time_pair` | Identical | $0$ |
| `pair_history_count` | Identical | $0$ |
| `new_device_flag` | Identical | $0$ |
| `minutes_since_pin_reset` | Identical | $0.000000$ |
| `minutes_since_sim_change` | Identical | $0.000000$ |
| `session_seconds` | Identical | $0.000000$ |
| `recipient_age_days` | Identical | $0.000000$ |
| `recipient_owner_type_code` | Identical | $0$ |
| `recipient_unique_senders_1h` | Identical | $0$ |
| `recipient_unique_senders_24h` | Identical | $0$ |
| `recipient_first_time_sender_share_24h` | Identical | $0.000000$ |
| `recipient_inflow_24h` | Identical | $0.000000$ |
| `recipient_outflow_24h` | Identical | $0.000000$ |
| `recipient_pass_through_ratio_24h` | Identical | $0.000000$ |
| `recipient_median_receipt_to_out_minutes` | Identical | $0.000000$ |
| `recipient_fan_in_7d` | Identical | $0$ |
| `recipient_fan_out_7d` | Identical | $0$ |
| `shared_device_wallet_count` | Identical | $0$ |
| `component_size_7d` | Identical | $0$ |
| `two_hop_confirmed_mule_share` | Identical | $0.000000$ |

**Total Feature Mismatches across 5,000+ checked transactions**: **0**.

---

## 4. Latency Benchmark Summary (`reports/latency.json`)

Benchmarked using `benchmarks/benchmark_latency.py` across 1,000 end-to-end API scoring requests:

- **Total Requests**: 1,000
- **Mean Latency**: 10.36 ms
- **p50 Latency**: 10.14 ms
- **p90 Latency**: 10.83 ms
- **p95 Latency**: 11.21 ms
- **p99 Latency**: 13.10 ms
- **Max Latency**: 56.54 ms
- **Target p95**: $< 150.0$ ms (**PASSED**, ~13x headroom)

---

## 5. Phase P4 Gate Verification

| Gate Criterion | Target / Requirement | Result | Status |
|---|---|---|---|
| **No Stub Header** | No response returns `X-GM-Stub` | Verified via HTTP client & tests | **PASS** |
| **Feature Parity** | Parity on $\ge 5,000$ sampled txns | 0 mismatches across 28 features | **PASS** |
| **p95 Latency** | Recorded; $< 150$ ms target | **11.21 ms** recorded in `latency.json` | **PASS** |
| **Interactive POST /score** | Plausible action, reasons, alert on `hold` | Verified via curl & `/docs` | **PASS** |
| **Role Authorization** | Analyst endpoints require `analyst` role | 403 on invalid/customer keys | **PASS** |
| **Audit Trail** | Every analyst action creates audit log | Verified in `tests/test_store.py` | **PASS** |
| **Release Note** | `release` action requires note | 422 raised if note missing | **PASS** |
| **Unit Test Suite** | All unit and regression tests pass | 63 / 63 tests pass cleanly | **PASS** |
| **Linter / Formatter** | Zero lint or formatting errors | `make lint` clean | **PASS** |

---

## 6. Interactive Verification Example

```bash
curl -X POST http://127.0.0.1:8000/v1/score \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo_customer_secret_key" \
  -d '{
    "txn_id": "T_TEST_001",
    "ts": "2026-02-14T10:22:31+06:00",
    "type": "send_money",
    "sender_wallet_id": "W01928",
    "recipient_wallet_id": "W08371",
    "amount_bdt": 25000.0,
    "channel": "app",
    "device_id": "DEV_NEW_1",
    "balance_before": 28000.0,
    "session_seconds": 45
  }'
```

**Response**:
```json
{
  "txn_id": "T_TEST_001",
  "risk_score": 0.6935,
  "action": "hold",
  "reason_codes": [
    {"code": "AMOUNT_UNUSUAL_FOR_SENDER", "weight": 0.28},
    {"code": "RECIPIENT_NEW", "weight": 0.18},
    {"code": "DEVICE_OR_PIN_CHANGE_RECENT", "weight": 0.15}
  ],
  "customer_message": {
    "bn": "নিরাপত্তা পর্যালোচনার জন্য এই স্থানান্তরটি সাময়িক স্থগিত রাখা হয়েছে। ৩০ মিনিটের মধ্যে সিদ্ধান্ত জানানো হবে।",
    "en": "This transfer is held for safety review. Target review within 30 minutes."
  },
  "alert_id": "ABE7F0BE9",
  "model_version": "m-1.0.0-full",
  "policy_version": "0.1",
  "latency_ms": 37.46
}
```

The resulting alert `ABE7F0BE9` is immediately visible in `/v1/alerts` with priority `17338.25` and full evidence dictionary.
