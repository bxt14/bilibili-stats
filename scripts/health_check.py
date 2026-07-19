#!/usr/bin/env python3
"""看板健康检查：检查cron采集是否正常运行"""
import os
import sys
import json
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

BASE_DIR = config.BASE_DIR
DATA_DIR = config.DATA_DIR

DAILY_CRON_HOUR = 8  # 日级cron在8:30运行，8点前不应期待当天数据

def check_hourly_log():
    """检查小时级日志是否在2小时内有更新"""
    log_path = os.path.join(config.LOGS_DIR, "hourly_sync.log")
    if not os.path.exists(log_path):
        return False, "hourly_sync.log 不存在"
    mtime = os.path.getmtime(log_path)
    age_hours = (time.time() - mtime) / 3600
    if age_hours > 2:
        return False, f"hourly_sync.log 已 {age_hours:.1f} 小时未更新（最后修改: {datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')}）"
    return True, f"hourly_sync.log 正常（{age_hours:.1f}小时前更新）"

def check_douyin_data():
    """检查活跃抖音视频数据是否按频率正常更新（hourly:2h阈值, daily:26h阈值）"""
    douyin_dir = os.path.join(DATA_DIR, "douyin_videos")
    if not os.path.exists(douyin_dir):
        return False, "douyin_videos 目录不存在"
    
    cutoff = datetime.now() - timedelta(days=30)
    now = datetime.now()
    active_files = []  # (fpath, threshold_hours)
    
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
                    # 根据发布时间判断频率级别（与fetch_douyin_batch.py一致）
                    days_since_publish = (now - publish_dt).total_seconds() / 86400
                    if days_since_publish <= 3:
                        threshold = 2  # hourly级别（每小时采集）
                    elif days_since_publish <= 14:
                        threshold = 6  # every4h级别（每4小时采集，留2h余量）
                    else:
                        threshold = 26  # daily级别（每天8:30采集，留余量）
                    active_files.append((fpath, threshold))
        except (json.JSONDecodeError, KeyError):
            continue
    
    if not active_files:
        return True, "无活跃抖音视频（30天内），跳过检查"
    
    stale_files = []
    for fpath, threshold in active_files:
        mtime = os.path.getmtime(fpath)
        age_hours = (time.time() - mtime) / 3600
        if age_hours > threshold:
            stale_files.append((os.path.basename(fpath), age_hours))
    
    if len(stale_files) == len(active_files):
        return False, f"所有活跃抖音视频均超阈值未更新: {[f'{f[0]}({f[1]:.1f}h)' for f in stale_files[:3]]}"
    if stale_files:
        return False, f"部分活跃抖音视频超阈值未更新: {[f'{f[0]}({f[1]:.1f}h)' for f in stale_files[:3]]}"
    return True, "抖音数据正常更新中"

def check_douyin_fans():
    """检查抖音粉丝数据是否近期更新（每日cron同步一次，24小时内应有更新）"""
    info_file = os.path.join(DATA_DIR, 'douyin_info.json')
    growth_file = os.path.join(DATA_DIR, 'douyin_growth.json')
    
    if not os.path.exists(info_file):
        return False, 'douyin_info.json 不存在'
    
    try:
        with open(info_file, 'r', encoding='utf-8') as f:
            info = json.load(f)
        
        update_time_str = info.get('update_time', '')
        if not update_time_str:
            return False, 'douyin_info.json 缺少 update_time 字段'
        
        # 解析更新时间 "YYYY-MM-DD HH:MM"
        update_dt = datetime.strptime(update_time_str, '%Y-%m-%d %H:%M')
        age_hours = (datetime.now() - update_dt).total_seconds() / 3600
        
        if age_hours > 26:  # 留2小时余量（daily cron 8:30运行）
            return False, f'抖音粉丝数据已 {age_hours:.1f} 小时未更新（最后更新: {update_time_str}）'
        
        # 同时检查 growth.json 最新记录的日期
        if os.path.exists(growth_file):
            with open(growth_file, 'r', encoding='utf-8') as f:
                growth = json.load(f)
            if growth:
                latest_date = growth[-1].get('date', '')
                today = datetime.now().strftime('%Y-%m-%d')
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                if latest_date not in (today, yesterday):
                    return False, f'抖音增长数据停在 {latest_date}（预期 {yesterday} 或 {today}）'
        
        fans = info.get('fans', 0)
        return True, f'抖音粉丝数据正常（{fans:,} 粉丝，更新于 {update_time_str}）'
    
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        return False, f'douyin_info.json 解析失败: {e}'

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
        ("抖音视频", check_douyin_data),
        ("抖音粉丝", check_douyin_fans),
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
