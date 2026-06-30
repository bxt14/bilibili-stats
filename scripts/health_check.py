#!/usr/bin/env python3
"""看板健康检查：检查cron采集是否正常运行"""
import os
import json
import time
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

DAILY_CRON_HOUR = 8  # 日级cron在8:30运行，8点前不应期待当天数据

def check_hourly_log():
    """检查小时级日志是否在2小时内有更新"""
    log_path = "/tmp/hourly_sync.log"
    if not os.path.exists(log_path):
        return False, "hourly_sync.log 不存在"
    mtime = os.path.getmtime(log_path)
    age_hours = (time.time() - mtime) / 3600
    if age_hours > 2:
        return False, f"hourly_sync.log 已 {age_hours:.1f} 小时未更新（最后修改: {datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')}）"
    return True, f"hourly_sync.log 正常（{age_hours:.1f}小时前更新）"

def check_douyin_data():
    """检查活跃抖音视频数据是否在2小时内有更新（仅检查发布30天内的视频）"""
    douyin_dir = os.path.join(DATA_DIR, "douyin_videos")
    if not os.path.exists(douyin_dir):
        return False, "douyin_videos 目录不存在"
    
    cutoff = datetime.now() - timedelta(days=30)
    active_files = []
    
    for f in os.listdir(douyin_dir):
        if not f.endswith('.json'):
            continue
        fpath = os.path.join(douyin_dir, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            publish_time_str = data.get('publish_time', '')
            if publish_time_str:
                for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                    try:
                        publish_dt = datetime.strptime(publish_time_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    publish_dt = None
                if publish_dt and publish_dt > cutoff:
                    active_files.append(fpath)
        except (json.JSONDecodeError, KeyError):
            continue
    
    if not active_files:
        return True, "无活跃抖音视频（30天内），跳过检查"
    
    stale_files = []
    for fpath in active_files:
        mtime = os.path.getmtime(fpath)
        age_hours = (time.time() - mtime) / 3600
        if age_hours > 2:
            stale_files.append((os.path.basename(fpath), age_hours))
    
    if len(stale_files) == len(active_files):
        return False, f"所有活跃抖音视频均超过2小时未更新: {[f'{f[0]}({f[1]:.1f}h)' for f in stale_files[:3]]}"
    if stale_files:
        return False, f"部分活跃抖音视频超过2小时未更新: {[f'{f[0]}({f[1]:.1f}h)' for f in stale_files[:3]]}"
    return True, "抖音数据正常更新中"

def check_bilibili_data():
    """检查B站视频数据是否有近期更新"""
    videos_dir = os.path.join(DATA_DIR, "videos")
    if not os.path.exists(videos_dir):
        return False, "videos 目录不存在"
    
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # 日级cron在8:30运行，8点前不应期待当天数据，检查昨天的即可
    if now.hour < DAILY_CRON_HOUR:
        has_data = any(yesterday in f for f in os.listdir(videos_dir))
        if not has_data:
            return False, f"昨天({yesterday})没有B站视频数据（日级cron未运行前检查昨日数据）"
        return True, "B站数据正常（日级cron运行前，检查昨日数据）"
    else:
        has_today_data = any(today in f for f in os.listdir(videos_dir))
        if not has_today_data:
            return False, f"今天({today})没有B站视频数据"
        return True, "B站数据正常"

if __name__ == "__main__":
    checks = [
        ("小时级采集", check_hourly_log),
        ("抖音数据", check_douyin_data),
        ("B站数据", check_bilibili_data),
    ]
    
    all_ok = True
    for name, check_fn in checks:
        ok, msg = check_fn()
        status = "✅" if ok else "❌"
        print(f"{status} {name}: {msg}")
        if not ok:
            all_ok = False
    
    exit(0 if all_ok else 1)
