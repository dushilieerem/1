import {researchFetch} from './researchClient';
import type {DetectRunRecord} from './detectStore';
export type FactorReportPhase='development'|'sealed';
export type ReportGate={passed:boolean;numerical_passed?:boolean;checks:Array<{name:string;actual:number|null;operator:string;threshold:number|boolean;passed:boolean;reason?:string}>};
export type ReadonlyFactorReportRun=Omit<DetectRunRecord,'projectId'|'request'|'finishedAt'|'elapsedSec'>&{projectId:string|null;request:Partial<DetectRunRecord['request']>;finishedAt:string|null;elapsedSec:number|null};
export type FactorHistorySummary={id:string;kind:'platform_history_summary';status:'saved'|'failed';computed_at:string|null;parameters:{universe:string;lookback_period:string;filter_limit_up:boolean|null;filter_suspended:boolean|null};date_range:null;metrics:Record<string,number|null>;metric_units:Record<string,'correlation'|'ratio'|'number'|'reported_coverage'>;missing_sections:string[];calculation_note:string|null;provenance:{rules_version:string;source:string;source_metrics:Record<string,number|null>;source_metric_units:Record<string,string>;factor_source_hash:null;data_release_id:null}};
export type SavedFactorReport={id:string;kind:'member_saved_report';label:string;report_url:string;status:'saved'|'failed';finished_at:string|null;elapsed_seconds:number|null;actual_date_range:{start?:string;end?:string}|null;parameters:Partial<DetectRunRecord['request']>;version:Record<string,string|null>;sections:{equity_curve:boolean;benchmark_curve:boolean;ic_series:boolean;rank_ic_series:boolean};server_verified:boolean};
export type FactorLibraryReports={factor:{imported_id:string;library_name:string;factor_id:string;display_name:string;category:string};history_summaries:FactorHistorySummary[];saved_reports:SavedFactorReport[];saved_reports_page?:{limit:number;has_more:boolean;next_cursor:string|null};history_page?:{limit:number;has_more:boolean};private_reports_allowed:boolean};
export type FactorAssetReport={readonly:true;phase:FactorReportPhase;report_id:string;asset:{id:string;display_name:string;version:number;kind:string;purpose:'research_only';approved_at:string|null};run:ReadonlyFactorReportRun;gate:ReportGate;provenance:{registration_hash:string;source_result_hash:string;result_projection_hash:string;request_source:string};back_url:string};
export class FactorReportReadError extends Error{constructor(message:string,public code:string,public status:number){super(message);}}
async function read<T>(path:string,signal?:AbortSignal):Promise<T>{
 const response=await researchFetch('/api/inst/quant/factor-workflow/'+path,{signal});const data=await response.json().catch(()=>({}));
 if(!response.ok){const detail=typeof data.error==='object'&&data.error?data.error:typeof data.detail==='object'&&data.detail?data.detail:data;const message=typeof detail.error==='string'?detail.error:typeof detail.message==='string'?detail.message:typeof data.error==='string'?data.error:typeof data.detail==='string'?data.detail:'报告暂时无法读取，请重试。';throw new FactorReportReadError(message,detail.code||'report_unavailable',response.status);}
 return data;
}
export async function loadImportedFactorReports(id:string,signal?:AbortSignal,cursor?:string):Promise<FactorLibraryReports>{
 const data=await read<FactorLibraryReports>('imports/'+encodeURIComponent(id)+'/reports'+(cursor?'?cursor='+encodeURIComponent(cursor):''),signal);
 if(data.factor?.imported_id!==id||!Array.isArray(data.history_summaries)||!Array.isArray(data.saved_reports)||data.saved_reports.some(x=>x.report_url!=='/quant/factor/report/'+encodeURIComponent(x.id)))throw new FactorReportReadError('返回的报告与所选因子不一致，请重试。','report_identity_mismatch',502);
 return data;
}
export function factorAssetReportPath(id:string,phase:FactorReportPhase){return '/quant/factor/assets/'+encodeURIComponent(id)+'/report/'+phase;}
export async function loadFactorAssetReport(id:string,phase:string,signal?:AbortSignal):Promise<FactorAssetReport>{
 if(phase!=='development'&&phase!=='sealed')throw new FactorReportReadError('报告类型不存在。','report_not_found',404);
 const data=await read<FactorAssetReport>('assets/'+encodeURIComponent(id)+'/reports/'+phase,signal);
 if(data.readonly!==true||data.asset?.id!==id||data.phase!==phase||data.run?.projectId!==null||data.run?.id!==data.report_id||!data.run?.result||data.back_url!=='/quant/factor/library?asset='+encodeURIComponent(id))throw new FactorReportReadError('报告与登记版本不一致，暂时无法展示。','report_identity_mismatch',502);
 return data;
}
export function reportDate(value:string|null|undefined){if(!value)return '未记录';const date=new Date(value);return Number.isFinite(date.valueOf())?date.toLocaleString('zh-CN',{hour12:false}):'未记录';}
export function historyMetric(value:unknown,unit?:string){if(typeof value!=='number'||!Number.isFinite(value))return '—';return unit==='ratio'?(value*100).toFixed(2)+'%':value.toFixed(unit==='correlation'?4:3);}
