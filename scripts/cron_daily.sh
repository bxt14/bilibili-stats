#!/bin/bash
export LARKSUITE_CLI_CONFIG_DIR="/tmp/.fuse_data/所有对话/主对话/.feishu_cli"
export LARKSUITE_CLI_DATA_DIR="/tmp/.fuse_data/所有对话/主对话/.feishu_cli"
cd /tmp/.fuse_data/所有对话/主对话/bilibili-stats

LOG=/tmp/daily_sync.log
echo "=== DAILY $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG" 2>&1

python3 -u scripts/fetch_data.py fans >> "$LOG" 2>&1
python3 -u scripts/fetch_data.py videos-daily >> "$LOG" 2>&1
python3 -u scripts/fetch_data.py douyin >> "$LOG" 2>&1

# 抖音视频采集：创建锁文件防止与hourly冲突
LOCKFILE=/tmp/douyin_fetch.lock
if [ -f "$LOCKFILE" ]; then
    lock_age=$(( $(date +%s) - $(stat -c %Y "$LOCKFILE" 2>/dev/null || echo 0) ))
    if [ "$lock_age" -lt 300 ]; then
        echo "抖音采集锁存在（${lock_age}秒前创建），跳过视频采集" >> "$LOG" 2>&1
    else
        echo "抖音采集锁过期，删除并继续" >> "$LOG" 2>&1
        rm -f "$LOCKFILE"
    fi
fi

# 清理Chrome残留标签页
python3 -u scripts/cleanup_chrome_tabs.py >> "$LOG" 2>&1

# 创建锁文件
date +%s > "$LOCKFILE"

timeout 180 python3 -u scripts/fetch_douyin_batch.py >> "$LOG" 2>&1
DOUYIN_EXIT=$?

# 删除锁文件
rm -f "$LOCKFILE"

if [ "$DOUYIN_EXIT" -eq 124 ]; then
    echo "⚠️ 抖音采集超时(180s)" >> "$LOG" 2>&1
    sleep 2
    python3 -u scripts/cleanup_chrome_tabs.py >> "$LOG" 2>&1
fi

python3 -u scripts/generate_html.py >> "$LOG" 2>&1

git add .
if git diff --cached --quiet; then
    echo "no changes" >> "$LOG" 2>&1
else
    git commit -m "daily: fans+videos+douyin" >> "$LOG" 2>&1
    git pull --rebase >> "$LOG" 2>&1
    git push >> "$LOG" 2>&1
fi
