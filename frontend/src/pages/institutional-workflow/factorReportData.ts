import type {YgBacktestResponse,YgCurvePoint} from '@/lib/ygApi';
export const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);
export function formatResearchNumber(v:unknown,percent=false){return finite(v)?percent?(v*100).toFixed(2)+'%':v.toLocaleString('zh-CN',{maximumFractionDigits:4}):'未返回';}
export type PlotSeries={name:string;values:(number|null)[];color?:string;kind?:'line'|'bar';dashed?:boolean;area?:boolean};
export type PlotData={dates:string[];series:PlotSeries[];percent?:boolean};
export function alignedCurves(curves:Array<{name:string;points?:Array<{date:string;value?:number|null}>|null;color?:string;dashed?:boolean}>,percent=false):PlotData{
 const dates=[...new Set(curves.flatMap(c=>(c.points||[]).map(p=>p.date)))].sort();
 return {dates,percent,series:curves.map(c=>{const map=new Map((c.points||[]).map(p=>[p.date,p.value]));return {name:c.name,color:c.color,dashed:c.dashed,values:dates.map(d=>{const v=map.get(d);return finite(v)?percent?(v-1)*100:v:null;})};})};
}
export function relativeCurve(equity?:YgCurvePoint[]|null,benchmark?:YgCurvePoint[]|null){
 const base=new Map((benchmark||[]).map(p=>[p.date,p.value]));
 return (equity||[]).map(p=>{const b=base.get(p.date);return {date:p.date,value:finite(p.value)&&finite(b)&&b>0?p.value/b:null};});
}
export function curveReturn(points?:Array<{date:string;value?:number|null}>|null){
 const last=points?.at(-1)?.value;return finite(last)?last-1:null;
}
export function periodReturns(curve?:YgCurvePoint[]|null){
 const rows:Array<{month:string;value:number|null}>=[];let previous=1,month='',last:number|null=null,invalid=false;
 const flush=()=>{if(!month)return;rows.push({month,value:!invalid&&finite(last)&&finite(previous)&&previous>0?last/previous-1:null});previous=last as number;};
 for(const p of [...(curve||[])].sort((a,b)=>a.date.localeCompare(b.date))){const next=p.date.slice(0,7);if(next!==month){flush();month=next;invalid=false;}last=finite(p.value)?p.value:null;if(last===null)invalid=true;}
 flush();return rows;
}
export function icStats(result:YgBacktestResponse){const fa=result.factor_analysis;const points=(fa?.ic_series||[]).filter(p=>finite(p.value));const mean=result.metrics?.ic??fa?.ic_mean,std=result.metrics?.ic_std??fa?.ic_std;return {count:points.length,positive:points.length?points.filter(p=>p.value>0).length/points.length:null,ir:finite(mean)&&finite(std)&&std>0?mean/std:null};}
export const metricLabels:Record<string,string>={ic:'Pearson IC',rank_ic:'Rank IC',ic_std:'IC 标准差',ic_ir:'IC IR',rank_ic_ir:'Rank IC IR',annual_return:'年化收益',total_return:'累计收益',max_drawdown:'最大回撤',sharpe_ratio:'夏普比率',sharpe:'夏普比率',sortino:'Sortino 比率',calmar:'Calmar 比率',volatility:'年化波动率',win_rate:'日收益胜率',turnover:'换手率（引擎口径）',total_turnover:'累计换手',trade_count:'交易计数（引擎口径）',total_cost:'累计成本 / 净值',commission_cost:'累计佣金 / 净值',stamp_tax_cost:'累计印花税 / 净值',slippage_cost:'累计滑点 / 净值',ff3_alpha:'FF3 Alpha',ff3_beta_mkt:'FF3 市场 Beta',ff3_beta_smb:'FF3 规模 Beta',ff3_beta_hml:'FF3 价值 Beta',ff3_r_squared:'FF3 拟合优度'};
export const percentKeys=new Set(['annual_return','total_return','max_drawdown','volatility','win_rate','turnover','total_cost','commission_cost','stamp_tax_cost','slippage_cost']);
export function groupSeries(result:YgBacktestResponse,benchmarkName:string):PlotData{
 const points=result.factor_analysis?.cumulative_series||[];
 const keys=[...new Set(points.flatMap(p=>Object.keys(p).filter(k=>/^layer\d+$/.test(k)&&finite(p[k]))))].sort((a,b)=>Number(a.slice(5))-Number(b.slice(5)));
 return alignedCurves([...keys.map(k=>({name:'Q'+k.slice(5),points:points.map(p=>({date:p.date,value:finite(p[k])?p[k] as number:null}))})),{name:benchmarkName,points:result.benchmark_curve,color:'#a2a9b8',dashed:true}],true);
}
