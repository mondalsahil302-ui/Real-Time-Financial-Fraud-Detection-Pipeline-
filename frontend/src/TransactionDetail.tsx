import { useEffect, useState } from 'react';
import { api } from './api';
import type { Tx } from './types';

const render = (value: unknown): string => value == null ? 'Not available' : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);

function Section({ title, value }: { title: string; value: unknown }) {
  return <section className="detail-section"><h4>{title}</h4><pre>{render(value)}</pre></section>;
}

export default function TransactionDetail({ id, onInvestigate }: { id: string; onInvestigate: () => void }) {
  const [transaction, setTransaction] = useState<Tx>();
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setTransaction(undefined);
    setError('');
    void api<Tx>(`/api/transactions/${encodeURIComponent(id)}`)
      .then(value => { if (active) setTransaction(value); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Could not load transaction'); });
    return () => { active = false; };
  }, [id]);
  const investigation = transaction?.investigation;
  return <div className="panel transaction-detail" role="region" aria-label="Transaction detail">
    <div className="panel-head"><div><h3>Transaction detail</h3><p className="mono">{id}</p></div><button className="primary" onClick={onInvestigate}>Investigate with Gemini</button></div>
    {error && <div className="notice error">{error}</div>}
    {!transaction && !error && <p>Loading authoritative transaction…</p>}
    {transaction && <>
      <div className="detail-grid">
        <Section title="Observed transaction facts (PaySim)" value={{ timestamp: transaction.generated_at, ...transaction.payload }} />
        <Section title="ML model output — not confirmed fraud" value={{ risk_level: transaction.risk_level, anomaly_score: transaction.anomaly_score, xgboost_probability: transaction.xgboost_probability, final_prediction: transaction.final_prediction, decision_path: transaction.decision_path, final_decision: transaction.final_decision }} />
        <Section title="Pipeline and investigation status" value={{ kafka_status: transaction.kafka_status, processing_status: transaction.processing_status, alert_id: transaction.alert_id, investigation_id: transaction.investigation_id, investigation_status: transaction.investigation_status }} />
        <Section title="Ground truth (supplied PaySim label)" value={{ isFraud: transaction.payload?.isFraud ?? 'Not supplied', note: 'The supplied label is separate from the ML prediction and alert decision.' }} />
      </div>
      {investigation && <div className="detail-grid">
        <Section title="Investigation summary / interpretation" value={investigation.investigation_summary} />
        <Section title="Risk assessment" value={investigation.alert_assessment} />
        <Section title="Observed and retrieved evidence" value={investigation.evidence} />
        <Section title="Risk factors" value={investigation.risk_factors} />
        <Section title="Counter-evidence" value={investigation.counter_evidence} />
        <Section title="Missing evidence" value={investigation.missing_evidence} />
        <Section title="Historical comparison (PaySim)" value={investigation.historical_comparison} />
        <Section title="Recommended review points" value={investigation.recommended_review_points} />
      </div>}
    </>}
  </div>;
}
