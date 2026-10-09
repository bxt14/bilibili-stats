#!/usr/bin/env python3
"""只暂存工作区中实际变更的文件，替代 `git add .`。

背景：项目运行在 FUSE 云盘上，数据文件成千上万。`git add .` 会触发
整目录遍历，在 IO 高峰（如日级 08:33）容易挂死。改为先 `status
--porcelain -z` 拿到精确变更路径，再只 add 这些路径；同时正确处理
重命名/拷贝记录与含空格、中文的文件名。

退出码：0 成功（含无变更）；非0 失败。
"""
import subprocess
import sys
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args, timeout=None):
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_DIR,
        capture_output=True,
        timeout=timeout,
    )


def main():
    r = git("-c", "core.optionalLock=false", "status", "--porcelain", "-z", timeout=40)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode("utf-8", "replace"))
        return r.returncode

    recs = r.stdout.split(b"\0")
    paths = []
    i = 0
    while i < len(recs):
        rec = recs[i]
        if not rec:
            i += 1
            continue
        code = rec[:2].decode("latin1")
        path = rec[3:]
        # 重命名/拷贝：记录后跟“旧路径\0新路径”，暂存新路径
        if code[0] in "RC" or code[1] in "RC":
            i += 1
            if i < len(recs) and recs[i]:
                path = recs[i]
        paths.append(path)
        i += 1

    if not paths:
        print("no changed files")
        return 0

    add = subprocess.run(
        ["git", "add", "--"] + [p.decode("utf-8", "surrogateescape") for p in paths],
        cwd=PROJECT_DIR,
        capture_output=True,
        timeout=90,
    )
    if add.returncode != 0:
        sys.stderr.write(add.stderr.decode("utf-8", "replace"))
        return add.returncode

    print(f"staged {len(paths)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
