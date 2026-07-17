#!/bin/bash
# Wrapper for cron_hourly.sh - 确保cron环境下可靠运行
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH
export GH_CONFIG_DIR="/app/data/所有对话/主对话/.gh"
export HOME="/root"
export NODE_NO_WARNINGS=1
export LARKSUITE_CLI_CONFIG_DIR="/app/data/所有对话/主对话/.feishu_cli"
export LARKSUITE_CLI_DATA_DIR="/app/data/所有对话/主对话/.feishu_cli"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"

cd /app/data/所有对话/主对话/bilibili-stats/ || exit 1

# 直接执行，所有输出追加到日志
/bin/bash /app/data/所有对话/主对话/bilibili-stats/scripts/cron_hourly.sh >> /app/data/所有对话/主对话/bilibili-stats/logs/hourly_sync.log 2>&1
