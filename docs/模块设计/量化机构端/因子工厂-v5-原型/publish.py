"""Publish only this design preview; never replace the application, V3 or V4 previews."""
from pathlib import Path
import shutil

source = Path(__file__).resolve().parent
root = next(p for p in source.parents if (p / 'frontend').is_dir())
target = root / 'frontend' / 'public' / 'quant-delivery' / 'factor-v5'
target.mkdir(parents=True, exist_ok=True)
for name in ('index.html', 'base.css', 'v5.css', 'app.js', 'README.md'):
    shutil.copy2(source / name, target / name)
spec = source.parent / '因子工厂V5-需求规格.md'
if spec.exists():
    shutil.copy2(spec, target / 'spec.md')
print(target)
