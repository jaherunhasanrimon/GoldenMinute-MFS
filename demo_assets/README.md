# GoldenMinutes Demo Assets Bundle (Safety Net)

This directory provides the minimal, self-contained assets bundle ($\approx 3.5\text{ MB}$, well under the 25 MB ceiling) to guarantee an immediate, robust, one-command demo experience (`make demo`) even on a completely fresh checkout before running full training.

## Contents
1. `models/m-1.0.0-small/`:
   - `variant_c_lgbm.joblib`: Graph-augmented LightGBM binary classifier
   - `variant_c_calibrator.joblib`: Isotonic probability calibrator
   - `anomaly_iforest.joblib`: Isolation Forest unsupervised anomaly detector
   - `fusion_model.joblib`: Transparent logistic stacking fusion model
2. `registry.json`: Model version registry pointing to `m-1.0.0-small` and `m-1.0.0-full`
3. Scenario seeds:
   - Senders: `W01928` (Karim Ahmed), `W01443` (Fatima Begum), `W03312` (Rafiqul Islam)
   - Recipients: `W08371` (Suspicious Mule), `W07712` (Trusted Relative), `W09920` (House Rent)
