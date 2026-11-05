"""Publish only this design preview; never replace the application or V3 baseline."""
from pathlib import Path
import shutil
import html

source = Path(__file__).resolve().parent
root = next(p for p in source.parents if (p / 'frontend').is_dir())
target = root / 'frontend' / 'public' / 'quant-delivery' / 'factor-v4'
target.mkdir(parents=True, exist_ok=True)
for name in ('index.html', 'style.css', 'app.js', 'README.md', '验收记录.md'):
    if (source / name).exists():
        shutil.copy2(source / name, target / name)
text = html.escape((source / 'README.md').read_text(encoding='utf-8'))
(target / 'design.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>因子工厂 V4 设计说明</title><style>body{max-width:960px;margin:40px auto;padding:0 24px;background:#f8f6fa;color:#302539;font:15px/1.9 system-ui}a{color:#65358d}pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:32px;border:1px solid #e8e0ee;border-radius:12px}</style><a href="index.html">← 返回交互原型</a><pre>'+text+'</pre></html>',encoding='utf-8')
print(target)
