"""Build the self-contained prototype and traceable PRD. Run from any cwd."""
from pathlib import Path
import json, subprocess, re, html, hashlib
ROOT=Path(__file__).resolve().parent
WB=ROOT.parent
DESIGN=WB/'docs'/'2026-11-04-business-fishbones'
OUT=WB/'web'/'assets'/'prototype-v3'
def esc(s): return html.escape(str(s))
def inline(s):
    s=esc(s)
    s=re.sub(r'\*\*(.*?)\*\*',r'<strong>\1</strong>',s)
    s=re.sub(r'\x60([^\x60]+)\x60',r'<code>\1</code>',s)
    s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',s)
    return s
def markdown(source):
    lines=source.splitlines();out=[];toc=[];i=0;counter=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line.startswith(chr(96)*3):
            chunk=[];i+=1
            while i<len(lines) and not lines[i].strip().startswith(chr(96)*3):chunk.append(lines[i]);i+=1
            out.append('<pre class="json">'+esc('\n'.join(chunk))+'</pre>');i+=1;continue
        if line.startswith('> '):
            quoted=[]
            while i<len(lines) and lines[i].strip().startswith('> '):quoted.append('<p>'+inline(lines[i].strip()[2:])+'</p>');i+=1
            out.append('<blockquote>'+''.join(quoted)+'</blockquote>');continue
        if re.match(r'^\d+\. ',line):
            ordered=[]
            while i<len(lines) and re.match(r'^\d+\. ',lines[i].strip()):ordered.append('<li>'+inline(re.sub(r'^\d+\. ','',lines[i].strip()))+'</li>');i+=1
            out.append('<ol>'+''.join(ordered)+'</ol>');continue
        h=re.match(r'^(#{1,4}) (.*)',line)
        if h:
            level=len(h[1]);counter+=1;anchor='section-'+str(counter)
            out.append(f'<h{level} id="{anchor}">'+inline(h[2])+f'</h{level}>')
            if level==2:toc.append((anchor,h[2]))
            i+=1;continue
        if line.startswith('|') and i+1<len(lines) and re.match(r'^\|[ :|\-]+\|$',lines[i+1].strip()):
            cells=lambda x:[inline(c.strip()) for c in x.strip().strip('|').split('|')]
            heads=cells(line);i+=2;rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                row=cells(lines[i]);assert len(row)==len(heads),(len(heads),row)
                rows.append('<tr>'+''.join('<td>'+v+'</td>' for v in row)+'</tr>');i+=1
            out.append('<div class="table-wrap"><table class="table"><thead><tr>'+''.join('<th>'+x+'</th>' for x in heads)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>');continue
        if re.match(r'^[-*] ',line):
            items=[]
            while i<len(lines) and re.match(r'^[-*] ',lines[i].strip()):items.append('<li>'+inline(lines[i].strip()[2:])+'</li>');i+=1
            out.append('<ul>'+''.join(items)+'</ul>');continue
        out.append('<p>'+inline(line)+'</p>');i+=1
    return '\n'.join(out),toc
def pipe(value):return str(value).replace('|','／').replace('\n','；')
def mdtable(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+['| '+' | '.join(pipe(v) for v in row)+' |' for row in rows])
def make_prd(blueprint,config):
    manual=(ROOT/'docs'/'prd-intro.md').read_text(encoding='utf-8') if (ROOT/'docs'/'prd-intro.md').exists() else '# SVQuant机构量化：产品需求文档 V3\n\n设计文档整理中。\n'
    parts=[manual,'','## 附录A：30个业务步骤的页面规格','',
    '以下规格由原型字段配置和已确认的业务拆解共同生成。所有工具名称为产品能力名称；是否已接真实接口见前文现状矩阵。字段默认值只用于原型场景，不作为投资门槛或通用最佳参数。','']
    for m in blueprint['modules']:
        parts += ['### '+m['name'],'',m['flow'],'']
        for s in m['stages']:
            page=config[s['id']]
            parts+=['#### '+s['id']+' '+s['name'],'',
             '- 页面路由：#'+m['id']+'/'+s['id']+'。',
             '- 输入：'+s['input'],
             '- 人工功能：'+s['manual'],
             '- 主操作：'+page['action']+'。',
             '- Agent角色：'+'、'.join(s['roles'])+'。任务：'+s['ai'],
             '- 工具事件：'+' → '.join(page['tools'])+'。',
             '- 输出：'+s['output'],
             '- 放行/介入：'+s['check'],'',
             mdtable(['字段','控件','原型默认值','取值／交互要求'],[
               [f['label'],f['type'],json.dumps(f['value'],ensure_ascii=False) if isinstance(f['value'],(list,bool)) else f['value'],
                (('范围 '+str(f.get('min'))+'～'+str(f.get('max'))) if f['type']=='number' else ('引用共享资产目录 '+f['options']) if isinstance(f['options'],str) else '、'.join(map(str,f['options'])) if f.get('options') else (f.get('help') or '输入变更保存草稿并记录版本影响'))]
               for f in page['fields']]),'']
    parts += ['## 附录B：Agent职责、权限与评测','',
     '18类逻辑职责由16类模块职责和2类共享职责组成，运行进程数量待正式架构与评测决定。共享验证须隔离数据和工具权限。','']
    for rid,r in blueprint['roles'].items():
        covered=[s['id'] for m in blueprint['modules'] for s in m['stages'] if rid in s['roles']]
        parts+=['### '+rid+' '+r['name'],'',mdtable(['项目','要求'],[
            ['对应业务步骤','、'.join(covered)],['任务',r['mission']],['工具',r['tools']],['交付',r['output']],['权限边界',r['boundary']],['评测关注',r['evaluation']]]),'']
    parts += ['## 附录C：公共管理入口与职责','']
    for m in blueprint['public']:
        parts += ['### '+m['name'],'',m['purpose'],'',m['flow'],'',mdtable(['步骤','功能与承担者','输出'],[
            [s['id']+' '+s['name'],s['label']+'：'+s['manual']+' '+s['ai'],s['output']] for s in m['stages']]),'']
    return '\n'.join(parts)
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    blueprint=json.loads((DESIGN/'design.json').read_text(encoding='utf-8'))
    blueprint['public']=json.loads((DESIGN/'public.json').read_text(encoding='utf-8'))
    blueprint['diagrams']={}
    for path in sorted((DESIGN/'figures').glob('*.svg')):
        key=path.stem[3:];blueprint['diagrams'][key]=path.read_text(encoding='utf-8')
    config=json.loads(subprocess.check_output(['node','-e',"process.stdout.write(JSON.stringify(require('./src/config.js').stages))"],cwd=ROOT,text=True))
    assert len(config)==30
    assert set(config)=={s['id'] for m in blueprint['modules'] for s in m['stages']}
    css=(ROOT/'src'/'style.css').read_text(encoding='utf-8')
    scripts='\n'.join((ROOT/'src'/n).read_text(encoding='utf-8') for n in ['config.js','model.js','views.js','app.js'])
    data=json.dumps(blueprint,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    csp="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'"
    common='<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="'+csp+'"><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27/%3E">'
    index='<!doctype html><html lang="zh-CN"><head>'+common+'<title>旸谷资本 · SVQuant机构量化 · 产品原型V3</title><style>'+css+'</style></head><body><div id="app"><main class="main"><h1>SVQuant · 机构量化</h1><p>正在打开交互原型…</p></main></div><dialog id="modal"></dialog><div id="toast" role="status" aria-live="polite"></div><noscript>请启用JavaScript以使用原型；产品需求文档可单独阅读。</noscript><script id="blueprint" type="application/json">'+data+'</script><script>'+scripts.replace('</script','<\\/script')+'</script></body></html>'
    (OUT/'index.html').write_text(index,encoding='utf-8')
    prd=make_prd(blueprint,config)
    (ROOT/'docs'/'PRD-v3.md').write_text(prd,encoding='utf-8')
    (OUT/'PRD.md').write_text(prd,encoding='utf-8')
    rendered,toc=markdown(prd)
    doccss='.doc-shell{display:grid;grid-template-columns:230px minmax(0,1fr);max-width:1600px;margin:auto}.doc-nav{padding:25px;position:sticky;top:0;height:100vh;overflow:auto;border-right:1px solid var(--border);font-size:12px}.doc-nav a{display:block;margin:12px 0}.doc-main{min-width:0;padding:34px 42px;background:var(--panel)}.doc-main h1{font-size:28px;margin-bottom:20px}.doc-main h2{font-size:22px;margin:40px 0 18px;scroll-margin-top:20px}.doc-main h3{font-size:18px;margin:28px 0 14px}.doc-main h4{font-size:15px;margin:24px 0 12px}.doc-main p{margin:13px 0}.doc-main ul,.doc-main ol{padding-left:22px}.doc-main blockquote{margin:18px 0;border-left:3px solid var(--primary);padding:3px 16px;background:var(--soft);color:var(--muted)}.doc-main li{margin:6px 0}.doc-main .table-wrap{margin:18px 0;border:1px solid var(--border);border-radius:6px}.doc-main code{font-size:12px;background:var(--bg);padding:2px 4px;border-radius:3px}@media(max-width:800px){.doc-shell{display:block}.doc-nav{position:static;height:auto;padding:18px;border-bottom:1px solid var(--border);display:flex;gap:10px;flex-wrap:wrap}.doc-nav a{margin:0}.doc-main{padding:24px 18px}}@media print{.doc-shell{display:block}.doc-nav{display:none}.doc-main{padding:0}.table{font-size:10px}.doc-main h2{break-before:page}}'
    nav='<nav class="doc-nav"><strong>SVQuant · PRD V3</strong><a href="index.html#overview">← 返回产品原型</a><a href="PRD.md" download>下载 Markdown 原文</a>'+''.join('<a href="#'+anchor+'">'+esc(label)+'</a>' for anchor,label in toc)+'</nav>'
    (OUT/'prd.html').write_text('<!doctype html><html lang="zh-CN"><head>'+common+'<title>SVQuant 机构量化 · 产品需求文档 V3</title><style>'+css+doccss+'</style></head><body><div class="doc-shell">'+nav+'<article class="doc-main">'+rendered+'</article></div></body></html>',encoding='utf-8')
    qa=(ROOT/'tests'/'responsive-template.html').read_text(encoding='utf-8')
    (OUT/'responsive-check.html').write_text(qa.replace('<!--PROTOTYPE-->',html.escape(index,quote=True)),encoding='utf-8')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json'}
    (OUT/'manifest.json').write_text(json.dumps({'version':'3.0','status':'interactive_prototype','production_actions':False,'files':hashes},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'steps':len(config),'roles':len(blueprint['roles']),'index_bytes':(OUT/'index.html').stat().st_size,'prd_chars':len(prd),'outputs':list(hashes)},ensure_ascii=False))
if __name__=='__main__':main()
