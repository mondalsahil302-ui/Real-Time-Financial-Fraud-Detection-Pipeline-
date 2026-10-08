import { useEffect, useState } from 'react';
import { api } from './api';
import type { ChatResult, LlmStatus } from './types';
import {
  AlertTriangle,
  Copy,
  Database,
  HelpCircle,
  Sparkles
} from './icons';

interface AssistantPanelProps {
  transactionId?: string;
}

export default function AssistantPanel({ transactionId }: AssistantPanelProps) {
  const [question, setQuestion] = useState('');
  const [conversationId, setConversationId] = useState('');
  const [result, setResult] = useState<ChatResult>();
  const [status, setStatus] = useState<LlmStatus>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [copyStatus, setCopyStatus] = useState('');

  useEffect(() => {
    let active = true;
    void api<LlmStatus>('/api/llm/status')
      .then((val) => {
        if (active) setStatus(val);
      })
      .catch((reason) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : 'Could not load AI provider status');
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const ask = async (promptText?: string) => {
    const query = (promptText ?? question).trim();
    if (query.length < 2 || busy) return;
    setBusy(true);
    setError('');
    setCopyStatus('');
    try {
      const answer = await api<ChatResult>('/api/llm/chat', {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({
          question: query,
          transaction_id: transactionId || undefined,
          conversation_id: conversationId || undefined,
          include_cassandra: true,
          include_fraud_knowledge: true,
          include_paysim_cases: true,
        }),
      });
      setConversationId(answer.conversation_id);
      setResult(answer);
      setQuestion('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Assistant request failed');
    } finally {
      setBusy(false);
    }
  };

  const copyAnswer = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.answer);
      setCopyStatus('Answer copied.');
      setTimeout(() => setCopyStatus(''), 2500);
    } catch {
      setCopyStatus('Could not copy the answer from this browser.');
    }
  };

  const configuredProvider = status?.provider
    ? status.provider[0].toUpperCase() + status.provider.slice(1)
    : 'Checking';
  const activeProvider = result?.llm_provider
    ? result.llm_provider[0].toUpperCase() + result.llm_provider.slice(1)
    : configuredProvider;

  const quickPrompts = transactionId
    ? [
        'Why was this transaction flagged? How does the model prediction compare with isFraud?',
        'Analyze sender balance depletion vs transaction amount',
        'Check destination account history for mule account patterns',
        'What evidence is missing to confirm fraud?',
      ]
    : [
        'Explain how Kafka, Spark, ML, RAG and Gemini work together.',
        'What are the 33 engineered features and how are they calculated?',
        'How does the multi-tier L1 to L5 risk classification operate?',
        'What is the threshold strategy for balancing Recall vs False Positives?',
      ];

  return (
    <div className="assistant-layout">
      <div className="panel assistant-panel">
        {/* Top Header Card */}
        <div className="panel-head assistant-head">
          <div>
            <div className="assistant-title-row">
              <span className="badge-tag">ENTERPRISE INVESTIGATION TOOL</span>
              <h3>AI Assistant</h3>
            </div>
            <p>
              {transactionId
                ? `Evidence retrieval for ${transactionId}`
                : 'Project knowledge from the existing fraud knowledge base'}
            </p>
          </div>
          <div className="assistant-provider-pill">
            <span className="live-dot" />
            <span>Provider: {configuredProvider}</span>
          </div>
        </div>

        {/* Engine Capability Ribbon */}
        <div className="assistant-meta-ribbon">
          <div className="meta-chip">
            <span className="meta-label">LLM MODEL</span>
            <strong className="mono">{status?.model || 'gemini-3.5-flash-lite'}</strong>
          </div>
          <div className="meta-chip">
            <span className="meta-label">RAG VECTOR RETRIEVAL</span>
            <strong className={status?.rag_enabled ? 'text-ok' : 'text-warn'}>
              {status?.rag_enabled ? 'ChromaDB Active' : 'Unavailable'}
            </strong>
          </div>
          <div className="meta-chip">
            <span className="meta-label">CASSANDRA CONTEXT</span>
            <strong className="text-ok">Enabled</strong>
          </div>
          <div className="meta-chip">
            <span className="meta-label">FALLBACK</span>
            <strong className="mono">{status?.fallback || 'None'}</strong>
          </div>
        </div>

        {status?.detail && (
          <div className="notice error" role="status">
            <AlertTriangle size={15} />
            <span>{status.detail}</span>
          </div>
        )}

        {/* Quick Recommended Prompts */}
        <div className="prompts-row">
          <span className="prompts-label">Suggested Inquiries:</span>
          <div className="prompts-list">
            {quickPrompts.map((p, idx) => (
              <button
                key={idx}
                type="button"
                className="prompt-chip"
                onClick={() => {
                  setQuestion(p);
                  void ask(p);
                }}
                disabled={busy}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Main Inquiry Form */}
        <div className="assistant-input-box">
          <label>
            Ask a question
            <textarea
              value={question}
              maxLength={2000}
              rows={3}
              placeholder={
                transactionId
                  ? 'Why was this transaction flagged? How does the model prediction compare with isFraud?'
                  : 'Explain how Kafka, Spark, ML, RAG and Gemini work together.'
              }
              onChange={(e) => setQuestion(e.target.value)}
              disabled={busy}
            />
          </label>
          <div className="assistant-actions-bar">
            <span className="subtle chars-counter">{question.length} / 2000 characters</span>
            <button
              className="primary"
              disabled={busy || question.trim().length < 2}
              onClick={() => void ask()}
            >
              <Sparkles size={14} />
              {busy
                ? `Retrieving evidence and asking ${configuredProvider}…`
                : conversationId
                ? 'Ask follow-up'
                : 'Ask AI'}
            </button>
          </div>
        </div>

        {error && (
          <div className="notice error" role="alert">
            <AlertTriangle size={15} />
            <span>{error}</span>
          </div>
        )}

        {/* Investigation Response Area */}
        {result && (
          <div className="assistant-answer" aria-live="polite">
            <div className="answer-header">
              <div className="answer-header-title">
                <Sparkles size={16} />
                <h3>Answer</h3>
              </div>
              <div className="answer-header-actions">
                <button type="button" className="copy-action-btn" onClick={() => void copyAnswer()}>
                  <Copy size={13} />
                  Copy answer
                </button>
                {copyStatus && <span className="copied-status" role="status">{copyStatus}</span>}
              </div>
            </div>

            <div className="answer-card">
              <p className="answer-text">{result.answer}</p>
            </div>

            <div className="answer-provenance-bar">
              <small>
                Answered by {activeProvider} · Model: {result.llm_model} · Retrieved sources: {result.retrieval_count}
              </small>
            </div>

            {/* Evidence Used Cards */}
            <div className="evidence-section">
              <div className="section-subtitle">
                <Database size={15} />
                <h3>Evidence used</h3>
              </div>
              {result.evidence.length ? (
                <ul className="evidence-grid">
                  {result.evidence.map((item, index) => (
                    <li key={`${item.source_type}:${item.source_id}:${index}`} className="evidence-card">
                      <div className="evidence-meta">
                        <span className="evidence-type-tag">{item.source_type}</span>
                        <span className="evidence-id mono">{item.source_id}</span>
                        {item.source && <span className="evidence-source subtle">· {item.source}</span>}
                      </div>
                      <pre className="evidence-payload">
                        {(typeof item.content === 'string'
                          ? item.content
                          : JSON.stringify(item.content, null, 2)
                        ).slice(0, 1400)}
                      </pre>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="subtle-note">No evidence sources were cited by the model.</p>
              )}
            </div>

            {/* Missing Evidence & Uncertainties */}
            <div className="uncertainties-grid">
              <div className="gap-card">
                <div className="section-subtitle">
                  <AlertTriangle size={14} />
                  <h3>Missing evidence</h3>
                </div>
                {result.missing_evidence.length ? (
                  <ul className="clean-list">
                    {result.missing_evidence.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="subtle-note">None reported by retrieval.</p>
                )}
              </div>

              <div className="gap-card">
                <div className="section-subtitle">
                  <HelpCircle size={14} />
                  <h3>Uncertainty</h3>
                </div>
                {result.uncertainties.length ? (
                  <ul className="clean-list">
                    {result.uncertainties.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="subtle-note">The model reported no additional uncertainty.</p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
