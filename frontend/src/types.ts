export type Tx = { transaction_id:string; batch_id:string; payload:Record<string, any>; generated_at:string; kafka_status:string; processing_status:string; risk_level?:string; anomaly_score?:number; xgboost_probability?:number; final_prediction?:number; decision_path?:string; final_decision?:string; alert_id?:string; investigation_id?:string; investigation_status:string; investigation?:Record<string,any> };
export type Page<T> = { items:T[]; page:number; page_size:number; total:number };
export type Service = {status:string; available:boolean; detail?:string; version?:string};
