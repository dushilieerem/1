import {getQuantSession} from '@/lib/quantAuth';
// Per-tab recovery only. Never store credentials or mix institutions/members.
function key(id:string,field:string){const s=getQuantSession();return `quant-factor-draft:${s?.org.id||'guest'}:${s?.user.id||'guest'}:${id}:${field}`;}
export function readFactorDraft(id:string,field:string){try{return sessionStorage.getItem(key(id,field))||'';}catch{return '';}}
export function writeFactorDraft(id:string,field:string,value:string){try{if(value)sessionStorage.setItem(key(id,field),value);else sessionStorage.removeItem(key(id,field));}catch{/* Unsaved-change warning still protects navigation when storage is unavailable. */}}
