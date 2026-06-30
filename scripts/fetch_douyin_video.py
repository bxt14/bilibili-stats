#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音视频数据采集脚本 - 通过Chrome CDP连接真实浏览器
绕过抖音反爬检测，采集视频数据（标题、点赞、评论、收藏、转发）

使用方式：
  1. 确保云电脑上Chrome已启动CDP：google-chrome --remote-debugging-port=9222 ...
  2. python3 fetch_douyin_video.py <视频链接或ID>

或者脚本会自动管理Chrome生命周期。
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("需要安装playwright: pip3 install playwright && playwright install chromium")
    sys.exit(1)


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DOUYIN_VIDEOS_DIR = os.path.join(DATA_DIR, 'douyin_videos')

CDP_PORT = 9222
CHROME_USER_DATA = '/tmp/chrome-douyin-profile'
DISPLAY_NUM = 99


def parse_count(text):
    """解析抖音的数量文本，如 '12.7万' -> 127000, '1236' -> 1236"""
    if not text:
        return 0
    text = text.strip().replace(',', '').replace(' ', '')
    try:
        if '亿' in text:
            return int(float(text.replace('亿', '')) * 100000000)
        elif '万' in text:
            return int(float(text.replace('万', '')) * 10000)
        else:
            return int(text)
    except (ValueError, TypeError):
        return 0


def ensure_chrome_running():
    """确保Chrome CDP实例正在运行"""
    import requests
    try:
        resp = requests.get(f'http://localhost:{CDP_PORT}/json/version', timeout=3)
        if resp.status_code == 200:
            print(f"  Chrome CDP已在运行 (端口{CDP_PORT})")
            return False  # 不需要关闭
    except:
        pass
    
    # 启动Chrome
    print(f"  启动Chrome CDP (端口{CDP_PORT})...")
    
    # 确保虚拟显示器运行
    result = subprocess.run(['pgrep', '-f', f'Xvfb :{DISPLAY_NUM}'], capture_output=True)
    if result.returncode != 0:
        subprocess.Popen(['Xvfb', f':{DISPLAY_NUM}', '-screen', '0', '1920x1080x24', '-ac'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    
    # 启动Chrome
    chrome_cmd = [
        'google-chrome',
        f'--remote-debugging-port={CDP_PORT}',
        '--no-first-run',
        '--no-default-browser-check',
        f'--user-data-dir={CHROME_USER_DATA}',
        '--disable-blink-features=AutomationControlled',
        '--no-sandbox',
        '--headless=new',
        'about:blank'
    ]
    
    env = os.environ.copy()
    env['DISPLAY'] = f':{DISPLAY_NUM}'
    
    subprocess.Popen(chrome_cmd, env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 等待CDP就绪
    for _ in range(15):
        try:
            resp = requests.get(f'http://localhost:{CDP_PORT}/json/version', timeout=2)
            if resp.status_code == 200:
                print(f"  Chrome CDP就绪")
                return True
        except:
            pass
        time.sleep(1)
    
    raise RuntimeError("Chrome CDP启动超时")


def resolve_short_url(url):
    """解析短链接，获取实际视频ID和长链接"""
    # 如果已经是长链接，直接提取ID
    match = re.search(r'/video/(\d+)', url)
    if match:
        return match.group(1), url
    
    # 尝试requests解析短链接
    import requests
    try:
        resp = requests.head(url, allow_redirects=True, timeout=10,
                           headers={'User-Agent': 'Mozilla/5.0'})
        final_url = resp.url
        match = re.search(r'/video/(\d+)', final_url)
        if match:
            return match.group(1), final_url
    except:
        pass
    
    return None, url


def fetch_douyin_video(video_url):
    """
    通过Chrome CDP采集抖音视频数据
    
    Args:
        video_url: 抖音视频链接（短链接或长链接）
    
    Returns:
        dict: 视频数据
    """
    video_id, resolved_url = resolve_short_url(video_url)
    
    if not resolved_url.startswith('https://www.douyin.com'):
        resolved_url = video_url
    
    print(f"  采集: {video_url}")
    if video_id:
        print(f"  视频ID: {video_id}")
    
    # 确保Chrome运行
    ensure_chrome_running()
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f'http://localhost:{CDP_PORT}')
        
        # 使用已有context或创建新的
        if browser.contexts:
            context = browser.contexts[0]
        else:
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
            )
        
        page = context.new_page()
        
        # Anti-detection
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            delete navigator.__proto__.webdriver;
        """)
        
        try:
            # 先访问首页获取cookies
            page.goto('https://www.douyin.com/', wait_until='domcontentloaded', timeout=20000)
            time.sleep(3)
            
            # 访问视频页
            page.goto(resolved_url, wait_until='domcontentloaded', timeout=30000)
            time.sleep(8)
            
            # 获取最终URL中的视频ID
            final_url = page.url
            if not video_id:
                match = re.search(r'/video/(\d+)', final_url)
                if match:
                    video_id = match.group(1)
            
            # 提取视频数据
            video_data = _parse_video_page(page, video_id)
            video_data['video_id'] = video_id or ''
            video_data['source_url'] = video_url
            video_data['fetch_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            return video_data
            
        except Exception as e:
            print(f"  采集失败: {e}")
            return None
        finally:
            page.close()


def _parse_video_page(page, video_id):
    """从视频页面提取数据"""
    video_data = {
        'video_id': video_id or '',
        'title': '',
        'author': '',
        'likes': 0,
        'comments': 0,
        'collects': 0,
        'shares': 0,
        'publish_time': '',
    }
    
    # 方法1: 从RENDER_DATA提取（最准确）
    try:
        render_data = page.evaluate('''() => {
            const el = document.getElementById('RENDER_DATA');
            if (el) return decodeURIComponent(el.textContent);
            return null;
        }''')
        
        if render_data:
            data = json.loads(render_data)
            dump = json.dumps(data)
            
            # 查找awemeDetail
            if 'awemeDetail' in dump:
                aweme = _find_in_json(data, 'awemeDetail')
                if aweme:
                    stats = aweme.get('statistics', {})
                    author = aweme.get('authorInfo', {})
                    video_data['title'] = aweme.get('desc', '')
                    video_data['author'] = author.get('nickname', '')
                    video_data['likes'] = stats.get('diggCount', 0)
                    video_data['comments'] = stats.get('commentCount', 0)
                    video_data['collects'] = stats.get('collectCount', 0)
                    video_data['shares'] = stats.get('shareCount', 0)
                    video_data['plays'] = stats.get('playCount', 0)
                    create_ts = aweme.get('createTime', 0)
                    if create_ts:
                        video_data['publish_time'] = datetime.fromtimestamp(int(create_ts)).strftime('%Y-%m-%d %H:%M')
                    return video_data
    except Exception as e:
        print(f"  RENDER_DATA解析失败: {e}")
    
    # 方法2: 从页面DOM文本提取（失败时重试最多2次）
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            text = page.inner_text('body', timeout=30000)
            video_data = _parse_from_text(text, video_data)
            break
        except Exception as e:
            if attempt < max_retries:
                print(f"  DOM解析失败(第{attempt+1}次)，等待5秒后重试...")
                time.sleep(5)
                try:
                    page.reload(wait_until='domcontentloaded', timeout=20000)
                    time.sleep(5)
                except:
                    pass
            else:
                print(f"  DOM解析失败(已重试{max_retries}次): {e}")
    
    return video_data


def _find_in_json(data, key, depth=0):
    """递归查找JSON中的key"""
    if depth > 5:
        return None
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for v in data.values():
            result = _find_in_json(v, key, depth + 1)
            if result:
                return result
    return None


def _parse_from_text(text, video_data):
    """从页面文本提取视频数据（备用方案）"""
    lines = text.split('\n')
    
    # 查找标题行（包含 "|" 且有话题标签）
    for i, line in enumerate(lines):
        if '|' in line and ('#' in line or '集' in line.split('|')[0]):
            # 可能是标题
            if len(line) > 10 and len(line) < 200:
                video_data['title'] = line.strip()
                break
    
    # 如果没找到标题，找包含"集"的行
    if not video_data['title']:
        for line in lines:
            if re.match(r'第\d+集', line):
                video_data['title'] = line.strip()
                break
    
    # 如果还没找到标题，找包含#话题标签且长度合理的行
    if not video_data['title']:
        for line in lines:
            stripped = line.strip()
            if '#' in stripped and len(stripped) > 10 and len(stripped) < 200:
                video_data['title'] = stripped
                break
    
    # 查找作者
    for i, line in enumerate(lines):
        if line.strip() == '毕导':
            video_data['author'] = '毕导'
            break
    
    # 查找互动数据 - 标题后面紧跟的数字
    if video_data['title']:
        title_idx = text.find(video_data['title'])
        if title_idx >= 0:
            after_title = text[title_idx + len(video_data['title']):title_idx + len(video_data['title']) + 200]
            nums = re.findall(r'[\d.]+万?|\d+', after_title)
            # 标题后前4个数字通常是：点赞、评论、收藏、转发
            nums_parsed = []
            for n in nums[:4]:
                nums_parsed.append(parse_count(n))
            
            if len(nums_parsed) >= 4:
                video_data['likes'] = nums_parsed[0]
                video_data['comments'] = nums_parsed[1]
                video_data['collects'] = nums_parsed[2]
                video_data['shares'] = nums_parsed[3]
            elif len(nums_parsed) >= 1:
                video_data['likes'] = nums_parsed[0]
    
    # 查找发布时间
    pub_match = re.search(r'发布时间：(\d{4}-\d{2}-\d{2}[\s]\d{2}:\d{2})', text)
    if pub_match:
        video_data['publish_time'] = pub_match.group(1)
    
    return video_data


def save_video_data(video_data):
    """保存视频数据到文件"""
    if not video_data or not video_data.get('video_id'):
        print("  无有效数据，跳过保存")
        return
    
    os.makedirs(DOUYIN_VIDEOS_DIR, exist_ok=True)
    
    video_id = video_data['video_id']
    filepath = os.path.join(DOUYIN_VIDEOS_DIR, f'{video_id}.json')
    
    # 如果已有数据，追加历史记录
    history = []
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            existing = json.load(f)
            history = existing.get('history', [])
    
    # 添加当前记录到历史
    record = {
        'fetch_time': video_data['fetch_time'],
        'likes': video_data.get('likes', 0),
        'comments': video_data.get('comments', 0),
        'collects': video_data.get('collects', 0),
        'shares': video_data.get('shares', 0),
        'plays': video_data.get('plays', 0),
    }
    
    # 数据校验：如果所有关键指标都是0，且历史数据不为空，说明采集失败，跳过保存
    if record['likes'] == 0 and record['comments'] == 0 and record['collects'] == 0 and record['shares'] == 0:
        if history and any(r.get('likes', 0) > 0 for r in history[-3:]):
            print(f"  ⚠️ 采集数据全为0，疑似页面未加载完成，跳过此条记录")
            # 不覆盖已有顶层数据，只保留history不变
            return
    
    history.append(record)
    
    # 更新视频数据
    video_data['history'] = history
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(video_data, f, ensure_ascii=False, indent=2)
    
    print(f"  已保存: {filepath}")
    print(f"  标题: {video_data.get('title', 'N/A')}")
    print(f"  点赞: {video_data.get('likes', 0):,} | 评论: {video_data.get('comments', 0):,} | 收藏: {video_data.get('collects', 0):,} | 转发: {video_data.get('shares', 0):,}")


def fetch_batch(video_urls):
    """批量采集多个视频"""
    results = []
    for url in video_urls:
        data = fetch_douyin_video(url)
        if data:
            save_video_data(data)
            results.append(data)
        time.sleep(3)  # 采集间隔
    return results


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("用法: python3 fetch_douyin_video.py <视频链接或ID> [更多链接...]")
        print("示例: python3 fetch_douyin_video.py https://v.douyin.com/kuJKhYj_CzY/")
        print("      python3 fetch_douyin_video.py 7639283518668836115")
        sys.exit(1)
    
    urls = sys.argv[1:]
    
    # 处理纯数字的视频ID
    processed_urls = []
    for u in urls:
        if re.match(r'^\d+$', u):
            processed_urls.append(f'https://www.douyin.com/video/{u}')
        else:
            processed_urls.append(u)
    
    print(f"\n开始采集 {len(processed_urls)} 个抖音视频...")
    
    results = fetch_batch(processed_urls)
    
    print(f"\n采集完成！成功 {len(results)}/{len(processed_urls)} 个")


if __name__ == '__main__':
    main()
