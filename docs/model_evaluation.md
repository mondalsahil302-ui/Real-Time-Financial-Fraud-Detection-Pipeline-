\# Model Evaluation



\## Autoencoder



The Autoencoder was evaluated on the final test set.



| Metric | Result |

|---|---:|

| True Positives | 594 |

| False Positives | 642 |

| False Negatives | 1,049 |

| Recall | 36.23% |

| Precision | 48.06% |

| F1-score | 0.41 |



\### Interpretation



\- True Positive: Actual fraud correctly detected.

\- False Positive: Normal transaction incorrectly flagged as fraud.

\- False Negative: Actual fraud missed by the model.

\- Recall measures how many actual fraud transactions were detected.

\- Precision measures how many flagged transactions were actually fraud.



\## Isolation Forest



At the selected evaluation threshold of `-0.05`:



| Metric | Result |

|---|---:|

| True Positives | 0 |

| False Positives | 31 |

| False Negatives | 1,643 |

| Recall | 0% |

| Precision | 0% |



\## Summary



The Autoencoder detected more actual fraud transactions than the Isolation Forest baseline in the evaluated test results.

