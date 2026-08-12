# Heartbeat 巡检清单

## 检查项
1. B站数据文件时间戳是否在最近2小时内（data/videos/BV1Kruq63E9J_all.json, BV1Ygub6hESJ_all.json）
2. 抖音数据文件时间戳是否在最近6小时内（data/douyin_videos/）
3. 无残留 Chrome 进程（pgrep -f remote-debugging-port=9222）
4. Git 工作区是否干净（git status --short）
5. 看板HTML是否在最近24小时内生成（docs/index.html）
6. 无残留 lock 文件（.git/index.lock, /tmp/cron_hourly.lock）

## 规则
- 正常 → 静默 NO_REPLY
- 异常 → notify 主 Agent，说明具体问题
