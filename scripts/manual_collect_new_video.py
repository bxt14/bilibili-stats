#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手动触发一次 B站视频采集 + HTML生成 + git推送（新视频入监控后初始化）"""
import subprocess, sys, os

os.chdir('/root/bilibili-stats')
steps = [
    ["python3", "-u", "scripts/fetch_data.py", "videos"],
    ["python3", "-u", "scripts/generate_html.py"],
]
for cmd in steps:
    print(f"\n===== RUN: {' '.join(cmd)} =====", flush=True)
    r = subprocess.run(cmd)
    print(f"===== EXIT {r.returncode} =====", flush=True)
    if r.returncode != 0:
        sys.exit(r.returncode)

# git 提交推送
subprocess.run(["git", "add", "."])
diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
if diff.returncode != 0:
    subprocess.run(["git", "commit", "-m", "watch: add BV1444B6pE71 (erjiedao 悬索曲线) + init data"])
    subprocess.run(["git", "pull", "--rebase"])
    r = subprocess.run(["git", "push", "origin", "main"])
    print("push exit:", r.returncode)
else:
    print("no changes to commit")
