import './domSetup.mjs';
import React from 'react';
import assert from 'node:assert/strict';
import test,{afterEach} from 'node:test';
import {render,fireEvent,cleanup,waitFor,within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {QuantFactorLibraryPage} from '../src/pages/institutional-workflow/QuantFactorLibraryPage';
import {clearFactorCache} from '../src/lib/factorCatalog';
Object.defineProperty(globalThis,'sessionStorage',{value:window.sessionStorage,configurable:true});
const originalFetch=globalThis.fetch;
afterEach(()=>{cleanup();globalThis.fetch=originalFetch;clearFactorCache();sessionStorage.clear();});
// Actual directory category counts read by PM; metadata fixture only, never product data.
const counts:Record<string,number>={'动量因子':34,'反转因子':28,'Beta因子':4,'日内结构因子':31,'区间与通道因子':8,'流动性因子':13,'资金流与量能因子':18,'量价关系因子':88,'波动率因子':53,'风险分布因子':3,'估值因子':1,'技术复合因子':50};
function setup(catalog:any[],imported:any[],assets:any[]=[]){
 sessionStorage.setItem('svquant_quant_session',JSON.stringify({product:'quant',token:'isolated-test',user:{id:9,username:'isolated'},org:{id:2,code:'dev'},permissions:{quant:'write'},can_write:true}));
 const requests:string[]=[];
 globalThis.fetch=async(input,init)=>{
  const path=new URL(String(input),'http://localhost').pathname;requests.push((init?.method||'GET')+' '+path);
  assert.equal(init?.method||'GET','GET','filter/search must never submit imports/research');
  if(path.endsWith('/reference'))return Response.json({items:imported});
  if(path.endsWith('/assets'))return Response.json({assets});
  if(path.endsWith('/re-catalog'))return Response.json({ok:true,factors:catalog});
  if(path.endsWith('/factor/index'))return Response.json({libraries:{}});
  throw Error('unexpected fixture route '+path);
 };
 return requests;
}
function importedFactor(f:any){return {id:f.name,source_library:f.library,source_factor_id:f.name,factor_name:f.name,display_name:f.display_name,definition:f.description,category:f.category_label||f.category_name,status:'imported_unreviewed',metrics_status:'pending',reference:null};}
test('机构库331去重：保留12真实分类计数，分类与独立搜索可组合，不发写请求',async()=>{
 const factors=Object.entries(counts).flatMap(([category,n],c)=>Array.from({length:n},(_,i)=>({name:`factor_${c}_${i}`,library:'主因子库',display_name:`${category}研究${i}`,description:`${category}定义${i}`,category_id:`SV${String(c+1).padStart(2,'0')}`,category_label:category,tags:Object.keys(counts)})));
 const requests=setup(factors,factors.map(importedFactor));
 const view=render(<MemoryRouter><QuantFactorLibraryPage/></MemoryRouter>);
 await waitFor(()=>assert.equal(within(view.getByRole('table')).getAllByRole('row').length,332));
 assert.ok(view.getByRole('button',{name:'全部 331'}));
 const chips=view.getByRole('group',{name:'因子分类'});
 assert.equal(within(chips).getAllByRole('button').length,13);
 for(const [label,count] of Object.entries(counts))assert.ok(within(chips).getByRole('button',{name:label+' '+count}));
 assert.equal(view.queryByRole('button',{name:/基本面与规模|风险与波动|^量价 /}),null);
 fireEvent.click(view.getByRole('button',{name:'量价关系因子 88'}));
 assert.equal(within(view.getByRole('table')).getAllByRole('row').length,89);
 const search=view.getByRole('textbox',{name:'搜索因子'});
 fireEvent.change(search,{target:{value:'factor_7_87'}});
 assert.equal(within(view.getByRole('table')).getAllByRole('row').length,2);assert.ok(view.getByText('量价关系因子研究87'));
 fireEvent.change(search,{target:{value:'factor_0_0'}});assert.ok(view.getByText('没有符合条件的因子。'));
 fireEvent.click(view.getByRole('button',{name:'全部 331'}));assert.ok(view.getByText('动量因子研究0'));
 fireEvent.change(search,{target:{value:''}});assert.equal(within(view.getByRole('table')).getAllByRole('row').length,332);
 assert.equal(view.queryByRole('combobox',{name:'筛选标签'}),null,'whole-catalog tags are not factor-specific tags');
 assert.ok(requests.every(x=>x.startsWith('GET ')));
});
test('分类使用逐因子中文口径并回退目录label；SV编号不作名称，仅研究资产保留真实标签',async()=>{
 const factors=[{name:'one',library:'主因子库',display_name:'目录动量',description:'定义',category_id:'SV01',category_name:'动量因子',tags:['全库标签']},{name:'two',library:'主因子库',display_name:'目录反转',description:'定义',category_id:'SV03',category_label:'反转因子',tags:['全库标签']}];
 const imported=factors.map(importedFactor);imported[0].category='';imported[1].category='SV03';
 setup(factors,imported,[{id:'qfa_isolated',kind:'novel_factor',display_name:'机构冻结研究',category:'动量因子',tags:['低换手研究'],hypothesis:'机构假设',source_factor:{factor_name:'approved'}}]);
 const view=render(<MemoryRouter><QuantFactorLibraryPage/></MemoryRouter>);
 await waitFor(()=>assert.ok(view.getByRole('button',{name:'全部 3'})));
 assert.ok(view.getByRole('button',{name:'动量因子 2'}));assert.ok(view.getByRole('button',{name:'反转因子 1'}));
 assert.equal(view.queryByText('SV01'),null);assert.equal(view.queryByText('SV03'),null);
 const tags=view.getByRole('combobox',{name:'筛选标签'});assert.deepEqual(within(tags).getAllByRole('option').map(x=>x.textContent),['全部标签','低换手研究']);
 fireEvent.change(tags,{target:{value:'低换手研究'}});assert.equal(within(view.getByRole('table')).getAllByRole('row').length,2);assert.ok(view.getByText('机构冻结研究'));
});
