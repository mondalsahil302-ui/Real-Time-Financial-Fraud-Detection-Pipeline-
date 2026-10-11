import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import confusion_matrix, classification_report
from sklearn.model_selection import train_test_split


DATA_PATH = "data/PS_20174392719_1491204439457_log.csv"
MODEL_PATH = "src/autoencoder_model.pkl"


def create_features(df):
    features = pd.DataFrame(index=df.index)

    features["amount"] = df["amount"]
    features["oldbalanceOrg"] = df["oldbalanceOrg"]
    features["newbalanceOrig"] = df["newbalanceOrig"]
    features["oldbalanceDest"] = df["oldbalanceDest"]
    features["newbalanceDest"] = df["newbalanceDest"]

    features["origin_balance_change"] = (
        df["oldbalanceOrg"] - df["newbalanceOrig"]
    )

    features["destination_balance_change"] = (
        df["newbalanceDest"] - df["oldbalanceDest"]
    )

    features["amount_to_origin_balance"] = (
        df["amount"] / (df["oldbalanceOrg"] + 1)
    )

    features["amount_to_destination_balance"] = (
        df["amount"] / (df["oldbalanceDest"] + 1)
    )

    features["origin_difference"] = (
        df["amount"] - features["origin_balance_change"]
    )

    features["destination_difference"] = (
        df["amount"] - features["destination_balance_change"]
    )

    return features


def evaluate_model():

    print("Loading Autoencoder and dataset...")

    package = joblib.load(MODEL_PATH)

    model = package["model"]
    encoder = package["encoder"]
    scaler = package["scaler"]

    columns = [
        "type",
        "amount",
        "oldbalanceOrg",
        "newbalanceOrig",
        "oldbalanceDest",
        "newbalanceDest",
        "isFraud",
    ]

    df = pd.read_csv(DATA_PATH, usecols=columns)

    y = df["isFraud"].astype(int)

    X_numeric = create_features(df)

    X_type = encoder.transform(df[["type"]])

    X = pd.concat(
        [
            X_numeric.reset_index(drop=True),
            pd.DataFrame(
                X_type,
                columns=encoder.get_feature_names_out(["type"]),
            ),
        ],
        axis=1,
    )

    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.fillna(0)

    X_scaled = scaler.transform(X)

    # First split: 80% development, 20% final test
    X_dev, X_test, y_dev, y_test = train_test_split(
        X_scaled,
        y,
        test_size=0.20,
        random_state=42,
        stratify=y,
    )

    # Second split: development -> training + validation
    X_train, X_val, y_train, y_val = train_test_split(
        X_dev,
        y_dev,
        test_size=0.20,
        random_state=42,
        stratify=y_dev,
    )

    print("Training samples:", len(X_train))
    print("Validation samples:", len(X_val))
    print("Test samples:", len(X_test))

    print("\nCalculating validation reconstruction errors...")

    val_reconstructed = model.predict(X_val)

    val_error = np.mean(
        np.square(X_val - val_reconstructed),
        axis=1,
    )

    # Select threshold on validation data.
    # Test several percentile thresholds.
    percentiles = [99, 99.2, 99.4, 99.6, 99.8, 99.9, 99.95]

    print("\nValidation Threshold Selection")
    print("-" * 80)

    best_threshold = None
    best_f1 = -1

    for percentile in percentiles:

        threshold = np.percentile(val_error, percentile)

        y_val_pred = (val_error > threshold).astype(int)

        tn, fp, fn, tp = confusion_matrix(
            y_val,
            y_val_pred
        ).ravel()

        precision = tp / (tp + fp) if (tp + fp) else 0
        recall = tp / (tp + fn) if (tp + fn) else 0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall)
            else 0
        )

        print(
            f"Percentile: {percentile:>6} | "
            f"Threshold: {threshold:.6f} | "
            f"TP: {tp:4d} | "
            f"FP: {fp:5d} | "
            f"FN: {fn:4d} | "
            f"Recall: {recall:.4f} | "
            f"Precision: {precision:.4f} | "
            f"F1: {f1:.4f}"
        )

        if f1 > best_f1:
            best_f1 = f1
            best_threshold = threshold

    print("\nSelected validation threshold:", best_threshold)

    # Final evaluation on completely unseen test data
    print("\nEvaluating on final test data...")

    test_reconstructed = model.predict(X_test)

    test_error = np.mean(
        np.square(X_test - test_reconstructed),
        axis=1,
    )

    y_test_pred = (test_error > best_threshold).astype(int)

    print("\nFinal Confusion Matrix:")
    print(confusion_matrix(y_test, y_test_pred))

    print("\nFinal Classification Report:")
    print(
        classification_report(
            y_test,
            y_test_pred,
            zero_division=0,
        )
    )


if __name__ == "__main__":
    evaluate_model()