#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音视频数据采集脚本 - 移动端分享页 API 方案

通过 iesdouyin 移动端分享页获取视频数据（标题、点赞、评论、收藏、转发），
不依赖 Chrome/Playwright，纯 HTTP + 正则/JSON 解析。

采集策略：
  1. 请求 https://www.iesdouyin.com/share/video/{video_id}/ （iPhone UA）
  2. 优先从 _ROUTER_DATA JSON 中提取 videoInfoRes.item_list[0]
  3. JSON 无数据时降级为正则提取（兼容旧版/不同IP返回的HTML格式）
  4. 全0值时自动重试最多3次，间隔2秒

使用方式：
  python3 fetch_douyin_video.py <视频链接或ID> [更多链接...]
  示例:
    python3 fetch_douyin_video.py https://v.douyin.com/xxxxx/
    python3 fetch_douyin_video.py 7639283518668836115
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

# ============ 移动端 API 配置 ============
MOBILE_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 '
    'Mobile/15E148 Safari/604.1'
)

SHARE_URL_TEMPLATE = 'https://www.iesdouyin.com/share/video/{video_id}/'

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
    """解析短链接，获取实际视频ID。

    Returns:
        tuple: (video_id, resolved_url)
    """
    # 如果已经是长链接，直接提取ID
    match = re.search(r'/video/(\d+)', url)
    if match:
        return match.group(1), url

    # 纯数字ID
    if re.match(r'^\d+$', url):
        return url, SHARE_URL_TEMPLATE.format(video_id=url)

    # 尝试解析短链接（跟随重定向）
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': MOBILE_UA},
            method='HEAD',
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            final_url = resp.url
            match = re.search(r'/video/(\d+)', final_url)
            if match:
                return match.group(1), final_url
    except Exception:
        pass

    # GET 方式兜底（某些短链不支持HEAD）
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': MOBILE_UA},
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            final_url = resp.url
            match = re.search(r'/video/(\d+)', final_url)
            if match:
                return match.group(1), final_url
    except Exception:
        pass

    return None, url


def _fetch_html(video_id):
    """请求移动端分享页，返回 HTML 文本。"""
    url = SHARE_URL_TEMPLATE.format(video_id=video_id)
    req = urllib.request.Request(url, headers={
        'User-Agent': MOBILE_UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read().decode('utf-8', errors='replace')


def _extract_router_data(html):
    """从 HTML 中提取 window._ROUTER_DATA JSON 对象。"""
    marker = 'window._ROUTER_DATA'
    idx = html.find(marker)
    if idx < 0:
        return None

    eq_pos = html.find('=', idx)
    if eq_pos < 0:
        return None

    start = eq_pos + 1
    # 跳过空白
    while start < len(html) and html[start] in ' \t\r\n':
        start += 1
    if start >= len(html) or html[start] != '{':
        return None

    # 括号匹配提取完整 JSON
    depth = 0
    end = start
    in_string = False
    escape = False
    for i in range(start, len(html)):
        ch = html[i]
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    try:
        return json.loads(html[start:end].strip().rstrip(';'))
    except (json.JSONDecodeError, ValueError):
        return None


def _parse_from_router_data(router_data, video_id):
    """从 _ROUTER_DATA JSON 中提取视频数据（新版SSR路径）。"""
    video_data = {
        'video_id': video_id or '',
        'title': '',
        'author': '',
        'likes': 0,
        'comments': 0,
        'collects': 0,
        'shares': 0,
        'plays': 0,
        'publish_time': '',
    }

    try:
        page_data = (
            router_data.get('loaderData', {})
            .get('video_(id)/page', {})
        )
        if not page_data:
            return None

        # 路径1: videoInfoRes.item_list[0]（标准SSR格式）
        video_info_res = page_data.get('videoInfoRes')
        if not video_info_res:
            return None

        item_list = video_info_res.get('item_list', [])
        if not item_list:
            # 有些版本在 filter_list 中
            filter_list = video_info_res.get('filter_list', [])
            if filter_list:
                item_list = [f.get('aweme_info', {}) for f in filter_list if f.get('aweme_info')]

        if not item_list:
            return None

        item = item_list[0]
        stats = item.get('statistics', item.get('stats', {}))

        video_data['title'] = item.get('desc', '')
        author_info = item.get('author', item.get('authorInfo', {}))
        video_data['author'] = author_info.get('nickname', '')
        video_data['likes'] = int(stats.get('digg_count', stats.get('diggCount', 0)) or 0)
        video_data['comments'] = int(stats.get('comment_count', stats.get('commentCount', 0)) or 0)
        video_data['collects'] = int(stats.get('collect_count', stats.get('collectCount', 0)) or 0)
        video_data['shares'] = int(stats.get('share_count', stats.get('shareCount', 0)) or 0)
        video_data['plays'] = int(stats.get('play_count', stats.get('playCount', 0)) or 0)

        create_ts = item.get('create_time', item.get('createTime', 0))
        if create_ts:
            video_data['publish_time'] = datetime.fromtimestamp(
                int(create_ts)
            ).strftime('%Y-%m-%d %H:%M')

        vid = item.get('aweme_id', '')
        if vid:
            video_data['video_id'] = str(vid)

        return video_data

    except Exception as e:
        print(f"  _ROUTER_DATA 解析异常: {e}")
        return None


def _parse_from_regex(html, video_id):
    """从 HTML 中正则提取视频数据（降级方案，兼容旧格式）。"""
    video_data = {
        'video_id': video_id or '',
        'title': '',
        'author': '',
        'likes': 0,
        'comments': 0,
        'collects': 0,
        'shares': 0,
        'plays': 0,
        'publish_time': '',
    }

    patterns = {
        'likes': r'digg_count["\s:]+(\d+)',
        'comments': r'comment_count["\s:]+(\d+)',
        'shares': r'share_count["\s:]+(\d+)',
        'collects': r'collect_count["\s:]+(\d+)',
        'plays': r'play_count["\s:]+(\d+)',
    }

    for field, pattern in patterns.items():
        m = re.search(pattern, html)
        if m:
            try:
                video_data[field] = int(m.group(1))
            except (ValueError, IndexError):
                pass

    # 标题
    m = re.search(r'"desc":"([^"]{5,200})"', html)
    if m:
        # 处理转义字符
        title = m.group(1)
        title = title.replace('\\n', '\n').replace('\\"', '"').replace('\\/', '/')
        video_data['title'] = title

    # 作者
    m = re.search(r'"nickname":"([^"]+)"', html)
    if m:
        video_data['author'] = m.group(1).replace('\\"', '"')

    # 发布时间
    m = re.search(r'create_time["\s:]+(\d+)', html)
    if m:
        try:
            ts = int(m.group(1))
            video_data['publish_time'] = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
        except (ValueError, OSError):
            pass

    return video_data


def fetch_douyin_video(video_url):
    """通过移动端分享页 API 采集抖音视频数据。

    Args:
        video_url: 抖音视频链接（短链接、长链接或纯数字ID）

    Returns:
        dict: 视频数据，失败返回 None
    """
    video_id, resolved_url = resolve_short_url(video_url)

    if not video_id:
        print(f"  无法解析视频ID: {video_url}")
        return None

    # 如果传入的是短链且没有解析到 iesdouyin URL，构造标准URL
    if not resolved_url or 'iesdouyin.com' not in resolved_url:
        resolved_url = SHARE_URL_TEMPLATE.format(video_id=video_id)

    print(f"  采集: {video_url}")
    print(f"  视频ID: {video_id}")

    video_data = None
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            html = _fetch_html(video_id)

            # 优先从 _ROUTER_DATA JSON 解析
            router_data = _extract_router_data(html)
            if router_data:
                parsed = _parse_from_router_data(router_data, video_id)
                if parsed and (parsed.get('likes', 0) > 0 or parsed.get('title')):
                    video_data = parsed
                    break

            # 降级：正则提取
            parsed = _parse_from_regex(html, video_id)
            if parsed and parsed.get('likes', 0) > 0:
                video_data = parsed
                break

            # 如果拿到了标题但数据全0，可能是页面未加载完整，重试
            if parsed and parsed.get('title'):
                video_data = parsed
                if attempt < MAX_RETRIES:
                    print(f"  数据全0，第{attempt}次重试（间隔{RETRY_INTERVAL}s）...")
                    time.sleep(RETRY_INTERVAL)
                    continue
                # 重试用完，接受当前数据
                break

            # 没拿到任何数据
            if attempt < MAX_RETRIES:
                print(f"  未获取到数据，第{attempt}次重试（间隔{RETRY_INTERVAL}s）...")
                time.sleep(RETRY_INTERVAL)
            else:
                print(f"  {MAX_RETRIES}次尝试后仍未获取到数据（页面可能已改版或视频不可用）")

        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
            print(f"  HTTP错误: {last_error}")
            if e.code == 404:
                # 视频不存在，不重试
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

    # 补全元数据
    if not video_data.get('video_id'):
        video_data['video_id'] = video_id
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
    print(f"\n开始采集 {len(urls)} 个抖音视频（移动端API方案，无需Chrome）...")

    results = fetch_batch(urls)

    print(f"\n采集完成！成功 {len(results)}/{len(urls)} 个")


if __name__ == '__main__':
    main()
