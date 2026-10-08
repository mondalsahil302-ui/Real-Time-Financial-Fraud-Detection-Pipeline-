import { useEffect, useState } from 'react';
import { api } from './api';
import type { Tx } from './types';
import {
  AlertTriangle,
  CheckCircle,
  Copy,
  FileText,
  ShieldAlert,
  Sparkles,
  Workflow,
  X,
  Layers,
  Clock
} from './icons';

interface TransactionDetailProps {
  id: string;
  onInvestigate: () => void;
  onClose?: () => void;
}

const formatCurrency = (val: any) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(val) || 0);

const formatNumber = (val: any, decimals = 4) => {
  if (val === null || val === undefined || isNaN(Number(val))) return '—';
  return Number(val).toFixed(decimals);
};

export default function TransactionDetail({ id, onInvestigate, onClose }: TransactionDetailProps) {
  const [transaction, setTransaction] = useState<Tx>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setTransaction(undefined);
    setError('');

    void api<Tx>(`/api/transactions/${encodeURIComponent(id)}`)
      .then((val) => {
        if (active) {
          setTransaction(val);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Could not load authoritative transaction');
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [id]);

  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  const payload = transaction?.payload || {};
  const amount = Number(payload.amount) || 0;
  const oldOrig = Number(payload.oldbalanceOrg) || 0;
  const newOrig = Number(payload.newbalanceOrig) || 0;
  const origDelta = oldOrig - newOrig;
  const origError = amount - origDelta;

  const oldDest = Number(payload.oldbalanceDest) || 0;
  const newDest = Number(payload.newbalanceDest) || 0;
  const destDelta = newDest - oldDest;
  const destError = amount - destDelta;

  const groundTruthFraud = payload.isFraud === 1;
  const modelFraud = transaction?.final_prediction === 1 || transaction?.processing_status === 'FRAUD_ALERT';

  let evaluationPill = { label: 'Evaluation Pending', color: 'slate' };
  if (payload.isFraud !== undefined && transaction?.final_prediction !== undefined) {
    if (groundTruthFraud && modelFraud) {
      evaluationPill = { label: 'True Positive (Fraud Detected)', color: 'emerald' };
    } else if (!groundTruthFraud && !modelFraud) {
      evaluationPill = { label: 'True Negative (Accurate Low Risk)', color: 'blue' };
    } else if (!groundTruthFraud && modelFraud) {
      evaluationPill = { label: 'False Positive (Benign Flagged)', color: 'amber' };
    } else if (groundTruthFraud && !modelFraud) {
      evaluationPill = { label: 'False Negative (Missed Anomaly)', color: 'rose' };
    }
  }

  const riskTier = transaction?.risk_level || '—';
  const getRiskClass = (tier: string) => {
    switch (tier) {
      case 'L5':
        return 'risk-l5';
      case 'L4':
        return 'risk-l4';
      case 'L3':
        return 'risk-l3';
      case 'L2':
        return 'risk-l2';
      case 'L1':
        return 'risk-l1';
      default:
        return 'risk-neutral';
    }
  };

  const investigation = transaction?.investigation;

  return (
    <div className="panel transaction-detail-panel" role="region" aria-label="Transaction detail">
      {/* Detail Header */}
      <div className="detail-header">
        <div className="detail-header-left">
          <div className="detail-title-row">
            <span className="badge-tag">TRANSACTION RECORD</span>
            <h3 className="mono detail-id">{id}</h3>
            <button
              className="copy-btn"
              onClick={copyId}
              title="Copy transaction ID"
              aria-label="Copy transaction ID"
            >
              <Copy size={14} />
              {copied && <span className="copied-tooltip">Copied</span>}
            </button>
          </div>
          <div className="detail-status-chips">
            <span className={`risk-badge ${getRiskClass(riskTier)}`}>
              Risk: {riskTier}
            </span>
            <span
              className={`status-chip ${
                transaction?.processing_status === 'FRAUD_ALERT'
                  ? 'status-fraud'
                  : transaction?.processing_status === 'LOW_RISK'
                  ? 'status-ok'
                  : 'status-pending'
              }`}
            >
              Decision: {transaction?.final_decision || transaction?.processing_status || 'PROCESSING'}
            </span>
            <span className={`status-chip ${transaction?.kafka_status === 'SENT' ? 'status-ok' : 'status-muted'}`}>
              Kafka: {transaction?.kafka_status || 'UNKNOWN'}
            </span>
            {transaction?.investigation_status && (
              <span className="status-chip status-neutral">
                Case: {transaction.investigation_status}
              </span>
            )}
          </div>
        </div>

        <div className="detail-header-actions">
          <button className="primary" onClick={onInvestigate} id="investigate-gemini-btn">
            <Sparkles size={15} />
            Investigate with Gemini
          </button>
          {onClose && (
            <button className="icon-button" onClick={onClose} aria-label="Close detail pane">
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="notice error">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="detail-loading">
          <Clock size={16} /> Loading authoritative transaction details from Cassandra & Control Store…
        </div>
      )}

      {transaction && (
        <div className="detail-body">
          {/* Top Quick Facts Ribbon */}
          <div className="facts-ribbon">
            <div className="fact-item">
              <span className="fact-label">EVENT TYPE</span>
              <strong className="fact-value type-tag">{payload.type || 'UNKNOWN'}</strong>
            </div>
            <div className="fact-item">
              <span className="fact-label">AMOUNT</span>
              <strong className="fact-value amount-lg mono">{formatCurrency(amount)}</strong>
            </div>
            <div className="fact-item">
              <span className="fact-label">STEP (TIME)</span>
              <strong className="fact-value mono">Hour {payload.step ?? '—'}</strong>
            </div>
            <div className="fact-item">
              <span className="fact-label">GROUND TRUTH (PAYSIM)</span>
              <span className={`eval-pill ${groundTruthFraud ? 'eval-fraud' : 'eval-normal'}`}>
                {groundTruthFraud ? '1 (CONFIRMED FRAUD)' : '0 (LEGITIMATE)'}
              </span>
            </div>
            <div className="fact-item">
              <span className="fact-label">ML CLASSIFICATION</span>
              <span className={`eval-pill eval-${evaluationPill.color}`}>
                {evaluationPill.label}
              </span>
            </div>
          </div>

          <div className="detail-grid-layout">
            {/* Card 1: Sender & Receiver Account Balances */}
            <div className="detail-card">
              <div className="detail-card-head">
                <h4>
                  <Workflow size={15} /> Flow of Funds & Account Balances
                </h4>
              </div>
              <div className="detail-card-content">
                <div className="balance-flow-box">
                  <div className="account-column">
                    <span className="account-tag-label">ORIGIN (SENDER)</span>
                    <span className="account-id mono">{payload.nameOrig || '—'}</span>
                    <div className="balance-diff">
                      <div className="balance-row">
                        <span>Balance Before:</span>
                        <strong className="mono">{formatCurrency(oldOrig)}</strong>
                      </div>
                      <div className="balance-row">
                        <span>Balance After:</span>
                        <strong className="mono">{formatCurrency(newOrig)}</strong>
                      </div>
                      <div className="balance-row highlight">
                        <span>Net Depletion:</span>
                        <strong className="mono">{formatCurrency(origDelta)}</strong>
                      </div>
                      <div className="balance-row subtle">
                        <span>Balance Error:</span>
                        <span className="mono">{formatCurrency(origError)}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flow-arrow">➔</div>

                  <div className="account-column">
                    <span className="account-tag-label">DESTINATION (RECIPIENT)</span>
                    <span className="account-id mono">{payload.nameDest || '—'}</span>
                    <div className="balance-diff">
                      <div className="balance-row">
                        <span>Balance Before:</span>
                        <strong className="mono">{formatCurrency(oldDest)}</strong>
                      </div>
                      <div className="balance-row">
                        <span>Balance After:</span>
                        <strong className="mono">{formatCurrency(newDest)}</strong>
                      </div>
                      <div className="balance-row highlight">
                        <span>Net Influx:</span>
                        <strong className="mono">{formatCurrency(destDelta)}</strong>
                      </div>
                      <div className="balance-row subtle">
                        <span>Balance Error:</span>
                        <span className="mono">{formatCurrency(destError)}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="heuristics-flags">
                  <div className={`flag-chip ${newOrig === 0 ? 'flag-alert' : 'flag-neutral'}`}>
                    {newOrig === 0 ? '⚠️ Account fully drained (Zero Balance After)' : '✓ Residual balance maintained'}
                  </div>
                  <div className={`flag-chip ${oldDest === 0 ? 'flag-info' : 'flag-neutral'}`}>
                    {oldDest === 0 ? 'ℹ️ New/Empty Recipient Account (Zero Balance Before)' : '✓ Recipient had prior balance'}
                  </div>
                </div>
              </div>
            </div>

            {/* Card 2: ML Model Assessment */}
            <div className="detail-card">
              <div className="detail-card-head">
                <h4>
                  <ShieldAlert size={15} /> Machine Learning Scoring Assessment
                </h4>
              </div>
              <div className="detail-card-content">
                <div className="stat-rows">
                  <div className="stat-line">
                    <span className="stat-name">Multi-Level Risk Tier:</span>
                    <strong className={`risk-badge inline ${getRiskClass(riskTier)}`}>
                      {riskTier} ({riskTier === 'L5' ? 'Critical Threat' : riskTier === 'L4' ? 'High Threat' : riskTier === 'L3' ? 'Guarded' : riskTier === 'L2' ? 'Low Risk' : 'Normal'})
                    </strong>
                  </div>
                  <div className="stat-line">
                    <span className="stat-name">Autoencoder Reconstruction Error:</span>
                    <span className="stat-val mono">{formatNumber(transaction.anomaly_score, 6)}</span>
                  </div>
                  <div className="stat-line">
                    <span className="stat-name">XGBoost Fraud Probability:</span>
                    <span className="stat-val mono">
                      {transaction.xgboost_probability !== undefined
                        ? `${(Number(transaction.xgboost_probability) * 100).toFixed(2)}%`
                        : '—'}
                    </span>
                  </div>
                  <div className="stat-line">
                    <span className="stat-name">Supervised / Unsupervised Prediction:</span>
                    <span className="stat-val mono">
                      {transaction.final_prediction === 1 ? '1 (Flagged Anomaly)' : '0 (Normal Flow)'}
                    </span>
                  </div>
                  <div className="stat-line">
                    <span className="stat-name">Spark Decision Path / Rule:</span>
                    <span className="stat-val path-tag mono">{transaction.decision_path || 'DEFAULT_HEURISTIC'}</span>
                  </div>
                  <div className="stat-line">
                    <span className="stat-name">Execution Decision:</span>
                    <strong className="stat-val highlight">{transaction.final_decision || transaction.processing_status}</strong>
                  </div>
                </div>
              </div>
            </div>

            {/* Card 3: Provenance & Infrastructure Metadata */}
            <div className="detail-card">
              <div className="detail-card-head">
                <h4>
                  <Layers size={15} /> Streaming Pipeline Provenance
                </h4>
              </div>
              <div className="detail-card-content">
                <div className="stat-rows">
                  <div className="stat-line">
                    <span className="stat-name">Ingestion Batch ID:</span>
                    <span className="stat-val mono">{transaction.batch_id || 'Direct Stream'}</span>
                  </div>
                  <div className="stat-line">
                    <span className="stat-name">Kafka Acknowledgement:</span>
                    <span className="stat-val mono">
                      Partition {transaction.kafka_partition ?? '—'} · Offset {transaction.kafka_offset ?? '—'}
                    </span>
                  </div>
                  <div className="stat-line">
                    <span className="stat-name">Ingestion Timestamp:</span>
                    <span className="stat-val mono">{new Date(transaction.generated_at).toLocaleString()}</span>
                  </div>
                  <div className="stat-line">
                    <span className="stat-name">Fraud Alert ID:</span>
                    <span className="stat-val mono">{transaction.alert_id || 'None (Cleared)'}</span>
                  </div>
                  <div className="stat-line">
                    <span className="stat-name">Investigation Record ID:</span>
                    <span className="stat-val mono">{transaction.investigation_id || 'None'}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Card 4: Automated Case Investigation (if present) */}
            {investigation && (
              <div className="detail-card span-full">
                <div className="detail-card-head">
                  <h4>
                    <Sparkles size={15} /> Automated Gemini & RAG Case Investigation
                  </h4>
                  <span className="badge-tag">CASSANDRA + CHROMA EVIDENCE</span>
                </div>
                <div className="detail-card-content investigation-content">
                  {investigation.investigation_summary && (
                    <div className="investigation-block">
                      <h5>Executive Summary</h5>
                      <p className="summary-text">{investigation.investigation_summary}</p>
                    </div>
                  )}

                  {investigation.alert_assessment && (
                    <div className="investigation-block">
                      <h5>Risk & Severity Assessment</h5>
                      <p>{investigation.alert_assessment}</p>
                    </div>
                  )}

                  <div className="investigation-two-col">
                    {Array.isArray(investigation.risk_factors) && investigation.risk_factors.length > 0 && (
                      <div className="investigation-box">
                        <h5>
                          <AlertTriangle size={14} /> Risk Factors Identified
                        </h5>
                        <ul>
                          {investigation.risk_factors.map((rf: string, i: number) => (
                            <li key={i}>{rf}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {Array.isArray(investigation.counter_evidence) && investigation.counter_evidence.length > 0 && (
                      <div className="investigation-box">
                        <h5>
                          <CheckCircle size={14} /> Counter-Evidence / Mitigating Factors
                        </h5>
                        <ul>
                          {investigation.counter_evidence.map((ce: string, i: number) => (
                            <li key={i}>{ce}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>

                  {Array.isArray(investigation.missing_evidence) && investigation.missing_evidence.length > 0 && (
                    <div className="investigation-block">
                      <h5>Information Gaps & Missing Evidence</h5>
                      <ul className="gap-list">
                        {investigation.missing_evidence.map((gap: string, i: number) => (
                          <li key={i}>{gap}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {Array.isArray(investigation.uncertainties) && investigation.uncertainties.length > 0 && (
                    <div className="investigation-block">
                      <h5>Model & Evidence Uncertainties</h5>
                      <ul className="gap-list">
                        {investigation.uncertainties.map((unc: string, i: number) => (
                          <li key={i}>{unc}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {Array.isArray(investigation.evidence) && investigation.evidence.length > 0 && (
                    <div className="investigation-block">
                      <h5>Retrieved Case Evidence ({investigation.evidence.length} sources)</h5>
                      <div className="evidence-grid" style={{ marginTop: '8px' }}>
                        {investigation.evidence.map((ev: any, idx: number) => (
                          <div className="evidence-card" key={idx}>
                            <div className="evidence-meta">
                              <span className="evidence-type-tag">{ev.source_type}</span>
                              <span className="evidence-id mono">{ev.source_id}</span>
                            </div>
                            <p style={{ margin: 0, fontSize: '11.5px', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
                              {ev.finding || (typeof ev.content === 'string' ? ev.content : JSON.stringify(ev.content))}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {Array.isArray(investigation.recommended_review_points) &&
                    investigation.recommended_review_points.length > 0 && (
                      <div className="investigation-block">
                        <h5>Recommended Action Points for Analyst</h5>
                        <ul className="action-list">
                          {investigation.recommended_review_points.map((pt: string, i: number) => (
                            <li key={i}>{pt}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                </div>
              </div>
            )}
          </div>

          {/* Raw JSON Accordion */}
          <div className="raw-accordion">
            <button
              className="raw-toggle-btn"
              onClick={() => setShowRaw(!showRaw)}
              aria-expanded={showRaw}
            >
              <FileText size={14} />
              <span>{showRaw ? 'Hide Raw Technical JSON Payload' : 'View Raw Technical JSON Payload (Auditor Mode)'}</span>
            </button>
            {showRaw && (
              <div className="raw-content">
                <pre className="raw-code">
                  {JSON.stringify(transaction, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
