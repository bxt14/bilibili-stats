#!/bin/bash
export NODE_NO_WARNINGS=1
export LARKSUITE_CLI_CONFIG_DIR="/tmp/.fuse_data/所有对话/主对话/.feishu_cli"
export LARKSUITE_CLI_DATA_DIR="/tmp/.fuse_data/所有对话/主对话/.feishu_cli"
cd /tmp/.fuse_data/所有对话/主对话/bilibili-stats

LOG=/tmp/.fuse_data/所有对话/主对话/bilibili-stats/logs/hourly_sync.log
echo "=== HOURLY $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG" 2>&1

python3 -u scripts/fetch_data.py videos >> "$LOG" 2>&1

# 抖音采集：检查锁文件，避免与daily cron冲突
LOCKFILE=/tmp/douyin_fetch.lock
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

# 检查Chrome CDP是否响应，超时则重启
if ! curl -s --max-time 5 http://localhost:9222/json/version > /dev/null 2>&1; then
    echo "Chrome CDP无响应，正在重启..." >> "$LOG" 2>&1
    pkill -f "chrome-douyin-profile" 2>/dev/null
    sleep 2
    nohup google-chrome --no-sandbox --disable-gpu --remote-debugging-port=9222 \
        --no-first-run --no-default-browser-check \
        --user-data-dir=/tmp/chrome-douyin-profile \
        --disable-blink-features=AutomationControlled \
        --headless=new about:blank > /dev/null 2>&1 &
    sleep 3
    if curl -s --max-time 5 http://localhost:9222/json/version > /dev/null 2>&1; then
        echo "Chrome CDP重启成功" >> "$LOG" 2>&1
    else
        echo "Chrome CDP重启失败，跳过抖音采集" >> "$LOG" 2>&1
        python3 -u scripts/generate_html.py >> "$LOG" 2>&1
        git add .
        if git diff --cached --quiet; then
            echo "no changes" >> "$LOG" 2>&1
        else
            git commit -m "hourly: videos only (douyin skipped)" >> "$LOG" 2>&1
            git pull --rebase >> "$LOG" 2>&1
            git push origin main >> "$LOG" 2>&1
        fi
        exit 0
    fi
fi

# 检查Chrome标签页数量，超过3个则重启Chrome
TAB_COUNT=$(curl -s --max-time 5 http://localhost:9222/json/list 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 99)
if [ "$TAB_COUNT" -gt 3 ]; then
    echo "Chrome标签页过多($TAB_COUNT个)，重启Chrome..." >> "$LOG" 2>&1
    pkill -f "chrome-douyin-profile" 2>/dev/null
    sleep 2
    nohup google-chrome --no-sandbox --disable-gpu --remote-debugging-port=9222 \
        --no-first-run --no-default-browser-check \
        --user-data-dir=/tmp/chrome-douyin-profile \
        --disable-blink-features=AutomationControlled \
        --headless=new about:blank > /dev/null 2>&1 &
    sleep 3
    echo "Chrome已重启" >> "$LOG" 2>&1
else
    echo "Chrome标签页正常($TAB_COUNT个)" >> "$LOG" 2>&1
    python3 -u scripts/cleanup_chrome_tabs.py >> "$LOG" 2>&1
fi

# 检查service_worker残留
SW_COUNT=$(curl -s --max-time 5 http://localhost:9222/json/list 2>/dev/null | python3 -c "import sys,json; tabs=json.load(sys.stdin); print(sum(1 for t in tabs if t.get('type')=='service_worker'))" 2>/dev/null || echo 0)
if [ "$SW_COUNT" -gt 0 ]; then
    echo "检测到${SW_COUNT}个service_worker残留，重启Chrome..." >> "$LOG" 2>&1
    pkill -f "chrome-douyin-profile" 2>/dev/null
    sleep 2
    nohup google-chrome --no-sandbox --disable-gpu --remote-debugging-port=9222 \
        --no-first-run --no-default-browser-check \
        --user-data-dir=/tmp/chrome-douyin-profile \
        --disable-blink-features=AutomationControlled \
        --headless=new about:blank > /dev/null 2>&1 &
    sleep 3
    echo "Chrome已重启(清除service_worker)" >> "$LOG" 2>&1
fi

# 创建锁文件
date +%s > "$LOCKFILE"

# 运行抖音采集（传递 --mode hourly 启用频率分级）
timeout 600 python3 -u scripts/fetch_douyin_batch.py --mode hourly >> "$LOG" 2>&1
DOUYIN_EXIT=$?

# 删除锁文件
rm -f "$LOCKFILE"

if [ "$DOUYIN_EXIT" -eq 124 ]; then
    echo "⚠️ 抖音采集超时(600s)，可能需要检查Chrome状态" >> "$LOG" 2>&1
    sleep 2
    python3 -u scripts/cleanup_chrome_tabs.py >> "$LOG" 2>&1
fi

python3 -u scripts/generate_html.py >> "$LOG" 2>&1

git add .
if git diff --cached --quiet; then
    echo "no changes" >> "$LOG" 2>&1
else
    git commit -m "hourly: videos+douyin" >> "$LOG" 2>&1
    git pull --rebase >> "$LOG" 2>&1
    git push origin main >> "$LOG" 2>&1
fi
