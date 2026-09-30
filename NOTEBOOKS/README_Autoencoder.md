# Autoencoder — PaySim Fraud Detection

## 1. Overview

This README documents the **Autoencoder anomaly-detection experiment** implemented in:

```text
Autoencoder_Model_Test.ipynb
```

The experiment tests whether a deep Autoencoder can detect potentially fraudulent PaySim transactions by learning the normal transaction pattern and measuring how well each transaction can be reconstructed.

The experiment follows the same data preparation and evaluation philosophy used for the Isolation Forest experiment so that the two approaches can be compared under a consistent setup.

### Core idea

```text
PaySim transaction
        ↓
Feature engineering
        ↓
19 numerical/model features
        ↓
StandardScaler
        ↓
Deep Autoencoder
        ↓
Reconstructed transaction
        ↓
Reconstruction error
        ↓
Validation-selected threshold
        ↓
Normal / Anomaly (Potential Fraud)
```

The Autoencoder is trained **without fraud labels**. It learns from legitimate transactions and uses reconstruction error as the anomaly score.

---

## 2. Experiment Objective

The purpose of the notebook is to evaluate a deep neural Autoencoder as an anomaly detector for financial fraud detection.

The main questions addressed by the experiment are:

1. Can the Autoencoder learn a representation of normal PaySim transactions?
2. Do fraudulent transactions generally produce larger reconstruction errors?
3. Can a validation-derived threshold convert reconstruction error into a fraud-alert decision?
4. How does the model perform on an untouched test set?
5. Can the trained model, scaler, feature list, configuration, and evaluation results be serialized for later integration into the streaming pipeline?

---

## 3. Dataset

### Dataset

```text
PaySim Synthetic Financial Dataset
File:
PS_20174392719_1491204439457_log.csv
```

The notebook loads the first **500,000 transactions** for this experiment.

This is an experimental subset of the PaySim dataset, not the complete dataset.

### Dataset scope

| Item | Value |
|---|---:|
| Rows loaded | 500,000 |
| Raw columns | 11 |
| Training rows | 300,000 |
| Validation rows | 100,000 |
| Test rows | 100,000 |
| Normal training rows | 299,860 |
| Fraud removed from training | 140 |
| Validation fraud cases | 46 |
| Test fraud cases | 47 |
| Fraud rate in loaded data | 0.0466% |

The very low fraud rate means the dataset is **extremely imbalanced**.

Because of this imbalance, accuracy alone is not sufficient to judge the quality of a fraud detector. Precision, recall, F1-score, PR-AUC, confusion-matrix counts, and false-negative behavior are especially important.

---

## 4. Raw Dataset Schema

The original PaySim input contains the following 11 columns.

| Column | Role | Description |
|---|---|---|
| `step` | Input feature | Time step in the PaySim simulation |
| `type` | Input feature | Transaction type |
| `amount` | Input feature | Transaction amount |
| `nameOrig` | Identifier | Origin/sender account identifier |
| `oldbalanceOrg` | Input feature | Origin account balance before the transaction |
| `newbalanceOrig` | Input feature | Origin account balance after the transaction |
| `nameDest` | Identifier | Destination/receiver account identifier |
| `oldbalanceDest` | Input feature | Destination account balance before the transaction |
| `newbalanceDest` | Input feature | Destination account balance after the transaction |
| `isFraud` | Target only | Ground-truth fraud label used for evaluation |
| `isFlaggedFraud` | Excluded | Existing PaySim fraud flag; not provided to the Autoencoder |

### Important leakage rule

The following fields are **not used as Autoencoder inputs**:

```text
isFraud
isFlaggedFraud
nameOrig
nameDest
```

`isFraud` is retained only as the evaluation target.

The Autoencoder therefore does not receive the true fraud label during training.

---

# 5. Notebook Structure

The notebook is organized into the following blocks:

```text
Block 1  — Import Libraries and Check Environment
Block 2  — Project Configuration
Block 3  — Load PaySim Dataset
Block 4  — Data Quality & Fraud Distribution
Block 5  — Feature Engineering
Block 6  — Train / Validation / Test Split
Block 7  — Feature Scaling
Block 8  — 1K+ Very Deep Autoencoder
Block 9  — Train the Autoencoder
Block 10 — Training & Validation Loss Analysis
Block 11 — Reconstruction Error / Anomaly Score
Block 12 — Fraud Detection Threshold Selection
Block 13 — Final Test Set Evaluation
Block 14 — Reconstruction Error Visual Analysis
Block 15 — Save Complete Autoencoder Experiment
```

The notebook is intentionally designed to be executed one block at a time so that every stage can be checked before continuing.

---

# 6. Reproducibility and Configuration

The experiment uses a fixed random seed:

```python
RANDOM_STATE = 42
```

Main configuration:

```python
MAX_ROWS = 500_000

TEST_SIZE = 0.20
VALIDATION_SIZE = 0.25

EPOCHS = 20
BATCH_SIZE = 512
LEARNING_RATE = 0.001
PATIENCE = 3
```

### Interpretation

The 80% portion remaining after the test split is divided again:

```text
80% × 75% = 60% training
80% × 25% = 20% validation

Final:
60% training
20% validation
20% test
```

The test set remains untouched until final evaluation.

---

# 7. Data Quality Checks

The notebook checks:

- Dataset shape
- Data types
- Missing values
- Duplicate rows
- Transaction type distribution
- Fraud/legitimate distribution
- `isFlaggedFraud` distribution
- Transaction amount statistics

Recorded checks for the 500,000-row experiment:

```text
Rows               : 500,000
Columns            : 11
Missing values     : 0
Duplicate rows     : 0
Fraud              : 233
Legitimate         : 499,767
Fraud rate         : 0.0466%
```

The dataset was therefore clean with respect to missing and duplicate rows in the loaded subset.

---

# 8. Feature Engineering

The Autoencoder uses the same engineered 19-feature representation used in the corresponding Isolation Forest experiment.

The feature engineering stage derives additional transaction-behavior features before model training.

## 8.1 Balance movement features

### Origin balance change

```python
orig_balance_change = oldbalanceOrg - newbalanceOrig
```

This represents the amount by which the sender/origin balance decreased.

### Destination balance change

```python
dest_balance_change = newbalanceDest - oldbalanceDest
```

This represents the amount by which the destination balance increased.

---

## 8.2 Balance consistency error features

### Origin balance error

```python
orig_balance_error = amount - orig_balance_change
```

### Destination balance error

```python
dest_balance_error = amount - dest_balance_change
```

These features represent the difference between the transaction amount and the observed balance movement.

Large deviations can indicate that the observed transaction behavior does not follow the expected balance movement pattern.

---

## 8.3 Zero-balance indicator features

The following binary indicators are created:

```python
orig_zero_after = (newbalanceOrig == 0).astype(int)

dest_zero_before = (oldbalanceDest == 0).astype(int)

dest_zero_after = (newbalanceDest == 0).astype(int)
```

These allow the model to distinguish transactions associated with zero balances.

---

## 8.4 Log-transformed transaction amount

The transaction amount is also transformed using:

```python
log_amount = np.log1p(amount)
```

This provides a compressed representation of the amount while retaining its ordering.

---

## 8.5 Transaction-type encoding

The categorical transaction type is converted into one-hot encoded columns:

```text
type_CASH_IN
type_CASH_OUT
type_DEBIT
type_PAYMENT
type_TRANSFER
```

---

# 9. Final 19-Feature Contract

The final feature matrix contains exactly **19 features** in the following order:

| # | Feature |
|---:|---|
| 1 | `step` |
| 2 | `amount` |
| 3 | `oldbalanceOrg` |
| 4 | `newbalanceOrig` |
| 5 | `oldbalanceDest` |
| 6 | `newbalanceDest` |
| 7 | `orig_balance_change` |
| 8 | `dest_balance_change` |
| 9 | `orig_balance_error` |
| 10 | `dest_balance_error` |
| 11 | `orig_zero_after` |
| 12 | `dest_zero_before` |
| 13 | `dest_zero_after` |
| 14 | `log_amount` |
| 15 | `type_CASH_IN` |
| 16 | `type_CASH_OUT` |
| 17 | `type_DEBIT` |
| 18 | `type_PAYMENT` |
| 19 | `type_TRANSFER` |

The notebook confirms:

```text
Feature matrix shape:
500,000 × 19

NaN values:
0

Infinite values:
0
```

### Production requirement

This 19-feature contract is part of the model definition.

For future streaming inference, the same:

- feature names
- feature formulas
- categorical encoding
- feature order
- data types
- excluded fields

must be reproduced before sending a transaction to the Autoencoder.

---

# 10. Train / Validation / Test Strategy

The notebook uses a stratified 60/20/20 split.

```text
500,000 transactions
        │
        ├── 300,000 Training
        │
        ├── 100,000 Validation
        │
        └── 100,000 Test
```

The important anomaly-detection rule is that **training uses legitimate transactions only**.

### Training composition

```text
Training rows              : 300,000
Legitimate training rows   : 299,860
Fraud rows removed         : 140
```

### Validation and test

```text
Validation fraud cases : 46
Test fraud cases       : 47
```

The fraud labels remain available for validation and testing, but they are not used as Autoencoder training targets.

---

# 11. Why Normal-Only Training Is Used

The Autoencoder is being used as an anomaly detector rather than as a conventional supervised classifier.

The model learns:

```text
What does a normal transaction look like?
```

It is not directly trained to learn:

```text
What does a fraud transaction look like?
```

The logic is:

```text
Legitimate transactions
        ↓
Autoencoder learns normal patterns
        ↓
New transaction
        ↓
Reconstruct transaction
        ↓
Measure reconstruction error
        ↓
Low error  → resembles learned normal pattern
High error → appears anomalous
```

This makes the experiment consistent with the intended anomaly-detection formulation.

---

# 12. Feature Scaling

Before being given to the neural network, the 19 features are standardized using:

```python
scaler = StandardScaler()
```

The scaler is fitted using the **legitimate training data** and then applied to validation and test data.

The resulting shapes are:

```text
Training normal data : (299860, 19)
Validation data      : (100000, 19)
Test data            : (100000, 19)
```

Recorded scaling time:

```text
0.1095 seconds
```

### Why scaling is important here

The Autoencoder is a neural network that optimizes a numeric reconstruction loss.

The raw PaySim features operate on very different numerical scales. For example:

- transaction amount can be very large,
- balances can be very large,
- binary indicators are only 0/1,
- one-hot transaction types are 0/1.

Standardization puts the input variables onto comparable scales for neural-network training.

---

# 13. Autoencoder Architecture

The notebook implements a deep symmetric Autoencoder named:

```text
PaySim_1K_Deep_Autoencoder
```

The model receives **19 input features**.

The encoder progressively compresses those 19 values into an **8-dimensional latent representation**.

The decoder then expands the latent representation back into 19 reconstructed values.

## Architecture

```text
Input
  19
   │
   ▼
 1024
   │
Batch Normalization
   │
Dropout (5%)
   │
   ▼
  512
   │
Batch Normalization
   │
   ▼
  256
   │
   ▼
  128
   │
   ▼
   64
   │
   ▼
   32
   │
   ▼
   16
   │
   ▼
    8
   │
   │  LATENT SPACE
   │
   ▼
   16
   │
   ▼
   32
   │
   ▼
   64
   │
   ▼
  128
   │
   ▼
  256
   │
   ▼
  512
   │
Batch Normalization
   │
   ▼
 1024
   │
Batch Normalization
   │
   ▼
  19
   │
   ▼
Reconstructed Input
```

### Encoder

```text
19 → 1024 → 512 → 256 → 128 → 64 → 32 → 16 → 8
```

### Decoder

```text
8 → 16 → 32 → 64 → 128 → 256 → 512 → 1024 → 19
```

---

# 14. Neural-Network Components

## Activation

Hidden layers use:

```text
ReLU
```

The output layer uses:

```text
Linear
```

The linear output is appropriate because the decoder is reconstructing continuous scaled feature values.

## Batch Normalization

Batch normalization is used in selected layers to stabilize the neural-network training process.

## Dropout

A 5% dropout layer is used after the first 1024-neuron encoder layer:

```text
Dropout = 0.05
```

## L2 Regularization

Dense layers use:

```text
L2 = 1e-5
```

This adds a small regularization penalty to discourage overly large network weights.

---

# 15. Optimization Configuration

The network is compiled with:

```text
Optimizer : Adam
Learning rate : 0.001
Loss : Mean Squared Error
```

### Why Mean Squared Error is used

The Autoencoder is reconstructing the original input vector.

For one transaction, the reconstruction error is conceptually:

```text
MSE =
mean(
    (original_feature_1 - reconstructed_feature_1)^2,
    ...
    (original_feature_19 - reconstructed_feature_19)^2
)
```

The notebook later uses this per-transaction reconstruction error as the anomaly score.

---

# 16. Training Configuration

Requested training configuration:

```text
Epochs             : 20
Batch size         : 512
Learning rate      : 0.001
Early stopping     : patience = 3
```

The Autoencoder was trained to reconstruct the input itself:

```python
X_train_normal_scaled → X_train_normal_scaled
```

No fraud labels are supplied during training.

---

# 17. Early Stopping and Best Checkpoint

The notebook uses two callbacks:

### EarlyStopping

```text
Monitor : val_loss
Patience: 3
Restore best weights: Yes
```

### ModelCheckpoint

```text
models/autoencoder_best.keras
```

The best model is determined from validation reconstruction loss.

---

# 18. Actual Training Result

Although 20 epochs were requested, training completed after **12 epochs** because early stopping was triggered.

```text
Epochs requested : 20
Epochs completed : 12
Training time   : 191.70 seconds
```

The best validation reconstruction loss occurred at:

```text
Best epoch : 9
Training loss : 0.04061466
Validation loss : 0.06716587
```

### Loss history

| Epoch | Training Loss | Validation Loss |
|---:|---:|---:|
| 1 | 0.15059364 | 0.72859466 |
| 2 | 0.08472797 | 0.52516204 |
| 3 | 0.06541089 | 0.12298133 |
| 4 | 0.06194230 | 0.10418962 |
| 5 | 0.05100050 | 0.12014533 |
| 6 | 0.04648630 | 0.09501662 |
| 7 | 0.04249734 | 0.17210725 |
| 8 | 0.04596574 | 0.07222733 |
| 9 | 0.04061466 | 0.06716587 |
| 10 | 0.03785515 | 0.08254946 |
| 11 | 0.03923496 | 0.29481331 |
| 12 | 0.03951332 | 0.07024303 |

The best checkpoint was therefore associated with epoch 9.

---

# 19. Reconstruction Error

The Autoencoder generates a reconstructed version of each transaction.

The notebook calculates a per-transaction score with:

```python
reconstructed = model.predict(data)

error = np.mean(
    np.square(data - reconstructed),
    axis=1
)
```

This produces one reconstruction-error value for each transaction.

### Interpretation

```text
Low reconstruction error
    ↓
Transaction resembles the patterns learned from normal data

High reconstruction error
    ↓
Transaction appears more anomalous
```

The reconstruction error is therefore the model's continuous anomaly score.

It is **not a probability of fraud**.

---

# 20. Validation and Test Scoring

Recorded inference/scoring times:

```text
Validation scoring time : 2.31 seconds
Test scoring time       : 1.94 seconds
```

Both validation and test sets contain 100,000 transactions.

At this stage the notebook has continuous reconstruction errors only.

A fraud threshold is selected separately on validation data.

---

# 21. Threshold Selection

The reconstruction error must be converted into a binary decision.

The notebook evaluates **300 threshold candidates** on the validation dataset.

The tested threshold range was:

```text
Lowest candidate  : 0.11215683
Highest candidate : 1.74720635
```

For every candidate threshold, the notebook calculates:

- Precision
- Recall
- F1-score
- True Negatives
- False Positives
- False Negatives
- True Positives

---

# 22. Decision Rule

The notebook uses:

```text
reconstruction_error < threshold
    → Normal (0)

reconstruction_error >= threshold
    → Anomaly / Potential Fraud (1)
```

This direction is important.

A transaction is not flagged because its score is low. It is flagged because its reconstruction error reaches or exceeds the threshold.

---

# 23. Selected Threshold

The threshold chosen from the validation set was the threshold with the highest validation F1-score.

```text
Selected threshold : 1.74720635
```

Validation performance at this threshold:

| Metric | Validation Result |
|---|---:|
| Precision | 0.1600 |
| Recall | 0.3478 |
| F1-score | 0.2192 |
| True Positives | 16 |
| False Positives | 84 |
| False Negatives | 30 |
| True Negatives | 99,870 |

The threshold is frozen before final test evaluation.

---

# 24. Recall-Oriented Analysis

Because missing fraudulent transactions is an important concern in fraud detection, the notebook also checks for a threshold that achieves:

```text
Target recall = 95%
```

Result:

```text
No tested threshold achieved the requested 95% recall target.
```

This is an important result.

It means that within the tested threshold range, the Autoencoder did not provide a threshold that reached the requested recall level on the validation set.

Therefore, the experiment proceeds with the validation F1-selected threshold.

---

# 25. Final Test Evaluation

The selected threshold is applied to the untouched test set.

```text
Test transactions : 100,000
Actual fraud cases : 47
```

Final results:

| Metric | Test Result |
|---|---:|
| Precision | 0.1122 |
| Recall | 0.2340 |
| F1-score | 0.1517 |
| ROC-AUC | 0.9063 |
| PR-AUC | 0.1561 |

---

# 26. Confusion Matrix

The final test confusion matrix is:

|  | Predicted Legitimate | Predicted Fraud |
|---|---:|---:|
| Actual Legitimate | 99,866 | 87 |
| Actual Fraud | 36 | 11 |

Therefore:

```text
True Negatives  : 99,866
False Positives : 87
False Negatives : 36
True Positives  : 11
```

---

# 27. Fraud Detection Breakdown

The Autoencoder generated:

```text
Fraud alerts generated : 98
Actual fraud cases     : 47
Fraud cases detected   : 11
Fraud cases missed     : 36
```

The resulting fraud recall was:

```text
11 / 47 = 23.404%
```

The false-negative rate was:

```text
76.5957%
```

This means that, in this particular 100,000-transaction test set, the Autoencoder did not detect a large share of the fraudulent cases at the selected operating threshold.

The result should therefore be interpreted as an **experimental anomaly-detection benchmark**, not as evidence that the current configuration is already suitable as a production fraud detector.

---

# 28. Threshold-Independent Metrics

The notebook also reports:

### ROC-AUC

```text
0.9063
```

ROC-AUC evaluates how well the continuous reconstruction-error scores rank the two classes across thresholds.

### PR-AUC

```text
0.1561
```

PR-AUC evaluates the precision-recall behavior of the score ranking.

Given the extreme class imbalance, PR-AUC is particularly useful for understanding fraud-detection performance.

---

# 29. Why Accuracy Is Not the Main Metric

The classification report produced by the notebook shows:

```text
Accuracy : 0.9988
```

At first glance this looks very high.

However, the test set contains:

```text
99,953 legitimate
47 fraud
```

A model can achieve very high accuracy while still missing many fraudulent transactions.

The Autoencoder demonstrates this clearly:

```text
Accuracy          : 99.88%
Fraud recall      : 23.40%
Fraud false-negative rate : 76.60%
```

Therefore the README treats fraud-class recall, false negatives, precision, F1, and PR-AUC as more informative operating indicators than accuracy alone.

---

# 30. Visual Analysis

The notebook includes visual analysis of the reconstruction-error scores.

The visual block examines:

1. Reconstruction-error statistics.
2. Reconstruction-error percentiles.
3. Score distributions.
4. Legitimate-versus-fraud error distributions.
5. A box plot of reconstruction errors.
6. Prediction distribution.
7. Highest-error transactions.
8. Missed fraud transactions.
9. False-positive transactions.
10. The selected decision threshold.

The main visual question is:

```text
Do fraudulent transactions tend to receive higher
reconstruction errors than legitimate transactions?
```

The amount of overlap between the two score distributions is also important.

If fraud and legitimate transactions have substantial reconstruction-error overlap, a single threshold will inevitably create a trade-off between:

```text
False positives
        ↕
False negatives
```

---

# 31. Highest-Error Transactions

The notebook identifies the 20 test transactions with the highest reconstruction errors.

These records are useful for investigating:

- unusual transaction amounts,
- balance inconsistencies,
- unusual transaction types,
- zero-balance behavior,
- other patterns that the Autoencoder finds difficult to reconstruct.

These records should be treated as **anomalous candidates**, not automatically as confirmed fraud.

---

# 32. Missed Fraud Analysis

The notebook also displays fraud transactions that were below the selected reconstruction-error threshold.

These are false negatives.

For the final test run:

```text
Actual fraud : 47
Detected     : 11
Missed       : 36
```

Studying these transactions is valuable because it can reveal whether the Autoencoder is failing on particular transaction types or feature patterns.

---

# 33. False-Positive Analysis

The notebook also displays legitimate transactions that exceeded the threshold.

These are false positives.

For the final test run:

```text
False positives : 87
```

This analysis is useful for understanding which legitimate transaction patterns appear unusual to the model.

---

# 34. Model Artifacts

The notebook saves the Autoencoder experiment into the project `models/` and `results/` directories.

## Model files

```text
models/
├── autoencoder_final.keras
├── autoencoder_best.keras
├── autoencoder_scaler.pkl
├── autoencoder_features.json
└── autoencoder_config.json
```

## Result file

```text
results/
└── autoencoder_final_results.json
```

---

# 35. Artifact Details

## `autoencoder_final.keras`

Contains the trained Autoencoder model.

This is the main neural-network artifact used for reconstruction during inference.

---

## `autoencoder_best.keras`

Contains the checkpoint saved when validation loss was at its best.

The training run used:

```text
EarlyStopping(
    monitor="val_loss",
    patience=3,
    restore_best_weights=True
)
```

The best validation-loss epoch was:

```text
Epoch 9
```

---

## `autoencoder_scaler.pkl`

Contains the fitted `StandardScaler`.

This file is required because inference must apply the same scaling transformation that was used during training.

---

## `autoencoder_features.json`

Contains the exact list of 19 model features.

This file defines the feature order expected by the Autoencoder.

---

## `autoencoder_config.json`

Stores the model configuration, including:

```text
Model name
Input dimensions
Latent dimensions
Largest hidden layer
Encoder architecture
Decoder architecture
Activation
Optimizer
Learning rate
Loss
Requested epochs
Completed epochs
Batch size
Early-stopping patience
Random state
Training data definition
Threshold source
Final threshold
```

---

## `autoencoder_final_results.json`

Stores the final evaluation metrics, including:

```text
Threshold
Precision
Recall
F1-score
ROC-AUC
PR-AUC
True Negatives
False Positives
False Negatives
True Positives
False Positive Rate
False Negative Rate
```

---

# 36. Current Production Inference Contract

The serialized model should be used together with the scaler, feature list, and configuration.

The intended inference sequence is:

```text
Kafka JSON transaction
        ↓
Parse transaction
        ↓
Apply exact 19-feature engineering
        ↓
Apply exact feature ordering
        ↓
Apply autoencoder_scaler.pkl
        ↓
Load autoencoder_final.keras
        ↓
Reconstruct transaction
        ↓
Calculate reconstruction error
        ↓
Compare with frozen threshold
        ↓
Normal / Potential Fraud
```

The threshold currently stored by the experiment is:

```text
1.74720635
```

---

# 37. Streaming Integration

For the planned real-time financial fraud pipeline, the Autoencoder can conceptually sit behind Kafka and Spark:

```text
PaySim / Transaction Source
          ↓
       Kafka
          ↓
Spark Structured Streaming
          ↓
Validation / Parsing
          ↓
19-Feature Engineering
          ↓
StandardScaler
          ↓
Autoencoder
          ↓
Reconstruction Error
          ↓
Threshold = 1.74720635
          │
          ├───────────────┐
          ↓               ↓
      Normal         Potential Fraud
          ↓               ↓
      Cassandra       Fraud Alert Flow
                          ↓
                      RAG / LLM
                          ↓
                  Explanation / Context
                          ↓
                       Monitoring
```

The Autoencoder itself is responsible for generating the anomaly score.

A later RAG/LLM layer can provide contextual explanations for alerts, but it should not be confused with the anomaly detector.

---

# 38. Production Consistency Requirements

For reliable inference, the following must remain identical between training and streaming:

### Feature logic

The same formulas must be used.

### Feature order

The exact 19-feature order must be preserved.

### Transaction-type encoding

The same one-hot columns must be generated.

### Scaling

The saved training scaler must be used.

### Model

The saved `.keras` model must be loaded.

### Threshold

The stored threshold must be used consistently unless a new calibration experiment explicitly replaces it.

---

# 39. Important Limitations

This experiment has several limitations that should be recorded in a project or research review.

## 39.1 Dataset subset

The current experiment uses:

```text
500,000 transactions
```

rather than the full PaySim dataset.

Performance may change when the full dataset is used.

---

## 39.2 Severe class imbalance

Fraud represents only:

```text
0.0466%
```

of the loaded transactions.

This makes fraud-class metrics difficult and makes accuracy misleading as a standalone measure.

---

## 39.3 False negatives remain high

At the selected operating threshold:

```text
Recall : 23.40%
False Negative Rate : 76.60%
```

Because missing fraud is important in the intended application, this is a major limitation of the current Autoencoder configuration.

---

## 39.4 The 95% recall target was not achieved

The threshold search explicitly tested for a 95% recall operating point.

No tested threshold reached the target on the validation set.

---

## 39.5 Reconstruction error is not fraud probability

A high reconstruction error means:

```text
The transaction is difficult for the model to reconstruct
based on patterns learned from normal data.
```

It does not mean:

```text
There is exactly X% probability that this transaction is fraud.
```

---

## 39.6 Threshold sensitivity

Changing the threshold changes:

```text
Precision
Recall
False positives
False negatives
```

The selected value should therefore be treated as an operating point, not as an inherent property of the Autoencoder.

---

## 39.7 Synthetic dataset

PaySim is a synthetic financial transaction environment.

Real-world fraud patterns may differ from the patterns present in the simulated data.

---

# 40. Reproducibility

The experiment is intended to be reproducible using:

```text
Random state : 42
Rows         : 500,000
Split        : 60/20/20
Features     : 19
Scaler       : StandardScaler
Epochs       : 20 requested
Batch size   : 512
Learning rate: 0.001
Patience     : 3
Latent size  : 8
```

TensorFlow was successfully loaded in the recorded run:

```text
TensorFlow : 2.21.0
NumPy      : 2.2.6
Pandas     : 2.3.3
scikit-learn : 1.7.2
```

---

# 41. Run Instructions

From the project environment, open:

```text
Autoencoder_Model_Test.ipynb
```

Make sure the dataset is present at:

```text
data/
└── PS_20174392719_1491204439457_log.csv
```

Run the notebook sequentially from Block 1 through Block 15.

The notebook creates:

```text
models/
results/
```

and writes the Autoencoder artifacts described above.

---

# 42. Company / Research Review Summary

The current Autoencoder experiment demonstrates a complete anomaly-detection workflow:

```text
Raw transaction data
        ↓
Data quality validation
        ↓
Feature engineering
        ↓
Leakage-controlled split
        ↓
Normal-only training
        ↓
Standardization
        ↓
Deep Autoencoder
        ↓
Early stopping
        ↓
Reconstruction error
        ↓
Validation threshold selection
        ↓
Untouched test evaluation
        ↓
Error analysis
        ↓
Model serialization
```

The experiment is technically complete as a benchmark pipeline and produces reusable artifacts for later integration.

However, the current test results show that the Autoencoder still misses a substantial portion of fraudulent transactions at the selected threshold:

```text
Recall          : 23.40%
False negatives : 36 / 47
False-negative rate : 76.60%
```

The recorded ROC-AUC is higher:

```text
ROC-AUC = 0.9063
```

but the operating-point fraud recall remains limited.

This distinction is important:

```text
Good score ranking behavior
        ≠
High fraud detection recall at the chosen threshold
```

Therefore the current model should be treated as an evaluated experimental candidate rather than as a final production fraud detector.

---

# 43. Quick Reference

## Dataset

```text
PaySim
500,000-row experiment
11 raw columns
0.0466% fraud
```

## Model

```text
Deep Autoencoder
19 inputs
8-dimensional latent space
1024 largest hidden layer
ReLU hidden activations
Linear output
Batch Normalization
5% Dropout
L2 = 1e-5
Adam
Learning rate = 0.001
MSE loss
```

## Training

```text
Normal-only training
299,860 legitimate transactions
20 epochs requested
12 epochs completed
Best epoch = 9
Training time = 191.70 s
```

## Threshold

```text
Source = validation set
Method = best validation F1
Threshold = 1.74720635
95% recall target = not achieved
```

## Test results

```text
Precision = 0.1122
Recall    = 0.2340
F1        = 0.1517
ROC-AUC   = 0.9063
PR-AUC    = 0.1561

TN = 99,866
FP = 87
FN = 36
TP = 11
```

## Main artifacts

```text
models/autoencoder_final.keras
models/autoencoder_best.keras
models/autoencoder_scaler.pkl
models/autoencoder_features.json
models/autoencoder_config.json
results/autoencoder_final_results.json
```

---

# 44. Final Technical Takeaway

The Autoencoder experiment successfully implements unsupervised/semi-unsupervised anomaly detection by learning normal transaction patterns and using reconstruction error to identify unusual transactions.

The most important outcome is not the raw accuracy of the model, but the complete and reproducible pipeline around it:

```text
Consistent features
        +
Normal-only training
        +
Feature scaling
        +
Deep reconstruction model
        +
Validation threshold calibration
        +
Untouched test evaluation
        +
Serialized deployment artifacts
```

The current experiment establishes a solid baseline for further Autoencoder work, including testing alternative architectures, latent dimensions, regularization, training strategy, threshold calibration, and full-dataset experiments before any production deployment decision is made.
