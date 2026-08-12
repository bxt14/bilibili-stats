#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音视频批量采集脚本 - 移动端分享页 API 方案

通过 iesdouyin 移动端分享页批量采集视频数据，不依赖 Chrome/Playwright。
核心采集逻辑复用 fetch_douyin_video.py 中的函数。

特性：
- 按视频年龄分级采集频率（新视频每小时，中等每4小时，老视频每天）
- 全0值自动重试3次（每次间隔2秒），视频间间隔1秒避免限流
- 单视频失败不中断整个流程
- IP级风控时熔断2小时，避免加重封锁

使用方式：
  python3 fetch_douyin_batch.py [--mode hourly|daily]
    hourly: 按分级频率（默认）- 新视频每小时，中等每4小时，老视频每天
    daily:  全部采集
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

# 从 fetch_douyin_video.py 导入共享函数
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from fetch_douyin_video import (
    fetch_douyin_video,
    save_video_data,
    COLLECT_INTERVAL,
)

BASE_DIR = config.BASE_DIR
DATA_DIR = config.DATA_DIR
DOUYIN_VIDEOS_DIR = config.DOUYIN_VIDEOS_DIR

# 频率分级阈值（统一从config读取）
HOURLY_MAX_AGE_DAYS = config.DOUYIN_HOURLY_MAX_AGE_DAYS
EVERY4H_MAX_AGE_DAYS = config.DOUYIN_EVERY4H_MAX_AGE_DAYS
DAILY_MAX_AGE_DAYS = config.DOUYIN_DAILY_MAX_AGE_DAYS

# ============ 熔断机制 ============
CIRCUIT_BREAKER_FILE = os.path.join(config.LOGS_DIR, 'douyin_circuit_open_until')
CIRCUIT_BREAKER_SECONDS = 2 * 3600  # 熔断时长2小时


def circuit_is_open():
    """检查熔断器是否处于打开状态（应跳过采集）"""
    try:
        if os.path.exists(CIRCUIT_BREAKER_FILE):
            with open(CIRCUIT_BREAKER_FILE, 'r') as f:
                until = float(f.read().strip())
            remaining = until - time.time()
            if remaining > 0:
                print(f"熔断器打开中（剩余 {remaining/60:.0f} 分钟），跳过本次抖音采集")
                return True
            else:
                os.remove(CIRCUIT_BREAKER_FILE)
    except (ValueError, IOError):
        pass
    return False


def circuit_open():
    """打开熔断器"""
    os.makedirs(os.path.dirname(CIRCUIT_BREAKER_FILE), exist_ok=True)
    with open(CIRCUIT_BREAKER_FILE, 'w') as f:
        f.write(str(time.time() + CIRCUIT_BREAKER_SECONDS))
    print(f"⚠️ 熔断器已打开，{CIRCUIT_BREAKER_SECONDS//3600}小时内暂停抖音采集")


def circuit_close():
    """采集成功，关闭熔断器"""
    if os.path.exists(CIRCUIT_BREAKER_FILE):
        os.remove(CIRCUIT_BREAKER_FILE)


def get_active_videos(max_age_days=30):
    """获取需要采集的活跃视频列表，按频率分级。

    扫描 douyin_videos/ 目录下所有 JSON 文件，同时也从
    all_2026_videos.json 中补充标记为 douyin_only 的视频。

    Returns:
        dict: {'hourly': [...], 'every4h': [...], 'daily': [...]}
    """
    active = {'hourly': [], 'every4h': [], 'daily': []}
    seen_ids = set()

    def _classify_video(video_id, title, publish_time, source_url):
        """将视频按年龄分级加入 active 列表。"""
        if not video_id or video_id in seen_ids:
            return
        seen_ids.add(video_id)

        pub_dt = _parse_publish_time(publish_time)
        if not pub_dt:
            # 无法确定发布时间的视频归入 daily（保守策略）
            active['daily'].append({
                'video_id': video_id,
                'url': source_url or f'https://www.iesdouyin.com/share/video/{video_id}/',
                'title': (title or '')[:40],
                'publish_time': publish_time or '',
            })
            return

        cutoff = datetime.now() - timedelta(days=max_age_days)
        if pub_dt < cutoff:
            return

        url = source_url if source_url else f'https://www.iesdouyin.com/share/video/{video_id}/'
        entry = {
            'video_id': video_id,
            'url': url,
            'title': (title or '')[:40],
            'publish_time': publish_time,
        }

        age_days = (datetime.now() - pub_dt).days
        if age_days <= HOURLY_MAX_AGE_DAYS:
            active['hourly'].append(entry)
        elif age_days <= EVERY4H_MAX_AGE_DAYS:
            active['every4h'].append(entry)
        else:
            active['daily'].append(entry)

    # 1. 扫描已有的 douyin_videos/ JSON 文件
    if os.path.exists(DOUYIN_VIDEOS_DIR):
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

                # 跳过无有效数据的视频
                history = data.get('history', [])
                has_valid_data = data.get('likes', 0) > 0 or (
                    history and any(r.get('likes', 0) > 0 for r in history[-3:]))
                if not video_id or not has_valid_data:
                    continue

                _classify_video(video_id, title, publish_time, source_url)

            except (json.JSONDecodeError, KeyError, IOError):
                continue

    # 2. 从 all_2026_videos.json 补充 douyin_only 视频
    all_videos_path = os.path.join(DATA_DIR, 'all_2026_videos.json')
    if os.path.exists(all_videos_path):
        try:
            with open(all_videos_path, 'r', encoding='utf-8') as f:
                all_videos = json.load(f)

            # 支持列表或字典格式
            if isinstance(all_videos, dict):
                video_list = all_videos.get('videos', [])
            elif isinstance(all_videos, list):
                video_list = all_videos
            else:
                video_list = []

            for v in video_list:
                if not isinstance(v, dict):
                    continue
                # 只采集标记为 douyin_only 或包含 douyin_id 的视频
                douyin_id = v.get('douyin_id', '')
                source = v.get('source', '')
                if source == 'douyin_only' or (douyin_id and source != 'bilibili'):
                    video_id = str(douyin_id or v.get('id', ''))
                    if not video_id:
                        continue
                    title = v.get('title', '')
                    publish_time = v.get('publish_time', '')
                    source_url = f'https://www.iesdouyin.com/share/video/{video_id}/'
                    _classify_video(video_id, title, publish_time, source_url)

        except (json.JSONDecodeError, IOError):
            pass

    return active


def _parse_publish_time(publish_time):
    """从发布时间字符串推断 datetime，支持多种格式。"""
    if not publish_time:
        return None

    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(publish_time, fmt)
        except ValueError:
            continue

    # 尝试时间戳
    try:
        ts = int(publish_time)
        if ts > 1e12:
            ts = ts // 1000
        return datetime.fromtimestamp(ts)
    except (ValueError, OSError):
        pass

    return None


def select_videos_for_collection(active_videos, mode='hourly'):
    """根据采集模式选择要采集的视频。

    hourly模式:
      - 新视频(<=3天): 每次都采集
      - 中等视频(3-14天): 仅在0,4,8,12,16,20点采集
      - 老视频(14-30天): 不采集（由daily模式负责）

    daily模式:
      - 所有活跃视频都采集
    """
    to_collect = list(active_videos['hourly'])  # 新视频总是采集

    if mode == 'hourly':
        current_hour = datetime.now().hour
        # 每4小时采集中等年龄视频 (0,4,8,12,16,20点)
        if current_hour % 4 == 0:
            to_collect.extend(active_videos['every4h'])
    elif mode == 'daily':
        to_collect.extend(active_videos['every4h'])
        to_collect.extend(active_videos['daily'])

    return to_collect


def do_batch(videos_to_collect):
    """执行批量采集（移动端API，无Chrome依赖）。

    Args:
        videos_to_collect: 要采集的视频列表

    Returns:
        tuple: (success_count, failed_count)
    """
    success_count = 0
    failed_count = 0
    total = len(videos_to_collect)

    for i, v in enumerate(videos_to_collect, 1):
        print(f"\n  [{i}/{total}] 采集: {v['video_id']} - {v.get('title', '') or 'N/A'}")
        print(f"    URL: {v['url']}")

        try:
            data = fetch_douyin_video(v['url'])
            if data and data.get('likes', 0) > 0:
                save_video_data(data)
                success_count += 1
                print(f"    OK 成功 (点赞:{data.get('likes', 0):,})")
            elif data and data.get('title'):
                # 拿到了标题但数据全0，仍然保存（save_video_data内部会判断是否跳过）
                save_video_data(data)
                if data.get('likes', 0) > 0:
                    success_count += 1
                else:
                    failed_count += 1
                    print(f"    X 数据全0（移动端API未返回统计数据，已记录日志）")
            else:
                failed_count += 1
                print(f"    X 未能获取视频数据")
        except Exception as e:
            failed_count += 1
            print(f"    X 异常: {e}")

        # 视频间间隔，避免限流
        if i < total:
            time.sleep(COLLECT_INTERVAL)

    return success_count, failed_count


def parse_args():
    """解析命令行参数。

    支持格式:
      --mode hourly
      --mode daily
      hourly
      daily
    """
    mode = 'hourly'
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--mode' and i + 1 < len(args):
            mode = args[i + 1]
            i += 2
        elif args[i] in ('hourly', 'daily'):
            mode = args[i]
            i += 1
        else:
            i += 1

    if mode not in ('hourly', 'daily'):
        print(f"未知模式: {mode}，使用默认 hourly")
        mode = 'hourly'

    return mode


def main():
    mode = parse_args()

    print(f"\n{'='*60}")
    print(f"抖音视频批量采集: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"模式: {mode}（移动端API方案，无需Chrome）")
    print(f"{'='*60}")

    # 熔断检查
    if circuit_is_open():
        return 0

    active = get_active_videos()
    total_active = sum(len(v) for v in active.values())
    print(f"活跃视频数: {total_active}")
    if total_active > 0:
        print(f"  新视频(<={HOURLY_MAX_AGE_DAYS}天): {len(active['hourly'])}个")
        print(f"  中等视频(<={EVERY4H_MAX_AGE_DAYS}天): {len(active['every4h'])}个")
        print(f"  老视频(<={DAILY_MAX_AGE_DAYS}天): {len(active['daily'])}个")

    to_collect = select_videos_for_collection(active, mode)

    if not to_collect:
        print("本次无需采集（按分级频率，当前时段无待采集视频）")
        return 0

    print(f"\n本次需采集: {len(to_collect)}个")

    success_count, failed_count = do_batch(to_collect)

    print(f"\n{'='*60}")
    print(f"采集完成！成功 {success_count}/{len(to_collect)} 个", end='')
    if failed_count:
        print(f"，失败 {failed_count} 个")
    else:
        print()

    # 全部失败：判定为IP级风控，打开熔断器
    if success_count == 0 and len(to_collect) > 0:
        circuit_open()
        return 1
    elif success_count > 0:
        # 有成功就关闭熔断
        circuit_close()

    # 部分失败不返回错误码（不中断流程）
    return 0


if __name__ == '__main__':
    sys.exit(main())
