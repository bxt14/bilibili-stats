#!/bin/bash
# 小时级采集：B站视频 + 抖音视频 + 生成HTML + git推送
# 抖音采集已改为抖音App API(api.amemv.com)方案，纯HTTP无浏览器依赖
# B站采集使用HTTP API，同样不依赖Chrome
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJ_DIR" || exit 1

# git 凭证：credential.helper 走 gh CLI，必须显式指向工作区的 gh 配置目录（cron 环境无此变量，否则 push 静默失败）
export GH_CONFIG_DIR="$PROJ_DIR/../.gh"

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

# 3. 抖音视频采集（App API，纯HTTP）
timeout 300 python3 -u scripts/fetch_douyin_batch.py --mode hourly >> "$LOG" 2>&1

# 4. 生成HTML
python3 -u scripts/generate_html.py >> "$LOG" 2>&1

# 5. Git提交推送
git add .
if git diff --cached --quiet; then
    echo "no changes" >> "$LOG" 2>&1
else
    git commit -m "hourly: videos+douyin" >> "$LOG" 2>&1
    git pull --rebase >> "$LOG" 2>&1
    git push origin main >> "$LOG" 2>&1
fi
