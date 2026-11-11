import {useEffect,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {loadImportedFactorReports,FactorReportReadError,historyMetric,reportDate,type FactorLibraryReports as ReportIndex,type FactorHistorySummary} from '@/lib/factorLibraryReports';
import {researchScopeLabel} from '@/lib/factorPresentation';
import type {ResearchAssetSummary} from '@/lib/factorResearchAssets';
import type {Row} from './QuantFactorLibraryPage';
const pools:Record<string,string>={CSI300:'沪深300',CSI500:'中证500',CSI800:'中证800',CSI1000:'中证1000',SSE50:'上证50'};
const periods:Record<string,string>={'3m':'近3月','1y':'近1年','3y':'近3年','10y':'近10年',all:'全部区间'};
function label(s:FactorHistorySummary){const p=s.parameters;return [pools[p.universe]||p.universe,periods[p.lookback_period]||p.lookback_period,p.filter_limit_up==null?'涨停过滤未记录':p.filter_limit_up?'过滤涨停':'保留涨停',p.filter_suspended===false?'保留停牌':p.filter_suspended==null?'停牌过滤未记录':null].filter(Boolean).join(' · ');}
const mainMetrics=[['rank_ic','Rank IC'],['ic_mean','Pearson IC'],['ir','ICIR'],['annual_return','年化收益'],['max_drawdown','最大回撤'],['sharpe','夏普比率']];
const otherMetrics=[['ic_std','IC 标准差'],['turnover','日均单边换手'],['q1_turnover','最高组单边换手'],['q5_turnover','最低组单边换手'],['q1_return','最高组收益'],['q5_return','最低组收益'],['long_short_spread','多空收益差'],['win_rate','胜率'],['volatility','年化波动率']];
export function FactorLibraryReports({row,replications,onReplication}:{row:Row;replications:ResearchAssetSummary[];onReplication:(id:string)=>void}){
 const [data,setData]=useState<ReportIndex>(),[loading,setLoading]=useState(Boolean(row.importedId)),[error,setError]=useState(''),[retry,setRetry]=useState(0),[selected,setSelected]=useState(''),[moreLoading,setMoreLoading]=useState(false),[moreError,setMoreError]=useState('');
 const epoch=useRef(0),pageController=useRef<AbortController|null>(null);
 useEffect(()=>{let active=true;const controller=new AbortController();++epoch.current;pageController.current?.abort();setMoreLoading(false);setMoreError('');setData(undefined);setError('');setSelected('');if(!row.importedId){setLoading(false);return;}setLoading(true);
  void loadImportedFactorReports(row.importedId,controller.signal).then(next=>{if(!active)return;if(next.factor.library_name!==row.library||next.factor.factor_id!==(row.sourceFactorId||row.name))throw new FactorReportReadError('返回的报告与所选因子不一致，请重试。','report_identity_mismatch',502);setData(next);const first=next.history_summaries.find(x=>x.parameters.universe==='CSI300'&&x.parameters.lookback_period==='3y'&&x.parameters.filter_limit_up===true)||next.history_summaries[0];setSelected(first?.id||'');}).catch(e=>{if(active&&!controller.signal.aborted)setError(e instanceof Error?e.message:'报告暂时无法读取，请重试。');}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;++epoch.current;controller.abort();pageController.current?.abort();};
 },[row.importedId,row.library,row.sourceFactorId,row.name,retry]);
 async function loadMore(){
  const cursor=data?.saved_reports_page?.next_cursor;if(!row.importedId||!cursor||moreLoading)return;
  const current=epoch.current,controller=new AbortController();pageController.current=controller;setMoreLoading(true);setMoreError('');
  try{const next=await loadImportedFactorReports(row.importedId,controller.signal,cursor);if(current!==epoch.current)return;if(next.factor.library_name!==row.library||next.factor.factor_id!==(row.sourceFactorId||row.name))throw Error('返回的报告与所选因子不一致，请重试。');if(next.saved_reports_page?.has_more&&next.saved_reports_page.next_cursor===cursor)throw Error('后续报告暂时无法读取，请重试。');setData(previous=>previous?{...previous,saved_reports:[...previous.saved_reports,...next.saved_reports.filter(x=>!previous.saved_reports.some(old=>old.id===x.id))],saved_reports_page:next.saved_reports_page}:previous);}
  catch(e){if(current===epoch.current&&!controller.signal.aborted)setMoreError(e instanceof Error?e.message:'后续报告暂时无法读取。');}finally{if(current===epoch.current)setMoreLoading(false);}
 }
 const summary=data?.history_summaries.find(x=>x.id===selected);
 return <section role="tabpanel" aria-label="回测报告" className="ff-library-reports">
  {loading?<p role="status">正在读取已保存的回测报告…</p>:error?<div role="alert"><p>{error}</p><button type="button" className="btn small" onClick={()=>setRetry(x=>x+1)}>重试读取报告</button></div>:<>
   <section className="ff-report-section"><div className="ff-report-heading"><h3>平台历史回测</h3><span className="badge gray">历史摘要</span></div>
    {summary?<><label className="field"><span>已保存的回测范围</span><select value={selected} onChange={e=>setSelected(e.target.value)}>{data?.history_summaries.map(x=><option key={x.id} value={x.id}>{label(x)}</option>)}</select></label>{data?.history_page?.has_more&&<p className="fine">当前展示最近 {data.history_page.limit} 份历史摘要。</p>}<p className="fine">计算时间 {reportDate(summary.computed_at)}</p>{summary.status==='failed'&&<p className="hint warning">这份历史记录未完成计算，可查看已保存的信息。</p>}
     <dl className="ff-report-stats">{mainMetrics.map(([key,title])=><div key={key}><dt>{title}</dt><dd>{historyMetric(summary.metrics[key],summary.metric_units[key])}</dd></div>)}</dl><p className="ff-copy">原记录保留了汇总指标，未保存净值与基准曲线。</p>
     <details className="ff-fold"><summary>更多指标与计算设定</summary><dl className="ff-kv">{otherMetrics.map(([key,title])=><div key={key}><dt>{title}</dt><dd>{historyMetric(summary.metrics[key],summary.metric_units[key])}</dd></div>)}</dl><p className="fine">{summary.calculation_note||'本条历史记录未提供完整计算设定。'}</p><p className="fine">回看区间以当时计算为准；未记录实际起止日、数据及源码版本，不能直接作为当前因子的准入依据。</p></details>
    </>:<p>暂无已保存的历史回测摘要。</p>}
   </section>
   <section className="ff-report-section"><h3>完整回测报告</h3>{data?.saved_reports.length?<div className="ff-saved-reports">{data.saved_reports.map(x=><article key={x.id} className="ff-saved-report"><div className="ff-report-heading"><strong>{x.actual_date_range?.start||'起始日未记录'} — {x.actual_date_range?.end||'结束日未记录'}</strong><Link className="btn small" to={x.report_url}>查看报告</Link></div><p>{pools[x.parameters.universe||'']||researchScopeLabel(x.parameters)} · {x.status==='failed'?'计算未完成':'已保存'} · {reportDate(x.finished_at)}</p>{(!x.sections.equity_curve||!x.sections.benchmark_curve)&&<p className="fine">部分曲线未保存，报告按实际记录展示。</p>}<details className="ff-fold"><summary>报告版本</summary><dl className="ff-kv"><dt>报告名称</dt><dd>{x.label||row.display}</dd><dt>因子实现版本</dt><dd className="break-words">{x.version.factor_source_hash||'未记录'}</dd><dt>数据版本</dt><dd className="break-words">{x.version.data_release_id||'未记录'}</dd><dt>计算方法版本</dt><dd>{x.version.metric_version||'未记录'}</dd></dl><p className="fine">报告反映当次定义和范围；记录存在不代表通过当前研究门槛。</p></details></article>)}</div>:<p>尚无可查看的完整回测报告。</p>}{moreError&&<p role="alert">{moreError}</p>}{data?.saved_reports_page?.has_more&&data.saved_reports_page.next_cursor&&<button type="button" className="btn small" disabled={moreLoading} onClick={()=>void loadMore()}>{moreLoading?'正在读取更多报告…':'加载更多报告'}</button>}</section>
  </>}
  <section className="ff-report-section"><h3>机构验证记录</h3>{replications.length?replications.map(a=><p key={a.id}><button type="button" className="text-link" onClick={()=>onReplication(a.id)}>{a.display_name} · 第 {a.version} 版 · 查看登记与报告</button></p>):<p>暂无本机构已登记的复现验证记录。</p>}</section>
 </section>;
}
