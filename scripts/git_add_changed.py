#!/usr/bin/env python3
"""只暂存工作区中实际变更的文件，替代 `git add .`。

背景：项目运行在 FUSE 云盘上，数据文件成千上万。`git add .` 以及默认的
`git status` 都会遍历整个工作区（尤其查找 untracked 文件），在 IO 高峰
（日级 08:33）容易挂死。本脚本策略：

1. tracked 文件改动：`status -z --untracked-files=no`，不遍历 untracked，
   稳定快速。daily 核心数据文件全部是 tracked，这是主数据。
2. untracked 新文件：`status -z`（配合 core.untrackedCache 增量），带较短
   超时；拿到则一并暂存，超时/失败也不阻塞 tracked 主数据。

正确处理重命名/拷贝记录与含空格、中文的文件名。
退出码：0 成功（含无变更）；非0 失败。
"""
import subprocess
import sys
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(args, timeout):
    return subprocess.run(args, cwd=PROJECT_DIR, capture_output=True, timeout=timeout)


def parse_porcelain_z(data: bytes):
    """解析 git status --porcelain -z 输出，返回 (code, path) 列表。

    重命名/拷贝记录为 `code path\\0 orig_path`，这里保留 path（新路径）。
    """
    recs = data.split(b"\0")
    out = []
    i = 0
    while i < len(recs):
        rec = recs[i]
        if not rec:
            i += 1
            continue
        code = rec[:2].decode("latin1")
        path = rec[3:]
        if code[0] in "RC" or code[1] in "RC":
            i += 1  # 跳过紧随的旧路径
            if i < len(recs) and recs[i]:
                path = recs[i]
        out.append((code, path))
        i += 1
    return out


def main():
    # 1) tracked 改动（不遍历 untracked）
    try:
        tr = run(
            ["git", "-c", "core.optionalLock=false", "status",
             "--porcelain", "-z", "--untracked-files=no"],
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write("tracked status 超时\n")
        return 1
    if tr.returncode != 0:
        sys.stderr.write(tr.stderr.decode("utf-8", "replace"))
        return tr.returncode

    entries = parse_porcelain_z(tr.stdout)
    paths = [p for _, p in entries]

    # 2) untracked 新文件（依赖 untracked cache，超时则跳过）
    try:
        ur = run(
            ["git", "-c", "core.optionalLock=false", "status",
             "--porcelain", "-z"],
            timeout=45,
        )
        if ur.returncode == 0:
            for code, p in parse_porcelain_z(ur.stdout):
                if code == "??" and p not in paths:
                    paths.append(p)
    except subprocess.TimeoutExpired:
        sys.stderr.write("untracked status 超时，跳过新文件\n")

    if not paths:
        print("no changed files")
        return 0

    decoded = [p.decode("utf-8", "surrogateescape") for p in paths]
    try:
        add = run(["git", "add", "--"] + decoded, timeout=90)
    except subprocess.TimeoutExpired:
        sys.stderr.write("git add 超时\n")
        return 1
    if add.returncode != 0:
        sys.stderr.write(add.stderr.decode("utf-8", "replace"))
        return add.returncode

    print(f"staged {len(paths)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
