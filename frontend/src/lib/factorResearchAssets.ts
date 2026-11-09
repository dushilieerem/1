import {researchFetch} from './researchClient';
import {createProject,saveProject} from './detectStore';
export type AssetCheck={name:string;actual:number|null;operator:string;threshold:number|boolean;passed:boolean};
export type AssetReport={report_id?:string;run_id?:string;passed?:boolean;gate?:{passed:boolean;checks:AssetCheck[]};metrics?:Record<string,number>;meta?:Record<string,string>};
export type ResearchAssetSummary={id:string;kind:'novel_factor'|'replication_validation';display_name:string;hypothesis:string;version:number;category:string;tags:string[];snapshot_hash:string;purpose:'research_only';source_factor?:{factor_name?:string;library_name?:string};approval:{at:string;note?:string}};
export type ResearchAsset=ResearchAssetSummary&{definition:{factor_name:string;factor_code?:string;library_name?:string;universe?:string;benchmark?:string};source_hash:string;method:Record<string,unknown>;policy_version:string;k:number;threshold:number;data:Record<string,unknown>;development_report:AssetReport;sealed_report:AssetReport;novelty_report:{gate:Record<string,unknown>}};
export const factorBusinessCategories=['动量因子','技术复合因子','区间与通道因子','反转因子','日内结构因子','流动性因子','资金流与量能因子','量价关系因子','估值因子','规模因子','Beta因子','波动率因子','风险分布因子','待分类'];
async function api<T>(path:string):Promise<T>{const response=await researchFetch('/api/factor-workflow/assets'+path);const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'研究资产暂时无法读取');return data;}
export function loadResearchAssets(){return api<{assets:ResearchAssetSummary[]}>('');}
export function loadResearchAsset(id:string){return api<ResearchAsset>('/'+encodeURIComponent(id));}
export async function reuseResearchAsset(asset:ResearchAsset){
 const def=asset.definition;
 if(!def.factor_name||(!def.factor_code&&!def.library_name))throw Error('固定资产没有可执行定义，不能建立新研究');
 const p=await createProject(def.factor_name,asset.hypothesis,'基于：'+asset.display_name);
 return saveProject({...p,config:{...p.config,factorCodes:[def.factor_name],weights:[1],powers:[1],factorLibraries:def.library_name?{[def.factor_name]:def.library_name}:{},
  ...(def.factor_code?{draftFactor:{name:def.factor_name,body:def.factor_code,description:asset.hypothesis,category:asset.category}}:{}),
  sourceResearchAsset:{id:asset.id,version:asset.version,snapshotHash:asset.snapshot_hash,purpose:'research_only'},
  researchContext:{direction:asset.kind==='replication_validation'?'已有因子复现':'因子研究',question:asset.hypothesis,background:'引用已登记研究资产 '+asset.display_name+' 第'+asset.version+'版；新研究需重新确认范围、预算和验证，不继承通过状态。'}}});
}
