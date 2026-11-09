import {Link} from 'react-router-dom';
import {FactorModuleTabs,WorkspaceHeading} from './QuantWorkspacePages';

const people=[['研究负责人','挖掘任务、授权、预算'],['因子研究员','观察、意见、接手分支'],['因子复核人','入库决定']];
const units=[
 ['挖掘任务调度','规则：排队、并发与跨挖掘任务预算','未接入'],
 ['F0 研究决策','模型决策 + 白名单 + 连续推进','可用（模型）'],
 ['F1 起点检索','因子库与历史试验可读','可用'],
 ['F2 假设研究','草稿必须由研究员确认','可用（人工确认）'],
 ['F3 因子实现','生成后进入静态校验与 F4','可用（人工确认）'],
 ['F4 检验诊断','真实 RE 单次回测；NW t 由 R1 日度序列计算','可用'],
 ['F5 独立复核','独立意见可用；封存执行真实运行（AC-08/08b/08c 均失败）','可用（部分）'],
];
const services=[['数据视图','固定版本、时点口径'],['因子计算','ResearchEngine 9527'],['试验台账','只追加，不可删'],['封存执行','每候选一次'],['因子库查重','含待审候选']];

export function QuantFactorCapabilitiesPage(){
 return <>
  <WorkspaceHeading eyebrow="FACTOR FACTORY" title="能力与评测" description="按真实接入状态展示；没有评测分数就显示待接入，不填场景值。"><Link className="btn" to="/quant/agents">Agent 管理</Link></WorkspaceHeading>
  <FactorModuleTabs active="caps"/>
  <div className="card"><div className="card-head"><div><h2>研究系统组成</h2><p className="fine">挖掘任务调度分配挖掘任务；每个挖掘任务一个研究决策 Agent，按结果调用专职单元；独立复核与研究隔离。</p></div><span className="badge purple">编排版本 v1</span></div><div className="card-body"><div className="cap-diagram">
   <div className="cap-col"><h4>人</h4><div className="units">{people.map(([n,d])=><div className="unit" key={n}><span className="ui">◎</span><div><b>{n}</b><small>{d}</small></div></div>)}</div></div>
   <div className="cap-col"><h4>Agent 与能力单元</h4><div className="coord"><b>挖掘任务调度</b><br/><small>未接入：排队、并发与跨挖掘任务预算尚无真实运行</small></div><div style={{textAlign:'center',color:'#b9a9c8'}}>↓</div><div className="coord"><b>F0 · 研究决策 Agent</b><br/><small>每挖掘任务一个实例 · 下一步 · 修订 · 分支 · 放弃 · 提交</small></div><div style={{textAlign:'center',color:'#b9a9c8'}}>↓ 按结果调用</div><div className="units">{units.filter(x=>x[0]!=='挖掘任务调度').map(([n,d,s])=><div className="unit" key={n}><span className="ui">{n.slice(0,2)}</span><div><b>{n}</b><small>{d}</small></div><span className={'badge '+(s==='可用'?'live':'gray')}>{s}</span></div>)}</div></div>
   <div className="cap-col"><h4>确定性服务（不由模型决定）</h4><div className="units">{services.map(([n,d])=><div className="unit" key={n}><span className="ui">▤</span><div><b>{n}</b><small>{d}</small></div></div>)}</div></div>
  </div></div></div>
  <div className="card"><div className="card-head"><div><h2>能力单元与评测</h2><p className="fine">评测集和得分尚未接入；没有得分就显示待接入，不填场景值。</p></div></div><div className="table-wrap"><table className="table"><thead><tr><th>功能点</th><th>能力单元</th><th>形态</th><th>当前证据</th><th>评测集</th><th>当前得分</th><th>版本</th></tr></thead><tbody>
   {units.map(([n,d,s])=><tr key={n}><td><b>{n.split(' ')[0]}</b></td><td>{n}</td><td><span className={'badge '+(s==='可用'?'live':'gray')}>{s}</span></td><td className="fine">{d}</td><td>待接入</td><td><span className="score">—</span></td><td>—</td></tr>)}
  </tbody></table></div></div>
  <div className="card"><div className="card-head"><div><h2>编排方案对照实验</h2><p className="fine">同数据视图、同挖掘任务、同预算与门槛；尚未运行，不给比较结论或模拟得分。</p></div><span className="badge gray">计划中 · 未运行</span></div><div className="card-body"><div className="arms">
   <div className="arm"><h4>A · 固定顺序流水线</h4><div className="flow">F1 → F2 → F3 → F4 → F5 → F6</div>同一批专职单元按固定顺序交接；失败按规则回上一步，没有 F0。</div>
   <div className="arm"><h4>B · 研究决策 + 专职单元</h4><div className="flow">F0 ⇄ F1…F4; F5 独立</div>F0 按结果选择调用任一单元，可修订、分支、换方向、放弃（当前方案）。</div>
   <div className="arm"><h4>C · 人工研究基线</h4><div className="flow">研究员 + 同一工作台</div>研究员使用相同工具与台账，不用 Agent。</div>
  </div><p className="hint">评测与实验计划接入前，不展示“已通过”或得分。</p></div></div>
 </>;
}
