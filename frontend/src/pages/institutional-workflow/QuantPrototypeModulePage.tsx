import {useEffect,useRef,useState} from 'react';
import {Link,useLocation,useNavigate} from 'react-router-dom';
const routes:Record<string,string>={overview:'/quant',data:'/quant/data',factor:'/quant/factor',strategy:'/quant/strategy',portfolio:'/quant/portfolio',monitor:'/quant/monitor',review:'/quant/reviews',agents:'/quant/agents'};
const labels:Record<string,string>={overview:'管理驾驶舱',data:'数据资源',factor:'因子工厂',strategy:'策略研究',portfolio:'组合与执行',monitor:'运行与风险',review:'审查中心',agents:'Agent 管理'};
/** Original accepted prototype, not a replacement design or personal-platform page. */
export function QuantPrototypeModulePage(){
 const location=useLocation(),navigate=useNavigate(),frame=useRef<HTMLIFrameElement>(null);
 const segment=location.pathname.split('/')[2]||'overview',page=segment==='reviews'?'review':segment;
 const sub=location.pathname.includes('/library')?'/library':location.pathname.includes('/reports')?'/experiments':'';
 const [height,setHeight]=useState(900);
 useEffect(()=>{setHeight(900);const receive=(event:MessageEvent)=>{
  if(event.origin!==window.location.origin||event.source!==frame.current?.contentWindow||event.data?.type!=='quant-prototype-state')return;
  const next=event.data.page;
  if(typeof next==='string'&&routes[next]&&next!==page){navigate(routes[next]);return;}
  const h=event.data.height;if(typeof h==='number'&&Number.isFinite(h))setHeight(Math.max(500,Math.min(12000,h+8)));
 };window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive);},[page,navigate]);
 return <section className="prototype-module"><div className="prototype-notice" role="note"><span><b>原型预览</b>　保留完整设计与交互；本模块的场景数据、AI 执行和审批仅供预览，尚未接通真实业务。</span>{page==='review'&&<Link className="btn small" to="/quant/reviews/factors">真实因子研究复核 →</Link>}{page==='agents'&&<Link className="btn small" to="/quant/factor/experiments">真实因子任务与产物 →</Link>}</div><iframe ref={frame} key={page+sub} className="prototype-frame" title={labels[page]+'完整交互原型'} src={'/quant-delivery/prototype-module.html#'+page+sub} style={{height}}/></section>;
}
