import {researchFetch} from './researchClient';
export type FactorLibrarySource={imported_id:string;library_id:number;library_name:string;factor_id:string;function_name:string|null;source_code:string;source_sha256:string;source_hash:string;source_hash_scope:string;source_kind:'current_library_definition';execution_validated:false};
export class FactorSourceReadError extends Error{constructor(message:string,public code:string,public status:number){super(message);}}
export async function loadImportedFactorSource(id:string,signal:AbortSignal):Promise<FactorLibrarySource>{
 const response=await researchFetch('/api/inst/quant/factor-workflow/imports/'+encodeURIComponent(id)+'/source',{signal});
 const data=await response.json().catch(()=>({}));
 if(!response.ok){const detail=typeof data.error==='object'?data.error:typeof data.detail==='object'?data.detail:data;throw new FactorSourceReadError(typeof detail.error==='string'?detail.error:typeof detail.message==='string'?detail.message:typeof data.error==='string'?data.error:'源码暂时无法读取，请重试。',detail.code||'source_unavailable',response.status);}
 if(data.imported_id!==id||typeof data.source_code!=='string'||!data.source_code.trim())throw new FactorSourceReadError('返回的源码与所选因子不一致，请重试。','source_identity_mismatch',502);
 return data;
}
