# Final Model Selection — PaySim Fraud Detection

## 1. Final Selected Model

### **Isolation Forest**

Based on the recorded comparison between the two implemented experiments, **Isolation Forest is selected as the current final model for the real-time fraud-detection pipeline**.

This selection is based on the measured operating metrics and computational results from the comparison notebook, with particular attention to the project's requirement to reduce missed fraudulent transactions (false negatives).

> **Important:** This is the selected model for the current experiment and test protocol. It is not a claim that Isolation Forest is universally superior to Autoencoders for every fraud-detection problem.

--
# 2. Why Isolation Forest Was Selected 

1. **Isolation Forest detected more fraudulent transactions:** 15 true positives versus 11 for the Autoencoder.
2. **It produced fewer false negatives:** 32 missed fraud cases versus 36, which is important because missed fraud is a critical risk in this project.
3. **It achieved higher recall:** 31.91% versus 23.40%, meaning it captured a larger share of the fraud cases in the test set.
4. **It achieved higher precision:** 14.85% versus 11.22%, so a larger proportion of its generated alerts were actual fraud in this experiment.
5. **It achieved a higher F1-score:** 20.27% versus 15.17%, giving better balance between precision and recall at the selected thresholds.
6. **It achieved a higher PR-AUC:** 19.50% versus 15.61%, which is particularly relevant for this highly imbalanced fraud-detection dataset.
7. **It produced slightly fewer false positives:** 86 versus 87, while simultaneously producing fewer false negatives.
8. **It trained much faster:** 16.77 seconds versus 191.70 seconds for the Autoencoder, reducing experimentation and retraining cost.
9. **It demonstrated measured real-time characteristics:** about 0.0625 ms/transaction latency and about 15,997 transactions/second throughput in the recorded test.
10. **Although the Autoencoder had the higher ROC-AUC (0.9063 vs 0.8569), Isolation Forest performed better at the selected operating point and better matched the project's false-negative and real-time requirements.**

---

# 3. Final Comparison

| Metric | Isolation Forest | Autoencoder | Selected |
|---|---:|---:|---|
| Precision | 0.1485 | 0.1122 | Isolation Forest |
| Recall | 0.3191 | 0.2340 | Isolation Forest |
| F1-score | 0.2027 | 0.1517 | Isolation Forest |
| PR-AUC | 0.1950 | 0.1561 | Isolation Forest |
| ROC-AUC | 0.8569 | **0.9063** | Autoencoder |
| True Positives | **15** | 11 | Isolation Forest |
| False Positives | **86** | 87 | Isolation Forest |
| False Negatives | **32** | 36 | Isolation Forest |
| False Negative Rate | **0.6809** | 0.7660 | Isolation Forest |
| Training Time (sec) | **16.77** | 191.70 | Isolation Forest |
| Inference Latency (ms/transaction) | **0.0625** | Not recorded | Isolation Forest |
| Throughput (transactions/sec) | **15,996.75** | Not recorded | Isolation Forest |

### Important interpretation

The comparison notebook explicitly records that the **operating thresholds are model-specific** and should not be compared numerically:

```text
Isolation Forest threshold = 0.107197
Autoencoder threshold     = 1.747206
```

These numbers are on different score scales:

```text
Isolation Forest → isolation/anomaly score

Autoencoder     → reconstruction error
```

Therefore, the lower numerical value of one threshold does not make that model better.

---

# 4. Fraud-Capture Comparison

The test set contained:

```text
Actual fraud cases = 47
```

### Isolation Forest

```text
Detected fraud (TP) = 15
Missed fraud (FN)   = 32
Recall              = 31.91%
```

### Autoencoder

```text
Detected fraud (TP) = 11
Missed fraud (FN)   = 36
Recall              = 23.40%
```

For the project's stated priority of reducing missed fraud, the current experiment provides stronger operating results for Isolation Forest.

---

# 5. False-Negative Focus

False negatives represent fraudulent transactions that were classified as legitimate.

The recorded results are:

```text
Isolation Forest:
FN = 32
FNR = 68.09%

Autoencoder:
FN = 36
FNR = 76.60%
```

The difference is:

```text
4 fewer missed fraud cases
```

in the recorded 100,000-row test set.

The relative improvement should not be overstated: both models still miss a substantial number of fraud cases at their selected operating thresholds.

---

# 6. Why Recall and False Negatives Matter

This project is designed for financial fraud detection.

A false negative means:

```text
Fraudulent transaction
        ↓
Model does not flag it
        ↓
Potential fraud passes through the first detection layer
```

Therefore, a model that improves recall and reduces false negatives can be operationally important.

At the same time, the system cannot simply maximize recall without considering false positives, because excessive alerts can overload investigators and downstream alert-handling systems.

The current selection therefore considers the combined evidence:

```text
Recall
+
False negatives
+
Precision
+
F1
+
PR-AUC
+
Operational speed
```

rather than a single metric.

---

# 7. ROC-AUC Exception

The Autoencoder achieved the higher ROC-AUC:

```text
Autoencoder     = 0.9063
Isolation Forest = 0.8569
```

This is important and should be reported.

ROC-AUC measures ranking performance over many possible thresholds. The final model, however, operates at a specific threshold and is intended for real-time alert generation.

At the selected operating points in this experiment:

```text
Isolation Forest
→ higher recall
→ fewer false negatives
→ higher precision
→ higher F1
→ higher PR-AUC
```

The decision is therefore based on the project's operating requirements rather than ROC-AUC alone.

---

# 8. Precision-Recall Consideration

The dataset is extremely imbalanced, with fraud representing only a very small fraction of transactions.

Recorded PR-AUC:

```text
Isolation Forest = 0.19496
Autoencoder      = 0.15606
```

Isolation Forest therefore produced the stronger precision-recall profile in this experiment.

PR-AUC is especially informative here because the project is concerned with identifying a rare fraud class rather than simply separating a large legitimate class.

---

# 9. Computational Comparison

## Isolation Forest

```text
Training time            = 16.7669 seconds
Test inference time      = 6.2513 seconds
Latency                  = 0.0625 ms/transaction
Throughput               = 15,996.75 transactions/second
```

## Autoencoder

```text
Training time            = 191.7006 seconds
Inference latency        = Not recorded
Throughput               = Not recorded
```

The recorded computational evidence therefore strongly supports Isolation Forest for the current real-time implementation.

The comparison notebook does not provide directly measured Autoencoder latency or throughput, so no conclusion should be made from those missing values.

---

# 10. Model Characteristics

| Dimension | Isolation Forest | Autoencoder |
|---|---|---|
| Model family | Tree ensemble | Deep neural network |
| Learning mechanism | Isolation-based | Reconstruction-based |
| Anomaly score | Isolation score | Reconstruction error |
| Main tuning areas | Trees, sample size, feature sampling | Layers, latent dimension, learning rate, epochs |
| Scaling | Generally less sensitive | Important for neural-network training |
| Engineering profile | Fast anomaly detection | Deep non-linear representation learning |

The two models solve the anomaly-detection problem using different mechanisms, so their score distributions and threshold scales are naturally different.

---

# 11. Experiment Scope and Comparability

The comparison notebook reports the following:

```text
Rows loaded       : 500,000 for both
Number of features: 19 for both
Validation rows   : 100,000 for both
Test rows         : 100,000 for both
```

The notebook also flags a training-data difference:

```text
Isolation Forest training rows: 300,000
Autoencoder training rows    : 299,860
```

The reason is that the Autoencoder is trained only on normal transactions, and the Isolation Forest experiment explicitly records both total training rows and normal-only training rows.

This difference should be acknowledged in a research or company review. The reported comparison is useful for model selection within the current project, but a final scientific benchmark should keep every training condition fully identical.

---

# 12. Final Selection Decision

## Selected:

# **Isolation Forest**

The selection is supported by the current experiment because it:

```text
captures more fraud cases
        ↓
misses fewer fraud cases
        ↓
has higher recall
        ↓
has higher precision
        ↓
has higher F1
        ↓
has higher PR-AUC
        ↓
trains substantially faster
        ↓
has measured low-latency / high-throughput inference
```

The Autoencoder remains an important benchmark because it achieved a higher ROC-AUC and demonstrates a different anomaly-detection approach.

It should be retained as a comparison model rather than discarded from the research record.

---

# 13. Final System Position

The selected production-oriented flow is:

```text
Transaction Source
       ↓
Kafka: transactions
       ↓
Spark Structured Streaming
       ↓
Validation / Parsing
       ↓
19-Feature Engineering
       ↓
Serialized Isolation Forest
       ↓
Anomaly Score
       ↓
Operating Threshold
       │
       ├──────────────→ Normal
       │
       └──────────────→ Potential Fraud
                              ↓
                       fraud-alerts topic
                              ↓
                           Cassandra
                              ↓
                       RAG / LLM Layer
                              ↓
                    Explanation / Context
                              ↓
                         Monitoring
```

The RAG/LLM layer is an explanation and investigation-support layer. It is not replacing the Isolation Forest fraud detector.

---

# 14. Recommended Next Stage

The selection of Isolation Forest should be treated as the **current model-selection decision**, after which development should move to:

```text
Model selection
      ↓
Model serialization validation
      ↓
Streaming inference integration
      ↓
Kafka → Spark → Isolation Forest
      ↓
Threshold-based alert generation
      ↓
Cassandra persistence
      ↓
Fraud-alerts topic
      ↓
RAG / LLM explanation
      ↓
Monitoring and evaluation
```

Before production deployment, the selected model should be re-evaluated on a larger/full dataset and under a clearly defined operating target, especially because the current recall and false-negative rate are still limited.

---

# 15. One-Paragraph Final Statement

**Isolation Forest is selected as the current final fraud-detection model because, under the recorded comparison protocol, it detected more fraudulent transactions, produced fewer false negatives, achieved higher recall, precision, F1-score, and PR-AUC, and trained substantially faster than the Autoencoder. It also has measured low inference latency and high throughput for the planned real-time pipeline. The Autoencoder achieved a higher ROC-AUC, so it remains a meaningful benchmark, but its selected operating point produced fewer detected fraud cases and more missed fraud cases. The current decision therefore favors Isolation Forest based on the project's operational focus on fraud capture, false-negative reduction, and real-time processing.**

---

# 16. Final Reference Numbers

```text
                ISOLATION FOREST     AUTOENCODER
--------------------------------------------------
Precision              0.1485           0.1122
Recall                 0.3191           0.2340
F1-score               0.2027           0.1517
PR-AUC                 0.1950           0.1561
ROC-AUC                0.8569           0.9063

TP                         15               11
FP                         86               87
FN                         32               36
TN                     99,867           99,866

Training time (s)       16.77            191.70
Latency (ms/txn)        0.0625              N/A
Throughput (txn/s)   15,996.75              N/A
```

## Final Selected Model

```text
Isolation Forest
```

## Selection Basis

```text
Fraud recall
False-negative count
Precision
F1-score
PR-AUC
Real-time computational performance
```
