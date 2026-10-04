# GoldenMinutes: Data Dictionary & Normalization Mapping

This document defines canonical entity schemas (ARCHITECTURE.md Section 6) and records all normalization mappings from the supplied synthetic dataset (`goldentimes_synthetic_dataset/`) into canonical Parquet tables.

## Normalization Mappings from Raw Bootstrap CSVs

| Source File & Column | Canonical Table & Column | Transformation / Rule |
|---|---|---|
| `customers.csv: customer_id` | `customers: customer_id` | String pass-through |
| `customers.csv: age` | `customers: age_band` | Derived: `<25` -> `young`, `25-50` -> `middle`, `>50` -> `senior` |
| `customers.csv: district` | `customers: region_type` | Mapped: Dhaka/Chittagong -> `urban`, regional hubs -> `semi_urban`, others -> `rural` |
| `customers.csv: risk_profile` | `customers: persona` | Mapped: `low` -> `salaried`, `medium` -> `small_trader`, `high` -> `student`, `very_high` -> `remittance_receiver` |
| `customers.csv: registration_date` | `customers: registered_at` | Localized to UTC timestamp |
| `customers.csv: account_age_days` | `customers: kyc_level` | Derived: `account_age_days > 180` -> `full`, else `basic` |
| `wallets.csv: wallet_id` | `wallets: wallet_id` | String pass-through |
| `wallets.csv: customer_id` | `wallets: customer_id` | Nullable string pass-through |
| `wallets.csv: primary_agent_id` | `wallets: opened_via_agent_id` | String pass-through |
| `wallets.csv: wallet_status` | `wallets: status` | String pass-through (`active`, `suspended`, `closed`) |
| `agents.csv: agent_id` | `agents: agent_id` | String pass-through |
| `agents.csv: district` | `agents: region_type` | Same district mapping as customers |
| `devices_wallets.csv: device_id` | `device_links: device_id` | String pass-through |
| `devices_wallets.csv: wallet_id` | `device_links: wallet_id` | String pass-through |
| `devices_wallets.csv: first_seen` | `device_links: first_seen_at` | Localized to UTC timestamp |
| `devices_wallets.csv: last_seen` | `device_links: last_seen_at` | Localized to UTC timestamp |
| `transactions.csv: transaction_id` | `transactions: txn_id` | Renamed to `txn_id` |
| `transactions.csv: timestamp` | `transactions: ts` | Localized to UTC timestamp |
| `transactions.csv: transaction_type` | `transactions: type` | Renamed to `type` (`send_money`, `cash_out`, etc.) |
| `transactions.csv: sender_wallet_id` | `transactions: sender_wallet_id` | String pass-through |
| `transactions.csv: receiver_wallet_id` | `transactions: recipient_wallet_id` | Renamed to `recipient_wallet_id` |
| `transactions.csv: amount` | `transactions: amount_bdt` | Renamed to `amount_bdt` |
| `transactions.csv: sender_device_id` | `transactions: device_id` | Renamed to `device_id` |
| `transactions.csv: is_fraud` | `labels: is_fraud` | **ISOLATED INTO LABELS TABLE (Never in transactions)** |
| `transactions.csv: fraud_type` | `labels: typology` | **ISOLATED INTO LABELS TABLE (Never in transactions)** |
| `transactions.csv: mule_account` | `labels: is_mule_recipient` | **ISOLATED INTO LABELS TABLE (Never in transactions)** |
| `mule_ground_truth.csv: wallet_id` | `hidden_truth: wallet_id` | String pass-through |
| `mule_ground_truth.csv: mule_label` | `hidden_truth: is_mule` | Integer flag (0/1) |

## Canonical Tables (Parquet)

### 1. `customers`
- `customer_id` (string): Unique synthetic customer identifier.
- `age_band` (string): 'young', 'middle', 'senior'.
- `region_type` (string): 'urban', 'semi_urban', 'rural'.
- `persona` (string): 'salaried', 'student', 'small_trader', 'remittance_receiver'.
- `registered_at` (datetime UTC): Synthetic registration timestamp.
- `kyc_level` (string): 'basic' or 'full'.

### 2. `wallets`
- `wallet_id` (string): Unique synthetic wallet identifier.
- `customer_id` (string, nullable): Owning customer identifier.
- `owner_type` (string): 'customer', 'agent', 'merchant'.
- `opened_at` (datetime UTC): Wallet creation timestamp.
- `opened_via_agent_id` (string, nullable): Onboarding agent identifier.
- `status` (string): 'active', 'suspended', 'closed'.

### 3. `agents`
- `agent_id` (string): Unique synthetic agent identifier.
- `region_type` (string): 'urban', 'semi_urban', 'rural'.
- `opened_at` (datetime UTC): Registration timestamp.

### 4. `device_links`
- `wallet_id` (string): Wallet ID.
- `device_id` (string): Synthetic device ID.
- `first_seen_at` (datetime UTC): First seen timestamp.
- `last_seen_at` (datetime UTC): Last seen timestamp.

### 5. `auth_events`
- `event_id` (string): Unique event identifier.
- `wallet_id` (string): Wallet ID.
- `ts` (datetime UTC): Event timestamp.
- `event_type` (string): 'pin_reset', 'sim_change', 'new_device_login'.
- `device_id` (string): Associated device ID.

### 6. `transactions` (Sanitized Model Inputs — Leak-Free)
- `txn_id` (string): Unique transaction ID.
- `ts` (datetime UTC): Transaction timestamp (globally monotone).
- `type` (string): 'send_money', 'cash_in', 'cash_out', 'merchant_pay', 'bill_pay', 'add_money_card'.
- `sender_wallet_id` (string): Originating wallet ID.
- `recipient_wallet_id` (string, nullable): Destination wallet ID.
- `agent_id` (string, nullable): Servicing agent ID.
- `amount_bdt` (float): Transaction amount in synthetic BDT.
- `channel` (string): 'app', 'ussd', 'agent'.
- `device_id` (string): Originating device ID.
- `session_seconds` (integer): App session length before transaction.
- `balance_before` (float): Wallet balance immediately prior to transaction.

### 7. `confirmations`
- `wallet_id` (string): Confirmed mule or compromised wallet.
- `confirmed_at` (datetime UTC): Simulated analyst confirmation timestamp (`ts + confirmation_lag_hours`).
- `source` (string): 'analyst_confirmation'.
- *Rule*: Never emitted for the held-out `agent_collusion` typology.

### 8. `labels` (Evaluation & Ground Truth Only)
- `txn_id` (string): Linked transaction ID.
- `is_fraud` (integer, 0/1): Binary fraud flag.
- `typology` (string): Injected scenario label.
- `case_id` (string): Linked investigation case ID.
- `is_mule_recipient` (integer, 0/1): Recipient is a confirmed mule.

### 9. `hidden_truth` (Evaluation & Graph Ground Truth Only)
- `wallet_id` (string): Wallet ID.
- `is_mule` (integer, 0/1): Behavioral mule flag.
- `mule_ring_id` (string): Identified ring membership if applicable.
- `agent_is_collusive` (integer, 0/1): Collusive agent indicator.
