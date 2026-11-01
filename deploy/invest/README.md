# Invest 值守扫描定时器

收盘后扫描自选异动与组合诊断，写入 `invest_event_log`（同日同标题去重）。

```bash
# 安装（替换路径与用户）
sudo sed -e 's|__REPO_DIR__|/home/dev01/project/SVQuant|g' \
         -e 's|__RUN_USER__|dev01|g' \
         deploy/invest/svquant-invest-scan.service | sudo tee /etc/systemd/system/svquant-invest-scan.service
sudo cp deploy/invest/svquant-invest-scan.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now svquant-invest-scan.timer
```

手动运行：

```bash
.ci/venv/bin/python scripts/invest_watch_scan.py --user-id 1
```

不提供实时推送；实时行情（H01）与舆情（F23）到位后再接事件总线。
