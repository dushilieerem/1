# UX105 真实加载与只读HTTP核验

实际加载完成：源码主仓5575aeab3d12f995a8f5163bc6e04b98ea38752f；私有RE080821882b69f1a64701617420d7ac27abb9283b。

18804 PID3176526→1760602，18799 PID249329→1761723；原argv/cwd/env保持，仅温和退出，没有force kill。19536、共享服务和数据库选择不变，无DDL/迁移/切库/研究/模型/审批/在线建议写入。

前后五类研究、当前物理未知、owned active/external unknown/slot held和RE queued/running均0，可用内存大于16GiB。18799 HTTP200、ok=true、db=ok、schema_ok=true；RE/api/health status=ok，受控执行required/enabled及固定view/no-current-fallback能力保留。前端及v105原型入口HTTP200。

现有注册研究员经真实HTTP登录（唯一POST，仅登录/审计）；3真实导入源码与部署SQLite原文逐字及SHA对应：SV01_0001/alpha158_cntd、SV02_0001/bias、SV11_0001/pe_raw。API原始source_sha256和包含工具/适配器source_hash均保留，源码查看不标执行验证通过。无登录拒绝401、不存在记录404；其他机构检查结果及限制见source-load-evidence.json实际http_checks，不用单元替身冒称在线完成。原r4 E2报告真实GET200，历史不重算。

source-load-evidence.json是实际网络HTTP+原生read-only源PG/SQLite；此前source-bff-isolated.log含鉴权/数据依赖替身，性质分开。剪贴板OS实际内容由PM通过浏览器后续实测，本开发只验证给copy helper的原文及原生dialog焦点/回退。

独立开发库仍prepared_verified_not_loaded。后续切换需另按PM维护窗口及源快照差异核验；CR102暂存未整合，不在本次运行身份/迁移中。
