export type ComparisonRow = {
 reference_id:string; factor_name?:string; status:string;
 mean_abs_spearman?:number|null; valid_days?:number; min_pairs?:number;
 coverage?:number; error?:string; source_hash?:string;
};
export type NoveltyEvidence = {
 status:string; message?:string; run_id?:string; reference_hash?:string;
 reference_scope?:string; comparisons?:ComparisonRow[];
 gate?:{passed:boolean; complete:boolean; expected_count:number; compared_count:number;
 max_abs_correlation:number|null; threshold:number; closest?:ComparisonRow;
 failed_references?:string[]; limitation:string; residual?:{status:string}};
};
const numberText=(n:number|null|undefined)=>n==null?'未取得':n.toFixed(4);
export function FactorNoveltyEvidence({evidence,purpose}:{evidence?:NoveltyEvidence;purpose?:unknown}){
 const g=evidence?.gate;
 const rows=evidence?.comparisons||[];
 return <section className="rounded-lg border border-purple-100 bg-purple-50/40 p-4" aria-label="因子库去重证据">
  <h3 className="font-semibold">与已有因子库的差异</h3>
  <p className="mt-2 text-sm">{!evidence?(purpose==='replication'?'已有因子复现：不申报新发现。':'尚无数值去重证据，不能把指标通过视为新因子通过。'):evidence.message||({running:'正在比较因子值',passed:'预登记去重条件通过',failed:'去重条件未通过',incomplete:'比较证据不完整',unavailable:'去重计算服务尚不可用'}[evidence.status]||'去重证据待核对')}</p>
  {evidence?.reference_scope&&<p className="mt-2 text-xs text-slate-500">比较范围：{evidence.reference_scope}</p>}
  {g&&<>
   <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
    <dt>完整有效比较</dt><dd>{g.compared_count} / {g.expected_count}</dd>
    <dt>最相似因子</dt><dd>{g.closest?.factor_name||g.closest?.reference_id||'未取得'}</dd>
    <dt>最大日绝对秩相关均值</dt><dd>{numberText(g.max_abs_correlation)}（上限 {g.threshold}）</dd>
   </dl>
   {!g.complete&&<p className="mt-2 text-sm text-amber-800">未取得完整有效的全库数值对照，不能声称已通过全库比较。</p>}
   <p className="mt-2 text-xs text-slate-500">{g.limitation}</p>
  </>}
  {rows.length>0&&<details className="mt-3"><summary className="cursor-pointer text-sm font-medium">查看逐项比较证据（{rows.length} 项）</summary>
   <div className="mt-2 max-h-80 overflow-auto"><table className="w-full text-left text-xs"><thead><tr><th className="p-2">对照因子</th><th>状态</th><th>日绝对秩相关均值</th><th>有效日数</th><th>最低配对数</th><th>覆盖率</th></tr></thead>
    <tbody>{rows.map(r=><tr key={r.reference_id} className="border-t border-purple-100"><td className="p-2">{r.factor_name||r.reference_id}<span className="block text-slate-500">{r.reference_id}</span></td><td>{r.status==='succeeded'?'已计算':'未完成'}{r.error&&<span className="block text-red-700">{r.error}</span>}</td><td>{numberText(r.mean_abs_spearman)}</td><td>{r.valid_days??'—'}</td><td>{r.min_pairs??'—'}</td><td>{r.coverage==null?'—':(r.coverage*100).toFixed(1)+'%'}</td></tr>)}</tbody>
   </table></div>
  </details>}
  {evidence?.run_id&&<p className="mt-2 break-all text-xs text-slate-500">计算任务：{evidence.run_id}</p>}
  {evidence?.reference_hash&&<p className="mt-1 break-all text-xs text-slate-500">冻结对照库：{evidence.reference_hash}</p>}
  <p className="mt-2 text-xs text-slate-500">按同日共同股票计算因子值相关；收益曲线相关不代替因子值相关，低相关不等于已证明组合增量。</p>
 </section>;
}
