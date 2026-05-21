# 运营监控常驻进程

这个入口用于把“友商公开流量监控”跑成持续链路：

1. 同步启用友商的监控任务。
2. 调度 pending / 到期的 research jobs。
3. 执行 worker 消费 crawl units。
4. 采集完成后沿用 backfill + postprocess，生成公开流量快照。

## 本地一次性验证

```powershell
python scripts\run_ops_monitor.py --once --worker-iterations 1 --save-option postgres --headless
```

这个命令只跑一个周期，适合确认数据库、任务同步、调度和 worker 链路是否正常。

## 本地常驻运行

```powershell
python scripts\run_ops_monitor.py --interval 60 --worker-iterations 1 --save-option postgres --headless
```

默认策略：

- 友商监控任务间隔：`480` 分钟，也就是每天 3 次。
- 每个友商每次采集主页最新 `50` 条内容。
- 公开流量只代表公开可采集内容和公开互动指标，不代表平台后台真实曝光。
- 采集内容会按公开内容 ID 去重，快照里同时保存累计值和增量值。

## 常用参数

```powershell
python scripts\run_ops_monitor.py `
  --interval 60 `
  --monitor-interval-minutes 480 `
  --latest-limit 50 `
  --worker-iterations 1 `
  --max-attempts 4 `
  --save-option postgres `
  --headless
```

参数含义：

- `--once`：跑一个周期后退出。
- `--interval`：常驻循环间隔，单位秒。
- `--monitor-interval-minutes`：友商任务的采集间隔。
- `--latest-limit`：每次监控每个账号主页最新内容条数。
- `--worker-iterations`：每个周期执行几次 worker。
- `--save-option`：爬虫保存方式，建议和后端数据库配置保持一致。
- `--headless`：使用无头浏览器执行。

## 部署建议

第一版可以直接用 Windows 终端、PowerShell 后台任务或进程管理器常驻运行。迁移到服务器后，把同一条命令放入 Docker entrypoint、systemd、PM2 或 Windows Task Scheduler 都可以。

关键点是这个进程必须持续运行；只创建每日 3 次任务并不等于自动监控，scheduler 和 worker 需要按周期把任务调度并执行。
