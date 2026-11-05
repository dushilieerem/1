import {Link} from 'react-router-dom';
import {FactorModuleTabs,WorkspaceHeading} from './QuantWorkspacePages';

const units=[
 ['课题调度','规则','未接入','排队、并发与跨课题预算尚无真实运行'],
 ['F0 研究决策','Agent','未接入','自动推进与回退尚未上线'],
 ['F1 起点检索','能力单元','可用','因子库与历史试验可读'],
 ['F2 假设研究','子 Agent','可用（人工确认）','草稿必须由研究员确认'],
 ['F3 因子实现','子 Agent','可用（人工确认）','生成后进入静态校验与 F4'],
 ['F4 检验诊断','能力单元','可用','真实 RE 单次回测；NW t 由 R1 日度序列计算'],
 ['F5 独立复核','独立 Agent','未上线','封存 worker 与独立复核未验收'],
];

export function QuantFactorCapabilitiesPage(){
 return <>
  <WorkspaceHeading title="能力与评测" description="按真实接入状态展示；没有评测分数就显示待接入，不填场景值。"><Link className="btn" to="/quant/agents">Agent 管理</Link></WorkspaceHeading>
  <FactorModuleTabs active="caps"/>
  <div className="card"><div className="card-head"><div><h2>研究系统组成</h2><p className="fine">每个课题一个研究决策 Agent；F0、F5 未上线时不由页面冒充运行。</p></div></div><div className="card-body"><div className="units">
   {units.map(([name,form,status,note])=><div className="unit" key={name}><span className="ui">{name.startsWith('F')?name.slice(0,2):'⇅'}</span><div><b>{name}</b><small>{form} · {status}：{note}</small></div></div>)}
  </div><div className="svc"><span>数据视图</span><span>因子计算</span><span>试验台账</span><span>因子库查重</span><span>封存样本（未上线）</span><span>R1 日度 Rank IC</span></div></div></div>
  <div className="card"><div className="card-head"><h2>能力单元与评测</h2><span className="badge gray">评测集与得分：待接入</span></div><div className="table-wrap"><table className="table"><thead><tr><th>功能点</th><th>形态</th><th>状态</th><th>当前证据</th><th>评测得分</th></tr></thead><tbody>
   {units.map(([name,form,status,note])=><tr key={name}><td><strong>{name}</strong></td><td>{form}</td><td><span className={'badge '+(status==='可用'?'live':'gray')}>{status}</span></td><td className="fine">{note}</td><td>待接入</td></tr>)}
  </tbody></table></div></div>
  <div className="card"><div className="card-head"><h2>编排方案对照实验</h2><span className="badge gray">计划中 · 未运行</span></div><div className="card-body"><p className="fine">固定顺序流水线 / 研究决策 + 专职单元 / 人工基线三种编排尚未运行，不给比较结论或模拟得分。</p></div></div>
 </>;
}
