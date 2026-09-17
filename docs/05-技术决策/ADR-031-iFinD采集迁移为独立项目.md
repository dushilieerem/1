# ADR-031：iFinD 采集迁移为独立项目

## 问题

SVQuant 的 `MarketData/DataIngestion/data_ingestion/ifind` 同时承担供应商鉴权、HTTP 请求、历史回填、日更、源数据生成和活动数据发布。它与 ResearchEngine 只通过文件交接，却被放在同一仓库，导致凭据、依赖、发布节奏和故障域边界不清。

## 选择

将完整数据生产能力迁入独立 `IFind` 项目。独立项目采用 `src/` Python 包布局，保留 `data_ingestion.ifind` 内部命名空间，并接管 AkShare、共享质量检查、候选版本、备份以及历史回填/日更/发布 CLI。发布到 SVQuant 必须显式指定 `MarketData` 根目录，两个项目不互相导入源码。

SVQuant 只保留数据契约、活动发布物和只读 Provider/DataEngine。原 `MarketData/sources`、`releases`、`backups`、`DataIngestion` 全部迁入 IFind；原 `MarketData/current/*` 提升到 `MarketData/*`。

## 备选方案

1. 继续保留在 SVQuant：迁移成本最低，但供应商依赖、凭据和研究服务继续耦合，拒绝。
2. 只复制代码并保留旧入口：短期兼容，但形成双写和双事实来源，拒绝。
3. 改造成在线数据微服务：长期扩展性更强，但当前只需要批处理回填/发布，部署与运维成本过高，暂不采用。

## 后果

正面后果：采集与研究计算独立发布；凭据与供应商故障隔离；iFinD 可独立安装、测试、调度；SVQuant 运行时边界更清晰。

负面后果：运维需要维护两个项目及显式发布路径；既有脚本调用路径需要切换；跨仓变更需要同步验证数据契约。通过稳定 CLI、清单/质量报告、双项目测试和文档链接缓解。
