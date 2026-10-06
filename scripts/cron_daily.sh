#!/bin/bash
# 日级采集：粉丝数据 + 日频视频 + 抖音全量 + 生成HTML + git推送
# 抖音采集已改为抖音App API(api.amemv.com)方案，纯HTTP无浏览器依赖
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

# 3. 创建锁文件后采集（App API，纯HTTP）
date +%s > "$LOCKFILE"
timeout 300 python3 -u scripts/fetch_douyin_batch.py --mode daily >> "$LOG" 2>&1
DOUYIN_EXIT=$?
rm -f "$LOCKFILE"

if [ "$DOUYIN_EXIT" -eq 124 ]; then
    echo "⚠️ 抖音采集超时(300s)" >> "$LOG" 2>&1
fi

# 4. 生成HTML
python3 -u scripts/generate_html.py >> "$LOG" 2>&1

# 5. Git提交推送
# 安全清理残留 index.lock：仅当锁文件为0字节（操作未完成）且无git进程运行时删除
safe_clean_lock() {
    local lock="$PROJ_DIR/.git/index.lock"
    [ -f "$lock" ] || return 0
    # FUSE幻影锁多为0字节且会自消，先等待最多30秒，避免误删真实操作的锁
    local waited=0
    while [ -f "$lock" ] && [ "$waited" -lt 30 ]; do
        sleep 5
        waited=$((waited+5))
    done
    [ -f "$lock" ] || { echo "index.lock 已自消" >> "$LOG" 2>&1; return 0; }
    local size
    size=$(stat -c%s "$lock" 2>/dev/null || echo "-1")
    if [ "$size" != "0" ]; then
        echo "index.lock 非空（${size}字节），存在活跃git操作，保留" >> "$LOG" 2>&1
        return 1
    fi
    if pgrep -x git > /dev/null 2>&1; then
        echo "index.lock 为0字节但有git进程运行中，保留" >> "$LOG" 2>&1
        return 1
    fi
    rm -f "$lock" 2>/dev/null
    echo "已清理残留0字节 index.lock（无git进程，等待${waited}s未自消）" >> "$LOG" 2>&1
    return 0
}

# 针对FUSE幻影锁的重试封装：命令失败时清理0字节死锁后重试
git_with_lock_retry() {
    local max="$1"; shift
    local attempt=1
    while [ "$attempt" -le "$max" ]; do
        if "$@" >> "$LOG" 2>&1; then
            return 0
        fi
        echo "git命令失败(第${attempt}/${max}次): $*" >> "$LOG" 2>&1
        safe_clean_lock || true
        attempt=$((attempt+1))
        [ "$attempt" -le "$max" ] && sleep 10
    done
    return 1
}

safe_clean_lock
git_with_lock_retry 4 git add .
if git diff --cached --quiet; then
    echo "no changes" >> "$LOG" 2>&1
else
    git_with_lock_retry 4 git commit -m "daily: fans+videos+douyin"
    git pull --rebase >> "$LOG" 2>&1
    # push 网络抖动/握手失败重试
    push_ok=0
    for i in 1 2 3 4 5; do
        if git push origin main >> "$LOG" 2>&1; then push_ok=1; break; fi
        echo "git push 失败(第${i}/5次)" >> "$LOG" 2>&1
        sleep 15
    done
    [ "$push_ok" -eq 1 ] || echo "❌ git push 连续5次失败，需人工补推" >> "$LOG" 2>&1
fi
