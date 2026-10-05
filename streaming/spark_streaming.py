from __future__ import annotations

import json
import gc
import os
import sys
import time
from bisect import bisect_left
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from dotenv import load_dotenv

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, from_json, lit, log1p, struct, to_json, when
from pyspark.sql.streaming.state import GroupStateTimeout
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)


# ============================================================
# PROJECT PATHS
# ============================================================

# File:
#   project/
#       .env
#       models/
#       data/
#       checkpoints/
#       streaming/
#           spark_streaming.py
#
# Therefore parent.parent is the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag.metrics import DURATION as PROM_DURATION, count as metric_count, start_metrics_server

load_dotenv(PROJECT_ROOT / ".env")


def configure_windows_hadoop() -> None:
    """Expose local Hadoop native components before the JVM starts."""
    if os.name != "nt":
        return

    configured_home = os.getenv("HADOOP_HOME")
    if not configured_home:
        raise RuntimeError(
            "Windows Spark requires HADOOP_HOME to point to a Hadoop native "
            "installation containing bin\\hadoop.dll and bin\\winutils.exe. "
            "Set HADOOP_HOME in the process environment or project .env."
        )

    hadoop_home = Path(configured_home).expanduser().resolve()
    bin_dir = hadoop_home / "bin"
    dll_path = bin_dir / "hadoop.dll"
    winutils_path = bin_dir / "winutils.exe"
    missing = [str(path) for path in (dll_path, winutils_path) if not path.is_file()]
    if missing:
        raise RuntimeError(
            "Windows Hadoop native support is incomplete. Missing: "
            + ", ".join(missing)
            + ". Install native binaries built for the Hadoop version bundled "
            "with this PySpark installation; do not use an unverified build."
        )

    # Java inherits the Python process environment at JVM creation time.
    os.environ["HADOOP_HOME"] = str(hadoop_home)
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
    print(f"HADOOP_HOME = {hadoop_home}")
    print(f"Hadoop bin = {bin_dir}")
    print(f"hadoop.dll = {dll_path}")
    print(f"winutils.exe = {winutils_path}")


configure_windows_hadoop()

# Use the active interpreter for Spark workers instead of relying on a
# separate `python3` command, which is commonly absent on Windows.
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


def resolve_project_path(
    raw_path: str | None,
    default_relative: str,
) -> Path:
    """
    Resolve paths from .env relative to the project root.

    Windows compatibility:
    Spark's typical Unix default /tmp is mapped back into
    the project checkpoints directory instead of trying to use
    an invalid Windows /tmp path.
    """
    if not raw_path:
        return PROJECT_ROOT / default_relative

    normalized = raw_path.strip()

    if os.name == "nt" and (
        normalized == "/tmp"
        or normalized.startswith("/tmp/")
    ):
        return PROJECT_ROOT / default_relative

    path = Path(normalized)

    if path.is_absolute():
        return path

    return PROJECT_ROOT / path


# ============================================================
# ENVIRONMENT / KAFKA CONFIGURATION
# ============================================================

KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:9092",
)

TRANSACTIONS_TOPIC = os.getenv(
    "TRANSACTIONS_TOPIC",
    "transactions",
)

LOW_RISK_TOPIC = os.getenv(
    "LOW_RISK_TOPIC",
    "low-risk-transactions",
)

FRAUD_ALERTS_TOPIC = os.getenv(
    "FRAUD_ALERTS_TOPIC",
    "fraud-alerts",
)

SPARK_APP_NAME = os.getenv(
    "SPARK_APP_NAME",
    "fraud-detection-risk-router",
)

CHECKPOINT_ROOT = resolve_project_path(
    os.getenv(
        "SPARK_CHECKPOINT_DIR",
        "./checkpoints",
    ),
    "checkpoints",
)

# IMPORTANT:
# New checkpoint namespace because the previous v3/v4 layouts
# may contain incompatible ArrayType state.
RISK_CHECKPOINT_DIR = (
    CHECKPOINT_ROOT
    / "transactions_risk_33_v5_jsonstate"
)


# ============================================================
# MODEL ARTIFACT PATHS
# ============================================================

MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "isolation_forest_final.pkl"
)

FEATURES_PATH = (
    PROJECT_ROOT
    / "models"
    / "isolation_forest_features.json"
)

CONFIG_PATH = (
    PROJECT_ROOT
    / "models"
    / "isolation_forest_config.json"
)

XGBOOST_MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "xgboost_second_stage.json"
)

XGBOOST_FEATURES_PATH = (
    PROJECT_ROOT
    / "models"
    / "xgboost_second_stage_features.json"
)

XGBOOST_CONFIG_PATH = (
    PROJECT_ROOT
    / "models"
    / "xgboost_second_stage_config.json"
)


# ============================================================
# MODEL FEATURE CONTRACT
# ============================================================

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


MODEL_FEATURE_COLUMNS: List[str] = (
    BASE_FEATURE_COLUMNS
    + BEHAVIORAL_FEATURE_COLUMNS
)


FORBIDDEN_MODEL_COLUMNS = {
    "isFraud",
    "isFlaggedFraud",
    "nameOrig",
    "nameDest",
}


# ============================================================
# SPARK STATE SCHEMA
# ============================================================

# CRITICAL FIX:
#
# DO NOT use:
#
# StructField("steps", ArrayType(...))
# StructField("amounts", ArrayType(...))
# ...
#
# The previous implementation did exactly that and the Python
# worker failed in ArrayType.fromJson() with:
#
#     KeyError: 'elementType'
#
# Instead Spark stores ONE scalar String field. The history
# arrays live INSIDE that string as JSON.
#
# This keeps Spark's state schema:
#
#     struct<history_json:string>
#
# and therefore completely removes ArrayType from the Spark
# state contract.
STATE_SCHEMA_DDL = "history_json string"


# ============================================================
# INPUT TRANSACTION SCHEMA
# ============================================================

transaction_schema = StructType([
    StructField("transaction_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("source", StringType(), True),
    # Control Center correlation metadata; not included in model features.
    StructField("batch_id", StringType(), True),
    StructField("producer_sequence", IntegerType(), True),

    StructField("step", IntegerType(), True),
    StructField("event_step", IntegerType(), True),

    StructField("type", StringType(), True),
    StructField("amount", DoubleType(), True),

    StructField("nameOrig", StringType(), True),

    StructField(
        "oldbalanceOrg",
        DoubleType(),
        True,
    ),

    StructField(
        "newbalanceOrig",
        DoubleType(),
        True,
    ),

    StructField("nameDest", StringType(), True),

    StructField(
        "oldbalanceDest",
        DoubleType(),
        True,
    ),

    StructField(
        "newbalanceDest",
        DoubleType(),
        True,
    ),

    # Retained ONLY for evaluation/audit.
    # They are not part of the model features.
    StructField("isFraud", IntegerType(), True),
    StructField(
        "isFlaggedFraud",
        IntegerType(),
        True,
    ),
])


# ============================================================
# BEHAVIOR OUTPUT SCHEMA
# ============================================================

behavior_output_schema = StructType([
    StructField("transaction_id", StringType(), True),
    StructField("event_time", StringType(), True),
    StructField("source", StringType(), True),
    StructField("batch_id", StringType(), True),
    StructField("producer_sequence", IntegerType(), True),

    StructField("step", IntegerType(), True),
    StructField("event_step", IntegerType(), True),

    StructField("type", StringType(), True),
    StructField("amount", DoubleType(), True),

    StructField("nameOrig", StringType(), True),

    StructField(
        "oldbalanceOrg",
        DoubleType(),
        True,
    ),

    StructField(
        "newbalanceOrig",
        DoubleType(),
        True,
    ),

    StructField("nameDest", StringType(), True),

    StructField(
        "oldbalanceDest",
        DoubleType(),
        True,
    ),

    StructField(
        "newbalanceDest",
        DoubleType(),
        True,
    ),

    StructField(
        "kafka_topic",
        StringType(),
        True,
    ),

    StructField(
        "kafka_partition",
        IntegerType(),
        True,
    ),

    StructField(
        "kafka_offset",
        LongType(),
        True,
    ),

    StructField(
        "kafka_timestamp",
        TimestampType(),
        True,
    ),

    StructField(
        "kafka_key",
        StringType(),
        True,
    ),

    StructField(
        "isFraud",
        IntegerType(),
        True,
    ),

    StructField(
        "isFlaggedFraud",
        IntegerType(),
        True,
    ),

    *[
        StructField(feature, DoubleType(), True)
        for feature in BASE_FEATURE_COLUMNS
        if feature not in {
            "step",
            "amount",
            "oldbalanceOrg",
            "newbalanceOrig",
            "oldbalanceDest",
            "newbalanceDest",
        }
    ],

    *[
        StructField(
            feature,
            DoubleType(),
            True,
        )
        for feature in BEHAVIORAL_FEATURE_COLUMNS
    ],
])


# ============================================================
# MODEL ARTIFACT LOADING
# ============================================================

def load_runtime_artifacts(
) -> Tuple[
    Any,
    Dict[str, Any],
    Dict[str, float],
]:
    """
    Load and validate the final Isolation Forest artifacts.
    """

    required = [
        MODEL_PATH,
        FEATURES_PATH,
        CONFIG_PATH,
    ]

    missing = [
        str(path)
        for path in required
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Required Isolation Forest artifacts are missing:\n"
            + "\n".join(
                f"  - {path}"
                for path in missing
            )
        )

    with FEATURES_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:
        feature_payload = json.load(handle)

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:
        config = json.load(handle)

    saved_features = feature_payload.get(
        "feature_columns",
        [],
    )

    config_features = config.get(
        "feature_columns",
        [],
    )

    if saved_features != MODEL_FEATURE_COLUMNS:
        raise ValueError(
            "Feature file contract mismatch.\n"
            f"Expected:\n{MODEL_FEATURE_COLUMNS}\n"
            f"Got:\n{saved_features}"
        )

    if config_features != MODEL_FEATURE_COLUMNS:
        raise ValueError(
            "Config feature list mismatch.\n"
            f"Expected:\n{MODEL_FEATURE_COLUMNS}\n"
            f"Got:\n{config_features}"
        )

    forbidden_present = sorted(
        set(saved_features)
        .intersection(FORBIDDEN_MODEL_COLUMNS)
    )

    if forbidden_present:
        raise ValueError(
            "Forbidden columns are present in the "
            f"model feature contract: {forbidden_present}"
        )

    if len(MODEL_FEATURE_COLUMNS) != 33:
        raise ValueError(
            "Expected exactly 33 model features, "
            f"got {len(MODEL_FEATURE_COLUMNS)}"
        )

    thresholds = config.get("thresholds")

    if not isinstance(thresholds, dict):
        raise ValueError(
            "Isolation Forest config is missing "
            "a valid thresholds object."
        )

    threshold_names = [
        "T1",
        "T2",
        "T3",
        "T4",
    ]

    for name in threshold_names:
        if name not in thresholds:
            raise ValueError(
                f"Threshold {name} is missing."
            )

    ordered_thresholds = {
        name: float(thresholds[name])
        for name in threshold_names
    }

    if not (
        ordered_thresholds["T1"]
        < ordered_thresholds["T2"]
        < ordered_thresholds["T3"]
        < ordered_thresholds["T4"]
    ):
        raise ValueError(
            "Threshold ordering is invalid: "
            f"{ordered_thresholds}"
        )

    allowed_score_definitions = {
        "-model.decision_function(X)",
        "-IsolationForest.decision_function(X)",
    }

    if config.get(
        "anomaly_score_definition"
    ) not in allowed_score_definitions:
        raise ValueError(
            "Anomaly score definition must be "
            "negative Isolation Forest decision_function."
        )

    model = joblib.load(MODEL_PATH)

    feature_count = getattr(
        model,
        "n_features_in_",
        None,
    )

    if (
        feature_count is not None
        and int(feature_count) != 33
    ):
        raise ValueError(
            "The loaded Isolation Forest does not "
            "accept 33 features. "
            f"n_features_in_={feature_count}"
        )

    return (
        model,
        config,
        ordered_thresholds,
    )


def load_xgboost_runtime_artifacts(
) -> Tuple[
    Any,
    Dict[str, Any],
    List[str],
    float,
]:
    """
    Load and validate the second-stage XGBoost model.
    """

    if not XGBOOST_MODEL_PATH.exists():
        raise FileNotFoundError(
            "XGBoost model missing: "
            f"{XGBOOST_MODEL_PATH}"
        )

    if not XGBOOST_FEATURES_PATH.exists():
        raise FileNotFoundError(
            "XGBoost features missing: "
            f"{XGBOOST_FEATURES_PATH}"
        )

    if not XGBOOST_CONFIG_PATH.exists():
        raise FileNotFoundError(
            "XGBoost config missing: "
            f"{XGBOOST_CONFIG_PATH}"
        )

    with XGBOOST_FEATURES_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:
        feature_payload = json.load(handle)

    xgb_feature_columns = feature_payload.get(
        "feature_columns",
        [],
    )

    expected_xgb_features = (
        MODEL_FEATURE_COLUMNS
        + ["anomaly_score"]
    )

    if xgb_feature_columns != expected_xgb_features:
        raise ValueError(
            "XGBoost feature contract mismatch.\n"
            f"Expected:\n{expected_xgb_features}\n"
            f"Got:\n{xgb_feature_columns}"
        )

    with XGBOOST_CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:
        config = json.load(handle)

    threshold = float(
        config.get(
            "threshold",
            0.5,
        )
    )

    model = xgb.XGBClassifier()
    model.load_model(
        str(XGBOOST_MODEL_PATH)
    )

    return (
        model,
        config,
        xgb_feature_columns,
        threshold,
    )


# ============================================================
# LOAD LIGHTWEIGHT DRIVER-SIDE CONFIG
# ============================================================
# IMPORTANT: We load ONLY the config/thresholds/feature-lists here on
# the driver.  The actual model *objects* (Isolation Forest, XGBoost)
# are NOT loaded here and are NOT broadcast.  They are loaded lazily
# inside each Python worker by spark_worker_model.py.
#
# This is the fix for the Windows page-file / JVM OOM crash:
# a 313 MB serialised pickle must never travel through Spark's
# task-serialization path.

(
    _,          # model object – intentionally discarded on the driver
    RUNTIME_CONFIG,
    THRESHOLDS,
) = load_runtime_artifacts()

MODEL_VERSION = str(
    RUNTIME_CONFIG.get(
        "model_version",
        "isolation_forest_33_feature_v1",
    )
)

# Discard the driver-side IF model object immediately so it cannot
# accidentally end up in a task closure.
del _
gc.collect()


(
    _xgb_model_discard,   # discarded – only loaded in workers
    XGB_CONFIG,
    XGB_FEATURE_COLUMNS,
    XGB_THRESHOLD,
) = load_xgboost_runtime_artifacts()

# Discard the driver-side XGBoost model object immediately.
del _xgb_model_discard
gc.collect()

print(f"[driver] Thresholds loaded: T1={THRESHOLDS['T1']:.4f} T2={THRESHOLDS['T2']:.4f} T3={THRESHOLDS['T3']:.4f} T4={THRESHOLDS['T4']:.4f}")
print(f"[driver] XGBoost threshold: {XGB_THRESHOLD}")
print("[driver] Model objects discarded from driver – workers load from disk lazily.")



# ============================================================
# START SPARK
# ============================================================

spark = (
    SparkSession.builder
    .appName(SPARK_APP_NAME)
    .master(os.getenv("SPARK_MASTER", "local[2]"))
    .config(
        "spark.jars.packages",
        "org.apache.spark:spark-sql-kafka-0-10_2.13:4.2.0",
    )
    .config(
        "spark.jars.ivy",
        str(PROJECT_ROOT / ".spark-ivy"),
    )
    .config(
        "spark.sql.execution.arrow.pyspark.enabled",
        "true",
    )
    .config(
        "spark.sql.shuffle.partitions",
        "2",
    )
    .config(
        "spark.python.worker.reuse",
        "true",
    )
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

spark.sparkContext.addPyFile(
    str(PROJECT_ROOT / "streaming" / "spark_worker_model.py")
)


# ============================================================
# HARD RUNTIME CONTRACT CHECK
# ============================================================

if STATE_SCHEMA_DDL.strip().lower() != (
    "history_json string"
):
    raise RuntimeError(
        "Unexpected Spark state schema: "
        f"{STATE_SCHEMA_DDL!r}"
    )


# These prints are deliberately explicit so that we can see
# which version of the state implementation is really running.
print()
print("=" * 80)
print("RUNTIME STATE CONTRACT")
print("=" * 80)
print(
    f"STATE_SCHEMA_DDL = {STATE_SCHEMA_DDL}"
)
print(
    f"CHECKPOINT = {RISK_CHECKPOINT_DIR}"
)
print(
    "Spark state type = scalar String JSON"
)
print(
    "ArrayType state = DISABLED"
)
print("=" * 80)
print()

# ============================================================
# STATE -> HISTORY
# ============================================================

def _state_to_history(
    state: Any,
) -> Tuple[
    List[int],
    List[float],
    List[str],
    List[str],
    int | None,
]:
    """
    Read Spark's single String state field and decode
    the JSON rolling history.

    State format:

    {
        "steps": [...],
        "amounts": [...],
        "destinations": [...],
        "types": [...],
        "last_step": 123
    }
    """

    if not state.exists:
        return (
            [],
            [],
            [],
            [],
            None,
        )

    raw = state.get

    raw_json = (
        raw[0]
        if raw
        and raw[0]
        else "{}"
    )

    try:
        payload = json.loads(
            raw_json
        )
    except (
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(
            "Invalid fraud account state JSON: "
            f"{raw_json!r}"
        ) from exc

    steps = [
        int(value)
        for value in payload.get(
            "steps",
            [],
        )
    ]

    amounts = [
        float(value)
        for value in payload.get(
            "amounts",
            [],
        )
    ]

    destinations = [
        str(value)
        for value in payload.get(
            "destinations",
            [],
        )
    ]

    tx_types = [
        str(value)
        for value in payload.get(
            "types",
            [],
        )
    ]

    last_step_raw = payload.get(
        "last_step"
    )

    last_step = (
        None
        if last_step_raw is None
        else int(last_step_raw)
    )

    if not (
        len(steps)
        == len(amounts)
        == len(destinations)
        == len(tx_types)
    ):
        raise ValueError(
            "Fraud account state contains "
            "history fields with different lengths."
        )

    return (
        steps,
        amounts,
        destinations,
        tx_types,
        last_step,
    )


# ============================================================
# STATEFUL BEHAVIORAL FEATURE ENGINEERING
# ============================================================

def add_behavioral_features_stateful(
    key: Tuple[Any, ...],
    pdf_iterator: Iterator[pd.DataFrame],
    state: Any,
) -> Iterator[pd.DataFrame]:
    """
    Build historical behavioral features per originating account.

    Important:
    The current transaction is NOT inserted into history until
    after its own behavioral features are calculated.

    That prevents current-row leakage.
    """

    # Processing-time timeout handling.
    if state.hasTimedOut:
        state.remove()
        return

    frames = [
        pdf
        for pdf in pdf_iterator
        if pdf is not None
        and not pdf.empty
    ]

    if not frames:
        return

    pdf = pd.concat(
        frames,
        ignore_index=True,
    )

    # Deterministic ordering within the micro-batch.
    pdf = (
        pdf.sort_values(
            [
                "step",
                "kafka_partition",
                "kafka_offset",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    (
        history_steps,
        history_amounts,
        history_destinations,
        history_types,
        last_step,
    ) = _state_to_history(state)

    behavioral = {
        feature: []
        for feature in BEHAVIORAL_FEATURE_COLUMNS
    }

    # --------------------------------------------------------
    # Process each transaction using PRIOR history only.
    # --------------------------------------------------------

    for _, row in pdf.iterrows():

        current_step = int(
            row["step"]
        )

        current_amount = float(
            row["amount"]
        )

        current_dest = str(
            row["nameDest"]
        )

        current_type = str(
            row["type"]
        )

        # ----------------------------------------------------
        # Retain only relevant prior history.
        # ----------------------------------------------------

        cutoff = (
            current_step - 24
        )

        if history_steps:

            keep_from = bisect_left(
                history_steps,
                cutoff,
            )

            if keep_from > 0:
                history_steps = (
                    history_steps[keep_from:]
                )

                history_amounts = (
                    history_amounts[keep_from:]
                )

                history_destinations = (
                    history_destinations[
                        keep_from:
                    ]
                )

                history_types = (
                    history_types[
                        keep_from:
                    ]
                )

        # ----------------------------------------------------
        # Window indices based ONLY on prior history.
        # ----------------------------------------------------

        idx_1 = [
            idx
            for idx, previous_step
            in enumerate(history_steps)
            if current_step - previous_step <= 1
        ]

        idx_6 = [
            idx
            for idx, previous_step
            in enumerate(history_steps)
            if current_step - previous_step <= 6
        ]

        idx_24 = [
            idx
            for idx, previous_step
            in enumerate(history_steps)
            if current_step - previous_step <= 24
        ]

        amounts_6 = [
            history_amounts[idx]
            for idx in idx_6
        ]

        amounts_24 = [
            history_amounts[idx]
            for idx in idx_24
        ]

        destinations_24 = [
            history_destinations[idx]
            for idx in idx_24
        ]

        types_24 = [
            history_types[idx]
            for idx in idx_24
        ]

        # ----------------------------------------------------
        # Statistics
        # ----------------------------------------------------

        avg_6 = (
            float(
                np.mean(amounts_6)
            )
            if amounts_6
            else 0.0
        )

        avg_24 = (
            float(
                np.mean(amounts_24)
            )
            if amounts_24
            else 0.0
        )

        amount_ratio = (
            current_amount / avg_24
            if avg_24 > 0
            else 0.0
        )

        unique_destinations = (
            float(
                len(
                    set(destinations_24)
                )
            )
            if destinations_24
            else 0.0
        )

        new_destination = float(
            current_dest
            not in set(destinations_24)
        )

        cashout_count = float(
            sum(
                tx_type == "CASH_OUT"
                for tx_type in types_24
            )
        )

        transfer_count = float(
            sum(
                tx_type == "TRANSFER"
                for tx_type in types_24
            )
        )

        time_since_prev = (
            float(
                max(
                    0,
                    current_step
                    - history_steps[-1],
                )
            )
            if history_steps
            else 0.0
        )

        # ----------------------------------------------------
        # Balance depletion
        # ----------------------------------------------------

        old_balance_org = float(
            row["oldbalanceOrg"]
        )

        new_balance_orig = float(
            row["newbalanceOrig"]
        )

        depletion_ratio = 0.0

        if old_balance_org > 0.0:

            depletion_ratio = float(
                max(
                    0.0,
                    min(
                        1.0,
                        (
                            old_balance_org
                            - new_balance_orig
                        )
                        / old_balance_org,
                    ),
                )
            )

        # ----------------------------------------------------
        # Store behavioral features.
        # ----------------------------------------------------

        behavioral[
            "orig_tx_count_1step"
        ].append(
            float(len(idx_1))
        )

        behavioral[
            "orig_tx_count_6steps"
        ].append(
            float(len(idx_6))
        )

        behavioral[
            "orig_tx_count_24steps"
        ].append(
            float(len(idx_24))
        )

        behavioral[
            "orig_amount_sum_6steps"
        ].append(
            (
                float(np.sum(amounts_6))
                if amounts_6
                else 0.0
            )
        )

        behavioral[
            "orig_amount_sum_24steps"
        ].append(
            (
                float(np.sum(amounts_24))
                if amounts_24
                else 0.0
            )
        )

        behavioral[
            "orig_avg_amount_6steps"
        ].append(
            avg_6
        )

        behavioral[
            "orig_avg_amount_24steps"
        ].append(
            avg_24
        )

        behavioral[
            "orig_amount_ratio_to_avg_24steps"
        ].append(
            amount_ratio
        )

        behavioral[
            "orig_time_since_prev_step"
        ].append(
            time_since_prev
        )

        behavioral[
            "orig_unique_destinations_24steps"
        ].append(
            unique_destinations
        )

        behavioral[
            "orig_cashout_count_24steps"
        ].append(
            cashout_count
        )

        behavioral[
            "orig_transfer_count_24steps"
        ].append(
            transfer_count
        )

        behavioral[
            "orig_new_destination"
        ].append(
            new_destination
        )

        behavioral[
            "orig_balance_depletion_ratio"
        ].append(
            depletion_ratio
        )

        # ----------------------------------------------------
        # Add CURRENT transaction to history only AFTER
        # behavioral features were computed.
        # ----------------------------------------------------

        history_steps.append(
            current_step
        )

        history_amounts.append(
            current_amount
        )

        history_destinations.append(
            current_dest
        )

        history_types.append(
            current_type
        )

        last_step = current_step

    # ========================================================
    # RETAIN LAST 24 STEPS
    # ========================================================

    if history_steps:

        latest_step = (
            history_steps[-1]
        )

        final_cutoff = (
            latest_step - 24
        )

        keep_from = bisect_left(
            history_steps,
            final_cutoff,
        )

        history_steps = (
            history_steps[keep_from:]
        )

        history_amounts = (
            history_amounts[keep_from:]
        )

        history_destinations = (
            history_destinations[
                keep_from:
            ]
        )

        history_types = (
            history_types[
                keep_from:
            ]
        )

    # ========================================================
    # SERIALIZE STATE INTO ONE STRING
    # ========================================================

    state_payload = {
        "steps": [
            int(value)
            for value in history_steps
        ],
        "amounts": [
            float(value)
            for value in history_amounts
        ],
        "destinations": [
            str(value)
            for value in history_destinations
        ],
        "types": [
            str(value)
            for value in history_types
        ],
        "last_step": (
            None
            if last_step is None
            else int(last_step)
        ),
    }

    state.update(
        (
            json.dumps(
                state_payload,
                separators=(",", ":"),
            ),
        )
    )

    state.setTimeoutDuration(24 * 60 * 60 * 1000)

    # ========================================================
    # OUTPUT
    # ========================================================

    output = pdf.copy()

    for feature in BEHAVIORAL_FEATURE_COLUMNS:

        output[feature] = behavioral[
            feature
        ]

    yield output[
        [
            field.name
            for field
            in behavior_output_schema.fields
        ]
    ]


# ============================================================
# KAFKA STREAM
# ============================================================

raw_stream = (
    spark.readStream
    .format("kafka")
    .option(
        "kafka.bootstrap.servers",
        KAFKA_BOOTSTRAP_SERVERS,
    )
    .option(
        "subscribe",
        TRANSACTIONS_TOPIC,
    )
    .option(
        "startingOffsets",
        os.getenv("SPARK_STARTING_OFFSETS", "earliest"),
    )
    .option(
        "maxOffsetsPerTrigger",
        os.getenv("SPARK_MAX_OFFSETS_PER_TRIGGER", "500"),
    )
    .option(
        "failOnDataLoss",
        "false",
    )
    .load()
)


# ============================================================
# PARSE KAFKA JSON
# ============================================================

parsed_stream = (
    raw_stream
    .select(
        col("topic").alias(
            "kafka_topic"
        ),
        col("partition").alias(
            "kafka_partition"
        ),
        col("offset").alias(
            "kafka_offset"
        ),
        col("timestamp").alias(
            "kafka_timestamp"
        ),
        col("key")
        .cast("string")
        .alias("kafka_key"),
        col("value")
        .cast("string")
        .alias("json_value"),
    )
    .withColumn(
        "transaction",
        from_json(
            col("json_value"),
            transaction_schema,
        ),
    )
    .select(
        "kafka_topic",
        "kafka_partition",
        "kafka_offset",
        "kafka_timestamp",
        "kafka_key",
        "transaction.*",
    )
)


# ============================================================
# DATA VALIDATION
# ============================================================

validated_stream = (
    parsed_stream

    .filter(
        col("transaction_id").isNotNull()
    )

    .filter(
        col("type").isNotNull()
    )

    .filter(
        col("type").isin(
            "CASH_IN",
            "CASH_OUT",
            "DEBIT",
            "PAYMENT",
            "TRANSFER",
        )
    )

    .filter(
        col("amount").isNotNull()
    )

    .filter(
        col("amount") >= 0
    )

    .filter(
        col("step").isNotNull()
    )

    .filter(
        col("nameOrig").isNotNull()
    )

    .filter(
        col("nameDest").isNotNull()
    )

    .filter(
        col("oldbalanceOrg").isNotNull()
    )

    .filter(
        col("oldbalanceOrg") >= 0
    )

    .filter(
        col("newbalanceOrig").isNotNull()
    )

    .filter(
        col("newbalanceOrig") >= 0
    )

    .filter(
        col("oldbalanceDest").isNotNull()
    )

    .filter(
        col("oldbalanceDest") >= 0
    )

    .filter(
        col("newbalanceDest").isNotNull()
    )

    .filter(
        col("newbalanceDest") >= 0
    )
)


# ============================================================
# BASE FEATURE ENGINEERING
# ============================================================

base_feature_stream = (
    validated_stream

    .withColumn(
        "orig_balance_change",
        col("oldbalanceOrg")
        - col("newbalanceOrig"),
    )

    .withColumn(
        "dest_balance_change",
        col("newbalanceDest")
        - col("oldbalanceDest"),
    )

    .withColumn(
        "orig_balance_error",
        col("amount")
        - col("orig_balance_change"),
    )

    .withColumn(
        "dest_balance_error",
        col("amount")
        - col("dest_balance_change"),
    )

    .withColumn(
        "orig_zero_after",
        when(
            col("newbalanceOrig") == 0.0,
            1.0,
        ).otherwise(0.0),
    )

    .withColumn(
        "dest_zero_before",
        when(
            col("oldbalanceDest") == 0.0,
            1.0,
        ).otherwise(0.0),
    )

    .withColumn(
        "dest_zero_after",
        when(
            col("newbalanceDest") == 0.0,
            1.0,
        ).otherwise(0.0),
    )

    .withColumn(
        "log_amount",
        log1p(col("amount")),
    )

    .withColumn(
        "type_CASH_IN",
        when(
            col("type") == "CASH_IN",
            1.0,
        ).otherwise(0.0),
    )

    .withColumn(
        "type_CASH_OUT",
        when(
            col("type") == "CASH_OUT",
            1.0,
        ).otherwise(0.0),
    )

    .withColumn(
        "type_DEBIT",
        when(
            col("type") == "DEBIT",
            1.0,
        ).otherwise(0.0),
    )

    .withColumn(
        "type_PAYMENT",
        when(
            col("type") == "PAYMENT",
            1.0,
        ).otherwise(0.0),
    )

    .withColumn(
        "type_TRANSFER",
        when(
            col("type") == "TRANSFER",
            1.0,
        ).otherwise(0.0),
    )
)


# ============================================================
# STATE INPUT
# ============================================================

state_input_columns = list(dict.fromkeys([
    "transaction_id",
    "event_time",
    "source",
    "batch_id",
    "producer_sequence",
    "step",
    "event_step",
    "type",
    "amount",
    "nameOrig",
    "oldbalanceOrg",
    "newbalanceOrig",
    "nameDest",
    "oldbalanceDest",
    "newbalanceDest",
    "kafka_topic",
    "kafka_partition",
    "kafka_offset",
    "kafka_timestamp",
    "kafka_key",
    "isFraud",
    "isFlaggedFraud",
    *BASE_FEATURE_COLUMNS,
]))


state_input = (
    base_feature_stream.select(
        *state_input_columns
    )
)


# ============================================================
# STATEFUL BEHAVIORAL STREAM
# ============================================================

# CRITICAL FIX:
# stateStructType receives the DDL STRING.
#
# There is NO ArrayType Spark state anymore.
#
# Spark state is:
#
#     history_json string
#
# The actual rolling arrays are encoded inside that string.
behavioral_stream = (
    state_input

    .groupBy("nameOrig")

    .applyInPandasWithState(
        add_behavioral_features_stateful,

        outputStructType=(
            behavior_output_schema
        ),

        stateStructType=(
            STATE_SCHEMA_DDL
        ),

        outputMode="Append",

        timeoutConf=(
            GroupStateTimeout
            .ProcessingTimeTimeout
        ),
    )
)


# ============================================================
# ISOLATION FOREST SCORING
# ============================================================

def score_batch(
    df: DataFrame,
) -> DataFrame:
    """
    Apply the final 33-feature Isolation Forest.
    """

    output_schema = StructType(
        df.schema.fields
        + [
            StructField(
                "anomaly_score",
                DoubleType(),
                True,
            ),

            StructField(
                "risk_level",
                StringType(),
                True,
            ),

            StructField(
                "alert_required",
                IntegerType(),
                True,
            ),

            StructField(
                "risk_action",
                StringType(),
                True,
            ),

            StructField(
                "model_version",
                StringType(),
                True,
            ),
        ]
    )

    def score_partitions(
        pdf_iterator:
            Iterator[pd.DataFrame],
    ) -> Iterator[pd.DataFrame]:

        from spark_worker_model import load_isolation_forest

        model = load_isolation_forest(
            str(MODEL_PATH),
            expected_features=33,
        )

        t1 = THRESHOLDS["T1"]
        t2 = THRESHOLDS["T2"]
        t3 = THRESHOLDS["T3"]
        t4 = THRESHOLDS["T4"]

        for pdf in pdf_iterator:

            if (
                pdf is None
                or pdf.empty
            ):
                continue

            # Exact 33-feature contract.
            x = (
                pdf[
                    MODEL_FEATURE_COLUMNS
                ]
                .astype(np.float64)
            )

            if not np.isfinite(
                x.to_numpy()
            ).all():
                raise ValueError(
                    "Non-finite values detected "
                    "in the 33-feature streaming matrix."
                )

            # Higher anomaly score = more anomalous.
            scores = np.asarray(
                -model.decision_function(x),
                dtype=np.float64,
            )

            risks = np.select(
                [
                    scores < t1,
                    scores < t2,
                    scores < t3,
                    scores < t4,
                ],
                [
                    "L1",
                    "L2",
                    "L3",
                    "L4",
                ],
                default="L5",
            )

            result = pdf.copy()

            result["anomaly_score"] = (
                scores
            )

            result["risk_level"] = (
                risks
            )

            result["alert_required"] = (
                np.where(
                    np.isin(
                        risks,
                        [
                            "L3",
                            "L4",
                            "L5",
                        ],
                    ),
                    1,
                    0,
                )
                .astype(np.int32)
            )

            result["risk_action"] = (
                np.select(
                    [
                        np.isin(
                            risks,
                            ["L1"],
                        ),

                        np.isin(
                            risks,
                            ["L2"],
                        ),

                        np.isin(
                            risks,
                            ["L3"],
                        ),

                        np.isin(
                            risks,
                            ["L4"],
                        ),
                    ],
                    [
                        "ALLOW_STORE",
                        "ALLOW_MONITOR_STORE",
                        "INVESTIGATE",
                        "PRIORITY_INVESTIGATE",
                    ],
                    default=(
                        "CRITICAL_INVESTIGATE"
                    ),
                )
            )

            result["model_version"] = (
                MODEL_VERSION
            )

            yield result[
                [
                    field.name
                    for field
                    in output_schema.fields
                ]
            ]

    return df.mapInPandas(
        score_partitions,
        schema=output_schema,
    )


# ============================================================
# XGBOOST OUTPUT SCHEMA
# ============================================================

xgboost_output_schema = StructType([
    StructField(
        "transaction_id",
        StringType(),
        True,
    ),

    StructField(
        "event_time",
        StringType(),
        True,
    ),

    StructField(
        "source",
        StringType(),
        True,
    ),

    StructField("batch_id", StringType(), True),

    StructField("producer_sequence", IntegerType(), True),

    StructField(
        "step",
        IntegerType(),
        True,
    ),

    StructField(
        "event_step",
        IntegerType(),
        True,
    ),

    StructField(
        "type",
        StringType(),
        True,
    ),

    StructField(
        "amount",
        DoubleType(),
        True,
    ),

    StructField(
        "nameOrig",
        StringType(),
        True,
    ),

    StructField(
        "oldbalanceOrg",
        DoubleType(),
        True,
    ),

    StructField(
        "newbalanceOrig",
        DoubleType(),
        True,
    ),

    StructField(
        "nameDest",
        StringType(),
        True,
    ),

    StructField(
        "oldbalanceDest",
        DoubleType(),
        True,
    ),

    StructField(
        "newbalanceDest",
        DoubleType(),
        True,
    ),

    StructField(
        "kafka_topic",
        StringType(),
        True,
    ),

    StructField(
        "kafka_partition",
        IntegerType(),
        True,
    ),

    StructField(
        "kafka_offset",
        LongType(),
        True,
    ),

    StructField(
        "kafka_timestamp",
        TimestampType(),
        True,
    ),

    StructField(
        "kafka_key",
        StringType(),
        True,
    ),

    StructField(
        "anomaly_score",
        DoubleType(),
        True,
    ),

    StructField(
        "risk_level",
        StringType(),
        True,
    ),

    StructField(
        "alert_required",
        IntegerType(),
        True,
    ),

    StructField(
        "risk_action",
        StringType(),
        True,
    ),

    StructField(
        "model_version",
        StringType(),
        True,
    ),

    StructField(
        "xgboost_probability",
        DoubleType(),
        True,
    ),

    StructField(
        "xgboost_threshold",
        DoubleType(),
        True,
    ),

    StructField(
        "xgboost_prediction",
        IntegerType(),
        True,
    ),

    StructField(
        "xgboost_model_version",
        StringType(),
        True,
    ),

    StructField(
        "final_prediction",
        IntegerType(),
        True,
    ),

    StructField(
        "final_decision_path",
        StringType(),
        True,
    ),

    StructField(
        "final_risk_action",
        StringType(),
        True,
    ),
])


# ============================================================
# XGBOOST SECOND STAGE
# ============================================================

def apply_xgboost_second_stage(
    df: DataFrame,
) -> DataFrame:
    """Run XGBoost only on L1/L2 rows using worker-local model loading.

    XGBoost uses:
        33 Isolation Forest features
        +
        anomaly_score

    Total = 34 features.

    IMPORTANT: XGB_MODEL is NOT referenced from the driver here.
    The model is loaded lazily inside each Python worker process via
    spark_worker_model.load_xgboost(), which caches it in module-level
    state. This avoids serialising the 313 MB model through Spark's
    task-closure path.
    """

    if df.rdd.isEmpty():
        return spark.createDataFrame(
            [],
            schema=xgboost_output_schema,
        )

    # Capture lightweight primitives only (no model objects).
    xgb_feature_cols = XGB_FEATURE_COLUMNS
    xgb_threshold = float(XGB_THRESHOLD)
    xgb_model_version = str(
        XGB_CONFIG.get(
            "model_version",
            "xgboost_second_stage_v1",
        )
    )
    xgb_model_path = str(XGBOOST_MODEL_PATH)
    output_schema = xgboost_output_schema

    def _score_xgb_partitions(
        pdf_iterator: Iterator[pd.DataFrame],
    ) -> Iterator[pd.DataFrame]:
        from spark_worker_model import load_xgboost
        import numpy as _np

        model = load_xgboost(xgb_model_path)

        for pdf in pdf_iterator:
            if pdf is None or pdf.empty:
                continue

            x = pdf[xgb_feature_cols].astype(_np.float64)

            if not _np.isfinite(x.to_numpy()).all():
                raise ValueError(
                    "Non-finite values detected "
                    "in the 34-feature XGBoost matrix."
                )

            probabilities = model.predict_proba(x)[:, 1]
            predictions = (probabilities >= xgb_threshold).astype(_np.int32)

            result = pdf.copy()
            result["xgboost_probability"] = probabilities
            result["xgboost_threshold"] = float(xgb_threshold)
            result["xgboost_prediction"] = predictions
            result["xgboost_model_version"] = xgb_model_version

            result["final_prediction"] = predictions

            result["final_decision_path"] = _np.where(
                predictions == 1,
                "L1/L2 -> XGBoost -> fraud-alerts",
                "L1/L2 -> XGBoost -> low-risk",
            )

            result["final_risk_action"] = _np.where(
                predictions == 1,
                "FRAUD_ALERT",
                "LOW_RISK_STORE",
            )

            yield result[
                [field.name for field in output_schema.fields]
            ]

    return df.mapInPandas(
        _score_xgb_partitions,
        schema=xgboost_output_schema,
    )



# ============================================================
# KAFKA PAYLOAD CREATION
# ============================================================

def kafka_frame(
    df: DataFrame,
) -> DataFrame:
    """
    Convert final fraud-routing rows into Kafka key/value rows.
    """

    payload_columns = [
        "transaction_id",
        "event_time",
        "source",
        "batch_id",
        "producer_sequence",
        "step",
        "event_step",
        "type",
        "amount",
        "nameOrig",
        "oldbalanceOrg",
        "newbalanceOrig",
        "nameDest",
        "oldbalanceDest",
        "newbalanceDest",

        "anomaly_score",
        "risk_level",
        "alert_required",
        "risk_action",
        "model_version",

        "xgboost_probability",
        "xgboost_threshold",
        "xgboost_prediction",
        "xgboost_model_version",

        "final_prediction",
        "final_decision_path",
        "final_risk_action",
    ]

    return df.select(
        col("transaction_id")
        .cast("string")
        .alias("key"),

        to_json(
            struct(
                *[
                    col(column)
                    for column
                    in payload_columns
                ]
            )
        ).alias("value"),
    )


# ============================================================
# KAFKA PUBLISH
# ============================================================

def publish_topic(
    df: DataFrame,
    topic: str,
) -> None:
    """
    Publish a DataFrame to a Kafka topic.
    """

    if df.rdd.isEmpty():
        return

    (
        kafka_frame(df)
        .write
        .format("kafka")
        .option(
            "kafka.bootstrap.servers",
            KAFKA_BOOTSTRAP_SERVERS,
        )
        .option(
            "topic",
            topic,
        )
        .mode("append")
        .save()
    )


# ============================================================
# MICRO-BATCH ROUTER
# ============================================================

def route_micro_batch(
    batch_df: DataFrame,
    batch_id: int,
) -> None:
    """
    Final routing logic:

        Isolation Forest
             |
        +----+----+
        |         |
       L3-5     L1-2
        |         |
     ALERT      XGBoost
                  |
             +----+----+
             |         |
           Fraud     Low risk
             |         |
           ALERT      LOW-RISK
    """

    batch_started = time.perf_counter()
    print(f"[batch={batch_id}] START – scoring batch ...")
    scored = (
        score_batch(
            batch_df
        )
        .cache()
    )

    try:

        if scored.rdd.isEmpty():
            print(f"[batch={batch_id}] EMPTY – no rows in this micro-batch. Spark remains active.")
            return

        schema_columns = [
            field.name
            for field
            in xgboost_output_schema.fields
        ]

        # ----------------------------------------------------
        # DIRECT HIGH-RISK ALERTS
        # ----------------------------------------------------

        direct_alerts = (
            scored

            .filter(
                col("risk_level").isin(
                    "L3",
                    "L4",
                    "L5",
                )
            )

            .withColumn(
                "xgboost_probability",
                lit(None).cast(
                    DoubleType()
                ),
            )

            .withColumn(
                "xgboost_threshold",
                lit(None).cast(
                    DoubleType()
                ),
            )

            .withColumn(
                "xgboost_prediction",
                lit(None).cast(
                    IntegerType()
                ),
            )

            .withColumn(
                "xgboost_model_version",
                lit(None).cast(
                    StringType()
                ),
            )

            .withColumn(
                "final_prediction",
                lit(1).cast(
                    IntegerType()
                ),
            )

            .withColumn(
                "final_decision_path",
                lit(
                    "Isolation Forest -> fraud-alerts"
                ),
            )

            .withColumn(
                "final_risk_action",
                col("risk_action"),
            )

            .select(
                *schema_columns
            )
        )

        # ----------------------------------------------------
        # L1/L2 -> XGBOOST
        # ----------------------------------------------------

        low_risk = (
            scored
            .filter(
                col("risk_level").isin(
                    "L1",
                    "L2",
                )
            )
        )

        low_risk_with_xgb = (
            apply_xgboost_second_stage(
                low_risk
            )
        )

        # ----------------------------------------------------
        # XGBOOST FRAUD
        # ----------------------------------------------------

        xgb_fraud = (
            low_risk_with_xgb

            .filter(
                col(
                    "xgboost_prediction"
                ) == 1
            )

            .select(
                *schema_columns
            )
        )

        # ----------------------------------------------------
        # XGBOOST LOW RISK
        # ----------------------------------------------------

        xgb_legit = (
            low_risk_with_xgb

            .filter(
                col(
                    "xgboost_prediction"
                ) == 0
            )
        )

        # ----------------------------------------------------
        # FINAL FRAUD ALERT STREAM
        # ----------------------------------------------------

        fraud_alerts = (
            direct_alerts
            .unionByName(
                xgb_fraud
            )
        )

        # ----------------------------------------------------
        # PUBLISH
        # ----------------------------------------------------

        publish_topic(
            fraud_alerts,
            FRAUD_ALERTS_TOPIC,
        )

        publish_topic(
            xgb_legit,
            LOW_RISK_TOPIC,
        )

        # ----------------------------------------------------
        # BATCH METRICS
        # ----------------------------------------------------

        total_count = (
            scored.count()
        )

        low_risk_count = (
            low_risk.count()
        )

        direct_alert_count = (
            direct_alerts.count()
        )

        xgb_fraud_count = (
            xgb_fraud.count()
        )

        low_risk_final_count = (
            xgb_legit.count()
        )

        elapsed = time.perf_counter() - batch_started
        print(
            f"[batch={batch_id}] DONE – "
            f"total={total_count} "
            f"L1/L2={low_risk_count} "
            f"direct_alerts={direct_alert_count} "
            f"xgb_fraud={xgb_fraud_count} "
            f"low_risk={low_risk_final_count} "
            f"elapsed={elapsed:.2f}s"
        )

        metric_count("spark", "transactions_processed", "success", total_count)
        metric_count("spark", "fraud_alerts_produced", "success", direct_alert_count + xgb_fraud_count)
        metric_count("spark", "low_risk_produced", "success", low_risk_final_count)
        PROM_DURATION.labels("spark", "micro_batch").observe(time.perf_counter() - batch_started)

    except Exception:
        metric_count("spark", "micro_batch", "failure")
        raise

    finally:
        scored.unpersist()


# ============================================================
# START STREAMING QUERY
# ============================================================

start_metrics_server(port=int(os.getenv("SPARK_METRICS_PORT", "8002")))

query = (
    behavioral_stream

    .writeStream

    .foreachBatch(
        route_micro_batch
    )

    .option(
        "checkpointLocation",
        str(
            RISK_CHECKPOINT_DIR
        ),
    )

    .trigger(
        processingTime="5 seconds"
    )

    .start()
)


# ============================================================
# STARTUP INFORMATION
# ============================================================

print()
print("=" * 80)
print("FRAUD DETECTION PIPELINE")
print("=" * 80)

print(
    f"Project root: {PROJECT_ROOT}"
)

print(
    f"Kafka input: {TRANSACTIONS_TOPIC}"
)

print(
    f"Low-risk topic: {LOW_RISK_TOPIC}"
)

print(
    f"Fraud alert topic: {FRAUD_ALERTS_TOPIC}"
)

print(
    f"Checkpoint: {RISK_CHECKPOINT_DIR}"
)

print(
    "Starting offsets: "
    f"{os.getenv('SPARK_STARTING_OFFSETS', 'earliest')}"
)

print(
    f"IF feature count: "
    f"{len(MODEL_FEATURE_COLUMNS)}"
)

print(
    "IF thresholds: "
    f"T1={THRESHOLDS['T1']}, "
    f"T2={THRESHOLDS['T2']}, "
    f"T3={THRESHOLDS['T3']}, "
    f"T4={THRESHOLDS['T4']}"
)

print(
    f"XGB threshold: {XGB_THRESHOLD}"
)

print(
    "State implementation: "
    "history_json String"
)

print(
    "State ArrayType: DISABLED"
)

print(
    "Pipeline: "
    "Kafka -> Spark -> "
    "33 features -> "
    "Isolation Forest -> "
    "5-level risk routing -> "
    "XGBoost L1/L2 -> "
    "fraud-alerts / low-risk-transactions"
)

print("=" * 80)
print()

# ============================================================
# WAIT
# ============================================================


# ============================================================
# WAIT FOR TERMINATION (with defensive exception reporting)
# ============================================================

print("[query] Waiting for streaming query to terminate...")
print(f"[query] isActive = {query.isActive}")

try:
    query.awaitTermination()
except KeyboardInterrupt:
    print("\n[query] KeyboardInterrupt received. Stopping Spark streaming query...")
    query.stop()
    spark.stop()
    print("[query] Stopped cleanly.")
except Exception as exc:
    print(f"\n[query] Streaming query terminated with exception: {exc}")
finally:
    print("[query] === STREAMING QUERY TERMINATED ===")
    print(f"[query] isActive        : {query.isActive}")
    try:
        print(f"[query] exception()     : {query.exception()}")
    except Exception as e:
        print(f"[query] exception() call failed: {e}")
    try:
        print(f"[query] status          : {query.status}")
    except Exception as e:
        print(f"[query] status call failed: {e}")
    try:
        print(f"[query] lastProgress    : {query.lastProgress}")
    except Exception as e:
        print(f"[query] lastProgress call failed: {e}")

