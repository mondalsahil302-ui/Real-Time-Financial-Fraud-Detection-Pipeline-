import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(r'd:\Real-Time-Financial-Fraud-Detection-Pipeline-')
DATA = ROOT / 'data' / 'PS_20174392719_1491204439457_log.csv'
MODEL = joblib.load(ROOT / 'models' / 'isolation_forest_final.pkl')
config = json.loads((ROOT / 'models' / 'isolation_forest_config.json').read_text())
features = json.loads((ROOT / 'models' / 'isolation_forest_features.json').read_text())['feature_columns']
thresholds = config['thresholds']


def add_base_features(df):
    out = df.copy()
    out['orig_balance_change'] = out['oldbalanceOrg'] - out['newbalanceOrig']
    out['dest_balance_change'] = out['newbalanceDest'] - out['oldbalanceDest']
    out['orig_balance_error'] = out['amount'] - out['orig_balance_change']
    out['dest_balance_error'] = out['amount'] - out['dest_balance_change']
    out['orig_zero_after'] = (out['newbalanceOrig'] == 0.0).astype(int)
    out['dest_zero_before'] = (out['oldbalanceDest'] == 0.0).astype(int)
    out['dest_zero_after'] = (out['newbalanceDest'] == 0.0).astype(int)
    out['log_amount'] = np.log1p(out['amount'])
    for txn_type in ['CASH_IN', 'CASH_OUT', 'DEBIT', 'PAYMENT', 'TRANSFER']:
        out[f'type_{txn_type}'] = (out['type'] == txn_type).astype(int)
    return out


def compute_behavioral_features(df):
    rows = []
    for _, account_frame in df.sort_values(['nameOrig', 'step'], kind='mergesort').groupby('nameOrig', sort=False):
        account_frame = account_frame.sort_values(['step', 'amount'], kind='mergesort').reset_index(drop=True)
        history_steps = []
        history_amounts = []
        history_destinations = []
        history_types = []
        last_step = None
        for _, row in account_frame.iterrows():
            current_step = int(row['step'])
            current_amount = float(row['amount'])
            current_destination = str(row['nameDest'])
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
            amount_ratio = float(current_amount / avg_24) if avg_24 > 0 else 0.0
            unique_destinations = float(len(set(destinations_24))) if destinations_24 else 0.0
            new_destination = float(current_destination not in set(destinations_24))
            cashout_count = float(sum(tx_type == 'CASH_OUT' for tx_type in types_24))
            transfer_count = float(sum(tx_type == 'TRANSFER' for tx_type in types_24))
            time_since_prev = float(max(0, current_step - last_step)) if last_step is not None else 0.0
            old_balance = float(row['oldbalanceOrg'])
            depletion_ratio = 0.0 if old_balance <= 0 else float(max(0.0, min(1.0, (old_balance - float(row['newbalanceOrig'])) / old_balance)))
            payload = row.to_dict()
            payload['orig_tx_count_1step'] = float(len(idx_1))
            payload['orig_tx_count_6steps'] = float(len(idx_6))
            payload['orig_tx_count_24steps'] = float(len(idx_24))
            payload['orig_amount_sum_6steps'] = float(np.sum(amounts_6)) if amounts_6 else 0.0
            payload['orig_amount_sum_24steps'] = float(np.sum(amounts_24)) if amounts_24 else 0.0
            payload['orig_avg_amount_6steps'] = avg_6
            payload['orig_avg_amount_24steps'] = avg_24
            payload['orig_amount_ratio_to_avg_24steps'] = amount_ratio
            payload['orig_time_since_prev_step'] = time_since_prev
            payload['orig_unique_destinations_24steps'] = unique_destinations
            payload['orig_cashout_count_24steps'] = cashout_count
            payload['orig_transfer_count_24steps'] = transfer_count
            payload['orig_new_destination'] = new_destination
            payload['orig_balance_depletion_ratio'] = depletion_ratio
            rows.append(payload)
            history_steps.append(current_step)
            history_amounts.append(current_amount)
            history_destinations.append(current_destination)
            history_types.append(current_type)
            last_step = current_step
    return pd.DataFrame(rows)


df = pd.read_csv(DATA)
df["row_id"] = np.arange(len(df))
df = add_base_features(df)
df = compute_behavioral_features(df)
df = df.sort_values(['step', 'amount'], kind='mergesort').reset_index(drop=True)

n = len(df)
train_end = int(0.60 * n)
valid_end = int(0.80 * n)
train = df.iloc[:train_end].copy()
valid = df.iloc[train_end:valid_end].copy()
test = df.iloc[valid_end:].copy()

for split_name, frame in [('train', train), ('validation', valid), ('test', test)]:
    scores = -MODEL.decision_function(frame[features].astype(float))
    risk = np.select([
        scores < thresholds['T1'],
        scores < thresholds['T2'],
        scores < thresholds['T3'],
        scores < thresholds['T4'],
    ], ['L1','L2','L3','L4'], default='L5')
    frame = frame.copy()
    frame['anomaly_score'] = scores
    frame['risk_level'] = risk
    counts = frame['risk_level'].value_counts().to_dict()
    fraud_counts = frame.groupby('risk_level')['isFraud'].sum().to_dict()
    print(split_name)
    print('rows', len(frame), 'fraud', int(frame['isFraud'].sum()), 'legit', int((frame['isFraud']==0).sum()))
    print('risk_counts', counts)
    print('fraud_in_risk', {k:int(v) for k,v in fraud_counts.items()})
    print('L1/L2 fraud', int(frame.loc[frame['risk_level'].isin(['L1','L2']), 'isFraud'].sum()))
    print()

# full test metrics at T2 baseline per user requirement
scores = -MODEL.decision_function(test[features].astype(float))
fnl = np.select([
    scores < thresholds['T1'],
    scores < thresholds['T2'],
    scores < thresholds['T3'],
    scores < thresholds['T4'],
], ['L1','L2','L3','L4'], default='L5')
test['anomaly_score'] = scores
test['risk_level'] = pd.Series(fnl, index=test.index, name='risk_level')
fnl = test['risk_level']
# T2 test result: anything >= T2 is alert path? from original script likely threshold T2 used as IF decision threshold; user says T2 baseline gave TP=18 FN=11
# Evaluate direct alert at T2: >=T2 => alert. need use same logic.
alert = (scores >= thresholds['T2']).astype(int)
true = test['isFraud'].to_numpy().astype(int)
print('T2 baseline direct alert counts:')
print('TP', int(((alert==1)&(true==1)).sum()))
print('FN', int(((alert==0)&(true==1)).sum()))
print('total fraud', int(true.sum()))
print('L1 fraud', int(test.loc[fnl.isin(['L1']), 'isFraud'].sum()))
print('L2 fraud', int(test.loc[fnl.isin(['L2']), 'isFraud'].sum()))
print('L3/L4/L5 fraud', int(test.loc[fnl.isin(['L3','L4','L5']), 'isFraud'].sum()))
print('L1/L2 rows', int(test.loc[fnl.isin(['L1','L2'])].shape[0]))
print('first false negatives rows', test.loc[(true==1) & (alert==0), ['row_id','isFraud','anomaly_score','risk_level']].head(20).to_dict('records'))
