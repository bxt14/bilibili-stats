#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音视频批量采集脚本 - 单进程优化版

优化点：
- 单次CDP连接，共享浏览器上下文，仅首次访问首页获取cookie
- 不再spawn subprocess，在单进程内用Playwright连接CDP
- 超时自动重试，失败后重启Chrome再试一次
- 按视频年龄分级采集频率（新视频每小时，中等每4小时，老视频每天）
- 每个视频采集后关闭标签页，防止堆积

使用方式：
  python3 fetch_douyin_batch.py [--mode hourly|daily]
    hourly: 按分级频率（默认）- 新视频每小时，中等每4小时，老视频每天
    daily:  全部采集
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

# 从 fetch_douyin_video.py 导入共享函数
sys.path.insert(0, os.path.dirname(__file__))
import config
from fetch_douyin_video import (
    parse_count, _parse_video_page, save_video_data,
    ensure_chrome_running, CDP_PORT
)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("需要安装playwright: pip3 install playwright && playwright install chromium")
    sys.exit(1)

BASE_DIR = config.BASE_DIR
DATA_DIR = config.DATA_DIR
DOUYIN_VIDEOS_DIR = config.DOUYIN_VIDEOS_DIR

# 频率分级阈值（统一从config读取）
HOURLY_MAX_AGE_DAYS = config.DOUYIN_HOURLY_MAX_AGE_DAYS
EVERY4H_MAX_AGE_DAYS = config.DOUYIN_EVERY4H_MAX_AGE_DAYS
DAILY_MAX_AGE_DAYS = config.DOUYIN_DAILY_MAX_AGE_DAYS

# 页面等待时间
VIDEO_PAGE_WAIT_SECONDS = 6   # 视频页JS渲染等待（从8s降到6s）
HOMEPAGE_WAIT_SECONDS = 3     # 首页等待
PAGE_LOAD_TIMEOUT = 25000     # 页面加载超时(ms)
HOMEPAGE_LOAD_TIMEOUT = 20000 # 首页加载超时(ms)

# User-Agent
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'

# Anti-detection JS
ANTI_DETECT_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
delete navigator.__proto__.webdriver;
"""


def get_active_videos(max_age_days=30):
    """获取需要采集的活跃视频列表，按频率分级

    Returns:
        dict: {'hourly': [...], 'every4h': [...], 'daily': [...]}
    """
    active = {'hourly': [], 'every4h': [], 'daily': []}

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

            # 跳过无有效数据的视频
            history = data.get('history', [])
            has_valid_data = data.get('likes', 0) > 0 or (
                history and any(r.get('likes', 0) > 0 for r in history[-3:]))
            if not video_id or not has_valid_data:
                continue

            # 确定发布时间
            pub_dt = _parse_publish_time(publish_time, history)
            if not pub_dt or pub_dt < cutoff:
                continue

            url = source_url if source_url else f'https://www.douyin.com/video/{video_id}'

            entry = {
                'video_id': video_id,
                'url': url,
                'title': title[:40],
                'publish_time': publish_time,
            }

            age_days = (datetime.now() - pub_dt).days
            if age_days <= HOURLY_MAX_AGE_DAYS:
                active['hourly'].append(entry)
            elif age_days <= EVERY4H_MAX_AGE_DAYS:
                active['every4h'].append(entry)
            else:
                active['daily'].append(entry)

        except (json.JSONDecodeError, KeyError):
            continue

    return active


def _parse_publish_time(publish_time, history):
    """从发布时间字符串或历史记录推断发布时间"""
    if publish_time:
        for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.strptime(publish_time, fmt)
            except ValueError:
                continue

    if history:
        try:
            first_fetch = history[0].get('fetch_time', '')[:16]
            return datetime.strptime(first_fetch, '%Y-%m-%d %H:%M') - timedelta(hours=1)
        except (ValueError, IndexError):
            pass

    return None


def select_videos_for_collection(active_videos, mode='hourly'):
    """根据采集模式选择要采集的视频

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


def _new_page_with_anti_detect(context):
    """创建一个带反检测脚本的新页面"""
    page = context.new_page()
    page.add_init_script(ANTI_DETECT_JS)
    return page


def _close_page_safely(page):
    """安全关闭页面"""
    try:
        page.close()
    except Exception:
        pass


def visit_homepage(context):
    """访问抖音首页获取cookie（仅调用一次）"""
    print("  访问首页获取cookie...")
    page = _new_page_with_anti_detect(context)
    try:
        page.goto('https://www.douyin.com/', wait_until='domcontentloaded',
                  timeout=HOMEPAGE_LOAD_TIMEOUT)
        time.sleep(HOMEPAGE_WAIT_SECONDS)
    except Exception as e:
        print(f"  首页访问失败(非致命): {e}")
    finally:
        _close_page_safely(page)


def get_or_create_context(browser):
    """获取或创建浏览器上下文"""
    if browser.contexts:
        return browser.contexts[0]
    return browser.new_context(
        user_agent=USER_AGENT,
        viewport={'width': 1920, 'height': 1080},
        locale='zh-CN',
    )


def fetch_single_video(context, video_url, video_id):
    """在已有context中采集单个视频（跳过首页访问）

    Args:
        context: Playwright BrowserContext
        video_url: 视频URL
        video_id: 视频ID

    Returns:
        dict: 视频数据，失败返回None
    """
    page = _new_page_with_anti_detect(context)

    try:
        # 直接访问视频页，不访问首页
        page.goto(video_url, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)
        time.sleep(VIDEO_PAGE_WAIT_SECONDS)

        # 从最终URL提取视频ID
        if not video_id:
            match = re.search(r'/video/(\d+)', page.url)
            if match:
                video_id = match.group(1)

        video_data = _parse_video_page(page, video_id)
        video_data['video_id'] = video_id or ''
        video_data['source_url'] = video_url
        video_data['fetch_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        return video_data

    except Exception as e:
        print(f"  采集失败: {e}")
        return None
    finally:
        _close_page_safely(page)


def close_all_non_blank_tabs():
    """通过CDP协议关闭所有非about:blank的标签页"""
    try:
        import requests
        tabs = requests.get(f'http://localhost:{CDP_PORT}/json/list', timeout=5).json()
        for tab in tabs:
            if tab.get('type') == 'page' and tab.get('url') != 'about:blank':
                try:
                    requests.get(
                        f'http://localhost:{CDP_PORT}/json/close/{tab["id"]}',
                        timeout=3)
                except Exception:
                    pass
    except Exception:
        pass


def do_batch(videos_to_collect):
    """执行一次批量采集（单进程，共享上下文）

    Args:
        videos_to_collect: 要采集的视频列表

    Returns:
        tuple: (success_count, failed_videos)
    """
    success_count = 0
    failed_videos = []

    ensure_chrome_running()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f'http://localhost:{CDP_PORT}')
        context = get_or_create_context(browser)

        # 首次访问首页获取cookie
        visit_homepage(context)

        # 逐个采集
        total = len(videos_to_collect)
        for i, v in enumerate(videos_to_collect, 1):
            print(f"\n  [{i}/{total}] 采集: {v['video_id']} - {v['title'] or 'N/A'}")
            print(f"    URL: {v['url']}")

            try:
                data = fetch_single_video(context, v['url'], v['video_id'])
                if data and data.get('likes', 0) > 0:
                    save_video_data(data)
                    success_count += 1
                    print(f"    OK 成功 (点赞:{data.get('likes',0):,})")
                else:
                    print(f"    X 数据无效（疑似验证码或页面未加载）")
                    failed_videos.append(v)
            except Exception as e:
                print(f"    X 异常: {e}")
                failed_videos.append(v)

            # 采集间隔，避免触发反爬
            if i < total:
                time.sleep(2)

    return success_count, failed_videos


def restart_chrome():
    """重启Chrome CDP实例"""
    print("  重启Chrome...")
    subprocess.run(['pkill', '-f', 'chrome-douyin-profile'], capture_output=True)
    time.sleep(3)
    ensure_chrome_running()
    print("  Chrome已重启")


def fetch_all_batch(videos_to_collect):
    """批量采集，失败自动重试一次

    Args:
        videos_to_collect: 要采集的视频列表

    Returns:
        bool: 是否全部成功
    """
    if not videos_to_collect:
        print("无抖音视频需要采集")
        return True

    total = len(videos_to_collect)
    print(f"\n需采集 {total} 个抖音视频:")
    for v in videos_to_collect:
        print(f"  - {v['video_id']}: {v['title'] or 'N/A'} ({v['publish_time'] or 'N/A'})")

    # 首次尝试
    print(f"\n--- 第1次尝试 ---")
    success_count, failed_videos = do_batch(videos_to_collect)

    # 重试失败的视频
    if failed_videos:
        print(f"\n! {len(failed_videos)} 个视频失败，重启Chrome后重试...")
        restart_chrome()

        print(f"\n--- 第2次尝试（重试 {len(failed_videos)} 个） ---")
        retry_success, retry_failed = do_batch(failed_videos)
        success_count += retry_success

        if retry_failed:
            for v in retry_failed:
                print(f"  X 最终失败: {v['video_id']}")
    else:
        # 成功后清理残留标签页
        close_all_non_blank_tabs()

    print(f"\n采集完成！成功 {success_count}/{total} 个")
    return success_count == total


def parse_args():
    """解析命令行参数

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
    print(f"模式: {mode}")
    print(f"{'='*60}")

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

    success = fetch_all_batch(to_collect)

    if success:
        print("\nOK 抖音视频批量采集完成")
    else:
        print("\n! 部分视频采集失败")

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
