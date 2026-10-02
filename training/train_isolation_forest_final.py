from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "PS_20174392719_1491204439457_log.csv"
MODEL_DIR = ROOT / "models"
RESULTS_DIR = ROOT / "results"

BASE_FEATURE_COLUMNS: List[str] = [
    "step",
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
    "orig_balance_change",
    "dest_balance_change",
    "orig_balance_error",
    "dest_balance_error",
    "orig_zero_after",
    "dest_zero_before",
    "dest_zero_after",
    "log_amount",
    "type_CASH_IN",
    "type_CASH_OUT",
    "type_DEBIT",
    "type_PAYMENT",
    "type_TRANSFER",
]
BEHAVIORAL_FEATURE_COLUMNS: List[str] = [
    "orig_tx_count_1step",
    "orig_tx_count_6steps",
    "orig_tx_count_24steps",
    "orig_amount_sum_6steps",
    "orig_amount_sum_24steps",
    "orig_avg_amount_6steps",
    "orig_avg_amount_24steps",
    "orig_amount_ratio_to_avg_24steps",
    "orig_time_since_prev_step",
    "orig_unique_destinations_24steps",
    "orig_cashout_count_24steps",
    "orig_transfer_count_24steps",
    "orig_new_destination",
    "orig_balance_depletion_ratio",
]
MODEL_FEATURE_COLUMNS: List[str] = BASE_FEATURE_COLUMNS + BEHAVIORAL_FEATURE_COLUMNS
FORBIDDEN_MODEL_COLUMNS = {"isFraud", "isFlaggedFraud", "nameOrig", "nameDest"}


def add_base_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["orig_balance_change"] = out["oldbalanceOrg"] - out["newbalanceOrig"]
    out["dest_balance_change"] = out["newbalanceDest"] - out["oldbalanceDest"]
    out["orig_balance_error"] = out["amount"] - out["orig_balance_change"]
    out["dest_balance_error"] = out["amount"] - out["dest_balance_change"]
    out["orig_zero_after"] = (out["newbalanceOrig"] == 0.0).astype(int)
    out["dest_zero_before"] = (out["oldbalanceDest"] == 0.0).astype(int)
    out["dest_zero_after"] = (out["newbalanceDest"] == 0.0).astype(int)
    out["log_amount"] = np.log1p(out["amount"])
    for txn_type in ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]:
        out[f"type_{txn_type}"] = (out["type"] == txn_type).astype(int)
    return out


def compute_behavioral_features(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, account_frame in df.sort_values(["nameOrig", "step"], kind="mergesort").groupby("nameOrig", sort=False):
        account_frame = account_frame.sort_values(["step", "amount"], kind="mergesort").reset_index(drop=True)
        history_steps: List[int] = []
        history_amounts: List[float] = []
        history_destinations: List[str] = []
        history_types: List[str] = []
        last_step: int | None = None

        for _, row in account_frame.iterrows():
            current_step = int(row["step"])
            current_amount = float(row["amount"])
            current_destination = str(row["nameDest"])
            current_type = str(row["type"])

            idx_1 = [i for i, prev_step in enumerate(history_steps) if current_step - prev_step <= 1]
            idx_6 = [i for i, prev_step in enumerate(history_steps) if current_step - prev_step <= 6]
            idx_24 = [i for i, prev_step in enumerate(history_steps) if current_step - prev_step <= 24]

            amounts_6 = [history_amounts[i] for i in idx_6]
            amounts_24 = [history_amounts[i] for i in idx_24]
            destinations_24 = [history_destinations[i] for i in idx_24]
            types_24 = [history_types[i] for i in idx_24]

            avg_6 = float(np.mean(amounts_6)) if amounts_6 else 0.0
            avg_24 = float(np.mean(amounts_24)) if amounts_24 else 0.0
            amount_ratio = float(current_amount / avg_24) if avg_24 > 0 else 0.0
            unique_destinations = float(len(set(destinations_24))) if destinations_24 else 0.0
            new_destination = float(current_destination not in set(destinations_24))
            cashout_count = float(sum(tx_type == "CASH_OUT" for tx_type in types_24))
            transfer_count = float(sum(tx_type == "TRANSFER" for tx_type in types_24))
            time_since_prev = float(max(0, current_step - last_step)) if last_step is not None else 0.0

            depletion_ratio = 0.0
            old_balance = float(row["oldbalanceOrg"])
            if old_balance > 0:
                depletion_ratio = float(max(0.0, min(1.0, (old_balance - float(row["newbalanceOrig"])) / old_balance)))

            row_payload = row.to_dict()
            row_payload["orig_tx_count_1step"] = float(len(idx_1))
            row_payload["orig_tx_count_6steps"] = float(len(idx_6))
            row_payload["orig_tx_count_24steps"] = float(len(idx_24))
            row_payload["orig_amount_sum_6steps"] = float(np.sum(amounts_6)) if amounts_6 else 0.0
            row_payload["orig_amount_sum_24steps"] = float(np.sum(amounts_24)) if amounts_24 else 0.0
            row_payload["orig_avg_amount_6steps"] = avg_6
            row_payload["orig_avg_amount_24steps"] = avg_24
            row_payload["orig_amount_ratio_to_avg_24steps"] = amount_ratio
            row_payload["orig_time_since_prev_step"] = time_since_prev
            row_payload["orig_unique_destinations_24steps"] = unique_destinations
            row_payload["orig_cashout_count_24steps"] = cashout_count
            row_payload["orig_transfer_count_24steps"] = transfer_count
            row_payload["orig_new_destination"] = new_destination
            row_payload["orig_balance_depletion_ratio"] = depletion_ratio
            rows.append(row_payload)

            history_steps.append(current_step)
            history_amounts.append(current_amount)
            history_destinations.append(current_destination)
            history_types.append(current_type)
            last_step = current_step

    result = pd.DataFrame(rows)
    return result


def load_data(limit_rows: int | None = None) -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, nrows=limit_rows)
    if "isFraud" not in df.columns:
        raise ValueError("Dataset does not contain isFraud label")
    df = add_base_features(df)
    df = compute_behavioral_features(df)
    df = df.sort_values(["step", "amount"], kind="mergesort").reset_index(drop=True)
    return df


def assert_contract(columns: List[str]) -> None:
    if len(columns) != 33:
        raise ValueError(f"Expected 33 model features, got {len(columns)}")
    if columns != MODEL_FEATURE_COLUMNS:
        raise ValueError(f"Feature contract mismatch. Expected {MODEL_FEATURE_COLUMNS} but got {columns}")
    forbidden = sorted(set(columns).intersection(FORBIDDEN_MODEL_COLUMNS))
    if forbidden:
        raise ValueError(f"Forbidden columns present: {forbidden}")


def score_to_risk(scores: np.ndarray, thresholds: Dict[str, float]) -> np.ndarray:
    t1 = float(thresholds["T1"])
    t2 = float(thresholds["T2"])
    t3 = float(thresholds["T3"])
    t4 = float(thresholds["T4"])
    return np.select([
        scores < t1,
        scores < t2,
        scores < t3,
        scores < t4,
    ], ["L1", "L2", "L3", "L4"], default="L5")


def threshold_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    return {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "false_positives": int(((1 - y_true) * y_pred).sum()),
        "false_negatives": int((y_true * (1 - y_pred)).sum()),
        "true_positives": int((y_true * y_pred).sum()),
        "true_negatives": int(((1 - y_true) * (1 - y_pred)).sum()),
    }


def ranking_metrics(y_true: np.ndarray, y_scores: np.ndarray) -> Dict[str, float]:
    return {
        "pr_auc": float(average_precision_score(y_true, y_scores)),
        "roc_auc": float(roc_auc_score(y_true, y_scores)),
    }


def build_thresholds(valid_scores: np.ndarray, valid_labels: np.ndarray) -> Dict[str, float]:
    legit_scores = valid_scores[valid_labels == 0]
    caps = [0.01, 0.005, 0.001, 0.0005]
    thresholds = {}
    for idx, cap in enumerate(caps, start=1):
        thresholds[f"T{idx}"] = float(np.quantile(legit_scores, 1.0 - cap))
    if not (thresholds["T1"] < thresholds["T2"] < thresholds["T3"] < thresholds["T4"]):
        raise ValueError(f"Threshold ordering invalid: {thresholds}")
    return thresholds


def main() -> None:
    MODEL_DIR.mkdir(exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)

    df = load_data(limit_rows=500_000)
    assert_contract(MODEL_FEATURE_COLUMNS)

    n = len(df)
    train_end = int(0.60 * n)
    valid_end = int(0.80 * n)
    train_df = df.iloc[:train_end].copy()
    valid_df = df.iloc[train_end:valid_end].copy()
    test_df = df.iloc[valid_end:].copy()

    train_legit = train_df[train_df["isFraud"] == 0]
    model = IsolationForest(
        n_estimators=500,
        max_samples=0.5,
        max_features=1.0,
        contamination="auto",
        bootstrap=False,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(train_legit[MODEL_FEATURE_COLUMNS].astype(float))

    valid_scores = -model.decision_function(valid_df[MODEL_FEATURE_COLUMNS].astype(float))
    thresholds = build_thresholds(valid_scores, valid_df["isFraud"].to_numpy())
    test_scores = -model.decision_function(test_df[MODEL_FEATURE_COLUMNS].astype(float))
    valid_ranking_metrics = ranking_metrics(valid_df["isFraud"].to_numpy(), valid_scores)
    test_ranking_metrics = ranking_metrics(test_df["isFraud"].to_numpy(), test_scores)

    config = {
        "model_version": "isolation_forest_33_feature_v1",
        "model_type": "IsolationForest",
        "model_path": "models/isolation_forest_final.pkl",
        "feature_columns": MODEL_FEATURE_COLUMNS,
        "anomaly_score_definition": "-model.decision_function(X)",
        "higher_score_means_more_anomalous": True,
        "score_is_probability": False,
        "thresholds": thresholds,
        "risk_mapping": {
            "L1": "score < T1",
            "L2": "T1 <= score < T2",
            "L3": "T2 <= score < T3",
            "L4": "T3 <= score < T4",
            "L5": "score >= T4",
        },
        "training": {
            "train_rows": int(len(train_df)),
            "validation_rows": int(len(valid_df)),
            "test_rows": int(len(test_df)),
            "random_state": 42,
            "note": "Isolation Forest is unsupervised; labels are used only for validation and final evaluation.",
        },
    }

    feature_manifest = {
        "model_version": config["model_version"],
        "feature_count": len(MODEL_FEATURE_COLUMNS),
        "feature_columns": MODEL_FEATURE_COLUMNS,
        "forbidden_model_columns": sorted(FORBIDDEN_MODEL_COLUMNS),
        "anomaly_score_definition": config["anomaly_score_definition"],
        "higher_score_means_more_anomalous": True,
        "score_is_probability": False,
    }

    joblib.dump(model, MODEL_DIR / "isolation_forest_final.pkl")
    (MODEL_DIR / "isolation_forest_features.json").write_text(json.dumps(feature_manifest, indent=2), encoding="utf-8")
    (MODEL_DIR / "isolation_forest_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    validation_rows = []
    for threshold_name, threshold in thresholds.items():
        y_pred = (valid_scores >= threshold).astype(int)
        metrics = {**valid_ranking_metrics, **threshold_metrics(valid_df["isFraud"].to_numpy(), y_pred)}
        validation_rows.append({"split": "validation", "threshold_name": threshold_name, "threshold": float(threshold), **metrics})

    test_rows = []
    for threshold_name, threshold in thresholds.items():
        y_pred = (test_scores >= threshold).astype(int)
        metrics = {**test_ranking_metrics, **threshold_metrics(test_df["isFraud"].to_numpy(), y_pred)}
        test_rows.append({"split": "test", "threshold_name": threshold_name, "threshold": float(threshold), **metrics})

    payload = {
        "model_version": "isolation_forest_33_feature_v1",
        "dataset_rows": int(len(df)),
        "thresholds": thresholds,
        "validation_threshold_metrics": validation_rows,
        "test_threshold_metrics": test_rows,
        "feature_contract": feature_manifest,
    }
    (RESULTS_DIR / "isolation_forest_final_results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("=== Isolation Forest artifact generation complete ===")
    print(f"Model file: {MODEL_DIR / 'isolation_forest_final.pkl'}")
    print(f"Feature count: {len(MODEL_FEATURE_COLUMNS)}")
    print(f"Thresholds: {thresholds}")


if __name__ == "__main__":
    main()
