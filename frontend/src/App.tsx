import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowDownToLine,
  Bell,
  Blocks,
  ChartNoAxesCombined,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Cpu,
  Database,
  ExternalLink,
  Eye,
  FileText,
  Gauge,
  LayoutDashboard,
  ListFilter,
  Play,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Siren,
  Sparkles,
  Square,
  TrendingUp,
  Workflow,
} from './icons';
import { api, apiBaseUrl, socketUrl } from './api';
import type { ActivityEvent, Batch, DashboardData, Page, Service, SystemStatus, Tx } from './types';
import AssistantPanel from './AssistantPanel';
import TransactionDetail from './TransactionDetail';
import ManualTransactionForm from './ManualTransactionForm';

type Tab =
  | 'Dashboard'
  | 'Transactions'
  | 'Alerts'
  | 'Investigations'
  | 'AI Assistant'
  | 'Batch simulator'
  | 'Analytics'
  | 'Monitoring'
  | 'Activity';

const formatCurrency = (n: any) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(n) || 0);

const formatDate = (s?: string) => (s ? new Date(s).toLocaleString() : '—');

function Pill({ ok, warn, label }: { ok?: boolean; warn?: boolean; label: string }) {
  const cls = ok ? 'ok' : warn ? 'warn' : 'bad';
  return (
    <span className={`pill ${cls}`}>
      <i />
      {label}
    </span>
  );
}

function RiskBadge({ tier }: { tier?: string }) {
  const t = tier || '—';
  const cls =
    t === 'L5'
      ? 'risk-l5'
      : t === 'L4'
      ? 'risk-l4'
      : t === 'L3'
      ? 'risk-l3'
      : t === 'L2'
      ? 'risk-l2'
      : t === 'L1'
      ? 'risk-l1'
      : 'risk-neutral';
  return <span className={`risk-badge ${cls}`}>{t}</span>;
}

function Metric({
  label,
  value,
  note,
  accent,
}: {
  label: string;
  value: any;
  note?: string;
  accent?: string;
}) {
  return (
    <article className="metric">
      <div className="metric-label">{label}</div>
      <strong style={{ color: accent }}>{value ?? '—'}</strong>
      {note && <small>{note}</small>}
    </article>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>('Dashboard');
  const [dashboard, setDashboard] = useState<DashboardData>();
  const [system, setSystem] = useState<SystemStatus>();
  const [monitor, setMonitor] = useState<any>();
  const [activityEvents, setActivityEvents] = useState<ActivityEvent[]>([]);
  const [error, setError] = useState('');
  const [stamp, setStamp] = useState('');
  const [selectedId, setSelectedId] = useState('');

  // Transactions list state
  const [page, setPage] = useState(1);
  const [txPage, setTxPage] = useState<Page<Tx>>({ items: [], page: 1, page_size: 25, total: 0 });
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('');
  const [kafkaFilter, setKafkaFilter] = useState('');
  const [investigationFilter, setInvestigationFilter] = useState('');
  const [amountMin, setAmountMin] = useState('');
  const [amountMax, setAmountMax] = useState('');
  const [sortBy, setSortBy] = useState('generated_at');
  const [sortOrder, setSortOrder] = useState('desc');
  const [showManualForm, setShowManualForm] = useState(false);

  // Alerts tab dedicated state
  const [alertPage, setAlertPage] = useState(1);
  const [alertSearch, setAlertSearch] = useState('');
  const [alertPageData, setAlertPageData] = useState<Page<Tx>>({ items: [], page: 1, page_size: 25, total: 0 });

  // Investigations tab dedicated state
  const [invPage, setInvPage] = useState(1);
  const [invSearch, setInvSearch] = useState('');
  const [invStatus, setInvStatus] = useState('');
  const [invPageData, setInvPageData] = useState<Page<Tx>>({ items: [], page: 1, page_size: 25, total: 0 });

  // Batch simulator state
  const [count, setCount] = useState(50);
  const [delay, setDelay] = useState(0.1);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [allBatches, setAllBatches] = useState<Batch[]>([]);
  const [busy, setBusy] = useState(false);
  const [batchError, setBatchError] = useState('');
  const [batchTransactions, setBatchTransactions] = useState<Tx[]>([]);

  // Periodic polling for overview
  const refresh = useCallback(async () => {
    try {
      const [d, s, m, act] = await Promise.all([
        api<DashboardData>('/api/dashboard'),
        api<SystemStatus>('/api/system/status'),
        api<any>('/api/monitoring/overview'),
        api<{ items: ActivityEvent[] }>('/api/activity?limit=50'),
      ]);
      setDashboard(d);
      setSystem(s);
      setMonitor(m);
      setActivityEvents(act.items);
      setStamp(new Date().toLocaleTimeString());
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'API unavailable');
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  // Load transactions
  const loadTx = useCallback(async () => {
    try {
      const q = new URLSearchParams({
        page: String(page),
        page_size: '25',
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      if (search.trim()) q.set('search', search.trim());
      if (typeFilter) q.set('transaction_type', typeFilter);
      if (riskFilter) q.set('risk_level', riskFilter);
      if (decisionFilter) q.set('decision', decisionFilter);
      if (kafkaFilter) q.set('kafka_status', kafkaFilter);
      if (investigationFilter) q.set('investigation_status', investigationFilter);
      if (amountMin.trim()) q.set('amount_min', amountMin.trim());
      if (amountMax.trim()) q.set('amount_max', amountMax.trim());

      const res = await api<Page<Tx>>(`/api/transactions?${q}`);
      setTxPage(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load transactions');
    }
  }, [page, search, typeFilter, riskFilter, decisionFilter, kafkaFilter, investigationFilter, amountMin, amountMax, sortBy, sortOrder]);

  // Load dedicated alerts query
  const loadAlerts = useCallback(async () => {
    try {
      const q = new URLSearchParams({
        page: String(alertPage),
        page_size: '25',
      });
      if (alertSearch.trim()) q.set('search', alertSearch.trim());
      const res = await api<Page<Tx>>(`/api/alerts?${q}`);
      setAlertPageData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load alerts queue');
    }
  }, [alertPage, alertSearch]);

  // Load dedicated investigations query
  const loadInvestigations = useCallback(async () => {
    try {
      const q = new URLSearchParams({
        page: String(invPage),
        page_size: '25',
      });
      if (invSearch.trim()) q.set('search', invSearch.trim());
      if (invStatus) q.set('status', invStatus);
      const res = await api<Page<Tx>>(`/api/investigations?${q}`);
      setInvPageData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load investigation cases');
    }
  }, [invPage, invSearch, invStatus]);

  // Load all batches
  const loadBatches = useCallback(async () => {
    try {
      const res = await api<{ items: Batch[] }>('/api/batches?limit=25');
      setAllBatches(res.items);
    } catch {}
  }, []);

  useEffect(() => {
    if (tab === 'Transactions' || tab === 'AI Assistant' || tab === 'Analytics') {
      void loadTx();
    } else if (tab === 'Alerts') {
      void loadAlerts();
    } else if (tab === 'Investigations') {
      void loadInvestigations();
    } else if (tab === 'Batch simulator') {
      void loadBatches();
    }
  }, [tab, loadTx, loadAlerts, loadInvestigations, loadBatches]);

  // Start Batch Simulator
  const startBatch = async (overrideCount?: number, overrideDelay?: number) => {
    setBatchError('');
    setBusy(true);
    try {
      const b = await api<Batch>('/api/batches', {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({
          count: Number(overrideCount ?? count),
          delay: Number(overrideDelay ?? delay),
          source: 'frontend_simulator',
        }),
      });
      setBatch(b);
      setTab('Batch simulator');
      void loadBatches();
    } catch (e) {
      setBatchError(e instanceof Error ? e.message : 'Unable to start batch');
    } finally {
      setBusy(false);
    }
  };

  const cancelBatch = async () => {
    if (!batch) return;
    try {
      const res = await api<Batch>(`/api/batches/${batch.batch_id}/cancel`, { method: 'POST' });
      setBatch(res);
      void loadBatches();
    } catch (e) {
      setBatchError(e instanceof Error ? e.message : 'Unable to cancel batch');
    }
  };

  // Follow active batch progress
  useEffect(() => {
    if (!batch?.batch_id || !['QUEUED', 'RUNNING'].includes(batch.status)) return;
    let ws: WebSocket;
    let stopped = false;
    try {
      ws = new WebSocket(socketUrl(`/ws/batches/${batch.batch_id}`));
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.batch) setBatch(msg.batch);
          else void api<Batch>(`/api/batches/${batch.batch_id}`).then(setBatch);
          if (msg.transaction) {
            void api<Page<Tx>>(`/api/batches/${batch.batch_id}/transactions?page=1&page_size=20`).then((r) =>
              setBatchTransactions(r.items)
            );
          }
        } catch {}
      };
      ws.onerror = () => {
        if (!stopped) void api<Batch>(`/api/batches/${batch.batch_id}`).then(setBatch).catch(() => {});
      };
    } catch {}

    const timer = setInterval(() => {
      void api<Batch>(`/api/batches/${batch.batch_id}`).then(setBatch).catch(() => {});
      void api<Page<Tx>>(`/api/batches/${batch.batch_id}/transactions?page=1&page_size=20`)
        .then((r) => setBatchTransactions(r.items))
        .catch(() => {});
    }, 2000);

    return () => {
      stopped = true;
      ws?.close();
      clearInterval(timer);
    };
  }, [batch?.batch_id, batch?.status]);

  // Export CSV
  const exportCsv = () => {
    const rows = txPage.items;
    const cols = [
      'transaction_id',
      'batch_id',
      'type',
      'amount',
      'nameOrig',
      'nameDest',
      'step',
      'risk_level',
      'anomaly_score',
      'xgboost_probability',
      'final_prediction',
      'final_decision',
      'isFraud_ground_truth',
      'kafka_status',
      'investigation_status',
    ];
    const csv = [
      cols.join(','),
      ...rows.map((t) =>
        [
          t.transaction_id,
          t.batch_id,
          t.payload?.type,
          t.payload?.amount,
          t.payload?.nameOrig,
          t.payload?.nameDest,
          t.payload?.step,
          t.risk_level,
          t.anomaly_score,
          t.xgboost_probability,
          t.final_prediction,
          t.final_decision,
          t.payload?.isFraud,
          t.kafka_status,
          t.investigation_status,
        ]
          .map((v) => `"${String(v ?? '').replaceAll('"', '""')}"`)
          .join(',')
      ),
    ].join('\r\n');

    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = `fraud-ledger-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const summary = dashboard?.summary ?? {
    generated: 0,
    processed: 0,
    fraud_alerts: 0,
    low_risk: 0,
    investigations: 0,
    investigation_pending: 0,
    investigation_success: 0,
    investigation_failed: 0,
  };
  const services: Record<string, Service> = system?.services ?? {};
  const serviceKeys = [
    'kafka',
    'spark',
    'cassandra',
    'chroma',
    'gemini',
    'fraud_api',
    'prometheus',
    'grafana',
    'alertmanager',
    'cadvisor',
  ];
  const activeServicesCount = serviceKeys.filter((k) => services[k]?.available).length;

  return (
    <div className="shell">
      {/* Enterprise Sidebar Navigation */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand">
            <div className="brand-mark">
              <ShieldAlert size={20} />
            </div>
            <div className="brand-text">
              <b>FRAUD CONTROL</b>
              <small>ENTERPRISE RISK OPERATIONS</small>
            </div>
          </div>
          <div className="sidebar-env">
            <span className="sidebar-env-dot" />
            <span>Streaming Engine: Kafka & Spark</span>
          </div>
        </div>

        <nav>
          {/* Operations Section */}
          <div className="nav-group">
            <span className="nav-section-title">Operations</span>
            <button
              className={`nav-item ${tab === 'Dashboard' ? 'active' : ''}`}
              onClick={() => {
                setTab('Dashboard');
                setSelectedId('');
              }}
            >
              <LayoutDashboard size={16} />
              <span>Overview</span>
            </button>
            <button
              className={`nav-item ${tab === 'Transactions' ? 'active' : ''}`}
              onClick={() => {
                setTab('Transactions');
                setPage(1);
              }}
            >
              <Workflow size={16} />
              <span>Transactions</span>
              {txPage.total > 0 && <span className="count-badge">{txPage.total.toLocaleString()}</span>}
            </button>
            <button
              className={`nav-item ${tab === 'Batch simulator' ? 'active' : ''}`}
              onClick={() => setTab('Batch simulator')}
            >
              <Play size={16} />
              <span>Batch Simulator</span>
            </button>
          </div>

          {/* Risk & Triage Section */}
          <div className="nav-group">
            <span className="nav-section-title">Risk & Triage</span>
            <button
              className={`nav-item ${tab === 'Alerts' ? 'active' : ''}`}
              onClick={() => {
                setTab('Alerts');
                setSelectedId('');
                setAlertPage(1);
              }}
            >
              <Siren size={16} />
              <span>Fraud Alerts</span>
              {summary.fraud_alerts > 0 && <em>{summary.fraud_alerts.toLocaleString()}</em>}
            </button>
            <button
              className={`nav-item ${tab === 'Investigations' ? 'active' : ''}`}
              onClick={() => {
                setTab('Investigations');
                setSelectedId('');
                setInvPage(1);
              }}
            >
              <FileText size={16} />
              <span>Case Investigations</span>
              {summary.investigations > 0 && <span className="count-badge">{summary.investigations.toLocaleString()}</span>}
            </button>
          </div>

          {/* Intelligence & Analytics Section */}
          <div className="nav-group">
            <span className="nav-section-title">Intelligence & AI</span>
            <button
              className={`nav-item ${tab === 'AI Assistant' ? 'active' : ''}`}
              onClick={() => setTab('AI Assistant')}
            >
              <Sparkles size={16} />
              <span>AI Assistant</span>
            </button>
            <button
              className={`nav-item ${tab === 'Analytics' ? 'active' : ''}`}
              onClick={() => setTab('Analytics')}
            >
              <ChartNoAxesCombined size={16} />
              <span>Model & Analytics</span>
            </button>
          </div>

          {/* Infrastructure Section */}
          <div className="nav-group">
            <span className="nav-section-title">Infrastructure</span>
            <button
              className={`nav-item ${tab === 'Monitoring' ? 'active' : ''}`}
              onClick={() => setTab('Monitoring')}
            >
              <Gauge size={16} />
              <span>System Health</span>
            </button>
            <button
              className={`nav-item ${tab === 'Activity' ? 'active' : ''}`}
              onClick={() => setTab('Activity')}
            >
              <Activity size={16} />
              <span>Audit Activity Log</span>
            </button>
          </div>
        </nav>

        <div className="sidebar-bottom">
          <div className="user-badge">
            <div className="avatar">FL</div>
            <div className="user-info">
              <b>Fraud Analyst Console</b>
              <small>Tier 3 Risk Operations</small>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Workspace */}
      <main>
        {/* Topbar */}
        <header className="topbar">
          <div className="topbar-left">
            <div className="crumb">
              Control Center <span>/</span> {tab}
            </div>
            <h1>
              {tab === 'Dashboard'
                ? 'Fraud Detection Control Center'
                : tab === 'Transactions'
                ? 'Transaction Stream & Operational Ledger'
                : tab === 'Alerts'
                ? 'Fraud Alerts Triage Queue'
                : tab === 'Investigations'
                ? 'Case Management & RAG Evidence'
                : tab === 'AI Assistant'
                ? 'AI Fraud Investigation Workbench'
                : tab === 'Batch simulator'
                ? 'Synthetic Stream Workload Simulator'
                : tab === 'Analytics'
                ? 'Risk Distribution & Decision Analytics'
                : tab === 'Monitoring'
                ? 'Infrastructure & Pipeline Health'
                : 'System Audit Trail'}
            </h1>
          </div>

          <div className="top-actions">
            <div className="heartbeat-pill">
              <span className={`live-dot ${error ? 'offline' : ''}`} />
              <span>{error ? 'API Offline' : `${activeServicesCount}/10 Services Healthy · ${stamp || 'Syncing'}`}</span>
            </div>

            <button
              className="icon-button"
              aria-label="Refresh"
              title="Refresh Control Center"
              onClick={() => {
                void refresh();
                if (tab === 'Transactions') void loadTx();
                else if (tab === 'Alerts') void loadAlerts();
                else if (tab === 'Investigations') void loadInvestigations();
              }}
            >
              <RefreshCw size={15} />
            </button>

            <button
              className="icon-button"
              aria-label="Alerts"
              title="Open Fraud Alerts"
              onClick={() => setTab('Alerts')}
            >
              <Bell size={15} />
            </button>
          </div>
        </header>

        {/* Workspace Content */}
        <section className="content">
          {error && (
            <div className="notice error">
              <AlertTriangle size={16} />
              <span>
                {error} · Backend: <code>{apiBaseUrl}</code>
              </span>
              <button
                onClick={() => {
                  void refresh();
                  if (tab === 'Transactions') void loadTx();
                  else if (tab === 'Alerts') void loadAlerts();
                  else if (tab === 'Investigations') void loadInvestigations();
                }}
              >
                Retry
              </button>
            </div>
          )}

          {/* ========================================================= */}
          {/* TAB 1: OVERVIEW DASHBOARD */}
          {/* ========================================================= */}
          {tab === 'Dashboard' && (
            <>
              {/* Top Operational Metrics */}
              <div className="section-heading">
                <div>
                  <h2>Operational Pipeline Overview</h2>
                  <p>Real-time Kafka event ingestion, Spark streaming decisions, and multi-tier ML scoring</p>
                </div>
                <button className="text-button" onClick={() => setTab('Analytics')}>
                  View analytics & funnel <ChevronRight size={14} />
                </button>
              </div>

              <div className="metric-grid">
                <Metric
                  label="Transactions Ingested"
                  value={summary.generated.toLocaleString()}
                  note="Wire events sent to Kafka topic"
                />
                <Metric
                  label="Processed by Spark"
                  value={summary.processed.toLocaleString()}
                  note="Scored with 33 engineered features"
                />
                <Metric
                  label="Fraud Alerts Flagged"
                  value={summary.fraud_alerts.toLocaleString()}
                  accent="#f87171"
                  note="Published to fraud-alerts topic (L4/L5)"
                />
                <Metric
                  label="Low Risk Cleared"
                  value={summary.low_risk.toLocaleString()}
                  accent="#34d399"
                  note="Normal traffic routed to low-risk topic"
                />
                <Metric
                  label="RAG Investigations"
                  value={summary.investigations.toLocaleString()}
                  note={`${summary.investigation_success} completed · ${summary.investigation_failed} failed`}
                />
                <Metric
                  label="Catch Rate"
                  value={
                    summary.processed > 0
                      ? `${((summary.fraud_alerts / summary.processed) * 100).toFixed(1)}%`
                      : '0.0%'
                  }
                  accent="#60a5fa"
                  note="Alert ratio across active batches"
                />
              </div>

              {/* Cluster Service Matrix */}
              <div className="section-heading spaced">
                <div>
                  <h2>Pipeline Infrastructure Health</h2>
                  <p>Real-time availability probes across the 10 core architecture services</p>
                </div>
                <button className="text-button" onClick={() => setTab('Monitoring')}>
                  View all metrics <ChevronRight size={14} />
                </button>
              </div>

              <div className="service-grid">
                {serviceKeys.map((k) => {
                  const s = services[k];
                  const label =
                    k === 'fraud_api'
                      ? 'Control Center API'
                      : k === 'gemini'
                      ? 'Gemini 3.5 Flash'
                      : k === 'chroma'
                      ? 'Chroma Vector DB'
                      : k === 'cadvisor'
                      ? 'cAdvisor'
                      : k[0].toUpperCase() + k.slice(1);
                  return (
                    <div className="service" key={k}>
                      <div className="service-icon">
                        {k === 'cassandra' || k === 'chroma' ? (
                          <Database size={15} />
                        ) : k === 'spark' || k === 'cadvisor' ? (
                          <Cpu size={15} />
                        ) : k === 'gemini' ? (
                          <Sparkles size={15} />
                        ) : (
                          <Blocks size={15} />
                        )}
                      </div>
                      <span>{label}</span>
                      <Pill ok={s?.available} label={s?.status ?? 'checking'} />
                    </div>
                  );
                })}
              </div>

              {/* Two-Column Layout: Live Transactions & Batch Quick-Start */}
              <div className="dashboard-columns">
                {/* Recent Transactions */}
                <div className="panel">
                  <div className="panel-head">
                    <div>
                      <h3>Recent Ingested Transactions</h3>
                      <p>Authoritative events persisted from Kafka stream</p>
                    </div>
                    <button className="text-button" onClick={() => setTab('Transactions')}>
                      All transactions <ChevronRight size={14} />
                    </button>
                  </div>

                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Transaction ID</th>
                          <th>Type</th>
                          <th>Amount</th>
                          <th>Risk Tier</th>
                          <th>Spark Decision</th>
                          <th>Kafka Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(dashboard?.recent_transactions ?? []).slice(0, 8).map((t) => (
                          <tr
                            key={t.transaction_id}
                            className="clickable"
                            onClick={() => {
                              setSelectedId(t.transaction_id);
                              setTab('Transactions');
                            }}
                          >
                            <td>
                              <b className="mono">{t.transaction_id}</b>
                              <small className="block">{formatDate(t.generated_at)}</small>
                            </td>
                            <td>
                              <span className="type-tag">{t.payload?.type ?? '—'}</span>
                            </td>
                            <td className="mono">{formatCurrency(t.payload?.amount)}</td>
                            <td>
                              <RiskBadge tier={t.risk_level} />
                            </td>
                            <td>
                              <span
                                className={`status-chip ${
                                  t.processing_status === 'FRAUD_ALERT'
                                    ? 'status-fraud'
                                    : t.processing_status === 'LOW_RISK'
                                    ? 'status-ok'
                                    : 'status-pending'
                                }`}
                              >
                                {t.final_decision ?? t.processing_status}
                              </span>
                            </td>
                            <td>
                              <Pill ok={t.kafka_status === 'SENT'} label={t.kafka_status} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!dashboard?.recent_transactions?.length && (
                      <div className="empty">No transactions ingested yet in this session</div>
                    )}
                  </div>
                </div>

                {/* Right: Quick Batch Injector & Audit Feed */}
                <div>
                  <div className="panel">
                    <div className="panel-head">
                      <div>
                        <h3>Quick Workload Injector</h3>
                        <p>Stream synthetic PaySim transactions to Kafka</p>
                      </div>
                      <div className="round-icon">
                        <Play size={15} fill="currentColor" />
                      </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <label>
                        Event Count
                        <input
                          type="number"
                          min="1"
                          max="10000"
                          value={count}
                          onChange={(e) => setCount(Math.max(1, +e.target.value))}
                        />
                      </label>
                      <label>
                        Send Interval (seconds)
                        <input
                          type="number"
                          min="0"
                          max="5"
                          step="0.05"
                          value={delay}
                          onChange={(e) => setDelay(Math.max(0, +e.target.value))}
                        />
                      </label>

                      <div style={{ display: 'flex', gap: '6px', margin: '4px 0' }}>
                        <button
                          type="button"
                          className="secondary"
                          style={{ flex: 1, fontSize: '11px' }}
                          onClick={() => void startBatch(50, 0.05)}
                        >
                          Burst 50
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          style={{ flex: 1, fontSize: '11px' }}
                          onClick={() => void startBatch(200, 0.02)}
                        >
                          Burst 200
                        </button>
                      </div>

                      <button
                        className="primary full"
                        disabled={busy}
                        onClick={() => void startBatch()}
                      >
                        <Play size={14} fill="currentColor" />
                        {busy ? 'Starting Ingestion…' : 'Generate & Send to Kafka'}
                      </button>

                      {batchError && <p className="error-text">{batchError}</p>}
                    </div>
                  </div>

                  {/* Audit timeline */}
                  <div className="panel">
                    <div className="panel-head">
                      <div>
                        <h3>Live Stream Activity</h3>
                        <p>Decisions and acknowledgements</p>
                      </div>
                      <button className="text-button" onClick={() => setTab('Activity')}>
                        All logs <ChevronRight size={14} />
                      </button>
                    </div>

                    <div>
                      {(activityEvents ?? []).slice(0, 5).map((e) => (
                        <div className="activity-row" key={e.event_id}>
                          <span
                            className="activity-dot"
                            style={{
                              background:
                                e.event_type === 'fraud_alert'
                                  ? '#ef4444'
                                  : e.event_type === 'low_risk'
                                  ? '#10b981'
                                  : '#3b82f6',
                            }}
                          />
                          <div>
                            <b>{e.message}</b>
                            <small>{e.transaction_id || e.batch_id}</small>
                          </div>
                          <time>{formatDate(e.created_at)}</time>
                        </div>
                      ))}
                      {!activityEvents?.length && (
                        <div className="empty">No recent activity events recorded</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}

          {/* ========================================================= */}
          {/* TAB 2: TRANSACTIONS LEDGER */}
          {/* ========================================================= */}
          {tab === 'Transactions' && (
            <>
              <div className="section-heading">
                <div>
                  <h2>Operational Transaction Ledger</h2>
                  <p>High-density query interface for wire events, ML inference scores, and ground truth validation</p>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    className="secondary"
                    onClick={() => setShowManualForm(!showManualForm)}
                  >
                    <Plus size={14} />
                    {showManualForm ? 'Hide Form' : 'Create Single Event'}
                  </button>
                  <button className="secondary" onClick={exportCsv}>
                    <ArrowDownToLine size={14} />
                    Export Page CSV
                  </button>
                </div>
              </div>

              {showManualForm && <ManualTransactionForm />}

              {/* Multi-filter Toolbar */}
              <div className="panel filters">
                <div className="searchbox">
                  <Search size={15} />
                  <input
                    placeholder="Search Transaction ID, Origin, or Destination account…"
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setPage(1);
                    }}
                  />
                </div>

                <div className="selectbox">
                  <ListFilter size={15} />
                  <select
                    value={typeFilter}
                    onChange={(e) => {
                      setTypeFilter(e.target.value);
                      setPage(1);
                    }}
                  >
                    <option value="">All Types</option>
                    <option value="CASH_OUT">CASH_OUT</option>
                    <option value="TRANSFER">TRANSFER</option>
                    <option value="PAYMENT">PAYMENT</option>
                    <option value="CASH_IN">CASH_IN</option>
                    <option value="DEBIT">DEBIT</option>
                  </select>
                </div>

                <div className="selectbox">
                  <select
                    value={riskFilter}
                    onChange={(e) => {
                      setRiskFilter(e.target.value);
                      setPage(1);
                    }}
                  >
                    <option value="">All Risk Tiers</option>
                    <option value="L5">L5 - Critical</option>
                    <option value="L4">L4 - High</option>
                    <option value="L3">L3 - Guarded</option>
                    <option value="L2">L2 - Low</option>
                    <option value="L1">L1 - Normal</option>
                  </select>
                </div>

                <div className="selectbox">
                  <select
                    value={decisionFilter}
                    onChange={(e) => {
                      setDecisionFilter(e.target.value);
                      setPage(1);
                    }}
                  >
                    <option value="">All Decisions</option>
                    <option value="FRAUD_ALERT">FRAUD_ALERT</option>
                    <option value="LOW_RISK">LOW_RISK</option>
                  </select>
                </div>

                <div className="selectbox">
                  <select
                    value={kafkaFilter}
                    onChange={(e) => {
                      setKafkaFilter(e.target.value);
                      setPage(1);
                    }}
                  >
                    <option value="">All Kafka Delivery</option>
                    <option value="SENT">SENT</option>
                    <option value="PENDING">PENDING</option>
                  </select>
                </div>

                <div className="selectbox">
                  <select
                    value={investigationFilter}
                    onChange={(e) => {
                      setInvestigationFilter(e.target.value);
                      setPage(1);
                    }}
                  >
                    <option value="">All Case Statuses</option>
                    <option value="COMPLETED">COMPLETED</option>
                    <option value="PARTIAL">PARTIAL</option>
                    <option value="PENDING">PENDING</option>
                    <option value="NOT_APPLICABLE">NOT_APPLICABLE</option>
                  </select>
                </div>

                <input
                  type="number"
                  placeholder="Min Amount"
                  value={amountMin}
                  onChange={(e) => {
                    setAmountMin(e.target.value);
                    setPage(1);
                  }}
                  style={{ width: '100px', height: '34px', background: 'var(--bg-input)', border: '1px solid var(--border-main)', borderRadius: '4px', padding: '0 8px', color: 'var(--text-main)', fontSize: '11px' }}
                />

                <input
                  type="number"
                  placeholder="Max Amount"
                  value={amountMax}
                  onChange={(e) => {
                    setAmountMax(e.target.value);
                    setPage(1);
                  }}
                  style={{ width: '100px', height: '34px', background: 'var(--bg-input)', border: '1px solid var(--border-main)', borderRadius: '4px', padding: '0 8px', color: 'var(--text-main)', fontSize: '11px' }}
                />

                <select
                  aria-label="Sort transactions by"
                  value={sortBy}
                  onChange={(e) => {
                    setSortBy(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="generated_at">Sort by Timestamp</option>
                  <option value="amount">Sort by Amount</option>
                  <option value="risk_level">Sort by Risk Level</option>
                </select>

                <select
                  aria-label="Sort order"
                  value={sortOrder}
                  onChange={(e) => {
                    setSortOrder(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="desc">Descending</option>
                  <option value="asc">Ascending</option>
                </select>

                <span className="subtle" style={{ marginLeft: 'auto' }}>
                  {txPage.total.toLocaleString()} total records
                </span>
              </div>

              {/* Transactions Dense Table */}
              <div className="panel" style={{ padding: '0', overflow: 'hidden' }}>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Transaction ID / Ingest Time</th>
                        <th>Type</th>
                        <th>Amount</th>
                        <th>Origin Account</th>
                        <th>Destination Account</th>
                        <th>Step</th>
                        <th>Kafka</th>
                        <th>Risk Tier</th>
                        <th>Anomaly Score</th>
                        <th>XGBoost Prob</th>
                        <th>ML Prediction</th>
                        <th>Ground Truth (PaySim)</th>
                        <th>Final Decision</th>
                        <th>Case Status</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {txPage.items.map((t) => (
                        <tr
                          key={t.transaction_id}
                          className={`clickable ${selectedId === t.transaction_id ? 'row-selected' : ''}`}
                          onClick={() => setSelectedId(t.transaction_id)}
                        >
                          <td>
                            <b className="mono">{t.transaction_id}</b>
                            <small className="block">{formatDate(t.generated_at)}</small>
                          </td>
                          <td>
                            <span className="type-tag">{t.payload?.type ?? '—'}</span>
                          </td>
                          <td className="mono" style={{ fontWeight: 600 }}>
                            {formatCurrency(t.payload?.amount)}
                          </td>
                          <td className="mono" style={{ fontSize: '11px' }}>
                            {t.payload?.nameOrig ?? '—'}
                          </td>
                          <td className="mono" style={{ fontSize: '11px' }}>
                            {t.payload?.nameDest ?? '—'}
                          </td>
                          <td className="mono">{t.payload?.step ?? '—'}</td>
                          <td>
                            <Pill ok={t.kafka_status === 'SENT'} label={t.kafka_status} />
                          </td>
                          <td>
                            <RiskBadge tier={t.risk_level} />
                          </td>
                          <td className="mono">
                            {t.anomaly_score !== undefined ? Number(t.anomaly_score).toFixed(4) : '—'}
                          </td>
                          <td className="mono">
                            {t.xgboost_probability !== undefined
                              ? `${(Number(t.xgboost_probability) * 100).toFixed(1)}%`
                              : '—'}
                          </td>
                          <td className="mono">{t.final_prediction ?? '—'}</td>
                          <td>
                            {t.payload?.isFraud !== undefined ? (
                              <span
                                className={`pill ${t.payload.isFraud === 1 ? 'bad' : 'ok'}`}
                              >
                                {t.payload.isFraud === 1 ? 'Fraud (1)' : 'Legit (0)'}
                              </span>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td>
                            <span
                              className={`status-chip ${
                                t.processing_status === 'FRAUD_ALERT'
                                  ? 'status-fraud'
                                  : t.processing_status === 'LOW_RISK'
                                  ? 'status-ok'
                                  : 'status-pending'
                              }`}
                            >
                              {t.final_decision ?? t.processing_status}
                            </span>
                          </td>
                          <td>
                            <span className="status-chip status-neutral">
                              {t.investigation_status}
                            </span>
                          </td>
                          <td>
                            <button
                              className="secondary"
                              style={{ height: '26px', padding: '0 8px', fontSize: '11px' }}
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedId(t.transaction_id);
                              }}
                            >
                              <Eye size={12} /> Inspect
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!txPage.items.length && (
                    <div className="empty">No transactions match the selected filters</div>
                  )}
                </div>

                <div style={{ padding: '0 16px 14px' }}>
                  <Pagination
                    page={page}
                    total={txPage.total}
                    size={txPage.page_size}
                    set={setPage}
                  />
                </div>
              </div>

              {/* Authoritative Detail Drawer */}
              {selectedId && (
                <TransactionDetail
                  id={selectedId}
                  onInvestigate={() => setTab('AI Assistant')}
                  onClose={() => setSelectedId('')}
                />
              )}
            </>
          )}

          {/* ========================================================= */}
          {/* TAB 3: FRAUD ALERTS TRIAGE */}
          {/* ========================================================= */}
          {tab === 'Alerts' && (
            <>
              <div className="section-heading">
                <div>
                  <h2>Fraud Alerts Triage Queue</h2>
                  <p>Real-time queue of high-risk transactions published to the Kafka fraud-alerts topic</p>
                </div>
              </div>

              <div className="metric-grid">
                <Metric label="Total Alerts in Queue" value={alertPageData.total.toLocaleString()} accent="#f87171" />
                <Metric
                  label="Critical L5 Alerts"
                  value={alertPageData.items.filter((a) => a.risk_level === 'L5').length}
                  accent="#ef4444"
                  note="In current query view"
                />
                <Metric
                  label="High L4 Alerts"
                  value={alertPageData.items.filter((a) => a.risk_level === 'L4').length}
                  accent="#fb923c"
                  note="In current query view"
                />
                <Metric
                  label="Pending Review"
                  value={alertPageData.items.filter((a) => a.investigation_status === 'PENDING').length}
                  accent="#60a5fa"
                  note="Awaiting RAG resolution"
                />
              </div>

              {/* Alerts search toolbar */}
              <div className="panel filters">
                <div className="searchbox">
                  <Search size={15} />
                  <input
                    placeholder="Search alert by Transaction ID or Account ID…"
                    value={alertSearch}
                    onChange={(e) => {
                      setAlertSearch(e.target.value);
                      setAlertPage(1);
                    }}
                  />
                </div>
                <span className="subtle" style={{ marginLeft: 'auto' }}>
                  {alertPageData.total.toLocaleString()} active alerts
                </span>
              </div>

              <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Alerted Transaction ID</th>
                        <th>Alert ID</th>
                        <th>Event Type</th>
                        <th>Amount</th>
                        <th>Sender Account</th>
                        <th>Recipient Account</th>
                        <th>Risk Tier</th>
                        <th>Anomaly Score</th>
                        <th>XGBoost Prob</th>
                        <th>Ground Truth (PaySim)</th>
                        <th>Investigation Status</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {alertPageData.items.map((a) => (
                        <tr
                          key={a.transaction_id}
                          className={`clickable ${selectedId === a.transaction_id ? 'row-selected' : ''}`}
                          onClick={() => setSelectedId(a.transaction_id)}
                        >
                          <td>
                            <b className="mono">{a.transaction_id}</b>
                            <small className="block">{formatDate(a.generated_at)}</small>
                          </td>
                          <td className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            {a.alert_id || '—'}
                          </td>
                          <td>
                            <span className="type-tag">{a.payload?.type ?? '—'}</span>
                          </td>
                          <td className="mono" style={{ fontWeight: 600 }}>
                            {formatCurrency(a.payload?.amount)}
                          </td>
                          <td className="mono">{a.payload?.nameOrig ?? '—'}</td>
                          <td className="mono">{a.payload?.nameDest ?? '—'}</td>
                          <td>
                            <RiskBadge tier={a.risk_level} />
                          </td>
                          <td className="mono">
                            {a.anomaly_score !== undefined ? Number(a.anomaly_score).toFixed(4) : '—'}
                          </td>
                          <td className="mono">
                            {a.xgboost_probability !== undefined
                              ? `${(Number(a.xgboost_probability) * 100).toFixed(1)}%`
                              : '—'}
                          </td>
                          <td>
                            <span className={`pill ${a.payload?.isFraud === 1 ? 'bad' : 'ok'}`}>
                              {a.payload?.isFraud === 1 ? 'Fraud (1)' : 'Benign (0)'}
                            </span>
                          </td>
                          <td>
                            <span className="status-chip status-neutral">
                              {a.investigation_status}
                            </span>
                          </td>
                          <td>
                            <div style={{ display: 'flex', gap: '4px' }}>
                              <button
                                className="primary"
                                style={{ height: '26px', padding: '0 8px', fontSize: '11px' }}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSelectedId(a.transaction_id);
                                  setTab('AI Assistant');
                                }}
                              >
                                <Sparkles size={12} /> Investigate
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!alertPageData.items.length && (
                    <div className="empty">No fraud alerts matching this search</div>
                  )}
                </div>

                <div style={{ padding: '0 16px 14px' }}>
                  <Pagination
                    page={alertPage}
                    total={alertPageData.total}
                    size={alertPageData.page_size}
                    set={setAlertPage}
                  />
                </div>
              </div>

              {selectedId && (
                <TransactionDetail
                  id={selectedId}
                  onInvestigate={() => setTab('AI Assistant')}
                  onClose={() => setSelectedId('')}
                />
              )}
            </>
          )}

          {/* ========================================================= */}
          {/* TAB 4: CASE INVESTIGATIONS */}
          {/* ========================================================= */}
          {tab === 'Investigations' && (
            <>
              <div className="section-heading">
                <div>
                  <h2>Case Management & Evidence Workspace</h2>
                  <p>Automated and manual investigation records backed by Cassandra and Chroma RAG vector retrieval</p>
                </div>
              </div>

              <div className="metric-grid">
                <Metric label="Total Investigation Records" value={invPageData.total.toLocaleString()} />
                <Metric
                  label="Completed Analyses"
                  value={summary.investigation_success.toLocaleString()}
                  accent="#34d399"
                  note="Persisted RAG cases"
                />
                <Metric
                  label="Pending In-Flight"
                  value={summary.investigation_pending.toLocaleString()}
                  accent="#60a5fa"
                  note="Under active triage"
                />
                <Metric
                  label="Failed Analyses"
                  value={summary.investigation_failed.toLocaleString()}
                  accent="#f87171"
                  note="Missing retrieval/context"
                />
              </div>

              {/* Investigations search & filter toolbar */}
              <div className="panel filters">
                <div className="searchbox">
                  <Search size={15} />
                  <input
                    placeholder="Search case by Transaction ID or Account ID…"
                    value={invSearch}
                    onChange={(e) => {
                      setInvSearch(e.target.value);
                      setInvPage(1);
                    }}
                  />
                </div>

                <div className="selectbox">
                  <select
                    value={invStatus}
                    onChange={(e) => {
                      setInvStatus(e.target.value);
                      setInvPage(1);
                    }}
                  >
                    <option value="">All Case Statuses</option>
                    <option value="COMPLETED">COMPLETED</option>
                    <option value="PARTIAL">PARTIAL</option>
                    <option value="PENDING">PENDING</option>
                    <option value="INSUFFICIENT_EVIDENCE">INSUFFICIENT_EVIDENCE</option>
                    <option value="FAILED">FAILED</option>
                  </select>
                </div>

                <span className="subtle" style={{ marginLeft: 'auto' }}>
                  {invPageData.total.toLocaleString()} total cases
                </span>
              </div>

              <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Investigation ID / Transaction</th>
                        <th>Type</th>
                        <th>Amount</th>
                        <th>Risk Tier</th>
                        <th>Status</th>
                        <th>Summary / Risk Drivers</th>
                        <th>Evidence Retrieved</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invPageData.items.map((i) => (
                        <tr
                          key={i.transaction_id}
                          className={`clickable ${selectedId === i.transaction_id ? 'row-selected' : ''}`}
                          onClick={() => setSelectedId(i.transaction_id)}
                        >
                          <td>
                            <b className="mono">{i.investigation_id || `CASE-${i.transaction_id}`}</b>
                            <small className="block mono">{i.transaction_id}</small>
                          </td>
                          <td>
                            <span className="type-tag">{i.payload?.type ?? '—'}</span>
                          </td>
                          <td className="mono">{formatCurrency(i.payload?.amount)}</td>
                          <td>
                            <RiskBadge tier={i.risk_level} />
                          </td>
                          <td>
                            <span
                              className={`status-chip ${
                                i.investigation_status === 'COMPLETED'
                                  ? 'status-ok'
                                  : i.investigation_status === 'PARTIAL'
                                  ? 'status-pending'
                                  : 'status-neutral'
                              }`}
                            >
                              {i.investigation_status}
                            </span>
                          </td>
                          <td style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                              {i.investigation?.investigation_summary ||
                                (Array.isArray(i.investigation?.risk_factors)
                                  ? i.investigation.risk_factors[0]
                                  : 'Automated RAG evaluation in progress')}
                            </span>
                          </td>
                          <td className="mono">
                            {Array.isArray(i.investigation?.evidence)
                              ? `${i.investigation.evidence.length} sources`
                              : 'Pending'}
                          </td>
                          <td>
                            <button
                              className="secondary"
                              style={{ height: '26px', padding: '0 8px', fontSize: '11px' }}
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedId(i.transaction_id);
                              }}
                            >
                              <Eye size={12} /> View File
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!invPageData.items.length && (
                    <div className="empty">No investigation cases matching this criteria</div>
                  )}
                </div>

                <div style={{ padding: '0 16px 14px' }}>
                  <Pagination
                    page={invPage}
                    total={invPageData.total}
                    size={invPageData.page_size}
                    set={setInvPage}
                  />
                </div>
              </div>

              {selectedId && (
                <TransactionDetail
                  id={selectedId}
                  onInvestigate={() => setTab('AI Assistant')}
                  onClose={() => setSelectedId('')}
                />
              )}
            </>
          )}

          {/* ========================================================= */}
          {/* TAB 5: AI ASSISTANT (GEMINI RAG INVESTIGATOR) */}
          {/* ========================================================= */}
          {tab === 'AI Assistant' && (
            <>
              <div className="section-heading">
                <div>
                  <h2>AI Fraud Investigation Workbench</h2>
                  <p>
                    Interactive fraud intelligence powered by Google Gemini (gemini-3.5-flash-lite) grounded in ChromaDB RAG and live Cassandra context
                  </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="subtle">Target Context:</span>
                  <select
                    aria-label="Selected transaction"
                    value={selectedId}
                    onChange={(e) => setSelectedId(e.target.value)}
                    style={{ minWidth: '240px' }}
                  >
                    <option value="">General Pipeline Knowledge Base</option>
                    {txPage.items.map((t) => (
                      <option key={t.transaction_id} value={t.transaction_id}>
                        {t.transaction_id} · {t.payload?.type} · {formatCurrency(t.payload?.amount)}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {selectedId && (
                <TransactionDetail
                  id={selectedId}
                  onInvestigate={() =>
                    document.querySelector<HTMLTextAreaElement>('.assistant-input-box textarea')?.focus()
                  }
                  onClose={() => setSelectedId('')}
                />
              )}

              <AssistantPanel key={selectedId || 'general'} transactionId={selectedId || undefined} />
            </>
          )}

          {/* ========================================================= */}
          {/* TAB 6: BATCH SIMULATOR */}
          {/* ========================================================= */}
          {tab === 'Batch simulator' && (
            <>
              <div className="section-heading">
                <div>
                  <h2>Synthetic Stream Workload Simulator</h2>
                  <p>Stress-test the end-to-end Kafka topic ingest, Spark streaming micro-batches, and inference pipelines</p>
                </div>
              </div>

              <div className="panel simulator">
                <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                  <label style={{ minWidth: '180px' }}>
                    Transactions to Generate
                    <input
                      type="number"
                      min="1"
                      max="10000"
                      value={count}
                      onChange={(e) => setCount(Math.max(1, +e.target.value))}
                    />
                  </label>
                  <label style={{ minWidth: '180px' }}>
                    Delay Between Sends (sec)
                    <input
                      type="number"
                      min="0"
                      max="5"
                      step="0.01"
                      value={delay}
                      onChange={(e) => setDelay(Math.max(0, +e.target.value))}
                    />
                  </label>
                  <button
                    className="primary"
                    disabled={busy || ['QUEUED', 'RUNNING'].includes(batch?.status ?? '')}
                    onClick={() => void startBatch()}
                    style={{ height: '34px', marginBottom: '11px' }}
                  >
                    <Play size={14} fill="currentColor" />
                    {busy ? 'Initiating…' : 'Generate & Send Transactions'}
                  </button>
                </div>

                {batchError && <div className="notice error">{batchError}</div>}

                {batch && (
                  <>
                    <div className="batch-title">
                      <div>
                        <span className="eyebrow">ACTIVE BATCH ID</span>
                        <h3>{batch.batch_id}</h3>
                      </div>
                      <Pill ok={batch.status === 'COMPLETED'} label={batch.status} />
                    </div>

                    <div className="progress-info">
                      <span>Stream Generation Progress</span>
                      <b>
                        {batch.generated_count ?? 0} / {batch.requested_count} events
                      </b>
                    </div>
                    <div className="progress">
                      <i style={{ width: `${batch.progress ?? 0}%` }} />
                    </div>

                    <div className="batch-stats">
                      <span>
                        Requested: <b>{batch.requested_count ?? 0}</b>
                      </span>
                      <span>
                        Generated: <b>{batch.generated_count ?? 0}</b>
                      </span>
                      <span>
                        Kafka Acknowledged: <b>{batch.sent_count ?? 0}</b>
                      </span>
                      <span>
                        Send Errors: <b>{batch.failed_count ?? 0}</b>
                      </span>
                      <span>
                        Spark Processed: <b>{batch.processed ?? 0}</b>
                      </span>
                      <span>
                        Fraud Alerts (L4/L5): <b>{batch.fraud_alerts ?? 0}</b>
                      </span>
                      <span>
                        Low Risk (L1/L2/L3): <b>{batch.low_risk ?? 0}</b>
                      </span>
                      <span>
                        RAG Investigations: <b>{batch.investigation_requests ?? 0}</b>
                      </span>
                      <span>
                        Succeeded: <b>{batch.investigations_succeeded ?? 0}</b>
                      </span>
                      <span>
                        Elapsed:{' '}
                        <b>
                          {batch.started_at
                            ? `${Math.max(
                                0,
                                ((batch.completed_at ? Date.parse(batch.completed_at) : Date.now()) -
                                  Date.parse(batch.started_at)) /
                                  1000
                              ).toFixed(1)} s`
                            : '—'}
                        </b>
                      </span>
                    </div>

                    {['QUEUED', 'RUNNING'].includes(batch.status) && (
                      <button className="danger-button" onClick={() => void cancelBatch()}>
                        <Square size={13} /> Cancel Active Batch
                      </button>
                    )}
                  </>
                )}
              </div>

              {batch?.batch_id && (
                <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
                  <div className="panel-head" style={{ padding: '16px 20px 0' }}>
                    <div>
                      <h3>Transactions in Batch {batch.batch_id}</h3>
                      <p>Pipeline decisions update dynamically as Spark consumes the stream</p>
                    </div>
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Transaction ID</th>
                          <th>Type</th>
                          <th>Amount</th>
                          <th>Kafka</th>
                          <th>Risk Tier</th>
                          <th>Spark Decision</th>
                          <th>PaySim Ground Truth</th>
                          <th>Case Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {batchTransactions.map((t) => (
                          <tr
                            key={t.transaction_id}
                            className="clickable"
                            onClick={() => setSelectedId(t.transaction_id)}
                          >
                            <td className="mono">{t.transaction_id}</td>
                            <td>
                              <span className="type-tag">{t.payload?.type}</span>
                            </td>
                            <td className="mono">{formatCurrency(t.payload?.amount)}</td>
                            <td>
                              <Pill ok={t.kafka_status === 'SENT'} label={t.kafka_status} />
                            </td>
                            <td>
                              <RiskBadge tier={t.risk_level} />
                            </td>
                            <td>
                              <span
                                className={`status-chip ${
                                  t.processing_status === 'FRAUD_ALERT'
                                    ? 'status-fraud'
                                    : 'status-ok'
                                }`}
                              >
                                {t.final_decision ?? t.processing_status}
                              </span>
                            </td>
                            <td>{t.payload?.isFraud === 1 ? 'Fraud (1)' : 'Legit (0)'}</td>
                            <td>{t.investigation_status}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!batchTransactions.length && (
                      <div className="empty">Awaiting decisions for transactions in this batch…</div>
                    )}
                  </div>
                </div>
              )}

              {/* Historical Batches Table */}
              <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
                <div className="panel-head" style={{ padding: '16px 20px 0' }}>
                  <div>
                    <h3>Historical Streaming Batches</h3>
                    <p>Recent workload executions recorded in SQLite control store</p>
                  </div>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Batch ID</th>
                        <th>Created At</th>
                        <th>Status</th>
                        <th>Requested</th>
                        <th>Kafka Ack</th>
                        <th>Spark Processed</th>
                        <th>Fraud Alerts</th>
                        <th>Low Risk</th>
                        <th>Investigations</th>
                      </tr>
                    </thead>
                    <tbody>
                      {allBatches.map((b) => (
                        <tr
                          key={b.batch_id}
                          className="clickable"
                          onClick={() => {
                            setBatch(b);
                            void api<Page<Tx>>(`/api/batches/${b.batch_id}/transactions?page=1&page_size=20`).then((r) =>
                              setBatchTransactions(r.items)
                            );
                          }}
                        >
                          <td className="mono">
                            <b>{b.batch_id}</b>
                          </td>
                          <td className="mono">{formatDate(b.created_at)}</td>
                          <td>
                            <Pill ok={b.status === 'COMPLETED'} label={b.status} />
                          </td>
                          <td className="mono">{b.requested_count}</td>
                          <td className="mono">{b.sent_count}</td>
                          <td className="mono">{b.processed}</td>
                          <td className="mono" style={{ color: '#f87171' }}>
                            {b.fraud_alerts}
                          </td>
                          <td className="mono" style={{ color: '#34d399' }}>
                            {b.low_risk}
                          </td>
                          <td className="mono">{b.investigation_requests}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!allBatches.length && (
                    <div className="empty">No previous batches logged</div>
                  )}
                </div>
              </div>
            </>
          )}

          {/* ========================================================= */}
          {/* TAB 7: MODEL & RISK ANALYTICS */}
          {/* ========================================================= */}
          {tab === 'Analytics' && (
            <>
              <div className="section-heading">
                <div>
                  <h2>Model & Risk Analytics</h2>
                  <p>Performance evaluation, risk tier distributions, and streaming decision funnels</p>
                </div>
              </div>

              {/* Analytics Top Cards */}
              <div className="metric-grid">
                <Metric label="Total Evaluated Events" value={txPage.total.toLocaleString()} />
                <Metric
                  label="Fraud Rate"
                  value={
                    summary.processed > 0
                      ? `${((summary.fraud_alerts / summary.processed) * 100).toFixed(1)}%`
                      : '0.0%'
                  }
                  accent="#f87171"
                  note="Alerts / Spark processed"
                />
                <Metric
                  label="Critical L5 Rate"
                  value={
                    txPage.items.length > 0
                      ? `${(
                          (txPage.items.filter((t) => t.risk_level === 'L5').length /
                            txPage.items.length) *
                          100
                        ).toFixed(1)}%`
                      : '0.0%'
                  }
                  accent="#ef4444"
                  note="In current ledger page"
                />
                <Metric
                  label="Features Contract"
                  value="33 Attributes"
                  note="19 base features + 14 behavioral features"
                />
              </div>

              <div className="detail-grid-layout">
                {/* Decision Funnel */}
                <div className="detail-card">
                  <div className="detail-card-head">
                    <h4>
                      <TrendingUp size={15} /> Pipeline Decision Funnel
                    </h4>
                  </div>
                  <div className="detail-card-content">
                    <div className="funnel-container">
                      <div className="funnel-step">
                        <span className="funnel-step-num">1</span>
                        <div className="funnel-step-info">
                          <span className="funnel-step-title">PaySim Wire Event Generation</span>
                          <span className="funnel-step-desc">Validated 11 raw transaction fields</span>
                        </div>
                        <span className="funnel-step-stat">{summary.generated.toLocaleString()}</span>
                      </div>
                      <div className="funnel-step">
                        <span className="funnel-step-num">2</span>
                        <div className="funnel-step-info">
                          <span className="funnel-step-title">Kafka Distributed Ingestion</span>
                          <span className="funnel-step-desc">Acknowledged topic partition writes</span>
                        </div>
                        <span className="funnel-step-stat">{summary.generated.toLocaleString()}</span>
                      </div>
                      <div className="funnel-step">
                        <span className="funnel-step-num">3</span>
                        <div className="funnel-step-info">
                          <span className="funnel-step-title">Spark Feature Engineering (33 Features)</span>
                          <span className="funnel-step-desc">Rolling accounts, balance changes & ratios</span>
                        </div>
                        <span className="funnel-step-stat">{summary.processed.toLocaleString()}</span>
                      </div>
                      <div className="funnel-step">
                        <span className="funnel-step-num">4</span>
                        <div className="funnel-step-info">
                          <span className="funnel-step-title">Isolation Forest & Autoencoder Scoring</span>
                          <span className="funnel-step-desc">L1–L5 risk classification thresholds</span>
                        </div>
                        <span className="funnel-step-stat">{summary.processed.toLocaleString()}</span>
                      </div>
                      <div className="funnel-step">
                        <span className="funnel-step-num">5</span>
                        <div className="funnel-step-info">
                          <span className="funnel-step-title">Fraud Alert Escalation & RAG Triage</span>
                          <span className="funnel-step-desc">High risk routed to Cassandra & ChromaDB</span>
                        </div>
                        <span className="funnel-step-stat" style={{ color: '#f87171' }}>
                          {summary.fraud_alerts.toLocaleString()}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Risk Tier Distribution */}
                <div className="detail-card">
                  <div className="detail-card-head">
                    <h4>
                      <ShieldAlert size={15} /> Risk Tier Distribution (L1 – L5)
                    </h4>
                  </div>
                  <div className="detail-card-content">
                    <div className="dist-bars">
                      {[
                        {
                          tier: 'L5 - Critical Threat',
                          cls: 'fill-rose',
                          count: txPage.items.filter((t) => t.risk_level === 'L5').length,
                        },
                        {
                          tier: 'L4 - High Suspicion',
                          cls: 'fill-orange',
                          count: txPage.items.filter((t) => t.risk_level === 'L4').length,
                        },
                        {
                          tier: 'L3 - Guarded Risk',
                          cls: 'fill-amber',
                          count: txPage.items.filter((t) => t.risk_level === 'L3').length,
                        },
                        {
                          tier: 'L2 - Low Anomaly',
                          cls: 'fill-teal',
                          count: txPage.items.filter((t) => t.risk_level === 'L2').length,
                        },
                        {
                          tier: 'L1 - Normal Flow',
                          cls: 'fill-emerald',
                          count: txPage.items.filter((t) => t.risk_level === 'L1').length,
                        },
                      ].map((item, idx) => {
                        const total = Math.max(1, txPage.items.length);
                        const pct = ((item.count / total) * 100).toFixed(1);
                        return (
                          <div className="dist-bar-item" key={idx}>
                            <div className="dist-bar-header">
                              <span className="dist-bar-label">{item.tier}</span>
                              <span className="dist-bar-val">
                                {item.count} ({pct}%)
                              </span>
                            </div>
                            <div className="dist-bar-track">
                              <div
                                className={`dist-bar-fill ${item.cls}`}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Confusion Matrix vs PaySim Ground Truth */}
                <div className="detail-card span-full">
                  <div className="detail-card-head">
                    <h4>
                      <CheckCircle size={15} /> Empirical Confusion Matrix (Observed Batch Sample)
                    </h4>
                    <span className="badge-tag">PAYSIM GROUND TRUTH BENCHMARK</span>
                  </div>
                  <div className="detail-card-content">
                    {(() => {
                      const evaluated = txPage.items.filter(
                        (t) => t.payload?.isFraud !== undefined && t.final_prediction !== undefined
                      );
                      const tp = evaluated.filter(
                        (t) => t.payload?.isFraud === 1 && (t.final_prediction === 1 || t.processing_status === 'FRAUD_ALERT')
                      ).length;
                      const fp = evaluated.filter(
                        (t) => t.payload?.isFraud === 0 && (t.final_prediction === 1 || t.processing_status === 'FRAUD_ALERT')
                      ).length;
                      const tn = evaluated.filter(
                        (t) => t.payload?.isFraud === 0 && t.final_prediction === 0 && t.processing_status !== 'FRAUD_ALERT'
                      ).length;
                      const fn = evaluated.filter(
                        (t) => t.payload?.isFraud === 1 && t.final_prediction === 0 && t.processing_status !== 'FRAUD_ALERT'
                      ).length;

                      const precision = tp + fp > 0 ? ((tp / (tp + fp)) * 100).toFixed(1) : '—';
                      const recall = tp + fn > 0 ? ((tp / (tp + fn)) * 100).toFixed(1) : '—';
                      const f1 =
                        tp + fp > 0 && tp + fn > 0
                          ? ((2 * tp) / (2 * tp + fp + fn) * 100).toFixed(1)
                          : '—';

                      return (
                        <>
                          <div className="cm-grid">
                            <div className="cm-cell cm-tp">
                              <span className="cm-cell-title">True Positives (TP)</span>
                              <span className="cm-cell-count">{tp}</span>
                              <span className="cm-cell-desc">Fraud correctly caught and alerted</span>
                            </div>
                            <div className="cm-cell cm-fp">
                              <span className="cm-cell-title">False Positives (FP)</span>
                              <span className="cm-cell-count">{fp}</span>
                              <span className="cm-cell-desc">Legitimate transactions over-flagged</span>
                            </div>
                            <div className="cm-cell cm-fn">
                              <span className="cm-cell-title">False Negatives (FN)</span>
                              <span className="cm-cell-count">{fn}</span>
                              <span className="cm-cell-desc">Undetected fraud (Highest financial risk!)</span>
                            </div>
                            <div className="cm-cell cm-tn">
                              <span className="cm-cell-title">True Negatives (TN)</span>
                              <span className="cm-cell-count">{tn}</span>
                              <span className="cm-cell-desc">Legitimate transactions cleared as low risk</span>
                            </div>
                          </div>

                          <div style={{ display: 'flex', gap: '20px', marginTop: '14px', fontSize: '12px' }}>
                            <span>
                              Precision: <b className="mono">{precision}%</b>
                            </span>
                            <span>
                              Recall: <b className="mono">{recall}%</b>
                            </span>
                            <span>
                              F1 Score: <b className="mono">{f1}%</b>
                            </span>
                          </div>
                        </>
                      );
                    })()}
                  </div>
                </div>
              </div>
            </>
          )}

          {/* ========================================================= */}
          {/* TAB 8: SYSTEM MONITORING */}
          {/* ========================================================= */}
          {tab === 'Monitoring' && (
            <>
              <div className="section-heading">
                <div>
                  <h2>Infrastructure & Metrics Monitoring</h2>
                  <p>Direct query integration with Prometheus targets, Grafana dashboards, and Alertmanager</p>
                </div>
                <span className="subtle">Last scrape synced {stamp}</span>
              </div>

              {/* External Tool Links */}
              <div className="monitor-links">
                <ExternalLinkCard
                  label="Prometheus"
                  href={monitor?.links?.prometheus ?? 'http://localhost:9090'}
                  status={monitor?.prometheus?.status}
                />
                <ExternalLinkCard
                  label="Grafana"
                  href={monitor?.links?.grafana ?? 'http://localhost:3000'}
                  status={monitor?.grafana?.status}
                />
                <ExternalLinkCard
                  label="Alertmanager"
                  href={monitor?.links?.alertmanager ?? 'http://localhost:9093'}
                  status={monitor?.alertmanager?.status}
                />
              </div>

              {/* Prometheus Scrape Targets */}
              <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
                <div className="panel-head" style={{ padding: '16px 20px 0' }}>
                  <div>
                    <h3>Prometheus Scrape Targets</h3>
                    <p>Live target endpoints queried from /api/v1/targets</p>
                  </div>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Job Name</th>
                        <th>Instance Endpoint</th>
                        <th>Health</th>
                        <th>Last Scrape Timestamp</th>
                        <th>Duration</th>
                        <th>Last Error Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(monitor?.targets?.targets ?? []).map((t: any) => (
                        <tr key={`${t.job}${t.instance}`}>
                          <td>
                            <b>{t.job}</b>
                          </td>
                          <td className="mono">{t.instance}</td>
                          <td>
                            <Pill ok={t.health === 'up'} label={t.health} />
                          </td>
                          <td>{formatDate(t.last_scrape)}</td>
                          <td className="mono">
                            {t.scrape_duration_seconds
                              ? `${Number(t.scrape_duration_seconds).toFixed(3)} s`
                              : '—'}
                          </td>
                          <td className="error-cell">{t.last_error || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!monitor?.targets?.targets?.length && (
                    <div className="empty">Prometheus targets currently unavailable or starting</div>
                  )}
                </div>
              </div>

              {/* Metric Tiles from Prometheus */}
              <div className="metric-grid monitoring-metrics spaced">
                {Object.entries(monitor?.metrics ?? {}).map(([name, raw]: any) => (
                  <Metric
                    key={name}
                    label={name.replaceAll('_', ' ')}
                    value={
                      raw.available
                        ? raw.values?.[0]?.value === undefined
                          ? 'No samples'
                          : `${Number(raw.values[0].value).toLocaleString(undefined, {
                              maximumFractionDigits: 3,
                            })} ${raw.unit ?? ''}`
                        : 'Unavailable'
                    }
                    note={raw.available ? raw.description : raw.error ?? 'No series returned'}
                  />
                ))}
              </div>

              {/* Discovered Grafana Dashboards */}
              <div className="panel">
                <div className="panel-head">
                  <div>
                    <h3>Discovered Grafana Dashboards</h3>
                    <p>Time-series monitoring dashboards discovered via the Grafana API</p>
                  </div>
                </div>
                <div className="dashboard-links">
                  {(monitor?.grafana?.dashboards?.dashboards ?? []).map((d: any) => (
                    <a
                      key={d.uid}
                      href={`${monitor?.links?.grafana ?? 'http://localhost:3000'}${d.url}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {d.title} <ExternalLink size={13} />
                    </a>
                  ))}
                  {!monitor?.grafana?.dashboards?.dashboards?.length && (
                    <div className="subtle">No Grafana dashboards discovered or Grafana starting up</div>
                  )}
                </div>
              </div>
            </>
          )}

          {/* ========================================================= */}
          {/* TAB 9: AUDIT ACTIVITY LOG */}
          {/* ========================================================= */}
          {tab === 'Activity' && (
            <>
              <div className="section-heading">
                <div>
                  <h2>System Audit Activity Log</h2>
                  <p>Immutable chronological event log recorded by the Control Center</p>
                </div>
              </div>

              <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Event ID</th>
                        <th>Timestamp</th>
                        <th>Event Type</th>
                        <th>Associated ID</th>
                        <th>Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activityEvents.map((e) => (
                        <tr key={e.event_id}>
                          <td className="mono">#{e.event_id}</td>
                          <td className="mono">{formatDate(e.created_at)}</td>
                          <td>
                            <span
                              className={`pill ${
                                e.event_type === 'fraud_alert'
                                  ? 'bad'
                                  : e.event_type === 'low_risk'
                                  ? 'ok'
                                  : 'neutral'
                              }`}
                            >
                              {e.event_type}
                            </span>
                          </td>
                          <td className="mono">{e.transaction_id || e.batch_id || '—'}</td>
                          <td>{e.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!activityEvents.length && (
                    <div className="empty">No audit activity logged yet</div>
                  )}
                </div>
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  );
}

function Pagination({
  page,
  total,
  size,
  set,
}: {
  page: number;
  total: number;
  size: number;
  set: (n: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div className="pagination">
      <span>
        Showing {total ? (page - 1) * size + 1 : 0}–{Math.min(page * size, total)} of {total} records
      </span>
      <div>
        <button disabled={page <= 1} onClick={() => set(page - 1)} aria-label="Previous page">
          <ChevronLeft size={16} />
        </button>
        <b className="mono">
          Page {page} of {pages}
        </b>
        <button disabled={page >= pages} onClick={() => set(page + 1)} aria-label="Next page">
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}

function ExternalLinkCard({
  label,
  href,
  status,
}: {
  label: string;
  href: string;
  status?: string;
}) {
  return (
    <a className="external-card" href={href} target="_blank" rel="noreferrer">
      <div className="round-icon">
        <Gauge size={16} />
      </div>
      <div>
        <small>OPEN CONSOLE</small>
        <b>{label}</b>
      </div>
      <Pill ok={status === 'healthy' || status === 'up'} label={status ?? 'checking'} />
      <ExternalLink size={14} />
    </a>
  );
}
