#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成B站数据看板HTML - 科技粗野主义设计风格
包含：账号粉丝趋势 + 单个视频7项数据监控
"""
import json
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
VIDEO_DATA_DIR = os.path.join(DATA_DIR, 'videos')
DOCS_DIR = os.path.join(BASE_DIR, 'docs')



def escape_html(text):
    """转义HTML特殊字符"""
    if not text:
        return ''
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

def load_json(filename):
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def format_number(num):
    if num >= 100000000:
        return f"{num/100000000:.1f}亿"
    elif num >= 10000:
        return f"{num/10000:.1f}万"
    else:
        return f"{num:,}"


def generate_html():
    # 加载账号数据
    bidao_info = load_json('bidao_info.json') or {}
    erjiedao_info = load_json('erjiedao_info.json') or {}
    douyin_info = load_json('douyin_info.json') or {}
    
    # 加载所有2026年视频
    all_videos = load_json('all_2026_videos.json') or []
    
    # 加载每个监控视频的详细数据
    video_datasets = {}
    for video in all_videos:
        if video.get('is_monitoring'):
            bvid = video['bvid']
            data_file = os.path.join(VIDEO_DATA_DIR, f'{bvid}_all.json')
            meta_file = os.path.join(VIDEO_DATA_DIR, f'{bvid}_meta.json')
            
            if os.path.exists(data_file) and os.path.exists(meta_file):
                with open(data_file, 'r', encoding='utf-8') as f:
                    video_datasets[bvid] = {'data': json.load(f)}
                with open(meta_file, 'r', encoding='utf-8') as f:
                    video_datasets[bvid]['meta'] = json.load(f)
    
    # 加载抖音视频数据
    DOUYIN_VIDEO_DIR = os.path.join(DATA_DIR, 'douyin_videos')
    douyin_datasets = {}
    for video in all_videos:
        douyin_id = video.get('douyin_video_id')
        bvid = video['bvid']
        if douyin_id:
            douyin_file = os.path.join(DOUYIN_VIDEO_DIR, f'{douyin_id}.json')
            if os.path.exists(douyin_file):
                with open(douyin_file, 'r', encoding='utf-8') as f:
                    douyin_datasets[bvid] = json.load(f)
    
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 统计今年各账号视频发布数量
    bidao_videos_count = sum(1 for v in all_videos if v['owner'] == '毕导')
    erjie_videos_count = sum(1 for v in all_videos if v['owner'] == '毕的二阶导')
    
    # 按发布时间倒序排列
    all_videos.sort(key=lambda v: v.get('created', 0), reverse=True)

    # 生成视频卡片 - 按月份分组
    month_groups = {}
    
    for video in all_videos:
        bvid = video['bvid']
        is_monitoring = video.get('is_monitoring', False)
        
        # 获取最新数据（监控中的从详细数据取，已归档的从基础数据取）
        if bvid in video_datasets and video_datasets[bvid]['data']:
            latest = video_datasets[bvid]['data'][-1]
            cover = video_datasets[bvid]['meta']['cover']
            title = escape_html(video_datasets[bvid]['meta']['title'])
        else:
            latest = video
            cover = video['cover']
            title = escape_html(video['title'])
        
        # 有历史数据的视频显示增长
        growth = ''
        if bvid in video_datasets and len(video_datasets[bvid]['data']) > 1:
            first = video_datasets[bvid]['data'][0]
            total_growth = latest['view'] - first['view']
            growth = f'<div class="growth-badge">+{format_number(total_growth)}</div>'
        
        # 抖音数据行
        douyin_stats_html = ''
        if bvid in douyin_datasets:
            dy = douyin_datasets[bvid]
            douyin_stats_html = f"""<div class="video-stats douyin-stats">
            <span class="platform-tag-douyin">抖音</span>
            <div class="stat-pill">❤ {format_number(dy['likes'])}</div>
            <div class="stat-pill">💬 {format_number(dy['comments'])}</div>
            <div class="stat-pill">⭐ {format_number(dy['collects'])}</div>
            <div class="stat-pill">🔄 {format_number(dy['shares'])}</div>
          </div>"""
        
        status_class = "monitoring" if is_monitoring else "archived"
        status_text = "LIVE" if is_monitoring else "ARCHIVED"
        
        # 荣誉标签
        honor_tags_html = ''
        honor_info = video_datasets.get(bvid, {}).get('meta', {}).get('honor') if bvid in video_datasets else None
        if not honor_info:
            # 已归档视频从published_videos.json的honor字段取
            honor_info = video.get('honor', {})
        
        honor_tags = []
        if honor_info:
            if honor_info.get('best_rank', 0) > 0:
                rank = honor_info['best_rank']
                if rank == 1:
                    honor_tags.append(f'<span class="honor-tag honor-rank-1">🏆 全站排行榜最高第1名</span>')
                elif rank <= 10:
                    honor_tags.append(f'<span class="honor-tag honor-top-10">🏆 全站排行榜最高第{rank}名</span>')
                elif rank <= 100:
                    honor_tags.append(f'<span class="honor-tag honor-top-100">全站排行榜最高第{rank}名</span>')
            if honor_info.get('weekly_pick', 0) > 0:
                week_num = honor_info['weekly_pick']
                honor_tags.append(f'<span class="honor-tag honor-weekly">📺 每周必看第{week_num}期</span>')
        if honor_tags:
            honor_tags_html = f'<div class="honor-tags">{"".join(honor_tags)}</div>'
        
        has_chart_data = bvid in video_datasets
        onclick = f'onclick="showVideoChart(\'{bvid}\')"' if has_chart_data else ''
        cursor_class = 'clickable' if has_chart_data else ''
        
        card_html = f"""
    <div class="video-card {status_class} {cursor_class}" {onclick}>
      <div class="video-status">{status_text}</div>
      <div class="video-content">
        <div class="video-thumb-wrapper">
          <img class="video-thumb" src="https://images.weserv.nl/?url={cover}&w=200&h=125&fit=cover" alt="" referrerpolicy="no-referrer">
        </div>
        <div class="video-info">
          <h3 class="video-title">{title}</h3>
          {honor_tags_html}
          <div class="video-meta">
            <span class="meta-item">{video['created_str']}</span>
            <span class="meta-item">D+{(datetime.now() - datetime.fromtimestamp(video['created'])).days}</span>
          </div>
          <div class="video-stats">
            <div class="stat-pill">▶ {format_number(latest['view'])}</div>
            <div class="stat-pill">❤ {format_number(latest['like'])}</div>
            <div class="stat-pill">🪙 {format_number(latest['coin'])}</div>
            <div class="stat-pill">⭐ {format_number(latest['favorite'])}</div>
          </div>
          {douyin_stats_html}
          {growth}
        </div>
      </div>
    </div>"""
        
        # 按月份分组
        month_key = video['created_str'][:7]  # YYYY-MM
        if month_key not in month_groups:
            month_groups[month_key] = []
        month_groups[month_key].append(card_html)
    
    # 按月份倒序排列，生成带月份标题的卡片列表
    video_cards = []
    for month_key in sorted(month_groups.keys(), reverse=True):
        month_label = month_key + ' · ' + str(len(month_groups[month_key])) + ' VIDEOS'
        video_cards.append(f'<div class="month-group">')
        video_cards.append(f'<div class="month-header">{month_key} <span class="month-count">{len(month_groups[month_key])} VIDEOS</span></div>')
        video_cards.extend(month_groups[month_key])
        video_cards.append(f'</div>')
    
    # 准备视频数据JSON给前端
    video_data_json = json.dumps(video_datasets, ensure_ascii=False)
    
    # 粉丝增长数据
    growth_data = load_json('growth_all.json') or {}
    growth_json = json.dumps(growth_data, ensure_ascii=False)
    
    # 抖音粉丝增长数据
    douyin_growth_data = load_json('douyin_growth.json') or []
    douyin_growth_json = json.dumps(douyin_growth_data, ensure_ascii=False)
    
    # 准备抖音视频详细数据JSON（按bvid索引）
    douyin_video_data = {}
    for video in all_videos:
        douyin_id = video.get('douyin_video_id')
        bvid = video['bvid']
        if douyin_id and bvid in douyin_datasets:
            douyin_video_data[bvid] = douyin_datasets[bvid]
    douyin_video_data_json = json.dumps(douyin_video_data, ensure_ascii=False)
    
    # 计算本月涨粉量
    current_month = datetime.now().strftime('%Y-%m')
    month_start_fans_bidao = None
    month_start_fans_erjie = None
    latest_fans_bidao = None
    latest_fans_erjie = None
    
    for item in growth_data:
        if item['date'].startswith(current_month) and month_start_fans_bidao is None:
            month_start_fans_bidao = item['accounts']['bidao']['fans']
            month_start_fans_erjie = item['accounts']['erjiedao']['fans']
        latest_fans_bidao = item['accounts']['bidao']['fans']
        latest_fans_erjie = item['accounts']['erjiedao']['fans']
    
    month_growth_bidao = latest_fans_bidao - month_start_fans_bidao if (latest_fans_bidao and month_start_fans_bidao) else 0
    month_growth_erjie = latest_fans_erjie - month_start_fans_erjie if (latest_fans_erjie and month_start_fans_erjie) else 0
    
    # 抖音本月涨粉
    month_start_fans_douyin = None
    latest_fans_douyin = None
    for item in douyin_growth_data:
        if item['date'].startswith(current_month) and month_start_fans_douyin is None:
            month_start_fans_douyin = item['fans']
        latest_fans_douyin = item['fans']
    month_growth_douyin = latest_fans_douyin - month_start_fans_douyin if (latest_fans_douyin and month_start_fans_douyin) else 0

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DATA DASHBOARD // BILIBILI</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Bebas+Neue&family=Noto+Sans+SC:wght@400;700;900&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
  <style>
    :root {
      --accent-1: #00ff88;
      --accent-2: #ff0066;
      --accent-3: #00d4ff;
      --dark-1: #0a0a0a;
      --dark-2: #141414;
      --dark-3: #1a1a1a;
      --grid: rgba(0, 255, 136, 0.05);
    }
    
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    
    body {
      font-family: 'Noto Sans SC', 'Space Mono', monospace;
      background: var(--dark-1);
      color: #fff;
      min-height: 100vh;
      overflow-x: hidden;
      position: relative;
    }
    
    /* 噪点纹理背景 */
    body::before {
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E");
      pointer-events: none;
      z-index: 1;
    }
    
    /* 网格背景 */
    body::after {
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background-image: 
        linear-gradient(var(--grid) 1px, transparent 1px),
        linear-gradient(90deg, var(--grid) 1px, transparent 1px);
      background-size: 50px 50px;
      pointer-events: none;
      z-index: 1;
    }
    
    .container {
      max-width: 1400px;
      margin: 0 auto;
      padding: 40px 20px;
      position: relative;
      z-index: 2;
    }
    
    /* 大标题 - 粗野主义风格 */
    .hero-header {
      position: relative;
      margin-bottom: 60px;
      padding: 40px 0;
      border-bottom: 3px solid var(--accent-1);
    }
    
    .hero-header h1 {
      font-family: 'Bebas Neue', sans-serif;
      font-size: clamp(4rem, 12vw, 8rem);
      font-weight: 400;
      letter-spacing: -0.02em;
      line-height: 0.9;
      background: linear-gradient(135deg, var(--accent-1), var(--accent-3));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      position: relative;
      display: inline-block;
    }
    
    .hero-header h1::before {
      content: 'DATA // DASHBOARD';
      position: absolute;
      top: 2px;
      left: 2px;
      background: var(--accent-2);
      -webkit-background-clip: text;
      background-clip: text;
      opacity: 0.5;
      z-index: -1;
    }
    
    .subtitle {
      font-family: 'Space Mono', monospace;
      font-size: 0.9rem;
      color: var(--accent-1);
      margin-top: 15px;
      text-transform: uppercase;
      letter-spacing: 0.2em;
    }
    
    .update-time {
      position: absolute;
      top: 40px;
      right: 0;
      font-family: 'Space Mono', monospace;
      font-size: 0.75rem;
      color: #666;
    }
    
    /* 数据卡片网格 - 均匀三列 */
    .accounts-grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 30px;
      margin-bottom: 60px;
    }
    
    .account-card {
      background: var(--dark-2);
      border: 2px solid #222;
      padding: 40px;
      position: relative;
      overflow: hidden;
      transition: all 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    }
    
    .account-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 4px;
      background: linear-gradient(90deg, var(--accent-1), var(--accent-3));
    }
    
    .account-card:hover {
      border-color: var(--accent-1);
      transform: translateY(-5px);
      box-shadow: 0 20px 60px rgba(0, 255, 136, 0.1);
    }
    
    .account-card.secondary::before {
      background: linear-gradient(90deg, var(--accent-2), var(--accent-3));
    }
    
    .account-card.secondary:hover {
      border-color: var(--accent-2);
      box-shadow: 0 20px 60px rgba(255, 0, 102, 0.1);
    }
    
    .account-card.douyin::before {
      background: linear-gradient(90deg, #fe2c55, #25f4ee);
    }
    
    .account-card.douyin:hover {
      border-color: #fe2c55;
      box-shadow: 0 20px 60px rgba(254, 44, 85, 0.1);
    }
    
    .account-card.douyin .main-stat-value {
      color: #fe2c55;
    }
    
    .account-card.douyin .platform-badge {
      display: inline-block;
      background: linear-gradient(90deg, #fe2c55, #25f4ee);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      font-family: 'Space Mono', monospace;
      font-size: 0.75rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-left: 10px;
    }
    
    .account-card .platform-badge {
      display: inline-block;
      font-family: 'Space Mono', monospace;
      font-size: 0.75rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-left: 10px;
      opacity: 0.4;
    }
    
    .account-card.secondary .platform-badge {
      opacity: 0.4;
    }
    
    .account-title {
      font-family: 'Bebas Neue', sans-serif;
      font-size: 2.5rem;
      letter-spacing: 0.05em;
      margin-bottom: 30px;
      color: #fff;
    }
    
    /* 主数据展示 - 大数字 */
    .main-stat {
      margin-bottom: 40px;
      position: relative;
    }
    
    .main-stat-value {
      font-family: 'Space Mono', monospace;
      font-size: clamp(3rem, 8vw, 5rem);
      font-weight: 700;
      color: var(--accent-1);
      line-height: 1;
      letter-spacing: -0.02em;
    }
    
    .account-card.secondary .main-stat-value {
      color: var(--accent-2);
    }
    
    .main-stat-label {
      font-family: 'Space Mono', monospace;
      font-size: 0.85rem;
      color: #666;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-top: 8px;
    }
    
    /* 数据指标网格 */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 15px;
    }
    
    .stat-item {
      background: var(--dark-3);
      padding: 20px 15px;
      border: 1px solid #333;
      text-align: center;
      transition: all 0.3s ease;
      position: relative;
      overflow: hidden;
    }
    
    .stat-item::after {
      content: '';
      position: absolute;
      bottom: 0;
      left: 0;
      width: 100%;
      height: 2px;
      background: var(--accent-1);
      transform: scaleX(0);
      transform-origin: left;
      transition: transform 0.3s ease;
    }
    
    .stat-item:hover {
      border-color: var(--accent-1);
      background: rgba(0, 255, 136, 0.05);
    }
    
    .stat-item:hover::after {
      transform: scaleX(1);
    }
    
    .stat-value {
      font-family: 'Space Mono', monospace;
      font-size: 1.8rem;
      font-weight: 700;
      color: #fff;
      line-height: 1.2;
    }
    
    .stat-value.positive {
      color: var(--accent-1);
    }
    
    .stat-label {
      font-size: 0.75rem;
      color: #888;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-top: 5px;
    }
    
    /* 本月涨粉 - 横跨项 */
    .stat-item.full-width {
      grid-column: span 3;
      background: linear-gradient(135deg, rgba(0, 255, 136, 0.1), rgba(0, 212, 255, 0.1));
      border-color: rgba(0, 255, 136, 0.3);
    }
    
    .account-card.secondary .stat-item.full-width {
      background: linear-gradient(135deg, rgba(255, 0, 102, 0.1), rgba(0, 212, 255, 0.1));
      border-color: rgba(255, 0, 102, 0.3);
    }
    
    .stat-item.full-width .stat-value {
      font-size: 2.2rem;
    }
    
    /* 图表区域 */
    .chart-section {
      margin-bottom: 60px;
    }
    
    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 30px;
      padding-bottom: 15px;
      border-bottom: 1px solid #333;
    }
    
    .section-title {
      font-family: 'Bebas Neue', sans-serif;
      font-size: 2.5rem;
      letter-spacing: 0.05em;
      color: #fff;
    }
    
    .section-tag {
      font-family: 'Space Mono', monospace;
      font-size: 0.7rem;
      padding: 5px 15px;
      background: var(--accent-1);
      color: #000;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    
    .charts-container {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 30px;
    }
    
    .chart-wrapper {
      background: var(--dark-2);
      border: 2px solid #222;
      padding: 30px;
      position: relative;
    }
    
    .chart-wrapper::before {
      content: 'GROWTH';
      position: absolute;
      top: 15px;
      right: 20px;
      font-family: 'Space Mono', monospace;
      font-size: 0.7rem;
      color: #444;
      letter-spacing: 0.2em;
    }
    
    .chart-title {
      font-size: 1rem;
      color: var(--accent-1);
      margin-bottom: 20px;
      font-weight: 700;
      letter-spacing: 0.05em;
    }
    
    .chart-wrapper.secondary .chart-title {
      color: var(--accent-2);
    }
    
    .chart-wrapper.douyin .chart-title {
      color: #fe2c55;
    }
    
    .chart-wrapper.douyin::before {
      color: #fe2c55;
      opacity: 0.3;
    }
    
    .chart-container {
      width: 100%;
      height: 350px;
    }
    
    /* 视频列表区域 */
    .videos-section {
      margin-top: 40px;
    }
    
    .month-group {
      margin-bottom: 30px;
    }
    
    .month-header {
      font-family: 'Bebas Neue', sans-serif;
      font-size: 1.8rem;
      letter-spacing: 0.05em;
      color: var(--accent-3);
      padding: 12px 0 8px;
      margin-bottom: 15px;
      border-bottom: 1px solid rgba(0, 212, 255, 0.2);
      display: flex;
      align-items: center;
      gap: 12px;
    }
    
    .month-header .month-count {
      font-family: 'Space Mono', monospace;
      font-size: 0.7rem;
      padding: 3px 10px;
      background: rgba(0, 212, 255, 0.1);
      color: var(--accent-3);
      border: 1px solid rgba(0, 212, 255, 0.3);
      letter-spacing: 0.1em;
    }
    
    .douyin-stats {
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid rgba(254, 44, 85, 0.15);
    }
    
    .douyin-stats .stat-pill {
      border-color: rgba(254, 44, 85, 0.2);
    }
    
    .douyin-stats .stat-pill:hover {
      border-color: #fe2c55;
      color: #fe2c55;
    }
    
    .platform-tag-douyin {
      display: inline-block;
      font-family: 'Space Mono', monospace;
      font-size: 0.65rem;
      padding: 2px 8px;
      background: linear-gradient(90deg, #fe2c55, #25f4ee);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-right: 6px;
    }
    
    .honor-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin: 4px 0 2px 0;
    }
    
    .honor-tag {
      display: inline-block;
      font-size: 0.65rem;
      padding: 1px 6px;
      border-radius: 3px;
      font-weight: 600;
      letter-spacing: 0.02em;
      white-space: nowrap;
    }
    
    .honor-rank-1 {
      background: linear-gradient(90deg, #ffd700, #ffaa00);
      color: #1a1a2e;
    }
    
    .honor-top-10 {
      background: rgba(255, 215, 0, 0.15);
      color: #ffd700;
      border: 1px solid rgba(255, 215, 0, 0.3);
    }
    
    .honor-top-100 {
      background: rgba(0, 212, 255, 0.1);
      color: #00d4ff;
      border: 1px solid rgba(0, 212, 255, 0.2);
    }
    
    .honor-weekly {
      background: rgba(254, 44, 85, 0.12);
      color: #fe2c55;
      border: 1px solid rgba(254, 44, 85, 0.25);
    }
    
    .chart-controls .chart-divider {
      display: inline-block;
      width: 1px;
      height: 24px;
      background: #444;
      margin: 0 8px;
      vertical-align: middle;
    }
    
    .chart-btn.platform-btn {
      font-weight: 700;
      letter-spacing: 0.05em;
    }
    
    .chart-btn.platform-btn.active {
      background: rgba(0, 212, 255, 0.15);
    }
    
    #platformDouyin.active {
      border-color: #fe2c55 !important;
      color: #fe2c55 !important;
      background: rgba(254, 44, 85, 0.1) !important;
    }
    
    .videos-grid {
      display: grid;
      gap: 20px;
    }
    
    .video-card {
      background: var(--dark-2);
      border: 2px solid #222;
      padding: 25px;
      position: relative;
      transition: all 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    }
    
    .video-card:hover {
      border-color: var(--accent-3);
      transform: translateX(10px);
    }
    
    .video-card.clickable:hover {
      cursor: pointer;
    }
    
    .video-card.monitoring {
      border-left: 4px solid var(--accent-2);
    }
    
    .video-card.archived {
      opacity: 0.8;
    }
    
    .video-status {
      position: absolute;
      top: 15px;
      right: 20px;
      font-family: 'Space Mono', monospace;
      font-size: 0.65rem;
      padding: 4px 12px;
      background: var(--accent-2);
      color: #fff;
      letter-spacing: 0.15em;
      animation: pulse 2s infinite;
    }
    
    .video-card.archived .video-status {
      background: #444;
      animation: none;
    }
    
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    
    .video-content {
      display: flex;
      gap: 20px;
      align-items: flex-start;
    }
    
    .video-thumb-wrapper {
      flex-shrink: 0;
      position: relative;
      overflow: hidden;
    }
    
    .video-thumb {
      width: 160px;
      display: block;
      border: 2px solid #333;
      transition: transform 0.3s ease;
    }
    
    .video-card:hover .video-thumb {
      transform: scale(1.05);
    }
    
    .video-info {
      flex: 1;
    }
    
    .video-title {
      font-size: 1.1rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 12px;
      line-height: 1.4;
      padding-right: 80px;
    }
    
    .video-meta {
      display: flex;
      gap: 20px;
      margin-bottom: 15px;
    }
    
    .meta-item {
      font-family: 'Space Mono', monospace;
      font-size: 0.75rem;
      color: #666;
    }
    
    .video-stats {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    
    .stat-pill {
      background: var(--dark-3);
      padding: 6px 12px;
      border-radius: 2px;
      font-size: 0.8rem;
      color: #aaa;
      border: 1px solid #333;
      transition: all 0.3s ease;
    }
    
    .stat-pill:hover {
      border-color: var(--accent-1);
      color: var(--accent-1);
    }
    
    .growth-badge {
      display: inline-block;
      margin-top: 12px;
      font-family: 'Space Mono', monospace;
      font-size: 0.9rem;
      font-weight: 700;
      color: var(--accent-1);
      padding: 5px 15px;
      background: rgba(0, 255, 136, 0.1);
      border: 1px solid rgba(0, 255, 136, 0.3);
    }
    
    /* 模态框 */
    .modal {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.9);
      z-index: 1000;
      align-items: center;
      justify-content: center;
      backdrop-filter: blur(10px);
    }
    
    .modal.show {
      display: flex;
    }
    
    .modal-content {
      background: var(--dark-2);
      border: 2px solid #333;
      padding: 40px;
      max-width: 900px;
      width: 95%;
      max-height: 90vh;
      overflow-y: auto;
      position: relative;
    }
    
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 30px;
      padding-bottom: 20px;
      border-bottom: 1px solid #333;
    }
    
    .modal-title {
      font-family: 'Bebas Neue', sans-serif;
      font-size: 2rem;
      letter-spacing: 0.05em;
      color: #fff;
    }
    
    .close-btn {
      background: none;
      border: 2px solid #444;
      color: #888;
      width: 40px;
      height: 40px;
      font-size: 1.5rem;
      cursor: pointer;
      transition: all 0.3s ease;
      font-family: 'Space Mono', monospace;
    }
    
    .close-btn:hover {
      border-color: var(--accent-2);
      color: var(--accent-2);
    }
    
    .chart-controls {
      display: flex;
      gap: 10px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }
    
    .chart-btn {
      padding: 10px 20px;
      border: 2px solid #333;
      background: transparent;
      color: #888;
      cursor: pointer;
      font-family: 'Space Mono', monospace;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      transition: all 0.3s ease;
    }
    
    .chart-btn:hover,
    .chart-btn.active {
      border-color: var(--accent-1);
      color: var(--accent-1);
      background: rgba(0, 255, 136, 0.1);
    }
    
    /* 页脚 */
    .footer {
      margin-top: 80px;
      padding-top: 30px;
      border-top: 1px solid #222;
      text-align: center;
    }
    
    .footer p {
      font-family: 'Space Mono', monospace;
      font-size: 0.7rem;
      color: #444;
      letter-spacing: 0.2em;
      text-transform: uppercase;
    }
    
    /* 响应式 */
    @media (max-width: 1024px) {
      .accounts-grid {
        grid-template-columns: 1fr;
      }
      
      .charts-container {
        grid-template-columns: 1fr;
      }
    }
    
    @media (max-width: 768px) {
      .stats-grid {
        grid-template-columns: 1fr;
      }
      
      .stat-item.full-width {
        grid-column: span 1;
      }
      
      .video-content {
        flex-direction: column;
      }
      
      .video-thumb {
        width: 100%;
      }
      
      .video-title {
        padding-right: 0;
      }
      
      .update-time {
        position: relative;
        top: 0;
        margin-top: 15px;
      }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="hero-header">
      <h1>DATA DASHBOARD</h1>
      <div class="subtitle">BILIBILI × DOUYIN // 毕导 × 毕的二阶导</div>
      <div class="update-time">LAST UPDATE: """ + update_time + """</div>
    </div>

    <div class="accounts-grid">
      <div class="account-card">
        <div class="account-title">毕 导 <span class="platform-badge">BILIBILI</span></div>
        <div class="main-stat">
          <div class="main-stat-value">""" + format_number(bidao_info.get('fans', 0)) + """</div>
          <div class="main-stat-label">TOTAL FOLLOWERS</div>
        </div>
        <div class="stats-grid" style="grid-template-columns: 1fr 1fr;">
          <div class="stat-item">
            <div class="stat-value">""" + format_number(bidao_info.get('likes', 0)) + """</div>
            <div class="stat-label">总赞数</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">""" + str(bidao_videos_count) + """</div>
            <div class="stat-label">今年更新数</div>
          </div>
          <div class="stat-item full-width" style="grid-column: span 1;">
            <div class="stat-value positive">+""" + format_number(month_growth_bidao) + """</div>
            <div class="stat-label">本月涨粉</div>
          </div>
          <div class="stat-item full-width" style="grid-column: span 1;">
            <div class="stat-value positive">+""" + format_number(bidao_info.get('fans_add', 0)) + """</div>
            <div class="stat-label">昨日涨粉</div>
          </div>
        </div>
      </div>

      <div class="account-card secondary">
        <div class="account-title">毕的二阶导 <span class="platform-badge">BILIBILI</span></div>
        <div class="main-stat">
          <div class="main-stat-value">""" + format_number(erjiedao_info.get('fans', 0)) + """</div>
          <div class="main-stat-label">TOTAL FOLLOWERS</div>
        </div>
        <div class="stats-grid" style="grid-template-columns: 1fr 1fr;">
          <div class="stat-item">
            <div class="stat-value">""" + format_number(erjiedao_info.get('likes', 0)) + """</div>
            <div class="stat-label">总赞数</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">""" + str(erjie_videos_count) + """</div>
            <div class="stat-label">今年更新数</div>
          </div>
          <div class="stat-item full-width" style="grid-column: span 1;">
            <div class="stat-value positive">+""" + format_number(month_growth_erjie) + """</div>
            <div class="stat-label">本月涨粉</div>
          </div>
          <div class="stat-item full-width" style="grid-column: span 1;">
            <div class="stat-value positive">+""" + format_number(erjiedao_info.get('fans_add', 0)) + """</div>
            <div class="stat-label">昨日涨粉</div>
          </div>
        </div>
      </div>

      <div class="account-card douyin">
        <div class="account-title">毕 导 <span class="platform-badge">DOUYIN</span></div>
        <div class="main-stat">
          <div class="main-stat-value">""" + format_number(douyin_info.get('fans', 0)) + """</div>
          <div class="main-stat-label">TOTAL FOLLOWERS</div>
        </div>
        <div class="stats-grid" style="grid-template-columns: 1fr 1fr;">
          <div class="stat-item">
            <div class="stat-value">""" + format_number(douyin_info.get('likes', 0)) + """</div>
            <div class="stat-label">总赞数</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">""" + str(douyin_info.get('works', 0)) + """</div>
            <div class="stat-label">作品数</div>
          </div>
          <div class="stat-item full-width" style="grid-column: span 1;">
            <div class="stat-value positive">+""" + format_number(month_growth_douyin) + """</div>
            <div class="stat-label">本月涨粉</div>
          </div>
          <div class="stat-item full-width" style="grid-column: span 1;">
            <div class="stat-value positive">+""" + format_number(douyin_info.get('fans_add', 0)) + """</div>
            <div class="stat-label">昨日涨粉</div>
          </div>
        </div>
      </div>
    </div>

    <div class="chart-section">
      <div class="section-header">
        <div class="section-title">粉丝增长曲线</div>
        <div class="section-tag">DAILY DATA</div>
      </div>
      <div class="charts-container">
        <div class="chart-wrapper">
          <div class="chart-title">毕 导 // FANS GROWTH</div>
          <div id="bidaoChart" class="chart-container"></div>
        </div>
        <div class="chart-wrapper secondary">
          <div class="chart-title">二阶导 // FANS GROWTH</div>
          <div id="erjieChart" class="chart-container"></div>
        </div>
        
        <div class="chart-wrapper douyin">
          <div class="chart-title">毕导抖音 // FANS GROWTH</div>
          <div id="douyinChart" class="chart-container"></div>
        </div>
      </div>
    </div>

    <div class="videos-section">
      <div class="section-header">
        <div class="section-title">2026 视频作品</div>
        <div class="section-tag">""" + str(len(all_videos)) + """ VIDEOS</div>
      </div>
      <div class="videos-grid">
        """ + ''.join(video_cards) + """
      </div>
    </div>

    <div class="footer">
      <p>BUILT WITH DATA // POWERED BY BILIBILI API</p>
    </div>
  </div>

  <!-- 视频详情模态框 -->
  <div id="videoModal" class="modal">
    <div class="modal-content">
      <div class="modal-header">
        <h3 class="modal-title" id="modalVideoTitle">VIDEO DATA ANALYSIS</h3>
        <button class="close-btn" onclick="closeModal()">&times;</button>
      </div>
      <div class="chart-controls">
        <button class="chart-btn platform-btn active" onclick="setVideoPlatform('bilibili')" id="platformBilibili">B站 BILIBILI</button>
        <button class="chart-btn platform-btn" onclick="setVideoPlatform('douyin')" id="platformDouyin">抖音 DOUYIN</button>
        <span class="chart-divider"></span>
        <!-- B站指标按钮 -->
        <button class="chart-btn metric-btn metric-bilibili active" onclick="setVideoMetric('view')">播放量 VIEWS</button>
        <button class="chart-btn metric-btn metric-bilibili" onclick="setVideoMetric('like')">点赞 LIKES</button>
        <button class="chart-btn metric-btn metric-bilibili" onclick="setVideoMetric('coin')">投币 COINS</button>
        <button class="chart-btn metric-btn metric-bilibili" onclick="setVideoMetric('favorite')">收藏 FAVORITES</button>
        <button class="chart-btn metric-btn metric-bilibili" onclick="setVideoMetric('reply')">评论 REPLIES</button>
        <button class="chart-btn metric-btn metric-bilibili" onclick="setVideoMetric('share')">分享 SHARES</button>
        <button class="chart-btn metric-btn metric-bilibili" onclick="setVideoMetric('danmaku')">弹幕 DANMAKU</button>
        <!-- 抖音指标按钮 -->
        <button class="chart-btn metric-btn metric-douyin" style="display:none" onclick="setVideoMetric('likes')">点赞 LIKES</button>
        <button class="chart-btn metric-btn metric-douyin" style="display:none" onclick="setVideoMetric('comments')">评论 COMMENTS</button>
        <button class="chart-btn metric-btn metric-douyin" style="display:none" onclick="setVideoMetric('collects')">收藏 COLLECTS</button>
        <button class="chart-btn metric-btn metric-douyin" style="display:none" onclick="setVideoMetric('shares')">转发 SHARES</button>
      </div>
      <div id="videoChart" style="width: 100%; height: 400px;"></div>
    </div>
  </div>

  <script>
    const growthData = """ + growth_json + """;
    const videoData = """ + video_data_json + """;
    const douyinGrowthData = """ + douyin_growth_json + """;
    const douyinVideoData = """ + douyin_video_data_json + """;
    let currentVideoChart = null;
    let currentMetric = 'view';
    let currentBvid = null;
    let currentPlatform = 'bilibili';

    // 初始化粉丝增长图表
    function initCharts() {
      const bidaoChart = echarts.init(document.getElementById('bidaoChart'));
      const erjieChart = echarts.init(document.getElementById('erjieChart'));
      const douyinChart = echarts.init(document.getElementById('douyinChart'));
      
      const dates = growthData.map(item => item.date);
      const bidaoFans = growthData.map(item => item.accounts.bidao.fans);
      const erjieFans = growthData.map(item => item.accounts.erjiedao.fans || null);
      
      // 抖音数据
      const douyinDates = douyinGrowthData.map(item => item.date);
      const douyinFans = douyinGrowthData.map(item => item.fans);
      
      const commonOption = {
        backgroundColor: 'transparent',
        textStyle: {
          fontFamily: 'Space Mono, monospace',
          color: '#888'
        },
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(20, 20, 20, 0.95)',
          borderColor: '#00ff88',
          borderWidth: 1,
          textStyle: {
            color: '#fff',
            fontFamily: 'Space Mono, monospace'
          },
          formatter: function(params) {
            return params[0].axisValue + '<br/><strong>' + params[0].value.toLocaleString() + '</strong>';
          }
        },
        grid: {
          left: '10%',
          right: '5%',
          top: '15%',
          bottom: '15%'
        },
        xAxis: {
          type: 'category',
          data: dates,
          axisLine: { lineStyle: { color: '#333' } },
          axisLabel: { color: '#666', fontSize: 10 }
        },
        yAxis: {
          type: 'value',
          scale: true,
          axisLine: { lineStyle: { color: '#333' } },
          axisLabel: {
            color: '#666',
            fontSize: 10,
            formatter: function(v) {
              if (v >= 10000) return (v / 10000).toFixed(0) + '万';
              return v;
            }
          },
          splitLine: { lineStyle: { color: '#222' } }
        },
        series: [{
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { width: 3 },
          areaStyle: { opacity: 0.1 }
        }]
      };
      
      bidaoChart.setOption({
        ...commonOption,
        series: [{
          ...commonOption.series[0],
          data: bidaoFans,
          lineStyle: { width: 3, color: '#00ff88' },
          itemStyle: { color: '#00ff88' },
          areaStyle: { color: '#00ff88', opacity: 0.1 }
        }]
      });
      
      erjieChart.setOption({
        ...commonOption,
        series: [{
          ...commonOption.series[0],
          data: erjieFans,
          lineStyle: { width: 3, color: '#ff0066' },
          itemStyle: { color: '#ff0066' },
          areaStyle: { color: '#ff0066', opacity: 0.1 }
        }]
      });
      
      douyinChart.setOption({
        ...commonOption,
        tooltip: {
          ...commonOption.tooltip,
          borderColor: '#fe2c55'
        },
        xAxis: {
          ...commonOption.xAxis,
          data: douyinDates
        },
        series: [{
          ...commonOption.series[0],
          data: douyinFans,
          lineStyle: { width: 3, color: '#fe2c55' },
          itemStyle: { color: '#fe2c55' },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(254, 44, 85, 0.3)' },
            { offset: 1, color: 'rgba(37, 244, 238, 0.05)' }
          ]) }
        }]
      });
      
      // 响应式
      window.addEventListener('resize', () => {
        bidaoChart.resize();
        erjieChart.resize();
        douyinChart.resize();
      });
    }

    // 显示视频图表
    function showVideoChart(bvid) {
      currentBvid = bvid;
      currentPlatform = 'bilibili';
      currentMetric = 'view';
      
      const modal = document.getElementById('videoModal');
      modal.classList.add('show');
      
      // 检查是否有抖音数据，显示/隐藏抖音按钮
      const douyinBtn = document.getElementById('platformDouyin');
      if (douyinVideoData[bvid]) {
        douyinBtn.style.display = '';
      } else {
        douyinBtn.style.display = 'none';
      }
      
      // 重置平台按钮状态
      document.getElementById('platformBilibili').classList.add('active');
      document.getElementById('platformDouyin').classList.remove('active');
      // 重置指标按钮：显示B站按钮，隐藏抖音按钮
      document.querySelectorAll('.metric-bilibili').forEach(btn => {
        btn.style.display = '';
        btn.classList.remove('active');
      });
      document.querySelectorAll('.metric-douyin').forEach(btn => {
        btn.style.display = 'none';
        btn.classList.remove('active');
      });
      document.querySelector('.metric-bilibili').classList.add('active');
      
      const video = videoData[bvid];
      if (video && video.meta) {
        document.getElementById('modalVideoTitle').textContent = decodeURIComponent('" + encodeURIComponent(video.meta.title) + "').toUpperCase();
      }
      
      setTimeout(() => {
        renderVideoChart();
      }, 100);
    }

    // 关闭模态框
    function closeModal() {
      document.getElementById('videoModal').classList.remove('show');
      if (currentVideoChart) {
        currentVideoChart.dispose();
        currentVideoChart = null;
      }
    }

    // 设置视频指标
    function setVideoMetric(metric) {
      currentMetric = metric;
      document.querySelectorAll('.metric-btn').forEach(btn => btn.classList.remove('active'));
      event.target.classList.add('active');
      renderVideoChart();
    }

    // 设置视频平台
    function setVideoPlatform(platform) {
      currentPlatform = platform;
      document.querySelectorAll('.platform-btn').forEach(btn => btn.classList.remove('active'));
      event.target.classList.add('active');
      
      // 更新指标按钮：B站和抖音使用各自独立的按钮组
      if (platform === 'douyin') {
        currentMetric = 'likes';
        document.querySelectorAll('.metric-bilibili').forEach(btn => btn.style.display = 'none');
        document.querySelectorAll('.metric-douyin').forEach(btn => btn.style.display = '');
        document.querySelectorAll('.metric-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelector('.metric-douyin').classList.add('active');
      } else {
        currentMetric = 'view';
        document.querySelectorAll('.metric-bilibili').forEach(btn => btn.style.display = '');
        document.querySelectorAll('.metric-douyin').forEach(btn => btn.style.display = 'none');
        document.querySelectorAll('.metric-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelector('.metric-bilibili').classList.add('active');
      }
      
      renderVideoChart();
    }

    // 渲染视频图表
    function renderVideoChart() {
      if (!currentBvid) return;
      
      if (currentVideoChart) {
        currentVideoChart.dispose();
      }
      
      currentVideoChart = echarts.init(document.getElementById('videoChart'));
      
      let times, values, metricLabel, chartColor, borderColor;
      
      if (currentPlatform === 'douyin') {
        const dyData = douyinVideoData[currentBvid];
        if (!dyData || !dyData.history) return;
        
        times = dyData.history.map(item => {
          const parts = item.fetch_time.split(' ');
          return parts[0] + ' ' + parts[1].substring(0, 5);
        });
        values = dyData.history.map(item => item[currentMetric] || 0);
        
        const douyinMetricNames = {
          likes: '点赞', comments: '评论', collects: '收藏', shares: '转发'
        };
        metricLabel = douyinMetricNames[currentMetric] || currentMetric;
        chartColor = '#fe2c55';
        borderColor = '#fe2c55';
      } else {
        const video = videoData[currentBvid];
        if (!video || !video.data) return;
        
        times = video.data.map(item => {
          const date = new Date(item.timestamp * 1000);
          return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        });
        values = video.data.map(item => item[currentMetric]);
        
        const metricNames = {
          view: '播放量', like: '点赞', coin: '投币',
          favorite: '收藏', reply: '评论', share: '分享', danmaku: '弹幕'
        };
        metricLabel = metricNames[currentMetric] || currentMetric;
        chartColor = '#00d4ff';
        borderColor = '#00d4ff';
      }
      
      currentVideoChart.setOption({
        backgroundColor: 'transparent',
        textStyle: {
          fontFamily: 'Space Mono, monospace',
          color: '#888'
        },
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(20, 20, 20, 0.95)',
          borderColor: borderColor,
          borderWidth: 1,
          textStyle: {
            color: '#fff',
            fontFamily: 'Space Mono, monospace'
          },
          formatter: function(params) {
            return params[0].axisValue + '<br/><strong>' + params[0].value.toLocaleString() + '</strong>';
          }
        },
        title: {
          text: (currentPlatform === 'douyin' ? '抖音 ' : 'B站 ') + metricLabel.toUpperCase() + ' // TREND',
          textStyle: { color: chartColor, fontSize: 14, fontFamily: 'Space Mono, monospace' }
        },
        grid: {
          left: '10%',
          right: '5%',
          top: '15%',
          bottom: '15%'
        },
        xAxis: {
          type: 'category',
          data: times,
          axisLine: { lineStyle: { color: '#333' } },
          axisLabel: { color: '#666', fontSize: 10, rotate: times.length > 10 ? 30 : 0 }
        },
        yAxis: {
          type: 'value',
          scale: true,
          axisLine: { lineStyle: { color: '#333' } },
          axisLabel: {
            color: '#666',
            fontSize: 10,
            formatter: function(v) {
              if (v >= 10000) return (v / 10000).toFixed(0) + '万';
              return v;
            }
          },
          splitLine: { lineStyle: { color: '#222' } }
        },
        series: [{
          type: 'line',
          smooth: true,
          data: values,
          lineStyle: { width: 3, color: chartColor },
          itemStyle: { color: chartColor },
          areaStyle: currentPlatform === 'douyin' ? {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(254, 44, 85, 0.3)' },
              { offset: 1, color: 'rgba(37, 244, 238, 0.05)' }
            ])
          } : { color: chartColor, opacity: 0.1 },
          symbol: 'circle',
          symbolSize: 4
        }]
      });
    }

    // 点击模态框外部关闭
    document.getElementById('videoModal').addEventListener('click', (e) => {
      if (e.target.id === 'videoModal') {
        closeModal();
      }
    });

    // 初始化
    initCharts();
  </script>
</body>
</html>"""

    output_path = os.path.join(DOCS_DIR, 'index.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"HTML已生成: {output_path}")


if __name__ == '__main__':
    generate_html()
