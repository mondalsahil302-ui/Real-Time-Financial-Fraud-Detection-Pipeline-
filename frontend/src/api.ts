// Relative URLs go through Vite's development proxy. Set VITE_API_BASE_URL only when
// serving the built frontend from a different origin without a reverse proxy.
const BASE = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
export const apiBaseUrl = BASE || window.location.origin;
export async function api<T>(path:string, init?:RequestInit):Promise<T> {
  let res: Response;
  try {
    res=await fetch(`${BASE}${path}`,{...init,headers:{'Content-Type':'application/json',...init?.headers}});
  } catch {
    throw new Error(`Cannot reach the Control Center API (${apiBaseUrl}). Check that the backend is running.`);
  }
  if(!res.ok){let msg=`Request failed (${res.status})`;try{const body=await res.json();msg=typeof body.detail==='string'?body.detail:JSON.stringify(body.detail??body)}catch{} throw new Error(msg)}
  return res.json() as Promise<T>;
}
export const socketUrl=(path:string)=>`${apiBaseUrl.replace(/^http/,'ws')}${path}`;
