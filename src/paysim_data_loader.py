import pandas as pd

DATA_PATH = "data/PS_20174392719_1491204439457_log.csv"


def load_transactions():
    """Load PaySim transaction data."""
    df = pd.read_csv(DATA_PATH)

    print("Dataset loaded successfully")
    print("Rows:", len(df))
    print("Columns:", len(df.columns))
    print("Fraud transactions:", df["isFraud"].sum())

    return df


if __name__ == "__main__":
    load_transactions()