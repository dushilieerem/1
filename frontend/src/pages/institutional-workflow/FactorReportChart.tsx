import {useMemo,useRef} from 'react';
import ReactECharts from 'echarts-for-react';
import type {EChartsOption} from 'echarts';
import type {PlotData} from './factorReportData';
const palette=['#7651a1','#9ca9bb','#258f90','#d3974a','#557fbc','#b96d91','#828e4d','#7e77c8','#618c88','#bb895d'];
export function chartOption(plot:PlotData):EChartsOption{return {
 animation:false,color:plot.series.map((s,i)=>s.color||palette[i%palette.length]),textStyle:{fontFamily:'Inter, Microsoft YaHei, sans-serif',color:'#637086'},
 aria:{enabled:true},grid:{left:62,right:24,top:48,bottom:76},
 tooltip:{trigger:'axis',triggerOn:'mousemove|click|mousewheel',confine:true,backgroundColor:'#fff',borderColor:'#e6dfec',textStyle:{color:'#293449',fontSize:12},axisPointer:{type:'cross',label:{backgroundColor:'#515c71'}},valueFormatter:(v:unknown)=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(plot.percent?2:4)+(plot.percent?'%':''):'缺失'},
 legend:{type:'scroll',top:5,left:10,right:10,itemWidth:18,itemHeight:8,textStyle:{fontSize:12,color:'#5c667a'}},
 xAxis:{type:'category',boundaryGap:false,data:plot.dates,axisLine:{lineStyle:{color:'#e7eaf0'}},axisTick:{show:false},axisLabel:{fontSize:11,hideOverlap:true}},
 yAxis:{type:'value',scale:true,splitNumber:4,axisLabel:{formatter:(v:number)=>Number(v.toFixed(2))+(plot.percent?'%':''),fontSize:11},splitLine:{lineStyle:{color:'#edf0f5',type:'dashed'}}},
 dataZoom:[{type:'inside',filterMode:'none',zoomOnMouseWheel:'ctrl',moveOnMouseMove:true},{type:'slider',bottom:12,height:20,borderColor:'#e5dfeb',fillerColor:'rgba(118,81,161,.1)',handleStyle:{color:'#7651a1'},showDetail:false}],
 series:plot.series.map(s=>({name:s.name,type:s.kind||'line',data:s.values,showSymbol:false,connectNulls:false,smooth:false,lineStyle:{width:s.dashed?1.7:2,type:s.dashed?'dashed':'solid'},areaStyle:s.area?{opacity:.09}:undefined,emphasis:{focus:'series'},barMaxWidth:9})),
 };}
export function FactorReportChart({title,subtitle,plot,height=340}:{title:string;subtitle?:string;plot:PlotData;height?:number}){
 const chart=useRef<ReactECharts>(null);
 function zoom(last?:number){chart.current?.getEchartsInstance().dispatchAction({type:'dataZoom',startValue:plot.dates[Math.max(0,plot.dates.length-(last||plot.dates.length))],endValue:plot.dates.at(-1)});}
 const option=useMemo(()=>chartOption(plot),[plot]);const valid=plot.series.some(s=>s.values.some(v=>typeof v==='number'&&Number.isFinite(v)));
 return <section className="card qr-chart"><div className="qr-chart-head"><div><h3>{title}</h3>{subtitle&&<p>{subtitle}</p>}</div><span className="qr-chart-hint">悬停查看 · 点击图例筛选 · 拖动缩放</span></div>{valid?<><div className="qr-range" role="group" aria-label={title+'显示范围'}><span>显示范围</span>{([20,60,undefined] as const).map(n=><button className="btn small" key={n||'all'} type="button" onClick={()=>zoom(n)}>{n?'最近 '+n+' 期':'全部'}</button>)}</div><div aria-label={title+'交互图'}><ReactECharts ref={chart} option={option} notMerge style={{height}} opts={{renderer:'svg'}}/></div><details className="qr-data"><summary>查看图表数据（{plot.dates.length} 个日期）</summary><div className="qr-table-scroll"><table><thead><tr><th>日期</th>{plot.series.map(s=><th key={s.name}>{s.name}{plot.percent?'（%）':''}</th>)}</tr></thead><tbody>{plot.dates.map((d,i)=><tr key={d}><td>{d}</td>{plot.series.map(s=><td key={s.name}>{s.values[i]===null?'缺失':s.values[i]?.toFixed(4)}</td>)}</tr>)}</tbody></table></div></details></>:<p className="qr-empty">本次计算未返回此项有效序列。</p>}</section>;
}
