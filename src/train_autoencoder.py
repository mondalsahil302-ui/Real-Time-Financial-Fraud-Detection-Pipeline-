import joblib
import numpy as np
import pandas as pd

from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.neural_network import MLPRegressor


DATA_PATH = "data/PS_20174392719_1491204439457_log.csv"
MODEL_PATH = "src/autoencoder_model.pkl"


def create_features(df):
    """Create numerical features for fraud detection."""

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


def train_autoencoder():

    print("Loading PaySim dataset...")

    columns = [
        "type",
        "amount",
        "oldbalanceOrg",
        "newbalanceOrig",
        "oldbalanceDest",
        "newbalanceDest",
        "isFraud",
    ]

    df = pd.read_csv(
        DATA_PATH,
        usecols=columns
    )

    print("Total rows:", len(df))

    # Use only normal transactions for training
    normal_df = df[df["isFraud"] == 0].copy()

    # Use 500,000 normal transactions
    normal_df = normal_df.sample(
        n=min(500000, len(normal_df)),
        random_state=42
    )

    print(
        "Normal transactions used for training:",
        len(normal_df)
    )

    # Create numerical features
    X_numeric = create_features(normal_df)

    # Encode transaction type
    encoder = OneHotEncoder(
        handle_unknown="ignore",
        sparse_output=False
    )

    X_type = encoder.fit_transform(
        normal_df[["type"]]
    )

    # Combine numerical and categorical features
    X = pd.concat(
        [
            X_numeric.reset_index(drop=True),
            pd.DataFrame(
                X_type,
                columns=encoder.get_feature_names_out(["type"])
            ),
        ],
        axis=1,
    )

    # Handle invalid values
    X = X.replace(
        [np.inf, -np.inf],
        np.nan
    )

    X = X.fillna(0)

    # Scale features
    scaler = StandardScaler()

    X_scaled = scaler.fit_transform(X)

    print(
        "Training features:",
        X_scaled.shape[1]
    )

    print("Training Autoencoder...")

    model = MLPRegressor(
        hidden_layer_sizes=(32, 16, 32),
        activation="relu",
        solver="adam",
        batch_size=256,
        learning_rate_init=0.001,
        max_iter=30,
        random_state=42,
        verbose=True,
    )

    model.fit(
        X_scaled,
        X_scaled
    )

    # Threshold selected using validation data
    threshold = 0.04557055612619186

    joblib.dump(
        {
            "model": model,
            "encoder": encoder,
            "scaler": scaler,
            "threshold": threshold,
        },
        MODEL_PATH,
    )

    print("\nAutoencoder trained successfully.")
    print("Model saved to:", MODEL_PATH)
    print("Detection threshold:", threshold)


if __name__ == "__main__":
    train_autoencoder()