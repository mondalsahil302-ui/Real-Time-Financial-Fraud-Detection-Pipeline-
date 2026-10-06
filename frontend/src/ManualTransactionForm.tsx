import { useState } from 'react';
import { api } from './api';

const initial={step:1,type:'PAYMENT',amount:'100',nameOrig:'C_CONTROL_CENTER_1',oldbalanceOrg:'500',newbalanceOrig:'400',nameDest:'M_CONTROL_CENTER_1',oldbalanceDest:'0',newbalanceDest:'100'};

export default function ManualTransactionForm(){
  const [values,setValues]=useState(initial);const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');const [error,setError]=useState('');
  const change=(key:keyof typeof initial,value:string)=>setValues(current=>({...current,[key]:value}));
  const submit=async(e:React.FormEvent)=>{e.preventDefault();setBusy(true);setMessage('');setError('');try{
    const idempotencyKey=crypto.randomUUID();
    const result=await api<any>('/api/transactions',{method:'POST',headers:{'Idempotency-Key':idempotencyKey},body:JSON.stringify({...values,step:Number(values.step),amount:Number(values.amount),oldbalanceOrg:Number(values.oldbalanceOrg),newbalanceOrig:Number(values.newbalanceOrig),oldbalanceDest:Number(values.oldbalanceDest),newbalanceDest:Number(values.newbalanceDest)})});
    const tx=result.transaction;setMessage(`Kafka acknowledged ${tx.transaction_id} · partition ${tx.kafka_partition} · offset ${tx.kafka_offset}`);
  }catch(err){setError(err instanceof Error?err.message:'Could not send transaction')}finally{setBusy(false)}};
  return <form className="panel manual-form" onSubmit={submit}><div className="panel-head"><div><h3>Create individual transaction</h3><p>Send one validated event to the existing Kafka topic for Spark processing.</p></div></div>
    <div className="manual-grid"><label>Transaction type<select value={values.type} onChange={e=>change('type',e.target.value)}>{['CASH_IN','CASH_OUT','DEBIT','PAYMENT','TRANSFER'].map(x=><option key={x}>{x}</option>)}</select></label>
    <label>Amount<input type="number" min="0" step="0.01" value={values.amount} onChange={e=>change('amount',e.target.value)} required/></label><label>Step<input type="number" min="0" value={values.step} onChange={e=>change('step',e.target.value)} required/></label>
    <label>Origin account<input value={values.nameOrig} onChange={e=>change('nameOrig',e.target.value)} required/></label><label>Destination account<input value={values.nameDest} onChange={e=>change('nameDest',e.target.value)} required/></label>
    <label>Origin balance before<input type="number" min="0" step="0.01" value={values.oldbalanceOrg} onChange={e=>change('oldbalanceOrg',e.target.value)} required/></label><label>Origin balance after<input type="number" min="0" step="0.01" value={values.newbalanceOrig} onChange={e=>change('newbalanceOrig',e.target.value)} required/></label>
    <label>Destination balance before<input type="number" min="0" step="0.01" value={values.oldbalanceDest} onChange={e=>change('oldbalanceDest',e.target.value)} required/></label><label>Destination balance after<input type="number" min="0" step="0.01" value={values.newbalanceDest} onChange={e=>change('newbalanceDest',e.target.value)} required/></label></div>
    <button className="primary" disabled={busy}>{busy?'Sending to Kafka…':'Send transaction'}</button>{message&&<p className="success-text" role="status">{message}</p>}{error&&<p className="error-text" role="alert">{error}</p>}
  </form>
}
