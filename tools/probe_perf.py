import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(r'd:\Real-Time-Financial-Fraud-Detection-Pipeline-')
DATA_PATH = ROOT / 'data' / 'PS_20174392719_1491204439457_log.csv'

def add_base_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out['orig_balance_change'] = out['oldbalanceOrg'] - out['newbalanceOrig']
    out['dest_balance_change'] = out['newbalanceDest'] - out['oldbalanceDest']
    out['orig_balance_error'] = out['amount'] - out['orig_balance_change']
    out['dest_balance_error'] = out['amount'] - out['dest_balance_change']
    out['orig_zero_after'] = (out['newbalanceOrig'] == 0.0).astype(float)
    out['dest_zero_before'] = (out['oldbalanceDest'] == 0.0).astype(float)
    out['dest_zero_after'] = (out['newbalanceDest'] == 0.0).astype(float)
    out['log_amount'] = np.log1p(out['amount'])
    for tx_type in ['CASH_IN', 'CASH_OUT', 'DEBIT', 'PAYMENT', 'TRANSFER']:
        out[f'type_{tx_type}'] = (out['type'] == tx_type).astype(float)
    return out

def compute_behavioral_features(df: pd.DataFrame) -> pd.DataFrame:
    processed = []
    for _, group in df.groupby('nameOrig', sort=False):
        ordered = group.sort_values(['step', 'amount'], kind='mergesort').reset_index(drop=True)
        history_steps = []
        history_amounts = []
        history_destinations = []
        history_types = []
        for _, row in ordered.iterrows():
            current_step = int(row['step'])
            current_amount = float(row['amount'])
            current_dest = str(row['nameDest'])
            current_type = str(row['type'])
            idx_1 = [i for i, prev_step in enumerate(history_steps) if current_step - prev_step <= 1]
            idx_6 = [i for i, prev_step in enumerate(history_steps) if current_step - prev_step <= 6]
            idx_24 = [i for i, prev_step in enumerate(history_steps) if current_step - prev_step <= 24]
            amounts_6 = [history_amounts[i] for i in idx_6]
            amounts_24 = [history_amounts[i] for i in idx_24]
            destinations_24 = [history_destinations[i] for i in idx_24]
            types_24 = [history_types[i] for i in idx_24]
            avg_6 = float(np.mean(amounts_6)) if amounts_6 else 0.0
            avg_24 = float(np.mean(amounts_24)) if amounts_24 else 0.0
            ratio = float(current_amount / avg_24) if avg_24 > 0 else 0.0
            time_since_prev = float(current_step - history_steps[-1]) if history_steps else 0.0
            unique_destinations = float(len(set(destinations_24))) if destinations_24 else 0.0
            new_destination = float(current_dest not in set(destinations_24))
            cashout_count = float(sum(tx_type == 'CASH_OUT' for tx_type in types_24))
            transfer_count = float(sum(tx_type == 'TRANSFER' for tx_type in types_24))
            old_balance = float(row['oldbalanceOrg'])
            depletion_ratio = 0.0 if old_balance <= 0.0 else float(max(0.0, min(1.0, (old_balance - float(row['newbalanceOrig'])) / old_balance)))
            row_copy = row.copy()
            row_copy['orig_tx_count_1step'] = float(len(idx_1))
            row_copy['orig_tx_count_6steps'] = float(len(idx_6))
            row_copy['orig_tx_count_24steps'] = float(len(idx_24))
            row_copy['orig_amount_sum_6steps'] = float(np.sum(amounts_6)) if amounts_6 else 0.0
            row_copy['orig_amount_sum_24steps'] = float(np.sum(amounts_24)) if amounts_24 else 0.0
            row_copy['orig_avg_amount_6steps'] = avg_6
            row_copy['orig_avg_amount_24steps'] = avg_24
            row_copy['orig_amount_ratio_to_avg_24steps'] = ratio
            row_copy['orig_time_since_prev_step'] = time_since_prev
            row_copy['orig_unique_destinations_24steps'] = unique_destinations
            row_copy['orig_cashout_count_24steps'] = cashout_count
            row_copy['orig_transfer_count_24steps'] = transfer_count
            row_copy['orig_new_destination'] = new_destination
            row_copy['orig_balance_depletion_ratio'] = depletion_ratio
            processed.append(row_copy)
            history_steps.append(current_step)
            history_amounts.append(current_amount)
            history_destinations.append(current_dest)
            history_types.append(current_type)
    return pd.DataFrame(processed)

start = time.time()
df = pd.read_csv(DATA_PATH, nrows=20000)
df = add_base_features(df)
res = compute_behavioral_features(df)
print('rows', len(df), 'feature_rows', len(res), 'elapsed', round(time.time()-start, 2))
print(res.columns.tolist()[-10:])
