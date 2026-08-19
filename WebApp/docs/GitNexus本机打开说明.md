# GitNexus 本机怎么打开页面

## 一次性 / 偶发：修好 FTS（关键词搜）

```powershell
cd E:\quant-lab\SV\SVQuant
$env:GITNEXUS_LBUG_EXTENSION_INSTALL="auto"
npx gitnexus analyze --repair-fts
```

全量重建（可尝试修复空 id）：

```powershell
$env:GITNEXUS_LBUG_EXTENSION_INSTALL="auto"
npx gitnexus analyze --force
```

## 看图：官方 UI

```powershell
cd E:\quant-lab\SV\SVQuant
npx gitnexus serve -p 4747 --host 127.0.0.1
```

打开：**http://127.0.0.1:4747/**  
选仓库 **SVQuant**。勿点「完整流程图」。

## 读步骤：按产品模块（推荐）

另开终端：

```powershell
cd E:\quant-lab\SV\SVQuant\WebApp\docs
python -m http.server 8765 --bind 127.0.0.1
```

打开：**http://127.0.0.1:8765/module-flows.html**（亮色）

> **不要**用资源管理器双击打开（`file://` 会 Failed to fetch，连不上 GitNexus）。

左侧点「因子检测 / 因子库 / 策略…」；右侧竖向流程图 + 逐步函数/接口。  
连上 `gitnexus serve` 后可展开该页自动挖出的调用链。

全部自动链列表：**http://127.0.0.1:8765/gitnexus-flows.html**
