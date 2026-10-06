// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ManualTransactionForm from './ManualTransactionForm';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('ManualTransactionForm', () => {
  it('sends the existing transaction field names and shows Kafka acknowledgement', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok:true, json:async()=>({
      transaction:{transaction_id:'TX-REAL-1',kafka_partition:2,kafka_offset:41},
    }) });
    vi.stubGlobal('fetch', fetchMock);
    render(<ManualTransactionForm/>);
    fireEvent.click(screen.getByRole('button',{name:'Send transaction'}));
    await waitFor(()=>expect(screen.getByRole('status').textContent).toContain('partition 2 · offset 41'));
    const [,init]=fetchMock.mock.calls[0];
    const body=JSON.parse(init.body);
    expect(body).toMatchObject({type:'PAYMENT',nameOrig:'C_CONTROL_CENTER_1',nameDest:'M_CONTROL_CENTER_1',step:1});
    expect(body).not.toHaveProperty('transaction_type');
  });
});
