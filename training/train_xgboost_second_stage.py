from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "PS_20174392719_1491204439457_log.csv"
MODEL_DIR = ROOT / "models"
RESULTS_DIR = ROOT / "results"
IF_MODEL_PATH = MODEL_DIR / "isolation_forest_final.pkl"
IF_CONFIG_PATH = MODEL_DIR / "isolation_forest_config.json"
IF_FEATURES_PATH = MODEL_DIR / "isolation_forest_features.json"
XGB_MODEL_PATH = MODEL_DIR / "xgboost_second_stage.json"
XGB_FEATURES_PATH = MODEL_DIR / "xgboost_second_stage_features.json"
XGB_CONFIG_PATH = MODEL_DIR / "xgboost_second_stage_config.json"
THRESHOLD_GRID = [0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
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


def load_if_artifacts() -> Tuple[object, Dict[str, float], List[str]]:
    if not IF_MODEL_PATH.exists():
        raise FileNotFoundError(f"Missing final Isolation Forest model: {IF_MODEL_PATH}")
    if not IF_CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing final Isolation Forest config: {IF_CONFIG_PATH}")
    with IF_CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    with IF_FEATURES_PATH.open("r", encoding="utf-8") as handle:
        features = json.load(handle)["feature_columns"]
    if len(features) != 33:
        raise ValueError(f"Expected exactly 33 IF features, got {len(features)}: {features}")
    if features != MODEL_FEATURE_COLUMNS:
        raise ValueError(f"IF feature list mismatch. Expected {MODEL_FEATURE_COLUMNS}, got {features}")
    thresholds = {name: float(config["thresholds"][name]) for name in ["T1", "T2", "T3", "T4"]}
    if not (thresholds["T1"] < thresholds["T2"] < thresholds["T3"] < thresholds["T4"]):
        raise ValueError(f"Threshold ordering invalid: {thresholds}")
    model = joblib.load(IF_MODEL_PATH)
    return model, thresholds, features


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
    for tx_type in ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]:
        out[f"type_{tx_type}"] = (out["type"] == tx_type).astype(int)
    return out


def compute_behavioral_features(df: pd.DataFrame) -> pd.DataFrame:
    processed: List[dict] = []
    for _, account_frame in df.sort_values(["nameOrig", "step"], kind="mergesort").groupby("nameOrig", sort=False):
        ordered = account_frame.sort_values(["step", "amount"], kind="mergesort").reset_index(drop=True)
        history_steps: List[int] = []
        history_amounts: List[float] = []
        history_destinations: List[str] = []
        history_types: List[str] = []
        last_step: int | None = None
        for _, row in ordered.iterrows():
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
            old_balance = float(row["oldbalanceOrg"])
            depletion_ratio = 0.0 if old_balance <= 0.0 else float(max(0.0, min(1.0, (old_balance - float(row["newbalanceOrig"])) / old_balance)))
            payload = row.to_dict()
            payload["orig_tx_count_1step"] = float(len(idx_1))
            payload["orig_tx_count_6steps"] = float(len(idx_6))
            payload["orig_tx_count_24steps"] = float(len(idx_24))
            payload["orig_amount_sum_6steps"] = float(np.sum(amounts_6)) if amounts_6 else 0.0
            payload["orig_amount_sum_24steps"] = float(np.sum(amounts_24)) if amounts_24 else 0.0
            payload["orig_avg_amount_6steps"] = avg_6
            payload["orig_avg_amount_24steps"] = avg_24
            payload["orig_amount_ratio_to_avg_24steps"] = amount_ratio
            payload["orig_time_since_prev_step"] = time_since_prev
            payload["orig_unique_destinations_24steps"] = unique_destinations
            payload["orig_cashout_count_24steps"] = cashout_count
            payload["orig_transfer_count_24steps"] = transfer_count
            payload["orig_new_destination"] = new_destination
            payload["orig_balance_depletion_ratio"] = depletion_ratio
            processed.append(payload)
            history_steps.append(current_step)
            history_amounts.append(current_amount)
            history_destinations.append(current_destination)
            history_types.append(current_type)
            last_step = current_step
    return pd.DataFrame(processed)


def load_dataset(limit_rows: int | None = None) -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, nrows=limit_rows)
    if "isFraud" not in df.columns:
        raise ValueError("Dataset missing isFraud label.")
    df = add_base_features(df)
    df = compute_behavioral_features(df)
    df = df.reset_index(drop=True)
    df["row_id"] = np.arange(len(df))
    return df.sort_values(["step", "amount"], kind="mergesort").reset_index(drop=True)


def compute_if_risk(frame: pd.DataFrame, model: object, feature_columns: List[str], thresholds: Dict[str, float]) -> pd.DataFrame:
    scores = -model.decision_function(frame[feature_columns].astype(float))
    t1, t2, t3, t4 = thresholds["T1"], thresholds["T2"], thresholds["T3"], thresholds["T4"]
    risk = np.select([
        scores < t1,
        scores < t2,
        scores < t3,
        scores < t4,
    ], ["L1", "L2", "L3", "L4"], default="L5")
    out = frame.copy()
    out["anomaly_score"] = scores
    out["risk_level"] = risk
    return out


def ranking_metrics(y_true: np.ndarray, y_scores: np.ndarray) -> Dict[str, float]:
    return {
        "pr_auc": float(average_precision_score(y_true, y_scores)),
        "roc_auc": float(roc_auc_score(y_true, y_scores)),
    }


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, split_ranking_metrics: Dict[str, float]) -> Dict[str, float]:
    return {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        **split_ranking_metrics,
        "false_positives": int(((1 - y_true) * y_pred).sum()),
        "false_negatives": int((y_true * (1 - y_pred)).sum()),
        "true_positives": int((y_true * y_pred).sum()),
        "true_negatives": int(((1 - y_true) * (1 - y_pred)).sum()),
        "fpr": float((((1 - y_true) * y_pred).sum()) / max((1 - y_true).sum(), 1)),
    }


def build_population_report(split_name: str, frame: pd.DataFrame) -> Dict[str, Any]:
    total_rows = int(len(frame))
    fraud_rows = int(frame["isFraud"].sum())
    legit_rows = total_rows - fraud_rows
    risk_counts = {risk: int((frame["risk_level"] == risk).sum()) for risk in ["L1", "L2", "L3", "L4", "L5"]}
    fraud_by_risk = {risk: int(frame.loc[frame["risk_level"] == risk, "isFraud"].sum()) for risk in ["L1", "L2", "L3", "L4", "L5"]}
    return {
        "split": split_name,
        "total_rows": total_rows,
        "fraud_rows": fraud_rows,
        "legitimate_rows": legit_rows,
        "L1_rows": risk_counts["L1"],
        "L2_rows": risk_counts["L2"],
        "L3_rows": risk_counts["L3"],
        "L4_rows": risk_counts["L4"],
        "L5_rows": risk_counts["L5"],
        "fraud_in_L1": fraud_by_risk["L1"],
        "fraud_in_L2": fraud_by_risk["L2"],
        "fraud_in_L3": fraud_by_risk["L3"],
        "fraud_in_L4": fraud_by_risk["L4"],
        "fraud_in_L5": fraud_by_risk["L5"],
    }


def main() -> None:
    MODEL_DIR.mkdir(exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)

    model, thresholds, feature_columns = load_if_artifacts()
    dataset = load_dataset(limit_rows=500_000)
    if len(dataset) == 0:
        raise ValueError("Loaded dataset is empty.")

    train_end = int(0.60 * len(dataset))
    valid_end = int(0.80 * len(dataset))
    train_df = dataset.iloc[:train_end].copy().reset_index(drop=True)
    valid_df = dataset.iloc[train_end:valid_end].copy().reset_index(drop=True)
    test_df = dataset.iloc[valid_end:].copy().reset_index(drop=True)

    train_if = compute_if_risk(train_df, model, feature_columns, thresholds)
    valid_if = compute_if_risk(valid_df, model, feature_columns, thresholds)
    test_if = compute_if_risk(test_df, model, feature_columns, thresholds)

    population_report = [
        build_population_report("train", train_if),
        build_population_report("validation", valid_if),
        build_population_report("test", test_if),
    ]
    (RESULTS_DIR / "cascade_population_report.json").write_text(json.dumps(population_report, indent=2), encoding="utf-8")
    pd.DataFrame(population_report).to_csv(RESULTS_DIR / "cascade_population_report.csv", index=False)

    validation_report = next(item for item in population_report if item["split"] == "validation")
    valid_l1_l2_fraud = validation_report["fraud_in_L1"] + validation_report["fraud_in_L2"]
    if validation_report["fraud_rows"] > 0 and valid_l1_l2_fraud == 0:
        raise ValueError(
            "Validation L1/L2 population contains zero fraud cases even though frozen IF evaluation indicates fraud should be present there. "
            f"Report: {validation_report}"
        )
    if validation_report["fraud_rows"] == 0:
        raise ValueError(
            "Validation split contains zero fraud rows. This is a data construction failure and XGBoost training cannot proceed. "
            f"Report: {validation_report}"
        )

    test_labels = test_if["isFraud"].astype(int).to_numpy()
    test_scores = test_if["anomaly_score"].to_numpy()
    if_only_alert = (test_scores >= thresholds["T2"]).astype(int)
    if_total_fraud = int(test_labels.sum())
    if_tp = int(((if_only_alert == 1) & (test_labels == 1)).sum())
    if_fn = int(((if_only_alert == 0) & (test_labels == 1)).sum())
    l1_fraud = int(test_if.loc[test_if["risk_level"].eq("L1"), "isFraud"].sum())
    l2_fraud = int(test_if.loc[test_if["risk_level"].eq("L2"), "isFraud"].sum())
    l3_l4_l5_fraud = int(test_if.loc[test_if["risk_level"].isin(["L3", "L4", "L5"]), "isFraud"].sum())
    l1_l2_total_rows = int(test_if.loc[test_if["risk_level"].isin(["L1", "L2"])].shape[0])
    if_false_negative_row_ids = test_if.loc[(test_labels == 1) & (if_only_alert == 0), "row_id"].tolist()
    print("IF test fraud total", if_total_fraud)
    print("IF test TP", if_tp)
    print("IF test FN", if_fn)
    print("L1 fraud count", l1_fraud)
    print("L2 fraud count", l2_fraud)
    print("L3/L4/L5 fraud count", l3_l4_l5_fraud)
    print("L1/L2 total rows", l1_l2_total_rows)
    print("IF false-negative row ids", if_false_negative_row_ids[:20])

    xgb_feature_columns = feature_columns + ["anomaly_score"]
    if len(xgb_feature_columns) != 34:
        raise ValueError(f"XGBoost feature vector must contain exactly 34 columns; got {len(xgb_feature_columns)}.")

    train_l12 = train_if[train_if["risk_level"].isin(["L1", "L2"])].copy().reset_index(drop=True)
    valid_l12 = valid_if[valid_if["risk_level"].isin(["L1", "L2"])].copy().reset_index(drop=True)
    test_l12 = test_if[test_if["risk_level"].isin(["L1", "L2"])].copy().reset_index(drop=True)
    if len(valid_l12) == 0:
        raise ValueError("Validation L1/L2 population is empty after frozen IF routing.")
    if int(valid_l12["isFraud"].sum()) == 0:
        raise ValueError("Validation L1/L2 population contains zero fraud cases. This is a data construction failure, not a threshold problem.")

    X_train = train_l12[xgb_feature_columns].astype(float)
    y_train = train_l12["isFraud"].astype(int).to_numpy()
    X_valid = valid_l12[xgb_feature_columns].astype(float)
    y_valid = valid_l12["isFraud"].astype(int).to_numpy()
    scale_pos_weight = float((y_train == 0).sum() / max((y_train == 1).sum(), 1))

    candidate_configs = [
        {"max_depth": 3, "learning_rate": 0.05, "n_estimators": 200, "subsample": 0.9, "colsample_bytree": 0.8, "min_child_weight": 1, "reg_lambda": 1.0, "reg_alpha": 0.1},
        {"max_depth": 3, "learning_rate": 0.08, "n_estimators": 150, "subsample": 0.9, "colsample_bytree": 0.8, "min_child_weight": 1, "reg_lambda": 1.0, "reg_alpha": 0.1},
        {"max_depth": 4, "learning_rate": 0.05, "n_estimators": 200, "subsample": 0.9, "colsample_bytree": 0.8, "min_child_weight": 1, "reg_lambda": 1.0, "reg_alpha": 0.1},
    ]

    best_model = None
    best_threshold = None
    best_cfg = None
    best_validation_metrics = None
    threshold_rows = []
    best_key = None
    for cfg_idx, cfg in enumerate(candidate_configs):
        clf = xgb.XGBClassifier(
            objective="binary:logistic",
            eval_metric="aucpr",
            scale_pos_weight=scale_pos_weight,
            random_state=42,
            tree_method="hist",
            **cfg,
        )
        clf.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], verbose=False)
        valid_prob = clf.predict_proba(X_valid)[:, 1]
        valid_ranking_metrics = ranking_metrics(y_valid, valid_prob)
        for threshold in THRESHOLD_GRID:
            pred = (valid_prob >= threshold).astype(int)
            metrics = {
                "config_index": cfg_idx,
                "hyperparameters": cfg,
                "threshold": float(threshold),
                **compute_metrics(y_valid, pred, valid_ranking_metrics),
            }
            threshold_rows.append(metrics)
            candidate_key = (metrics["recall"], metrics["f1"], -metrics["false_positives"], -metrics["false_negatives"])
            if best_key is None or candidate_key > best_key:
                best_key = candidate_key
                best_model = clf
                best_threshold = float(threshold)
                best_cfg = cfg.copy()
                best_validation_metrics = metrics.copy()

    if best_model is None:
        raise RuntimeError("Could not train a valid XGBoost model on the frozen L1/L2 population.")

    print("training rows", len(train_l12), "training fraud rows", int(y_train.sum()), "training legitimate rows", int((y_train == 0).sum()))
    print("validation rows", len(valid_l12), "validation fraud rows", int(y_valid.sum()), "validation legitimate rows", int((y_valid == 0).sum()))
    print("test rows", len(test_l12), "test fraud rows", int(test_l12["isFraud"].sum()), "test legitimate rows", int((test_l12["isFraud"] == 0).sum()))
    print("XGBoost validation fraud count", int(y_valid.sum()))
    print("XGBoost selected threshold", best_threshold)
    print("XGBoost selected config", best_cfg)
    print("XGBoost selected validation metrics", best_validation_metrics)

    best_model.save_model(str(XGB_MODEL_PATH))
    XGB_FEATURES_PATH.write_text(json.dumps({
        "model_version": "xgboost_second_stage_v1",
        "feature_count": len(xgb_feature_columns),
        "feature_columns": xgb_feature_columns,
    }, indent=2), encoding="utf-8")
    XGB_CONFIG_PATH.write_text(json.dumps({
        "model_version": "xgboost_second_stage_v1",
        "threshold": best_threshold,
        "feature_columns": xgb_feature_columns,
        "threshold_policy": "validation_max_recall_then_f1_then_min_false_positives_then_min_false_negatives",
        "selected_config": best_cfg,
        "scale_pos_weight": scale_pos_weight,
        "validation_rows": int(len(valid_l12)),
        "test_rows": int(len(test_l12)),
        "selected_validation_metrics": best_validation_metrics,
    }, indent=2), encoding="utf-8")

    test_l12_prob = best_model.predict_proba(test_l12[xgb_feature_columns].astype(float))[:, 1]
    test_l12_pred = (test_l12_prob >= best_threshold).astype(int)
    full_test_alert = if_only_alert.copy()
    l12_positions = np.flatnonzero(test_if["risk_level"].isin(["L1", "L2"]).to_numpy())
    full_test_alert[l12_positions] = test_l12_pred

    final_y = test_if["isFraud"].astype(int).to_numpy()
    final_tp = int(((full_test_alert == 1) & (final_y == 1)).sum())
    final_fp = int(((full_test_alert == 1) & (final_y == 0)).sum())
    final_tn = int(((full_test_alert == 0) & (final_y == 0)).sum())
    final_fn = int(((full_test_alert == 0) & (final_y == 1)).sum())
    final_precision = float(precision_score(final_y, full_test_alert, zero_division=0))
    final_recall = float(recall_score(final_y, full_test_alert, zero_division=0))
    final_f1 = float(f1_score(final_y, full_test_alert, zero_division=0))
    final_fpr = float(final_fp / max(final_fp + final_tn, 1))
    fn_reduction = if_fn - final_fn
    fn_reduction_pct = ((fn_reduction / if_fn) * 100.0) if if_fn > 0 else 0.0
    xgb_recovered = int(((if_only_alert == 0) & (full_test_alert == 1) & (final_y == 1)).sum())

    cascade_result = {
        "if_only": {
            "TP": if_tp,
            "FP": int(((if_only_alert == 1) & (final_y == 0)).sum()),
            "TN": int(((if_only_alert == 0) & (final_y == 0)).sum()),
            "FN": if_fn,
            "precision": float(precision_score(final_y, if_only_alert, zero_division=0)),
            "recall": float(recall_score(final_y, if_only_alert, zero_division=0)),
            "f1": float(f1_score(final_y, if_only_alert, zero_division=0)),
            "fpr": float((((final_y == 0) & (if_only_alert == 1)).sum()) / max((final_y == 0).sum(), 1)),
            "alerts": int(if_only_alert.sum()),
        },
        "cascade": {
            "TP": final_tp,
            "FP": final_fp,
            "TN": final_tn,
            "FN": final_fn,
            "precision": final_precision,
            "recall": final_recall,
            "f1": final_f1,
            "fpr": final_fpr,
            "alerts": int(full_test_alert.sum()),
        },
        "xgboost_l12": {
            "test_rows": int(len(test_l12)),
            "fraud_rows": int(test_l12["isFraud"].sum()),
            "legitimate_rows": int((test_l12["isFraud"] == 0).sum()),
            "TP": int(((test_l12_pred == 1) & (test_l12["isFraud"].astype(int).to_numpy() == 1)).sum()),
            "FN": int(((test_l12_pred == 0) & (test_l12["isFraud"].astype(int).to_numpy() == 1)).sum()),
            "recovered_fraud": xgb_recovered,
        },
        "fn_reduction": fn_reduction,
        "fn_reduction_pct": fn_reduction_pct,
        "selected_threshold": best_threshold,
        "selected_model_version": "xgboost_second_stage_v1",
        "feature_columns": xgb_feature_columns,
        "feature_count": len(xgb_feature_columns),
    }
    (RESULTS_DIR / "cascade_evaluation.json").write_text(json.dumps(cascade_result, indent=2), encoding="utf-8")
    pd.DataFrame([{
        "IF_test_fraud_total": if_total_fraud,
        "IF_test_TP": if_tp,
        "IF_test_FN": if_fn,
        "L1_fraud_count": l1_fraud,
        "L2_fraud_count": l2_fraud,
        "L3_L4_L5_fraud_count": l3_l4_l5_fraud,
        "L1_L2_total_rows": l1_l2_total_rows,
        "xgboost_recovered_fraud": xgb_recovered,
        "final_FN": final_fn,
        "final_recall": final_recall,
        "final_precision": final_precision,
        "final_f1": final_f1,
        "final_fpr": final_fpr,
        "fn_reduction": fn_reduction,
        "fn_reduction_pct": fn_reduction_pct,
    }]).to_csv(RESULTS_DIR / "cascade_test_results.csv", index=False)
    pd.DataFrame(threshold_rows).to_csv(RESULTS_DIR / "xgboost_thresholds.csv", index=False)
    (RESULTS_DIR / "xgboost_validation_results.json").write_text(json.dumps({
        "model_version": "xgboost_second_stage_v1",
        "feature_columns": xgb_feature_columns,
        "feature_count": len(xgb_feature_columns),
        "selected_threshold": best_threshold,
        "selected_config": best_cfg,
        "scale_pos_weight": scale_pos_weight,
        "validation_fraud_rows": int(y_valid.sum()),
        "validation_rows": int(len(y_valid)),
        "selected_validation_metrics": best_validation_metrics,
        "threshold_candidates": threshold_rows,
    }, indent=2), encoding="utf-8")

    print(json.dumps({
        "cascade_population_report": population_report,
        "if_test_baseline": {
            "total_fraud": if_total_fraud,
            "TP": if_tp,
            "FN": if_fn,
            "L1_fraud_count": l1_fraud,
            "L2_fraud_count": l2_fraud,
            "L3_L4_L5_fraud_count": l3_l4_l5_fraud,
            "L1_L2_total_rows": l1_l2_total_rows,
        },
        "xgboost_validation_fraud_rows": int(y_valid.sum()),
        "selected_threshold": best_threshold,
        "xgb_recovered_fraud": xgb_recovered,
        "fn_reduction": fn_reduction,
        "fn_reduction_pct": fn_reduction_pct,
        "final_cascade_metrics": cascade_result["cascade"],
    }, indent=2))


if __name__ == "__main__":
    main()
