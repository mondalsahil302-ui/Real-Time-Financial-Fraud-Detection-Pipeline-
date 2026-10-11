import joblib
import pandas as pd

from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder


DATA_PATH = "data/PS_20174392719_1491204439457_log.csv"
MODEL_PATH = "src/isolation_forest_model.pkl"


def create_features(df):
    """Create numerical and categorical features for fraud detection."""

    features = pd.DataFrame(index=df.index)

    # Original numerical features
    features["amount"] = df["amount"]
    features["oldbalanceOrg"] = df["oldbalanceOrg"]
    features["newbalanceOrig"] = df["newbalanceOrig"]
    features["oldbalanceDest"] = df["oldbalanceDest"]
    features["newbalanceDest"] = df["newbalanceDest"]

    # Derived balance features
    features["origin_balance_change"] = (
        df["oldbalanceOrg"] - df["newbalanceOrig"]
    )

    features["destination_balance_change"] = (
        df["newbalanceDest"] - df["oldbalanceDest"]
    )

    # Transaction amount relative to sender balance
    features["amount_to_origin_balance"] = (
        df["amount"] / (df["oldbalanceOrg"] + 1)
    )

    # Transaction amount relative to destination balance
    features["amount_to_destination_balance"] = (
        df["amount"] / (df["oldbalanceDest"] + 1)
    )

    # Difference between transaction amount and sender balance change
    features["origin_difference"] = (
        df["amount"] - features["origin_balance_change"]
    )

    # Difference between transaction amount and destination balance change
    features["destination_difference"] = (
        df["amount"] - features["destination_balance_change"]
    )

    return features


def train_model():
    print("Loading PaySim dataset...")

    df = pd.read_csv(DATA_PATH)

    y = df["isFraud"].astype(int)

    # Create engineered numerical features
    X_numeric = create_features(df)

    # Encode transaction type
    encoder = OneHotEncoder(
        handle_unknown="ignore",
        sparse_output=False
    )

    X_type = encoder.fit_transform(df[["type"]])

    # Combine numerical and categorical features
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

    print("Training rows:", len(X_train))
    print("Testing rows:", len(X_test))
    print("Features:", X.shape[1])

    print("Training Isolation Forest...")

    model = IsolationForest(
        n_estimators=100,
        contamination=0.0013,
        random_state=42,
        n_jobs=-1,
    )

    # Unsupervised training — fraud labels are not used
    model.fit(X_train)

    joblib.dump(
        {
            "model": model,
            "encoder": encoder,
        },
        MODEL_PATH,
    )

    print("Model trained successfully.")
    print("Model saved to:", MODEL_PATH)


if __name__ == "__main__":
    train_model()