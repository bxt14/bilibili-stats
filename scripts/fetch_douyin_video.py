#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音视频数据采集脚本 - 抖音 App API 方案

通过抖音 App 私有 API (api.amemv.com) 获取视频数据（标题、点赞、评论、收藏、转发），
不依赖 Chrome/Playwright，不依赖签名（feed 接口无需 a_bogus），纯 HTTP + JSON 解析。

采集策略：
  1. 请求 https://api.amemv.com/aweme/v1/feed/?aweme_id={video_id}
  2. 从 aweme_list 中匹配目标视频，提取 statistics
  3. 失败自动重试最多3次，间隔2秒

使用方式：
  python3 fetch_douyin_video.py <视频链接或ID> [更多链接...]
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

BASE_DIR = config.BASE_DIR
DATA_DIR = config.DATA_DIR
DOUYIN_VIDEOS_DIR = config.DOUYIN_VIDEOS_DIR

# ============ 抖音 App API 配置 ============
# 使用 Android 抖音 App 的 UA，feed 接口无需签名即可返回数据
APP_UA = (
    'com.ss.android.ugc.aweme/2901 (Linux; U; Android 13; zh_CN; '
    'Pixel 7; Build/TQ3A.230705.001; '
    'Cronet/TTNetVersion:b4d74d15 2023-06-13 '
    'QuicVersion:0144d358 2023-05-29)'
)

FEED_API = 'https://api.amemv.com/aweme/v1/feed/?aweme_id={video_id}'

# 重试配置
MAX_RETRIES = 3
RETRY_INTERVAL = 2  # 秒
REQUEST_TIMEOUT = 15  # 秒

# 视频间采集间隔（秒）
COLLECT_INTERVAL = 1


def parse_count(text):
    """解析数量文本，如 '12.7万' -> 127000, '1236' -> 1236"""
    if not text:
        return 0
    text = str(text).strip().replace(',', '').replace(' ', '')
    try:
        if '亿' in text:
            return int(float(text.replace('亿', '')) * 100000000)
        elif '万' in text:
            return int(float(text.replace('万', '')) * 10000)
        else:
            return int(text)
    except (ValueError, TypeError):
        return 0


def resolve_short_url(url):
    """解析短链接，获取实际视频ID。"""
    # 如果已经是长链接，直接提取ID
    match = re.search(r'/video/(\d+)', url)
    if match:
        return match.group(1)

    # 纯数字ID
    if re.match(r'^\d+$', url):
        return url

    # 尝试解析短链接（跟随重定向）
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': APP_UA},
            method='HEAD',
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            final_url = resp.url
            match = re.search(r'/video/(\d+)', final_url)
            if match:
                return match.group(1)
    except Exception:
        pass

    # GET 方式兜底
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': APP_UA},
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            final_url = resp.url
            match = re.search(r'/video/(\d+)', final_url)
            if match:
                return match.group(1)
    except Exception:
        pass

    return None


def _fetch_feed(video_id):
    """请求抖音 App feed API，返回 JSON 数据。"""
    url = FEED_API.format(video_id=video_id)
    req = urllib.request.Request(url, headers={
        'User-Agent': APP_UA,
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _parse_feed(data, video_id):
    """从 feed API 响应中提取目标视频数据。"""
    video_data = {
        'video_id': video_id,
        'title': '',
        'author': '',
        'likes': 0,
        'comments': 0,
        'collects': 0,
        'shares': 0,
        'plays': 0,
        'publish_time': '',
    }

    aweme_list = data.get('aweme_list', [])
    if not aweme_list:
        return None

    # 优先匹配目标 aweme_id
    aweme = None
    for item in aweme_list:
        if str(item.get('aweme_id', '')) == str(video_id):
            aweme = item
            break
    if not aweme:
        aweme = aweme_list[0]

    stats = aweme.get('statistics', {})
    video_data['likes'] = int(stats.get('digg_count', 0) or 0)
    video_data['comments'] = int(stats.get('comment_count', 0) or 0)
    video_data['collects'] = int(stats.get('collect_count', 0) or 0)
    video_data['shares'] = int(stats.get('share_count', 0) or 0)
    video_data['plays'] = int(stats.get('play_count', 0) or 0)

    video_data['title'] = aweme.get('desc', '')
    author_info = aweme.get('author', {})
    video_data['author'] = author_info.get('nickname', '')

    create_ts = aweme.get('create_time', 0)
    if create_ts:
        try:
            video_data['publish_time'] = datetime.fromtimestamp(
                int(create_ts)
            ).strftime('%Y-%m-%d %H:%M')
        except (ValueError, OSError):
            pass

    aweme_id = aweme.get('aweme_id', '')
    if aweme_id:
        video_data['video_id'] = str(aweme_id)

    return video_data


def fetch_douyin_video(video_url):
    """通过抖音 App API 采集抖音视频数据。

    Args:
        video_url: 抖音视频链接（短链接、长链接或纯数字ID）

    Returns:
        dict: 视频数据，失败返回 None
    """
    video_id = resolve_short_url(video_url)

    if not video_id:
        print(f"  无法解析视频ID: {video_url}")
        return None

    print(f"  采集: {video_url}")
    print(f"  视频ID: {video_id}")

    video_data = None
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = _fetch_feed(video_id)
            parsed = _parse_feed(data, video_id)

            if parsed and parsed.get('likes', 0) > 0:
                video_data = parsed
                break

            if parsed and parsed.get('title'):
                # 有标题但点赞为0，可能是新视频或接口异常
                video_data = parsed
                if attempt < MAX_RETRIES:
                    print(f"  数据异常(likes=0)，第{attempt}次重试（间隔{RETRY_INTERVAL}s）...")
                    time.sleep(RETRY_INTERVAL)
                    continue
                break

            if attempt < MAX_RETRIES:
                print(f"  未获取到数据，第{attempt}次重试（间隔{RETRY_INTERVAL}s）...")
                time.sleep(RETRY_INTERVAL)
            else:
                print(f"  {MAX_RETRIES}次尝试后仍未获取到数据（接口可能变更或视频不可用）")

        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
            print(f"  HTTP错误: {last_error}")
            if e.code == 404:
                break
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_INTERVAL)
        except Exception as e:
            last_error = str(e)
            print(f"  请求异常(第{attempt}次): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_INTERVAL)

    if not video_data:
        if last_error:
            print(f"  采集失败: {last_error}")
        return None

    video_data['source_url'] = video_url
    video_data['fetch_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return video_data


def save_video_data(video_data):
    """保存视频数据到 JSON 文件，追加 history 记录。"""
    if not video_data or not video_data.get('video_id'):
        print("  无有效数据，跳过保存")
        return

    os.makedirs(DOUYIN_VIDEOS_DIR, exist_ok=True)

    video_id = video_data['video_id']
    filepath = os.path.join(DOUYIN_VIDEOS_DIR, f'{video_id}.json')

    # 如果已有数据，读取历史记录
    history = []
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                history = existing.get('history', [])
        except (json.JSONDecodeError, IOError):
            pass

    # 构建本次记录
    record = {
        'fetch_time': video_data['fetch_time'],
        'likes': video_data.get('likes', 0),
        'comments': video_data.get('comments', 0),
        'collects': video_data.get('collects', 0),
        'shares': video_data.get('shares', 0),
        'plays': video_data.get('plays', 0),
    }

    # 数据校验：全0且历史有正常数据，说明采集异常，跳过保存避免污染
    all_zero = all(record[k] == 0 for k in ('likes', 'comments', 'collects', 'shares'))
    if all_zero and history and any(r.get('likes', 0) > 0 for r in history[-3:]):
        print(f"  ⚠️ 采集数据全为0，疑似获取失败，跳过此条记录（不覆盖已有数据）")
        return

    history.append(record)
    video_data['history'] = history

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(video_data, f, ensure_ascii=False, indent=2)

    print(f"  已保存: {filepath}")
    print(f"  标题: {video_data.get('title', 'N/A')[:60]}")
    print(f"  作者: {video_data.get('author', 'N/A')}")
    print(f"  点赞: {video_data.get('likes', 0):,} | "
          f"评论: {video_data.get('comments', 0):,} | "
          f"收藏: {video_data.get('collects', 0):,} | "
          f"转发: {video_data.get('shares', 0):,}")


def fetch_batch(video_urls):
    """批量采集多个视频。"""
    results = []
    for i, url in enumerate(video_urls):
        data = fetch_douyin_video(url)
        if data:
            save_video_data(data)
            results.append(data)
        if i < len(video_urls) - 1:
            time.sleep(COLLECT_INTERVAL)
    return results


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("用法: python3 fetch_douyin_video.py <视频链接或ID> [更多链接...]")
        print("示例:")
        print("  python3 fetch_douyin_video.py https://v.douyin.com/xxxxx/")
        print("  python3 fetch_douyin_video.py 7639283518668836115")
        sys.exit(1)

    urls = sys.argv[1:]
    print(f"\n开始采集 {len(urls)} 个抖音视频（App API方案，无需Chrome）...")

    results = fetch_batch(urls)

    print(f"\n采集完成！成功 {len(results)}/{len(urls)} 个")


if __name__ == '__main__':
    main()
