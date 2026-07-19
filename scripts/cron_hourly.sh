#!/bin/bash
# 小时级采集：B站视频 + 抖音视频 + 生成HTML + git推送
# 环境变量由 scripts/config.py 统一管理，此脚本只管流程
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJ_DIR" || exit 1

LOG="$PROJ_DIR/logs/hourly_sync.log"
mkdir -p "$PROJ_DIR/logs"
echo "=== HOURLY $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG" 2>&1

# 1. B站视频采集（小时级）
python3 -u scripts/fetch_data.py videos >> "$LOG" 2>&1

# 2. 抖音采集：检查锁文件，避免与daily cron冲突
LOCKFILE="$PROJ_DIR/logs/douyin_fetch.lock"
if [ -f "$LOCKFILE" ]; then
    lock_age=$(( $(date +%s) - $(stat -c %Y "$LOCKFILE" 2>/dev/null || echo 0) ))
    if [ "$lock_age" -lt 300 ]; then
        echo "抖音采集锁存在（${lock_age}秒前创建），跳过本次采集" >> "$LOG" 2>&1
        python3 -u scripts/generate_html.py >> "$LOG" 2>&1
        git add .
        if git diff --cached --quiet; then
            echo "no changes" >> "$LOG" 2>&1
        else
            git commit -m "hourly: videos only (douyin locked)" >> "$LOG" 2>&1
            git pull --rebase >> "$LOG" 2>&1
            git push origin main >> "$LOG" 2>&1
        fi
        exit 0
    else
        echo "抖音采集锁过期（${lock_age}秒），删除并继续" >> "$LOG" 2>&1
        rm -f "$LOCKFILE"
    fi
fi

# 3. 检查Chrome CDP是否响应，超时则重启
if ! curl -s --max-time 5 http://localhost:9222/json/version > /dev/null 2>&1; then
    echo "Chrome CDP无响应，正在重启..." >> "$LOG" 2>&1
    pkill -f "remote-debugging-port=9222" 2>/dev/null
    sleep 2
    nohup google-chrome --no-sandbox --disable-gpu --remote-debugging-port=9222 \
        --no-first-run --no-default-browser-check \
        --user-data-dir="$PROJ_DIR/chrome-profile" \
        --disable-blink-features=AutomationControlled \
        --headless=new about:blank > /dev/null 2>&1 &
    sleep 3
    if curl -s --max-time 5 http://localhost:9222/json/version > /dev/null 2>&1; then
        echo "Chrome CDP重启成功" >> "$LOG" 2>&1
    else
        echo "Chrome CDP重启失败，跳过抖音采集" >> "$LOG" 2>&1
    fi
fi

# 4. 抖音视频采集
timeout 300 python3 -u scripts/fetch_douyin_batch.py --mode hourly >> "$LOG" 2>&1

# 5. 生成HTML
python3 -u scripts/generate_html.py >> "$LOG" 2>&1

# 6. Git提交推送
git add .
if git diff --cached --quiet; then
    echo "no changes" >> "$LOG" 2>&1
else
    git commit -m "hourly: videos+douyin" >> "$LOG" 2>&1
    git pull --rebase >> "$LOG" 2>&1
    git push origin main >> "$LOG" 2>&1
fi
