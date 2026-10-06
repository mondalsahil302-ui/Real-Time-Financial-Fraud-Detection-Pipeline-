// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import AssistantPanel from './AssistantPanel';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('AssistantPanel', () => {
  it('sends a transaction-aware question and displays only returned evidence', async () => {
    vi.spyOn(globalThis.crypto,'randomUUID').mockReturnValue('11111111-1111-4111-8111-111111111111');
    const fetchMock=vi.fn().mockImplementation((url:string)=>Promise.resolve({
      ok:true,
      json:async()=>url.includes('/api/llm/status')
        ? {provider:'gemini',model:'gemini-3.5-flash-lite',status:'ready',available:true,fallback:'none',rag_enabled:true}
        : {
          conversation_id:'conversation-1',question:'Why flagged?',answer:'The supplied model score triggered review.',
          transaction_id:'TX-1',evidence:[{source_type:'cassandra',source_id:'TX-1',content:{risk_level:'L5'}}],
          retrieval_count:1,missing_evidence:['No previous transaction history was retrieved.'],
          uncertainties:['The score is not proof of fraud.'],llm_provider:'gemini',llm_model:'gemini-3.5-flash-lite',
        },
    }));
    vi.stubGlobal('fetch',fetchMock);
    render(<AssistantPanel transactionId="TX-1"/>);
    fireEvent.change(screen.getByLabelText('Ask a question'),{target:{value:'Why flagged?'}});
    fireEvent.click(screen.getByRole('button',{name:'Ask AI'}));
    await waitFor(()=>expect(screen.getByText('The supplied model score triggered review.')).toBeTruthy());
    expect(screen.getByText('Evidence retrieval for TX-1')).toBeTruthy();
    const chatCall=fetchMock.mock.calls.find(([url])=>url.includes('/api/llm/chat'));
    expect(chatCall).toBeTruthy();
    expect(JSON.parse(chatCall![1].body).transaction_id).toBe('TX-1');
    expect(screen.getByText('Answered by Gemini · Model: gemini-3.5-flash-lite · Retrieved sources: 1')).toBeTruthy();
  });
});
