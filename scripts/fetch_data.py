#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站账号数据采集脚本
- 采集账号粉丝数据（每天一次）
- 采集视频详细数据：
  - 发布前5天：每小时一次
  - 发布5-30天：每天一次
  - 发布30天后：归档，不再采集
"""
import requests
import json
import time
import os
from datetime import datetime, timedelta

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Referer': 'https://www.bilibili.com'
}

# 账号配置
ACCOUNTS = {
    'bidao': {
        'uid': '254463269',
        'name': '毕导',
    },
    'erjiedao': {
        'uid': '489763089',
        'name': '毕的二阶导',
    }
}

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
VIDEO_DATA_DIR = os.path.join(DATA_DIR, 'videos')

# 从配置文件读取需要监控的视频
def load_watch_videos():
    config_file = os.path.join(DATA_DIR, 'watch_config.json')
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get('watch_videos', {})
    return {'bidao': [], 'erjiedao': []}

WATCH_VIDEOS = load_watch_videos()

# 采集策略：前5天每小时，5-30天每天，30天后归档
HIGH_FREQ_DAYS = 5
DAILY_FREQ_DAYS = 30


def fetch_account_info(uid):
    """获取账号基本信息"""
    try:
        url = f'https://api.bilibili.com/x/relation/stat?vmid={uid}'
        response = requests.get(url, headers=HEADERS, timeout=10)
        data = response.json()
        
        if data['code'] != 0:
            return None
        
        follower = data['data']['follower']
        
        url2 = f'https://api.bilibili.com/x/web-interface/card?mid={uid}&photo=true'
        response2 = requests.get(url2, headers=HEADERS, timeout=10)
        data2 = response2.json()
        
        if data2['code'] == 0:
            card = data2['data']['card']
            return {
                'uid': uid,
                'name': card['name'],
                'avatar': card['face'],
                'fans': follower,
                'sign': card['sign'],
                'level': card['level_info']['current_level']
            }
    except Exception as e:
        print(f'获取账号信息出错: {e}')
    
    return None


def fetch_video_detail(bvid):
    """获取单个视频的详细统计数据"""
    try:
        url = f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}'
        response = requests.get(url, headers=HEADERS, timeout=10)
        data = response.json()
        
        if data['code'] != 0:
            print(f'获取视频 {bvid} 失败: {data["message"]}')
            return None
        
        video_data = data['data']
        stat = video_data['stat']
        
        # 解析荣誉信息（全站排行榜、每周必看等）
        honor_info = {
            'best_rank': 0,       # 全站排行榜最高排名
            'weekly_pick': 0,     # 每周必看期数（0=未入选）
            'hot_pick': False,    # 热门收录
        }
        honor_list = video_data.get('honor_reply', {}).get('honor', [])
        for h in honor_list:
            h_type = h.get('type', 0)
            if h_type == 2:  # 每周必看
                honor_info['weekly_pick'] = h.get('weekly_recommend_num', 0)
            elif h_type == 3:  # 全站排行榜
                honor_info['best_rank'] = stat.get('his_rank', 0)
            elif h_type == 7:  # 热门收录
                honor_info['hot_pick'] = True
        
        # 如果honor_reply里没有排行榜但his_rank有值
        if honor_info['best_rank'] == 0 and stat.get('his_rank', 0) > 0:
            honor_info['best_rank'] = stat['his_rank']
        
        return {
            'bvid': bvid,
            'aid': video_data['aid'],
            'title': video_data['title'],
            'cover': video_data['pic'],
            'created': video_data['pubdate'],  # 发布时间戳
            'duration': video_data['duration'],
            'owner_name': video_data['owner']['name'],
            'owner_mid': video_data['owner']['mid'],
            # 统计数据
            'view': stat['view'],
            'danmaku': stat['danmaku'],
            'reply': stat['reply'],
            'favorite': stat['favorite'],
            'coin': stat['coin'],
            'share': stat['share'],
            'like': stat['like'],
            'now_rank': stat.get('now_rank', 0),
            'his_rank': stat.get('his_rank', 0),
            # 荣誉信息
            'honor': honor_info,
        }
    except Exception as e:
        print(f'获取视频详情出错 {bvid}: {e}')
    
    return None


def save_json(data, filepath):
    """保存JSON数据"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json_safe(filepath, default=None):
    """安全加载JSON文件"""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f'加载文件出错 {filepath}: {e}')
    return default if default is not None else []


def record_video_data(bvid, video_info):
    """记录单个视频的时刻数据"""
    now = datetime.now()
    timestamp = int(now.timestamp())
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M')
    
    # 创建这个视频的数据记录
    record = {
        'timestamp': timestamp,
        'date': date_str,
        'time': time_str,
        'view': video_info['view'],
        'like': video_info['like'],
        'coin': video_info['coin'],
        'favorite': video_info['favorite'],
        'reply': video_info['reply'],
        'danmaku': video_info['danmaku'],
        'share': video_info['share'],
    }
    
    # 保存/更新视频基本信息和荣誉
    meta_file = os.path.join(VIDEO_DATA_DIR, f'{bvid}_meta.json')
    meta = load_json_safe(meta_file, {})
    
    if not meta:
        meta = {
            'bvid': bvid,
            'title': video_info['title'],
            'cover': video_info['cover'],
            'created': video_info['created'],
            'owner_name': video_info['owner_name'],
            'owner_mid': video_info['owner_mid'],
            'duration': video_info['duration'],
        }
        print(f'  已创建视频元数据: {video_info["title"]}')
    
    # 每次都更新荣誉信息（排名可能随时间变化）
    honor = video_info.get('honor', {})
    if honor:
        existing_honor = meta.get('honor', {})
        # 取最高排名（数字越小排名越高）
        if honor.get('best_rank', 0) > 0:
            if existing_honor.get('best_rank', 0) == 0 or honor['best_rank'] < existing_honor['best_rank']:
                meta['honor'] = honor
                print(f'  🏆 更新荣誉: 全站最高第{honor["best_rank"]}名' + 
                      (f', 每周必看第{honor["weekly_pick"]}期' if honor.get('weekly_pick', 0) > 0 else ''))
            elif honor.get('weekly_pick', 0) > 0 and existing_honor.get('weekly_pick', 0) == 0:
                meta['honor'] = honor
                print(f'  🏆 更新荣誉: 每周必看第{honor["weekly_pick"]}期')
        elif honor.get('weekly_pick', 0) > 0 and existing_honor.get('weekly_pick', 0) == 0:
            meta['honor'] = honor
            print(f'  🏆 更新荣誉: 每周必看第{honor["weekly_pick"]}期')
    
    save_json(meta, meta_file)
    
    # 追加到当日数据文件
    day_file = os.path.join(VIDEO_DATA_DIR, f'{bvid}_{date_str}.json')
    day_data = load_json_safe(day_file, [])
    day_data.append(record)
    # 去重：同一小时只保留最后一个
    seen_h = {}
    for i, d in enumerate(day_data):
        t = d.get('time', '')
        hk = t.split(':')[0] if ':' in t else t
        seen_h[hk] = i
    if len(seen_h) < len(day_data):
        day_data = [day_data[i] for i in sorted(seen_h.values())]
    save_json(day_data, day_file)
    
    # 更新总文件：直接追加，避免每次全量重建
    all_file = os.path.join(VIDEO_DATA_DIR, f'{bvid}_all.json')
    all_data = load_json_safe(all_file, [])
    if not isinstance(all_data, list):
        all_data = []
    all_data.append(record)
    all_data.sort(key=lambda x: x.get('timestamp', 0))
    # 去重：同一小时只保留最后一个数据点
    seen_hours = {}
    for i, d in enumerate(all_data):
        t = d.get('time', '')
        hour_key = t.split(':')[0] if ':' in t else t
        seen_hours[hour_key] = i
    if len(seen_hours) < len(all_data):
        all_data = [all_data[i] for i in sorted(seen_hours.values())]
    save_json(all_data, all_file)
    
    return record


def get_video_freq(pub_timestamp):
    """
    根据发布时间判断采集频率
    返回: 'hourly' / 'daily' / 'archived'
    """
    days = (int(time.time()) - pub_timestamp) / 86400
    if days <= HIGH_FREQ_DAYS:
        return 'hourly'
    elif days <= DAILY_FREQ_DAYS:
        return 'daily'
    else:
        return 'archived'


def fetch_bilibili_account(uid):
    """从B站API获取账号粉丝数和获赞数"""
    # 获取粉丝数
    resp = requests.get(
        f'https://api.bilibili.com/x/relation/stat?vmid={uid}',
        headers=HEADERS, timeout=10
    )
    fans_data = resp.json()
    if fans_data.get('code') != 0:
        raise RuntimeError(f"获取粉丝数失败: {fans_data.get('message', 'unknown')}")
    fans = fans_data['data']['follower']
    
    # 获取获赞数
    resp2 = requests.get(
        f'https://api.bilibili.com/x/web-interface/card?mid={uid}&photo=true',
        headers=HEADERS, timeout=10
    )
    card_data = resp2.json()
    if card_data.get('code') != 0:
        raise RuntimeError(f"获取卡片数据失败: {card_data.get('message', 'unknown')}")
    likes = card_data['data']['like_num']
    
    return int(fans), int(likes)


def fetch_account_fans():
    """采集账号粉丝和赞数数据：B站API采集 → 写飞书 → 更新看板"""
    print("\n" + "=" * 60)
    print(f"更新账号数据: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    import subprocess
    
    # 1. 从B站API直接采集数据
    bidao_fans, bidao_likes = fetch_bilibili_account('254463269')
    erjie_fans, erjie_likes = fetch_bilibili_account('489763089')
    
    # 2. 从本地growth_all.json获取昨天数据，计算涨粉（不依赖飞书查询）
    yesterday_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    fans_add_bidao = 0
    fans_add_erjie = 0
    likes_add_bidao = 0
    likes_add_erjie = 0
    
    # 优先从本地growth数据计算涨粉和涨赞
    all_file = os.path.join(DATA_DIR, 'growth_all.json')
    growth_data = load_json_safe(all_file, [])
    
    yesterday_record = None
    for r in reversed(growth_data):
        if isinstance(r, dict) and r.get('date') == yesterday_date:
            yesterday_record = r
            break
    
    if yesterday_record:
        y_bidao_fans = yesterday_record.get('accounts', {}).get('bidao', {}).get('fans', 0)
        y_erjie_fans = yesterday_record.get('accounts', {}).get('erjiedao', {}).get('fans', 0)
        y_bidao_likes = yesterday_record.get('accounts', {}).get('bidao', {}).get('likes', 0)
        y_erjie_likes = yesterday_record.get('accounts', {}).get('erjiedao', {}).get('likes', 0)
        if y_bidao_fans:
            fans_add_bidao = bidao_fans - y_bidao_fans
        if y_erjie_fans:
            fans_add_erjie = erjie_fans - y_erjie_fans
        if y_bidao_likes:
            likes_add_bidao = bidao_likes - y_bidao_likes
        if y_erjie_likes:
            likes_add_erjie = erjie_likes - y_erjie_likes
        print(f"  对比昨日({yesterday_date})数据: 毕导粉丝={y_bidao_fans}, 二阶导粉丝={y_erjie_fans}")
    else:
        print(f"  未找到昨日({yesterday_date})本地数据，涨粉将显示为0")
    
    # 3. 写入飞书多维表格
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    feishu_json = json.dumps({
        "日期": now_str,
        "B站粉丝": bidao_fans,
        "B站获赞": bidao_likes,
        "二阶导B站粉丝": erjie_fans,
        "二阶导B站获赞": erjie_likes,
        "昨日涨粉": fans_add_bidao,
        "昨日小号涨粉": fans_add_erjie
    }, ensure_ascii=False)
    
    feishu_result = subprocess.run([
        'lark-cli', 'base', '+record-upsert', '--as', 'user',
        '--base-token', 'CZwHbS7d2alENJsYoJicXOLgnIe',
        '--table-id', 'tblMJtSgWy5EFZrH',
        '--json', feishu_json
    ], capture_output=True, text=True)
    
    try:
        feishu_resp = json.loads(feishu_result.stdout)
        if feishu_resp.get('ok'):
            print(f"\n飞书写入成功 ✅")
        else:
            print(f"\n飞书写入失败: {feishu_resp}")
    except:
        print(f"\n飞书写入结果: {feishu_result.stdout[:200]}")
    
    # 4. 保存看板数据
    bidao_info = {
        'name': '毕导',
        'fans': bidao_fans,
        'likes': bidao_likes,
        'fans_add': fans_add_bidao,
        'likes_add': likes_add_bidao
    }
    save_json(bidao_info, os.path.join(DATA_DIR, 'bidao_info.json'))
    
    erjie_info = {
        'name': '毕的二阶导',
        'fans': erjie_fans,
        'likes': erjie_likes,
        'fans_add': fans_add_erjie,
        'likes_add': likes_add_erjie
    }
    save_json(erjie_info, os.path.join(DATA_DIR, 'erjiedao_info.json'))
    
    print(f"\n毕导:")
    print(f"  粉丝: {bidao_fans:,} (+{fans_add_bidao:,})")
    print(f"  获赞: {bidao_likes:,} (+{likes_add_bidao:,})")
    
    print(f"\n毕的二阶导:")
    print(f"  粉丝: {erjie_fans:,} (+{fans_add_erjie:,})")
    print(f"  获赞: {erjie_likes:,} (+{likes_add_erjie:,})")
    
    # 5. 保存增长数据到growth文件
    today_str = datetime.now().strftime('%Y-%m-%d')
    growth_record = {
        'timestamp': int(time.time()),
        'date': today_str,
        'time': datetime.now().strftime('%H:%M'),
        'accounts': {
            'bidao': {
                'name': '毕导',
                'fans': bidao_fans,
                'likes': bidao_likes
            },
            'erjiedao': {
                'name': '毕的二阶导',
                'fans': erjie_fans,
                'likes': erjie_likes
            }
        }
    }
    
    day_file = os.path.join(DATA_DIR, f'growth_{today_str}.json')
    day_data = load_json_safe(day_file, [])
    if not isinstance(day_data, list):
        day_data = []
    # 去重：如果今天已有记录则覆盖
    day_data = [r for r in day_data if isinstance(r, dict) and r.get('date') != today_str]
    day_data.append(growth_record)
    save_json(day_data, day_file)
    
    # 更新总文件
    all_file = os.path.join(DATA_DIR, 'growth_all.json')
    all_data = load_json_safe(all_file, [])
    if not isinstance(all_data, list):
        all_data = []
    # 去重：移除今天的旧记录
    all_data = [r for r in all_data if isinstance(r, dict) and r.get('date') != today_str]
    all_data.append(growth_record)
    all_data.sort(key=lambda x: x.get('timestamp', 0))
    save_json(all_data, all_file)
    
    print(f"\n粉丝数据已保存，共 {len(all_data)} 条历史记录")


def fetch_douyin_data():
    """从飞书多维表格同步抖音粉丝历史数据"""
    import subprocess
    
    print("\n" + "=" * 60)
    print(f"同步抖音数据: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 从飞书多维表格读取抖音历史数据
    try:
        result = subprocess.run([
            'lark-cli', 'base', '+record-list',
            '--as', 'user',
            '--base-token', 'CZwHbS7d2alENJsYoJicXOLgnIe',
            '--table-id', 'tblLKeLyl0Bu65y8',
            '--limit', '200', '--format', 'json'
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            feishu_data = json.loads(result.stdout)
            records = feishu_data.get('data', {}).get('data', [])
            
            growth_list = []
            for r in records:
                # Fields: [0]null, [1]作品数, [2]关注数, [3]点赞数, [4]签名, [5]用户ID, [6]粉丝数, [7]链接, [8]昵称, [9]提取时间
                date_str = r[9][:10] if r[9] else None
                if date_str and r[6]:
                    growth_list.append({
                        'date': date_str,
                        'fans': int(r[6]),
                        'likes': int(r[3]),
                        'works': int(r[1])
                    })
            
            growth_list.sort(key=lambda x: x['date'])
            
            # 保存增长数据
            growth_file = os.path.join(DATA_DIR, 'douyin_growth.json')
            with open(growth_file, 'w', encoding='utf-8') as f:
                json.dump(growth_list, f, ensure_ascii=False, indent=2)
            
            # 更新douyin_info.json（最新一条）
            if growth_list:
                latest = growth_list[-1]
                prev = growth_list[-2] if len(growth_list) >= 2 else latest
                fans_add = latest['fans'] - prev['fans']
                
                info = {
                    'name': '毕导',
                    'platform': '抖音',
                    'fans': latest['fans'],
                    'likes': latest['likes'],
                    'works': latest['works'],
                    'fans_add': fans_add,
                    'update_time': datetime.now().strftime('%Y-%m-%d %H:%M')
                }
                info_file = os.path.join(DATA_DIR, 'douyin_info.json')
                with open(info_file, 'w', encoding='utf-8') as f:
                    json.dump(info, f, ensure_ascii=False, indent=2)
                
                print(f"  抖音数据同步成功: {len(growth_list)}条历史记录")
                print(f"  最新: 粉丝={latest['fans']:,}, 获赞={latest['likes']:,}")
                print(f"  昨日涨粉: {fans_add:+,}")
        else:
            print(f"  飞书读取失败: {result.stderr[:100]}")
            # 回退到本地数据
            douyin_file = os.path.join(DATA_DIR, 'douyin_info.json')
            existing = load_json_safe(douyin_file, {})
            if existing.get('fans'):
                print(f"  使用本地数据: 粉丝={existing.get('fans', 0):,}, 获赞={existing.get('likes', 0):,}")
    except Exception as e:
        print(f"  抖音数据同步异常: {e}")
        douyin_file = os.path.join(DATA_DIR, 'douyin_info.json')
        existing = load_json_safe(douyin_file, {})
        if existing.get('fans'):
            print(f"  使用本地数据: 粉丝={existing.get('fans', 0):,}, 获赞={existing.get('likes', 0):,}")



def sync_all_2026_videos():
    """同步all_2026_videos.json：确保watch_config中的视频都在索引中，并更新最新数据"""
    all_file = os.path.join(DATA_DIR, 'all_2026_videos.json')
    all_videos = load_json_safe(all_file, [])
    if not isinstance(all_videos, list):
        all_videos = []
    
    # 建立 bvid -> video 索引
    video_map = {v['bvid']: v for v in all_videos if isinstance(v, dict)}
    
    updated = False
    
    # 扫描 watch_config 中的所有视频
    for key, bvids in WATCH_VIDEOS.items():
        for bvid in bvids:
            if bvid not in video_map:
                # 新视频，从API获取信息并添加
                print(f"  发现新视频 {bvid}，正在添加到索引...")
                video_info = fetch_video_detail(bvid)
                if video_info:
                    entry = {
                        'bvid': bvid,
                        'title': video_info['title'],
                        'cover': video_info['cover'],
                        'created': video_info['created'],
                        'created_str': datetime.fromtimestamp(video_info['created']).strftime('%Y-%m-%d'),
                        'owner': video_info['owner_name'],
                        'owner_mid': video_info['owner_mid'],
                        'duration': video_info['duration'],
                        'view': video_info['view'],
                        'like': video_info['like'],
                        'coin': video_info['coin'],
                        'favorite': video_info['favorite'],
                        'reply': video_info['reply'],
                        'danmaku': video_info['danmaku'],
                        'share': video_info['share'],
                        'is_monitoring': True,
                        'douyin_video_id': '',
                        'honor': video_info.get('honor', {'best_rank': 0, 'weekly_pick': 0}),
                    }
                    all_videos.insert(0, entry)
                    video_map[bvid] = entry
                    updated = True
                    print(f"  已添加: {video_info['title']}")
    
    # 自动更新 is_monitoring 状态：超过30天的视频自动归档
    now = time.time()
    for v in all_videos:
        if not isinstance(v, dict):
            continue
        days = (now - v.get('created', 0)) / 86400
        should_monitor = days <= DAILY_FREQ_DAYS  # DAILY_FREQ_DAYS = 30
        if v.get('is_monitoring', False) != should_monitor:
            old = v.get('is_monitoring', False)
            v['is_monitoring'] = should_monitor
            updated = True
            print(f"  归档状态更新: {v['bvid']} {old} -> {should_monitor} ({days:.1f}天)")
    
    if updated:
        # 按发布时间倒序排列
        all_videos.sort(key=lambda v: v.get('created', 0), reverse=True)
        save_json(all_videos, all_file)
        print(f"  all_2026_videos.json 已更新，共 {len(all_videos)} 个视频")


def fetch_videos_data(freq_mode='hourly'):
    """
    采集视频详细数据
    freq_mode: 'hourly' - 采集前5天视频, 'daily' - 采集5-30天视频, 'all' - 采集所有未归档视频
    """
    print("\n" + "=" * 60)
    print(f"采集视频数据 ({freq_mode}): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 同步视频索引
    sync_all_2026_videos()
    
    videos_collected = []
    now_timestamp = int(time.time())
    
    for key, bvids in WATCH_VIDEOS.items():
        for bvid in bvids:
            print(f"\n正在获取: {bvid}")
            video_info = fetch_video_detail(bvid)
            
            if not video_info:
                continue
            
            # 判断采集频率
            freq = get_video_freq(video_info['created'])
            days_since_publish = (now_timestamp - video_info['created']) / 86400
            
            # 根据freq_mode过滤
            if freq == 'archived':
                print(f"  视频: {video_info['title']}")
                print(f"  发布: {days_since_publish:.1f}天前 (已归档，跳过)")
                continue
            elif freq == 'daily' and freq_mode == 'hourly':
                print(f"  视频: {video_info['title']}")
                print(f"  发布: {days_since_publish:.1f}天前 (日频，跳过小时级采集)")
                continue
            elif freq == 'hourly' and freq_mode == 'daily':
                print(f"  视频: {video_info['title']}")
                print(f"  发布: {days_since_publish:.1f}天前 (小时级，由整点任务采集)")
                continue
            
            freq_label = '每小时' if freq == 'hourly' else '每天'
            print(f"  视频: {video_info['title']}")
            print(f"  发布: {days_since_publish:.1f}天前 ({freq_label}采集)")
            print(f"  播放: {video_info['view']:,} | 点赞: {video_info['like']:,} | 投币: {video_info['coin']:,}")
            
            record = record_video_data(bvid, video_info)
            videos_collected.append({
                'bvid': bvid,
                'title': video_info['title'],
                'owner': video_info['owner_name'],
                'days_published': round(days_since_publish, 1),
                'freq': freq,
            })
    
    # 保存正在监控的视频列表
    watch_list_file = os.path.join(DATA_DIR, 'watch_videos.json')
    save_json(videos_collected, watch_list_file)
    
    print(f"\n视频采集完成，共监控 {len(videos_collected)} 个活跃视频")


def main(mode='all'):
    """
    主函数
    mode: 
      'all' - 采集粉丝+小时级视频
      'fans' - 只采集粉丝
      'videos' - 小时级视频采集
      'videos-daily' - 日频视频采集（5-30天的视频）
      'douyin' - 只同步抖音粉丝数据
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(VIDEO_DATA_DIR, exist_ok=True)
    
    if mode in ['all', 'fans']:
        fetch_account_fans()
        fetch_douyin_data()
    
    if mode in ['all', 'videos']:
        fetch_videos_data('hourly')
    
    if mode == 'videos-daily':
        fetch_videos_data('daily')
    
    if mode == 'douyin':
        fetch_douyin_data()
    
    print("\n" + "=" * 60)
    print("采集完成!")
    print("=" * 60)


if __name__ == '__main__':
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    main(mode)
