# 本批机构研究资产最小契约

- 唯一新批准动作：POST `/api/inst/quant/factor-workflow/reviews/{candidate_id}`，decision=`approve_research_and_register`；同请求含acknowledged=true、分类、标签、依据。旧research_supported仅反馈，历史未准入留档不升级。
- 存储：`quant_factor_candidates.archive.research_asset`，schema=`quant.research-asset.v1`；候选行锁内一次写review决定、approved、登记快照和事件。重复同一批准返回同一登记；不改个人库、共享RE或旧证据。
- 新发现资产id=`qfa_<candidate_id>`，kind=`novel_factor`；复现验证记录id=`qfr_<candidate_id>`，kind=`replication_validation`，只关联既有因子身份/源码版本，不创造一个新因子定义。登记版本1对应本次不可变候选快照，不冒称已有历史版本链。
- 必填身份/证据：org_id、candidate_id、snapshot_hash、定义及源码/来源hash、固定方法清单（id/version/contract/code digest）、topic与policy_version、数据/研发/封存区间、研发与验证报告引用、实际K及当时阈值、分类标签及确认来源、独立审批者/时间、research_only、登记完整性hash。新产生的候选在冻结时记录实际方法清单；缺失来源的历史候选不补造方法版本。
- 资格由后端重新核验：已领取独立复核人；非本人/同机构；冻结hash一致；当前可执行输入与候选一致；没有在途修改/计算；重新从可信结果计算研发硬门槛和当前K门槛；同候选/同hash封存通过；新发现的全部必要对照完整且合格；任何诊断/小参考证据不得准入。seal_failed_review禁止入库。
- GET `/api/inst/quant/factor-workflow/assets`：机构域内已登记对象的白名单目录摘要。
- GET `/api/inst/quant/factor-workflow/assets/{asset_id}`：白名单定义、固定来源/版本、研发报告摘要、审批与登记事实；登记时冻结的研发/封存/查重授权摘要对普通本机构研究成员可见；批准前内部封存明细仍按原权限。不开放作者私有project、聊天或全部candidate。
- 新研究复用只复制该资产冻结定义/必要范围与来源ID，走现有项目/计划/预算/检验工具；不继承已通过状态或封存资格。
- 因子库将新发现资产接入统一目录；复现验证记录附于已有因子身份。分类沿现行原型；没有因子级标签时未标注。
- 以上先隔离测试；实际人工决定由PM执行。资源诊断单独报方案，未获可控执行证据前不运行真实模型/回测。
