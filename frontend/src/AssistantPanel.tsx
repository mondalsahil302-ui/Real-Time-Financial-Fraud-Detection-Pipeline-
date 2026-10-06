import { useEffect, useState } from 'react';
import { api } from './api';

type Evidence = {
  source_type: string;
  source_id: string;
  content: unknown;
  source?: string;
};

type ChatResult = {
  conversation_id: string;
  answer: string;
  transaction_id?: string | null;
  evidence: Evidence[];
  retrieval_count: number;
  missing_evidence: string[];
  uncertainties: string[];
  llm_provider: string;
  llm_model: string;
};

type LlmStatus = {
  provider: string;
  model: string;
  status: string;
  available: boolean | null;
  fallback?: string | null;
  rag_enabled: boolean;
  detail?: string;
};

export default function AssistantPanel({ transactionId }: { transactionId?: string }) {
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
      .then(value => {
        if (active) setStatus(value);
      })
      .catch(reason => {
        if (active) {
          setError(reason instanceof Error ? reason.message : 'Could not load AI provider status');
        }
      });
    return () => { active = false; };
  }, []);

  const ask = async () => {
    if (question.trim().length < 2 || busy) return;
    setBusy(true);
    setError('');
    setCopyStatus('');
    try {
      const answer = await api<ChatResult>('/api/llm/chat', {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({
          question: question.trim(),
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

  return (
    <div className="assistant-layout">
      <div className="panel assistant-panel">
        <div className="panel-head">
          <div>
            <h3>AI Assistant</h3>
            <p>{transactionId ? `Evidence retrieval for ${transactionId}` : 'Project knowledge from the existing fraud knowledge base'}</p>
          </div>
          <span className="pill">Provider: {configuredProvider}</span>
        </div>
        <p>
          Model: {status?.model || 'Unavailable'} · RAG: {status?.rag_enabled ? 'Enabled' : 'Unavailable'} ·
          {' '}Fallback: {status?.fallback || 'None'}
        </p>
        {status?.detail && <div className="notice error" role="status">{status.detail}</div>}
        <label>
          Ask a question
          <textarea
            value={question}
            maxLength={2000}
            rows={3}
            placeholder={transactionId ? 'Why was this transaction flagged? How does the model prediction compare with isFraud?' : 'Explain how Kafka, Spark, ML, RAG and Gemini work together.'}
            onChange={event => setQuestion(event.target.value)}
          />
        </label>
        {error && <div className="notice error" role="alert">{error}</div>}
        <button className="primary" disabled={busy || question.trim().length < 2} onClick={() => void ask()}>
          {busy ? `Retrieving evidence and asking ${configuredProvider}…` : conversationId ? 'Ask follow-up' : 'Ask AI'}
        </button>
        {result && (
          <div className="assistant-answer" aria-live="polite">
            <h3>Answer</h3>
            <p className="answer-text">{result.answer}</p>
            <small>
              Answered by {activeProvider} · Model: {result.llm_model} · Retrieved sources: {result.retrieval_count}
            </small>
            <button type="button" onClick={() => void copyAnswer()}>Copy answer</button>
            {copyStatus && <small role="status">{copyStatus}</small>}
            <h3>Evidence used</h3>
            {result.evidence.length ? (
              <ul>
                {result.evidence.map((item, index) => (
                  <li key={`${item.source_type}:${item.source_id}:${index}`}>
                    <b>{item.source_type}</b> · {item.source_id}{item.source && ` · ${item.source}`}
                    <pre>{(typeof item.content === 'string' ? item.content : JSON.stringify(item.content, null, 2)).slice(0, 1400)}</pre>
                  </li>
                ))}
              </ul>
            ) : <p>No evidence sources were cited by the model.</p>}
            <h3>Missing evidence</h3>
            {result.missing_evidence.length
              ? <ul>{result.missing_evidence.map((item, index) => <li key={index}>{item}</li>)}</ul>
              : <p>None reported by retrieval.</p>}
            <h3>Uncertainty</h3>
            {result.uncertainties.length
              ? <ul>{result.uncertainties.map((item, index) => <li key={index}>{item}</li>)}</ul>
              : <p>The model reported no additional uncertainty.</p>}
          </div>
        )}
      </div>
    </div>
  );
}
