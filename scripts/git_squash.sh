#!/bin/bash
# 每月1号清理git历史，将所有提交压缩为一个快照
set -e

REPO_DIR="/Coze/Drive/运营实习生/所有对话/主对话/bilibili-stats"
cd "$REPO_DIR"

echo "[$(date)] 开始清理git历史..."

# 保存当前工作目录状态
git add -A
if ! git diff --cached --quiet; then
    git commit -m "data: 更新看板数据至$(date +%m-%d %H:%M)" || true
fi

# 创建orphan分支（无历史的全新分支）
git checkout --orphan temp_squash_branch
git add -A
git commit -m "Squash: 保留最新快照，清理历史 $(date +%Y-%m-%d)"

# 替换main分支
git branch -D main
git branch -m main

# 强制推送
git push -f origin main

# 清理本地git对象
git reflog expire --expire=now --all 2>/dev/null || true
git gc --prune=now 2>/dev/null || true

echo "[$(date)] git历史清理完成！.git大小: $(du -sh .git/ | cut -f1)"
