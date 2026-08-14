# SVQuant 本地启动 · 试用分口 · Scrcpy 投屏手册

> **路径**：`E:\日报-周报\SVQUANT_本地启动与投屏手册.md`  
> **机器约定**：代码在 `E:\quant-lab\SV\SVQuant\WebApp`；软件装 `F:\`（如 scrcpy）  
> **局域网本机 IP（示例）**：`192.168.3.32`（以你 `ipconfig` 为准）  
> **相关**：[`FRONTEND_DEV_VS_STABLE.md`](./FRONTEND_DEV_VS_STABLE.md)

---

## 1. 端口一览（先看这张表）

| 端口 | 是什么 | 谁用 | 怎么起 |
|------|--------|------|--------|
| **8766** | 后端 API（主站 + 知识库 `/api/kh/*` 都靠它） | 全家共用 | `python -u api_server.py` |
| **9530** | 主站前端 · **开发/测试版** | 我们改代码 | `npm run dev` |
| **9532** | 主站前端 · **冻结试用版** | 给别人先用 | `build:dist` 后再 `preview:stable` |
| **9531** | 知识库前端 | 管理知识库 | KnowledgeHub 里 `npm run dev` |
| **9527** | 同事 YGQuant ResearchEngine | 因子/回测计算 | 不在本机起；需能访问 `192.168.3.64:9527` |

**记一句：**

- 改页面、试新功能 → 用 **9530**  
- 别人用稳定初版 → 用 **9532**（不跟着你改实时变）  
- 知识库页面 → **9531**（API 仍是 8766）

---

## 2. 后端怎么启动（8766）

开一个 PowerShell / 终端：

```bat
cd /d E:\quant-lab\SV\SVQuant\WebApp\backend
conda activate SVQuant
python -u api_server.py
```

自检：

```bat
curl http://127.0.0.1:8766/api/health
```

浏览器也可开：`http://127.0.0.1:8766/docs`（若有）或知识库 Swagger：`http://127.0.0.1:8766/api/kh/docs`

> 主站前端、知识库前端、试用版 **都依赖这个后端**。8766 没起，页面会登录失败/接口挂。

---

## 3. 主站前端：开发版 9530（我们改这个）

### 3.1 启动

另开一个终端（后端保持开着）：

```bat
cd /d E:\quant-lab\SV\SVQuant\WebApp\frontend
npm run dev
```

- 本机：http://127.0.0.1:9530  
- 同事同网：http://192.168.3.32:9530  

### 3.2 怎么改、怎么测

1. 用 Cursor / VS Code 改 `frontend/src/...`  
2. 保存后 Vite 会热更新，**刷新 9530** 就能看见  
3. **不要**让长期试用的人盯着 9530——你一改他就跟着晃

---

## 4. 主站前端：冻结试用版 9532（给别人用）

### 4.1 第一次冻住 / 启动试用口

后端 8766 先开着。然后：

```bat
cd /d E:\quant-lab\SV\SVQuant\WebApp\frontend
npm run build:dist
npm run preview:stable
```

- 本机：http://127.0.0.1:9532  
- 同事：http://192.168.3.32:9532  

`preview:stable` 这个窗口要一直开着；关掉则 9532 不可访问。

### 4.2 改 9530 会不会动 9532？

**不会。**  
9532 看的是上次打好的 `dist` 包，不是源码热更新。

### 4.3 什么时候更新冻结版？

功能在 9530 测稳了，再执行：

```bat
cd /d E:\quant-lab\SV\SVQuant\WebApp\frontend
npm run build:dist
```

然后：

1. 在跑 `preview:stable` 的那个窗口里 **Ctrl+C** 停掉  
2. 再执行：

```bat
npm run preview:stable
```

同事 **强制刷新**（Ctrl+F5）9532 即可看到新包。

> `build:dist` 大约 **20～30 秒**（机器忙时可能近 1 分钟）。  
> 完整 `npm run build` 会先跑 TypeScript，当前仓库有历史类型报错可能失败；**更新试用包用 `build:dist` 即可**。

### 4.4 对照小结

| 动作 | 9530 开发 | 9532 试用 |
|------|-----------|-----------|
| 日常改代码 | ✅ 立刻变 | ❌ 不变 |
| 给别人稳定用 | ❌ 不合适 | ✅ 合适 |
| 发布新试用版 | — | `build:dist` + 重启 `preview:stable` |

---

## 5. 知识库怎么启动（9531）

知识库 **前端** 在 KnowledgeHub；**接口** 仍挂在主后端 8766。

### 5.1 先起后端（若还没起）

同第 2 节 → 8766。

### 5.2 再起知识库前端

```bat
cd /d E:\quant-lab\SV\SVQuant\WebApp\KnowledgeHub\frontend
npm run dev
```

- 本机：http://127.0.0.1:9531  
- 同事：http://192.168.3.32:9531  
- Swagger：http://127.0.0.1:8766/api/kh/docs  

说明文档：`WebApp/KnowledgeHub/README.md`、`KnowledgeHub/docs/使用说明.md`。

---

## 6. 推荐「全开」终端布局

| 终端 | 命令 | 端口 |
|------|------|------|
| 1 | `backend` → `conda activate SVQuant` → `python -u api_server.py` | 8766 |
| 2 | `frontend` → `npm run dev` | 9530（开发） |
| 3 | （需要试用时）`frontend` → `npm run preview:stable` | 9532（需先 build 过） |
| 4 | （需要知识库时）`KnowledgeHub\frontend` → `npm run dev` | 9531 |

一次性复制（按需开）：

```bat
:: 终端1 后端
cd /d E:\quant-lab\SV\SVQuant\WebApp\backend
conda activate SVQuant
python -u api_server.py

:: 终端2 开发前端
cd /d E:\quant-lab\SV\SVQuant\WebApp\frontend
npm run dev

:: 终端3 冻结试用（已 build 过）
cd /d E:\quant-lab\SV\SVQuant\WebApp\frontend
npm run preview:stable

:: 终端4 知识库
cd /d E:\quant-lab\SV\SVQuant\WebApp\KnowledgeHub\frontend
npm run dev
```

---

## 7. Scrcpy 手机投屏（安卓）

### 7.1 安装位置（已装好）

```
F:\scrcpy\scrcpy-win64-v4.1\scrcpy.exe
```

同目录自带 `adb.exe`。

### 7.2 手机准备

1. 开启 **开发者选项**  
2. 打开 **USB 调试**  
3. 若无线：再开 **无线调试**（安卓 11+）  
4. 手机与电脑同一 Wi‑Fi（无线时）

### 7.3 方式 A：USB 有线（最简单）

1. USB 连电脑，手机点「允许 USB 调试」  
2. 打开命令行：

```bat
cd /d F:\scrcpy\scrcpy-win64-v4.1
adb devices
scrcpy.exe
```

`adb devices` 里应出现设备；再出投屏窗口。

### 7.4 方式 B：无线调试（安卓 11+）

手机「无线调试」页上会有：

- **配对用**：IP + 配对端口 + 6 位配对码（第一次）  
- **连接用**：IP + 调试端口（主页面那一行，**不是**配对端口）

电脑：

```bat
cd /d F:\scrcpy\scrcpy-win64-v4.1

:: 第一次配对（端口、码以手机为准；下面数字是示例）
adb pair 192.168.3.34:43357
:: 回车后输入 6 位配对码

:: 再连接（调试端口以手机「IP 和端口」为准）
adb connect 192.168.3.34:40825
adb devices
adb disconnect 192.168.3.34:42073
adb disconnect adb-10ACAT08SG001UR-xVESAY._adb-tls-connect._tcp
scrcpy -s 192.168.3.34:40825
```

> 常见笔误：打成 `app` → 必须是 **`adb`**。

### 7.5 方式 C：USB 插一次转无线

```bat
cd /d F:\scrcpy\scrcpy-win64-v4.1
adb devices
adb tcpip 5555
adb connect 手机IP:5555
scrcpy.exe
```

之后可拔掉 USB（同网）。

### 7.6 不做投屏时的替代

只看网页布局：Chrome **F12 → 设备工具栏**，尺寸选 375×812，截图即可。

---

## 8. 自检清单

```bat
:: 后端
curl http://127.0.0.1:8766/api/health

:: 同事算力（因子/回测）
curl http://192.168.3.64:9527/api/health

:: 手机 ADB
cd /d F:\scrcpy\scrcpy-win64-v4.1
adb devices
```

| 现象 | 先查 |
|------|------|
| 前端能开但登录失败 | 8766 是否在跑 |
| 9532 打不开 | 是否执行过 `preview:stable`，端口是否被占 |
| 9532 还是旧页面 | 是否重新 `build:dist` **并重启** preview |
| 知识库白屏/接口挂 | 8766 是否在跑；是否开的是 9531 |
| scrcpy 无设备 | `adb devices`；无线是否 pair + connect；命令是否写成了 `adb` |

---

## 9. 和周任务文档的关系

- 手机适配施工序：[`MOBILE_ADAPT_DESIGN_2026-08-10.md`](./MOBILE_ADAPT_DESIGN_2026-08-10.md)  
- 开发/试用分口短文：[`FRONTEND_DEV_VS_STABLE.md`](./FRONTEND_DEV_VS_STABLE.md)  
- 本周打勾：[`WEEK_CHECKLIST_2026-08-10.md`](./WEEK_CHECKLIST_2026-08-10.md)  
