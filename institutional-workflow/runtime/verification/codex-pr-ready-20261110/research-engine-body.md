固定机构研究请求此前跟随current变化，且线程取消不能证明计算停止。本分支在原factor/novelty API和manager身份上增加可选受控子进程与明确冻结发布view；旧请求/未启用受控实例保留原路径。

- source `codex/factor-novelty-r4` `3bd36a2be90ca61998ac93cbda19e65239180373` → 最新fetch `origin/master` `0874e8dc15dadafeb2c952f2d4a0f86102168833`；merge-base `bb181851a2591da66bdc0439b0273c431497d616`。source-only2、target-only24提交、18文件，详见`source-base-diff.json`。未合并最新master，无整合测试/共享部署声明。
- 受控模式仅显式`RE_CONTROLLED_EXECUTION_REQUIRED=1`开启；开启而无policy时fail-closed，未开启保留原Experiment路径。保留原run/result schema及资源回执。AS是地址空间上限，RSS是监测停止线，不宣称硬RSS绝对不超。
- `frozen_data_view`是可选DTO；不接收任意本地路径。服务端发布根白名单校view/release/manifest和真实daily文件字节，核逻辑路径→目标、软链换绑/换回及provider实际字段路径，前后校验后返回actual identity。显式冻结请求不能静默用current；开发/novelty/heldout一致绑定。无此字段的旧接口兼容。
- 新计算继续原BacktestEngine/NoveltyExperiment，provider在fresh worker装配，终止/超时清理自有子进程并释放容量。没有BFF第二回测引擎或共享调度平台。
- 18项固定view/原引擎合成Parquet专项通过（2.806s/175431680B），包含合法发布链接、越界/字节变更/换绑、provider路径、dedup及旧模式；原受控worker/默认与required两分支测试见此前对应交付。未运行真实全库查重；真实市场/固定view字节证明依实际worker回执，metadata-only预检本身不证明字节已核。
- 仅自有18804按私有开关加载；共享9527/18803/current未改。本PR无数据库迁移、不改公司其他实例配置。
- 最新master24项尚未整合；本次文件层面无双边修改交集，但不能因此称合并必无冲突或兼容性已过。
- 历史PR #27 https://gitee.com/yanggu-yuanqi-intelligence/research-engine/pulls/27 已有本地链接记录；当前状态/源目标/是否包含这2提交未通过Gitee核实。请由有权限方确认复用/更新或另开，避免重复PR。本文未提交远程PR，无自合并/tag。
