import joblib
import pandas as pd

from sklearn.metrics import confusion_matrix, classification_report
from sklearn.model_selection import train_test_split


DATA_PATH = "data/PS_20174392719_1491204439457_log.csv"
MODEL_PATH = "src/isolation_forest_model.pkl"


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
    print("Loading model and dataset...")

    package = joblib.load(MODEL_PATH)

    model = package["model"]
    encoder = package["encoder"]

    df = pd.read_csv(DATA_PATH)

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

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
        stratify=y,
    )

    print("Calculating anomaly scores...")

    train_scores = model.decision_function(X_train)
    test_scores = model.decision_function(X_test)

    # Try several thresholds.
    thresholds = [
        0.05,
        0.00,
        -0.02,
        -0.05,
        -0.10,
        -0.15,
        -0.20,
    ]

    print("\nThreshold Evaluation:")

    for threshold in thresholds:

        y_pred = (test_scores < threshold).astype(int)

        cm = confusion_matrix(y_test, y_pred)

        tn, fp, fn, tp = cm.ravel()

        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0

        print(
            f"Threshold: {threshold:>5} | "
            f"TP: {tp:>4} | "
            f"FP: {fp:>5} | "
            f"FN: {fn:>4} | "
            f"Recall: {recall:.4f} | "
            f"Precision: {precision:.4f}"
        )

    print("\nDetailed evaluation using threshold -0.05:")

    threshold = -0.05

    y_pred = (test_scores < threshold).astype(int)

    print("\nConfusion Matrix:")
    print(confusion_matrix(y_test, y_pred))

    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, zero_division=0))


if __name__ == "__main__":
    evaluate_model()