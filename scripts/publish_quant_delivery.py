"""Build the internal review pack from tracked product docs; no server or database changes."""
from pathlib import Path
import importlib.util, shutil, zipfile, html, json
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs/模块设计/量化机构端'
OUT=ROOT/'frontend/public/quant-delivery'
spec=importlib.util.spec_from_file_location('prototype_renderer',ROOT/'frontend/institutional-workflow/prototype-v3/build.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
CSS="""body{margin:0;background:#f7f8fc;color:#211a2d;font:15px/1.8 system-ui,'Microsoft YaHei',sans-serif}main{max-width:1120px;margin:36px auto;padding:36px;background:white;border:1px solid #e6e0ed;border-radius:16px}a{color:#65358d}nav{display:flex;gap:24px;flex-wrap:wrap;margin-bottom:32px}h1{font-size:30px}h2{margin-top:36px}table{width:100%;border-collapse:collapse;font-size:14px}td,th{border:1px solid #e6e0ed;padding:10px;text-align:left;vertical-align:top}th{background:#f3eaf8}.table-wrap{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}blockquote{border-left:3px solid #65358d;padding-left:16px;color:#655c70}code{background:#f6f3f9;padding:2px 4px}li{margin:8px 0}@media(max-width:700px){main{margin:0;padding:20px}h1{font-size:25px}}"""
NAV='<nav><a href="/quant">真实机构量化系统</a><a href="index.html">今日成果</a><a href="prd.html">需求文档</a><a href="factor-novelty.html">新因子与去重验收</a><a href="prototype.html#overview">交互原型（模拟）</a><a href="quant-delivery.zip">下载交付包</a></nav>'
def page(md,title):
 body,_=module.markdown(md)
 return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+html.escape(title)+'</title><style>'+CSS+'</style><main>'+NAV+body+'</main></html>'
OUT.mkdir(parents=True,exist_ok=True)
prd=(DOCS/'PRD.md').read_text()
report=(DOCS/'今日成果-2026-11-05.md').read_text()
(DOCS/'prd.html').write_text(page(prd,'SVQuant 机构量化 · 需求文档 V3.8'))
(OUT/'prd.html').write_text(page(prd,'SVQuant 机构量化 · 需求文档 V3.8'))
(OUT/'index.html').write_text(page(report,'SVQuant 机构量化 · 今日成果'))
(OUT/'factor-iteration.html').write_text(page((DOCS/'因子工厂自动迭代与报告.md').read_text(),'因子工厂 · 自动迭代与报告'))
shutil.copyfile(DOCS/'因子工厂自动迭代与报告.md',OUT/'因子工厂自动迭代与报告.md')
(OUT/'factor-novelty.html').write_text(page((DOCS/'因子新颖性与因子库对照.md').read_text(),'因子工厂 · 新因子与去重验收'))
shutil.copyfile(DOCS/'因子新颖性与因子库对照.md',OUT/'因子新颖性与因子库对照.md')
shutil.copyfile(DOCS/'PRD.md',OUT/'PRD.md')
shutil.copyfile(DOCS/'今日成果-2026-11-05.md',OUT/'今日成果.md')
# Keep the actual interactive design intact and visibly identified as a prototype.
proto=(DOCS/'index.html').read_text().replace('href="/"', 'href="/quant"')
(OUT/'prototype.html').write_text(proto)
# Keep every original form, library, modal and Agent interaction for modules
# that are not implemented yet. Only adapt the surrounding navigation.
embedded_style = """<style id="quant-embedded-style">
html,body{margin:0;min-height:0;background:transparent}body>.app-shell,#app>.app-shell{display:block;min-height:0}
.sidebar,.topbar{display:none!important}.stage-area{min-width:0}.main{padding:0!important;max-width:none!important}
.bottom-caption{margin-bottom:8px}.menu-toggle{display:none!important}
</style>"""
embedded_bridge = """<script id="quant-embedded-bridge">
(function(){
 const pages=['overview','data','factor','strategy','portfolio','monitor','review','agents'];
 function report(){
  if(parent===window)return;
  const page=location.hash.slice(1).split('/')[0]||'overview';
  parent.postMessage({type:'quant-prototype-state',page,hash:location.hash,height:Math.ceil(document.body.getBoundingClientRect().height)},location.origin);
 }
 let scheduled=false;
 function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;report();});}
 new MutationObserver(schedule).observe(document.getElementById('app'),{childList:true,subtree:true,attributes:true});
 new ResizeObserver(schedule).observe(document.getElementById('app'));
 addEventListener('hashchange',schedule);addEventListener('resize',schedule);schedule();
})();
</script>"""
embedded=proto.replace('</head>',embedded_style+'</head>').replace('</body>',embedded_bridge+'</body>')
# Preview records must not collide with the standalone design review copy.
embedded=embedded.replace('sunvalley.workflow.prototype.v3.20261104','sunvalley.workflow.prototype.v3.20261104.embedded')
(OUT/'prototype-module.html').write_text(embedded)

with zipfile.ZipFile(OUT/'quant-delivery.zip','w',zipfile.ZIP_DEFLATED) as archive:
 for name in ['index.html','prototype.html','prd.html','PRD.md','今日成果.md','factor-iteration.html','因子工厂自动迭代与报告.md','factor-novelty.html','因子新颖性与因子库对照.md']:
  archive.write(OUT/name,name)
print('Published internal review pack:',OUT)

class BlueprintReader(HTMLParser):
 def handle_starttag(self,tag,attrs):self.active=tag=='script' and dict(attrs).get('type')=='application/json'
 def handle_data(self,data):
  if getattr(self,'active',False):
   try:
    obj=json.loads(data)
    if 'diagrams' in obj:(OUT/'factor-fishbone.svg').write_text(obj['diagrams']['factor'])
   except ValueError:pass
BlueprintReader().feed(proto)
