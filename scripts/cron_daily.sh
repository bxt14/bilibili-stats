#!/bin/bash
# 日级采集：粉丝数据 + 日频视频 + 抖音全量 + 生成HTML + git推送
# 环境变量由 scripts/config.py 统一管理，此脚本只管流程
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJ_DIR" || exit 1

# git 凭证：credential.helper 走 gh CLI，必须显式指向工作区的 gh 配置目录（cron 环境无此变量，否则 push 静默失败）
export GH_CONFIG_DIR="$PROJ_DIR/../.gh"

LOG="$PROJ_DIR/logs/daily_sync.log"
mkdir -p "$PROJ_DIR/logs"
echo "=== DAILY $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG" 2>&1

# 1. 粉丝数据（B站+抖音）+ 日频视频
python3 -u scripts/fetch_data.py fans >> "$LOG" 2>&1
python3 -u scripts/fetch_data.py videos-daily >> "$LOG" 2>&1
python3 -u scripts/fetch_data.py douyin >> "$LOG" 2>&1

# 2. 抖音视频全量采集：创建锁文件防止与hourly冲突
LOCKFILE="$PROJ_DIR/logs/douyin_fetch.lock"
if [ -f "$LOCKFILE" ]; then
    lock_age=$(( $(date +%s) - $(stat -c %Y "$LOCKFILE" 2>/dev/null || echo 0) ))
    if [ "$lock_age" -lt 300 ]; then
        echo "抖音采集锁存在（${lock_age}秒前创建），跳过视频采集" >> "$LOG" 2>&1
    else
        echo "抖音采集锁过期，删除并继续" >> "$LOG" 2>&1
        rm -f "$LOCKFILE"
    fi
fi

# 3. 清理Chrome残留标签页
python3 -u scripts/cleanup_chrome_tabs.py >> "$LOG" 2>&1

# 4. 创建锁文件后采集
date +%s > "$LOCKFILE"
timeout 300 python3 -u scripts/fetch_douyin_batch.py --mode daily >> "$LOG" 2>&1
DOUYIN_EXIT=$?
rm -f "$LOCKFILE"

if [ "$DOUYIN_EXIT" -eq 124 ]; then
    echo "⚠️ 抖音采集超时(300s)" >> "$LOG" 2>&1
    sleep 2
    python3 -u scripts/cleanup_chrome_tabs.py >> "$LOG" 2>&1
fi

# 5. 生成HTML
python3 -u scripts/generate_html.py >> "$LOG" 2>&1

# 6. Git提交推送
git add .
if git diff --cached --quiet; then
    echo "no changes" >> "$LOG" 2>&1
else
    git commit -m "daily: fans+videos+douyin" >> "$LOG" 2>&1
    git pull --rebase >> "$LOG" 2>&1
    git push origin main >> "$LOG" 2>&1
fi
