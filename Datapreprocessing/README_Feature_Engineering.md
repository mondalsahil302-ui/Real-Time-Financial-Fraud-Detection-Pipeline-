# PaySim Feature Engineering README

## 1. Purpose

This document describes the standalone feature-engineering stage of the Real-Time Financial Fraud Detection Pipeline.

The purpose is to transform raw PaySim transaction records into a consistent numerical representation for the selected Isolation Forest anomaly-detection model.

This README covers:

- raw input schema
- feature transformations
- final feature list
- feature definitions
- excluded columns
- validation
- exported outputs
- training-to-streaming feature contract

It does not describe model training, hyperparameter tuning, threshold optimization, Kafka, Spark, Cassandra, Grafana, RAG, or LLM implementation.

---

## 2. Dataset

The raw dataset is the PaySim synthetic financial transaction dataset used by this project.

Current source file:

```text
data/
└── PS_20174392719_1491204439457_log.csv
```

The standalone notebook currently uses:

```text
MAX_ROWS = 500,000
```

This matches the current Isolation Forest experiment.

The transformation logic is row-wise and can be applied to a larger dataset as long as the input schema and feature contract remain consistent.

---

## 3. Raw Input Schema

The raw PaySim file contains these columns:

| Column | Role | Description |
|---|---|---|
| `step` | Model input | PaySim simulation time step |
| `type` | Model input | Transaction type |
| `amount` | Model input | Transaction amount |
| `nameOrig` | Identifier | Origin/sender account identifier |
| `oldbalanceOrg` | Model input | Origin balance before transaction |
| `newbalanceOrig` | Model input | Origin balance after transaction |
| `nameDest` | Identifier | Destination/receiver account identifier |
| `oldbalanceDest` | Model input | Destination balance before transaction |
| `newbalanceDest` | Model input | Destination balance after transaction |
| `isFraud` | Ground truth | Fraud label used for evaluation |
| `isFlaggedFraud` | Existing flag | Existing PaySim flag; excluded from model input |

---

## 4. Feature-Engineering Design

The transformation follows this structure:

```text
                 RAW PAYSIM
                     |
        +------------+-------------+
        |            |             |
        v            v             v
     Numeric      Balance       Transaction
      fields       fields          type
        |            |             |
        |            v             v
        |        Derived        One-hot
        |         features      encoding
        |            |             |
        +------------+-------------+
                     |
                     v
              19 MODEL FEATURES
                     |
                     v
            ISOLATION FOREST
```

---

# 5. Final Feature Set

The current Isolation Forest feature contract contains exactly 19 columns:

```text
01. step
02. amount
03. oldbalanceOrg
04. newbalanceOrig
05. oldbalanceDest
06. newbalanceDest
07. orig_balance_change
08. dest_balance_change
09. orig_balance_error
10. dest_balance_error
11. orig_zero_after
12. dest_zero_before
13. dest_zero_after
14. log_amount
15. type_CASH_IN
16. type_CASH_OUT
17. type_DEBIT
18. type_PAYMENT
19. type_TRANSFER
```

Feature order is important and must remain unchanged during streaming inference.

---

# 6. Original Numerical Features

## 6.1 `step`

Source:

```text
step
```

Transformation:

```text
None
```

Meaning:

The PaySim simulation time step associated with the transaction.

---

## 6.2 `amount`

Source:

```text
amount
```

Transformation:

```text
None
```

Meaning:

The transaction amount.

The original `amount` remains in the model input. A separate `log_amount` feature is also created.

---

## 6.3 `oldbalanceOrg`

Meaning:

Origin/sender account balance before the transaction.

---

## 6.4 `newbalanceOrig`

Meaning:

Origin/sender account balance after the transaction.

---

## 6.5 `oldbalanceDest`

Meaning:

Destination/receiver account balance before the transaction.

---

## 6.6 `newbalanceDest`

Meaning:

Destination/receiver account balance after the transaction.

---

# 7. Derived Balance-Movement Features

## 7.1 `orig_balance_change`

Formula:

```python
orig_balance_change = oldbalanceOrg - newbalanceOrig
```

Interpretation:

```text
Origin balance before
        -
Origin balance after
        =
Observed reduction in origin balance
```

Example:

```text
oldbalanceOrg  = 170136.00
newbalanceOrig = 160296.36

orig_balance_change = 9839.64
```

This is consistent with the transaction amount in the example transaction.

---

## 7.2 `dest_balance_change`

Formula:

```python
dest_balance_change = newbalanceDest - oldbalanceDest
```

Interpretation:

```text
Destination balance after
        -
Destination balance before
        =
Observed destination balance movement
```

Example:

```text
oldbalanceDest = 21182
newbalanceDest = 0

dest_balance_change = -21182
```

The current feature definition intentionally preserves the signed direction of the observed destination balance movement.

---

# 8. Balance-Discrepancy Features

## 8.1 `orig_balance_error`

Formula:

```python
orig_balance_error = amount - orig_balance_change
```

Interpretation:

This represents the numerical difference between the transaction amount and the observed origin-side balance movement.

For an exactly matching balance movement:

```text
orig_balance_error = 0
```

Very small values close to zero can arise from floating-point representation.

---

## 8.2 `dest_balance_error`

Formula:

```python
dest_balance_error = amount - dest_balance_change
```

Interpretation:

This represents the numerical difference between the transaction amount and the signed destination-side balance movement under the current feature definition.

---

# 9. Zero-Balance Indicators

Three binary features are created.

## 9.1 `orig_zero_after`

Formula:

```python
orig_zero_after = (newbalanceOrig == 0).astype(int)
```

Interpretation:

```text
newbalanceOrig == 0  -> 1
otherwise             -> 0
```

It identifies whether the origin account balance becomes zero after the transaction.

---

## 9.2 `dest_zero_before`

Formula:

```python
dest_zero_before = (oldbalanceDest == 0).astype(int)
```

Interpretation:

```text
oldbalanceDest == 0 -> 1
otherwise            -> 0
```

It identifies whether the destination account balance was zero before the transaction.

---

## 9.3 `dest_zero_after`

Formula:

```python
dest_zero_after = (newbalanceDest == 0).astype(int)
```

Interpretation:

```text
newbalanceDest == 0 -> 1
otherwise            -> 0
```

It identifies whether the destination account balance is zero after the transaction.

---

# 10. Log-Transformed Amount

## `log_amount`

Formula:

```python
log_amount = np.log1p(amount)
```

Equivalent mathematical form:

\[
\log(1 + amount)
\]

Purpose:

A second representation of transaction amount is created using a logarithmic transformation.

Example:

```text
amount = 9839.64

log_amount ≈ 9.194276
```

The original `amount` remains in the feature set.

---

# 11. Transaction-Type Encoding

The raw categorical field is:

```text
type
```

The current dataset contains:

```text
CASH_IN
CASH_OUT
DEBIT
PAYMENT
TRANSFER
```

The notebook applies:

```python
pd.get_dummies(
    work,
    columns=["type"],
    prefix="type",
    dtype=int
)
```

This produces:

```text
type_CASH_IN
type_CASH_OUT
type_DEBIT
type_PAYMENT
type_TRANSFER
```

For example, a `PAYMENT` transaction becomes:

```text
type_CASH_IN   = 0
type_CASH_OUT  = 0
type_DEBIT     = 0
type_PAYMENT   = 1
type_TRANSFER  = 0
```

---

# 12. Columns Excluded from Model Input

The following fields are deliberately excluded from `X`:

```text
isFraud
isFlaggedFraud
nameOrig
nameDest
```

## `isFraud`

This is ground truth.

It is retained separately:

```python
y = work["isFraud"].astype(int)
```

and is used for model evaluation.

It must not be included in model input.

---

## `isFlaggedFraud`

The current experiment does not use this existing PaySim flag as a model feature.

---

## `nameOrig`

This is an origin account identifier.

It is retained in the raw transaction data but is not transformed into a model feature.

---

## `nameDest`

This is a destination account identifier.

It is retained in the raw transaction data but is not transformed into a model feature.

---

# 13. Model Input vs Ground Truth

The implementation keeps these two concepts separate:

```text
X
↓
19 model features

y
↓
isFraud
↓
ground truth for evaluation
```

This separation must remain intact in later streaming implementation.

---

# 14. Feature Validation

The notebook validates the engineered matrix.

## Missing values

```python
X.isna().sum().sum()
```

Expected:

```text
0
```

## Infinite values

```python
np.isinf(X.to_numpy()).sum()
```

Expected:

```text
0
```

## Forbidden columns

The notebook checks that:

```text
isFraud
isFlaggedFraud
nameOrig
nameDest
```

are absent from `X`.

---

# 15. Output Files

Running the notebook creates:

```text
feature_engineering_output/
│
├── paysim_feature_engineering_metadata.json
├── paysim_engineered_features_500k.csv
└── paysim_ground_truth_500k.csv
```

---

## 15.1 Metadata file

```text
paysim_feature_engineering_metadata.json
```

Contains:

- dataset name
- source file
- number of processed rows
- feature count
- exact feature order
- excluded columns
- ground-truth column
- transformation formulas
- validation results

---

## 15.2 Engineered feature matrix

```text
paysim_engineered_features_500k.csv
```

Contains only the 19 model-ready features.

It does not contain:

```text
isFraud
isFlaggedFraud
nameOrig
nameDest
```

---

## 15.3 Ground-truth file

```text
paysim_ground_truth_500k.csv
```

Contains:

```text
isFraud
```

This keeps the target label separate from model input.

---

# 16. Training-to-Streaming Contract

This is the most important integration rule.

The offline training path is:

```text
Raw PaySim
     ↓
Feature Engineering
     ↓
19 features
     ↓
Isolation Forest
```

The real-time path must be:

```text
Kafka JSON
     ↓
Same Feature Engineering
     ↓
Same 19 features
     ↓
Serialized Isolation Forest
```

The following must remain identical:

```text
feature names
feature formulas
feature order
transaction-type encoding
data types
excluded fields
```

A mismatch means the streaming model will not receive the same representation used during training.

---

# 17. Example: One Transaction

Example raw transaction:

```text
type = PAYMENT
amount = 9839.64

oldbalanceOrg = 170136
newbalanceOrig = 160296.36

oldbalanceDest = 0
newbalanceDest = 0
```

Derived values:

```text
orig_balance_change
= 170136 - 160296.36
= 9839.64

dest_balance_change
= 0 - 0
= 0

orig_balance_error
= 9839.64 - 9839.64
≈ 0

dest_balance_error
= 9839.64 - 0
= 9839.64

orig_zero_after = 0
dest_zero_before = 1
dest_zero_after = 1

log_amount ≈ 9.194276
```

Transaction type:

```text
type_CASH_IN   = 0
type_CASH_OUT  = 0
type_DEBIT     = 0
type_PAYMENT   = 1
type_TRANSFER  = 0
```

The final result is a 19-feature vector.

---

# 18. Position in the Full Fraud Pipeline

```text
PaySim
  ↓
Raw Transaction
  ↓
Feature Engineering
  ↓
19 Model Features
  ↓
Isolation Forest
  ↓
Anomaly Score
  ↓
Threshold
  ↓
Normal / Potential Fraud
```

The feature-engineering layer is the bridge between raw transaction data and ML inference.

---

# 19. Current Scope

The current notebook processes:

```text
500,000 PaySim rows
```

and produces:

```text
19 model features
```

It is intended to match the current Isolation Forest experiment.

The notebook does not imply that this 500,000-row experiment is the complete PaySim dataset.

The same transformations can later be applied to larger/full data processing as long as the model feature contract remains consistent.

---

# 20. Running the Notebook

From the project root:

```powershell
.\.venv\Scripts\python.exe -m notebook
```

Open:

```text
PaySim_Feature_Engineering.ipynb
```

Run cells sequentially with:

```text
Shift + Enter
```

---

# 21. Expected Final Result

The final notebook report should show:

```text
Dataset             : PaySim
Rows processed      : 500,000
Feature count       : 19
Ground truth        : isFraud
NaN values           : 0
Infinite values      : 0
```

and list the exact 19 feature columns.

---