# SVQuant 机构量化 · 产品原型 V3

2026-11-04 的流程方案版产品评审交付。五业务模块、30 步、18 类逻辑 Agent 职责；保留现有真实工具工作台。

## 打开

服务器既有 18796 服务已发布静态目录，不需要增加服务进程：

- 产品：/assets/prototype-v3/index.html#overview
- PRD：/assets/prototype-v3/prd.html
- Markdown：/assets/prototype-v3/PRD.md
- 响应式验收夹具：/assets/prototype-v3/responsive-check.html

通过既有 SSH 转发访问 http://127.0.0.1:18796。转发关闭不影响服务器；若只看原型，可直接打开交付包 index.html。index.html、prd.html 和 PRD.md 放在同一目录即可离线查看，原型没有第三方资源依赖。

## 内容与边界

每步包含业务输入、人工工具入口、可操作的结果、Agent 填写/执行预览及调用记录。支持资产复用、输入变更、旧证据失效、候选审查、固定审查快照、模拟资金授权、方法与 Skill 草案、评测发布门槛和计划配置。

这是交互原型：场景指标、报告、模型回复和工具事件均为模拟。配比金额实际做基础算术，但没有真实回测、AI 调用、后台调度、训练、采集、资金或订单操作。原型所有交互保存在浏览器专用 localStorage 键中。预览身份不是身份认证。

原有真实工作台仍位于 /，其能力和记录与本原型分开；另一版自主研究系统未改动。

## 编辑与构建

业务开发继续以公司服务器本目录为准，不回写本地迁移前应用。

- src/config.js：30 个步骤的表单、工具事件与产物配置。
- src/model.js：任务、输入版本、产物、候选、审查、方法与计划的原型状态规则。
- src/views.js：页面与组件渲染。
- src/app.js：浏览器交互、草稿保存、预览执行与路由。
- src/style.css：Sunvalley 紫白风格与响应式布局。
- docs/prd-intro.md：产品需求正文。
- docs/PRD-v3.md：正文与自动生成的页面/角色附录。
- tests/：Node 状态测试与响应式测试模板。

构建输入另含 ../docs/2026-11-04-business-fishbones/design.json、public.json、figures/*.svg。保持此相对目录即可在解压源码包后重新构建。

使用 Python 3.10+、Node 18+；无 npm 安装或前端构建依赖。服务器已有对应环境。执行：

    python workbench/prototype-v3/build.py
    node --test workbench/prototype-v3/tests/model.test.cjs workbench/prototype-v3/tests/version-cases.cjs

build.py 可从任意工作目录运行；示例命令按 institutional-workflow 根目录书写。产物自动输出到 workbench/web/assets/prototype-v3，刷新浏览器后可见。

响应式夹具使用同源 srcdoc 嵌入生成后的原型，以实际 iframe 内容视口检查 390 / 1280 / 1440 宽度。保持服务器原有 frame-ancestors 策略，不为了测试降低安全配置。

## 维护约定

审查显示提交时的固定证据，不把当前可编辑任务当作历史快照。输入变更或已有产物重算会使相关后续证据失效。旧审批保留，但不能放行新的资金方案或替换后的审批产物。历史 Agent 执行打开其确切产物，重复模拟部署使用同一回执。

不要把示例收益、IC 或勾选框接到正式准入。接入真实服务时替换状态适配层和执行事件来源，保留服务端权限、确定性计算、版本绑定与停止条件。PRD 第 8、10 章列出现有可复用能力和开发顺序。

本次未提交或推送 Git，没有重启既有业务服务。详细验证见 docs/acceptance.md。
