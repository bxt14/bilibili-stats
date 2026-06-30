#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音视频批量采集脚本 - 供crontab调用
扫描 data/douyin_videos/ 目录，对发布30天内的视频执行采集
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DOUYIN_VIDEOS_DIR = os.path.join(DATA_DIR, 'douyin_videos')
FETCH_SCRIPT = os.path.join(BASE_DIR, 'scripts', 'fetch_douyin_video.py')


def get_active_videos(max_age_days=30):
    """获取发布时间在max_age_days天内的抖音视频列表"""
    active = []
    if not os.path.exists(DOUYIN_VIDEOS_DIR):
        return active
    
    cutoff = datetime.now() - timedelta(days=max_age_days)
    
    for fname in os.listdir(DOUYIN_VIDEOS_DIR):
        if not fname.endswith('.json'):
            continue
        filepath = os.path.join(DOUYIN_VIDEOS_DIR, fname)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            video_id = data.get('video_id', fname.replace('.json', ''))
            publish_time = data.get('publish_time', '')
            source_url = data.get('source_url', '')
            title = data.get('title', '')
            
            # 跳过无有效数据的视频：顶层likes=0时也检查history
            history = data.get('history', [])
            has_valid_data = data.get('likes', 0) > 0 or (history and any(r.get('likes', 0) > 0 for r in history[-3:]))
            if not video_id or not has_valid_data:
                continue
            
            # 判断是否在采集窗口内
            # 优先用publish_time，其次用history最早时间，最后用文件修改时间
            effective_pub_time = publish_time
            if not effective_pub_time and history:
                first_fetch = history[0].get('fetch_time', '')
                if first_fetch:
                    effective_pub_time = first_fetch[:16].replace('-', '').replace(' ', '').replace(':', '')[:12]
                    # 直接用history最早时间的前一天作为近似发布时间
                    try:
                        first_dt = datetime.strptime(first_fetch[:16], '%Y-%m-%d %H:%M')
                        pub_dt = first_dt - timedelta(hours=1)  # 近似
                    except ValueError:
                        first_dt = None
            if publish_time:
                try:
                    pub_dt = datetime.strptime(publish_time, '%Y-%m-%d %H:%M')
                    if pub_dt < cutoff:
                        continue
                except ValueError:
                    pass
            elif not publish_time and history:
                # 用history最早时间近似判断
                try:
                    first_fetch = history[0].get('fetch_time', '')[:16]
                    first_dt = datetime.strptime(first_fetch, '%Y-%m-%d %H:%M')
                    if first_dt < cutoff:
                        continue
                except (ValueError, IndexError):
                    pass
            
            # 构造URL：优先用source_url，否则用ID构造
            if source_url:
                url = source_url
            else:
                url = f'https://www.douyin.com/video/{video_id}'
            
            active.append({
                'video_id': video_id,
                'url': url,
                'title': title[:40],
                'publish_time': publish_time
            })
        except (json.JSONDecodeError, KeyError):
            continue
    
    return active


def fetch_all(active_videos):
    """逐个采集活跃视频，每个视频独立超时，避免单个卡住阻塞全部"""
    if not active_videos:
        print("无活跃抖音视频需要采集")
        return True
    
    print(f"需采集 {len(active_videos)} 个抖音视频:")
    for v in active_videos:
        print(f"  - {v['video_id']}: {v['title'] or 'N/A'} ({v['publish_time'] or 'N/A'})")
    
    success_count = 0
    fail_count = 0
    
    for v in active_videos:
        try:
            cmd = [sys.executable, FETCH_SCRIPT, v['url']]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            if result.returncode == 0:
                success_count += 1
            else:
                fail_count += 1
                print(f"  ⚠️ 视频 {v['video_id']} 采集失败")
        except subprocess.TimeoutExpired:
            fail_count += 1
            print(f"  ⚠️ 视频 {v['video_id']} 采集超时(90s)，跳过")
    
    print(f"采集完成！成功 {success_count}/{len(active_videos)} 个")
    return fail_count == 0


def main():
    print(f"\n{'='*60}")
    print(f"抖音视频批量采集: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    active = get_active_videos()
    print(f"活跃视频数: {len(active)}")
    
    success = fetch_all(active)
    
    if success:
        print("\n✅ 抖音视频批量采集完成")
    else:
        print("\n⚠️ 部分视频采集失败")
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
