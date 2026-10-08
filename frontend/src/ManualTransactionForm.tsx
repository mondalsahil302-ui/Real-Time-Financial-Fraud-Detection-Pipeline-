import { useState } from 'react';
import { api } from './api';
import { AlertTriangle, CheckCircle, Play, Workflow } from './icons';

const initial = {
  step: 1,
  type: 'PAYMENT',
  amount: '100',
  nameOrig: 'C_CONTROL_CENTER_1',
  oldbalanceOrg: '500',
  newbalanceOrig: '400',
  nameDest: 'M_CONTROL_CENTER_1',
  oldbalanceDest: '0',
  newbalanceDest: '100',
};

const presets = [
  {
    label: 'Normal PAYMENT ($100)',
    data: {
      step: 1,
      type: 'PAYMENT',
      amount: '100',
      nameOrig: 'C_CONTROL_CENTER_1',
      oldbalanceOrg: '500',
      newbalanceOrig: '400',
      nameDest: 'M_CONTROL_CENTER_1',
      oldbalanceDest: '0',
      newbalanceDest: '100',
    },
  },
  {
    label: 'Suspicious CASH_OUT (Account Drained)',
    data: {
      step: 42,
      type: 'CASH_OUT',
      amount: '185000',
      nameOrig: 'C_DRAIN_SENDER_9',
      oldbalanceOrg: '185000',
      newbalanceOrig: '0',
      nameDest: 'C_MULE_CASHOUT_4',
      oldbalanceDest: '0',
      newbalanceDest: '185000',
    },
  },
  {
    label: 'Large Suspicious TRANSFER',
    data: {
      step: 74,
      type: 'TRANSFER',
      amount: '500000',
      nameOrig: 'C_CORP_ACCOUNT_8',
      oldbalanceOrg: '1200000',
      newbalanceOrig: '700000',
      nameDest: 'C_SHELL_DEST_2',
      oldbalanceDest: '0',
      newbalanceDest: '500000',
    },
  },
];

export default function ManualTransactionForm() {
  const [values, setValues] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const change = (key: keyof typeof initial, value: string) =>
    setValues((current) => ({ ...current, [key]: value }));

  const loadPreset = (presetData: typeof initial) => {
    setValues(presetData);
    setMessage('');
    setError('');
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMessage('');
    setError('');
    try {
      const idempotencyKey = crypto.randomUUID();
      const result = await api<any>('/api/transactions', {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: JSON.stringify({
          type: values.type,
          step: Number(values.step),
          amount: Number(values.amount),
          nameOrig: values.nameOrig,
          oldbalanceOrg: Number(values.oldbalanceOrg),
          newbalanceOrig: Number(values.newbalanceOrig),
          nameDest: values.nameDest,
          oldbalanceDest: Number(values.oldbalanceDest),
          newbalanceDest: Number(values.newbalanceDest),
        }),
      });
      const tx = result.transaction;
      setMessage(
        `Kafka acknowledged ${tx.transaction_id} · partition ${tx.kafka_partition} · offset ${tx.kafka_offset}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send transaction');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel manual-form" onSubmit={submit}>
      <div className="panel-head">
        <div>
          <div className="form-head-title">
            <Workflow size={16} />
            <h3>Create individual transaction</h3>
          </div>
          <p>Send one validated event to the existing Kafka topic for Spark processing.</p>
        </div>
        <div className="presets-bar">
          <span className="presets-label">Load Template:</span>
          {presets.map((p, i) => (
            <button
              key={i}
              type="button"
              className="preset-btn"
              onClick={() => loadPreset(p.data)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="manual-grid">
        <label>
          Transaction type
          <select value={values.type} onChange={(e) => change('type', e.target.value)}>
            {['CASH_IN', 'CASH_OUT', 'DEBIT', 'PAYMENT', 'TRANSFER'].map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        </label>

        <label>
          Amount
          <input
            type="number"
            min="0"
            step="0.01"
            value={values.amount}
            onChange={(e) => change('amount', e.target.value)}
            required
          />
        </label>

        <label>
          Step
          <input
            type="number"
            min="0"
            value={values.step}
            onChange={(e) => change('step', e.target.value)}
            required
          />
        </label>

        <label>
          Origin account
          <input
            value={values.nameOrig}
            onChange={(e) => change('nameOrig', e.target.value)}
            required
          />
        </label>

        <label>
          Origin balance before
          <input
            type="number"
            min="0"
            step="0.01"
            value={values.oldbalanceOrg}
            onChange={(e) => change('oldbalanceOrg', e.target.value)}
            required
          />
        </label>

        <label>
          Origin balance after
          <input
            type="number"
            min="0"
            step="0.01"
            value={values.newbalanceOrig}
            onChange={(e) => change('newbalanceOrig', e.target.value)}
            required
          />
        </label>

        <label>
          Destination account
          <input
            value={values.nameDest}
            onChange={(e) => change('nameDest', e.target.value)}
            required
          />
        </label>

        <label>
          Destination balance before
          <input
            type="number"
            min="0"
            step="0.01"
            value={values.oldbalanceDest}
            onChange={(e) => change('oldbalanceDest', e.target.value)}
            required
          />
        </label>

        <label>
          Destination balance after
          <input
            type="number"
            min="0"
            step="0.01"
            value={values.newbalanceDest}
            onChange={(e) => change('newbalanceDest', e.target.value)}
            required
          />
        </label>
      </div>

      <div className="manual-form-footer">
        <button className="primary" disabled={busy}>
          <Play size={14} fill="currentColor" />
          {busy ? 'Sending to Kafka…' : 'Send transaction'}
        </button>

        {message && (
          <div className="kafka-ack-alert" role="status">
            <CheckCircle size={15} />
            <span className="success-text">{message}</span>
          </div>
        )}

        {error && (
          <div className="kafka-error-alert" role="alert">
            <AlertTriangle size={15} />
            <span className="error-text">{error}</span>
          </div>
        )}
      </div>
    </form>
  );
}
