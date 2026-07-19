#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性修复脚本：从日文件重建所有 _all.json
背景：旧去重逻辑用 hour-only key 导致跨天数据被错误删除。
修复方法：扫描所有 {bvid}_{date}.json 日文件，合并、排序、按 timestamp//3600 去重，重建 _all.json
"""
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO_DATA_DIR = os.path.join(BASE_DIR, 'data', 'videos')


def repair_all():
    # 收集所有 bvid
    bvids = set()
    for f in os.listdir(VIDEO_DATA_DIR):
        m = re.match(r'(BV\w+)_(\d{4}-\d{2}-\d{2})\.json$', f)
        if m:
            bvids.add(m.group(1))

    print(f'发现 {len(bvids)} 个视频的日文件')

    total_repaired = 0
    for bvid in sorted(bvids):
        # 读取所有日文件
        all_records = []
        for f in sorted(os.listdir(VIDEO_DATA_DIR)):
            m = re.match(rf'{re.escape(bvid)}_(\d{{4}}-\d{{2}}-\d{{2}})\.json$', f)
            if not m:
                continue
            fpath = os.path.join(VIDEO_DATA_DIR, f)
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    day_data = json.load(fh)
                if isinstance(day_data, list):
                    all_records.extend(day_data)
            except (json.JSONDecodeError, IOError) as e:
                print(f'  ⚠️ 跳过损坏文件 {f}: {e}')

        if not all_records:
            continue

        # 排序 + 去重（timestamp//3600）
        all_records.sort(key=lambda x: x.get('timestamp', 0))
        seen = {}
        for i, d in enumerate(all_records):
            hk = d.get('timestamp', 0) // 3600
            seen[hk] = i
        deduped = [all_records[i] for i in sorted(seen.values())]

        # 对比现有 _all.json
        all_file = os.path.join(VIDEO_DATA_DIR, f'{bvid}_all.json')
        existing_count = 0
        if os.path.exists(all_file):
            try:
                with open(all_file, 'r', encoding='utf-8') as fh:
                    existing = json.load(fh)
                existing_count = len(existing) if isinstance(existing, list) else 0
            except (json.JSONDecodeError, IOError):
                pass

        if len(deduped) != existing_count:
            with open(all_file, 'w', encoding='utf-8') as fh:
                json.dump(deduped, fh, ensure_ascii=False, indent=2)
            diff = len(deduped) - existing_count
            print(f'  ✅ {bvid}: {existing_count} -> {len(deduped)} 条（恢复 {diff} 条）')
            total_repaired += 1
        else:
            print(f'  -- {bvid}: {existing_count} 条（无需修复）')

    print(f'\n修复完成，共重建 {total_repaired} 个 _all.json')


if __name__ == '__main__':
    repair_all()
