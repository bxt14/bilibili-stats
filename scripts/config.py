#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集中配置：路径、环境变量、常量统一管理
任何脚本 import config 即自动完成环境准备（cron极简环境下也能正常工作）
"""
import os

# ============ 路径（从__file__推导，不硬编码）============
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
VIDEO_DATA_DIR = os.path.join(DATA_DIR, 'videos')
DOUYIN_VIDEOS_DIR = os.path.join(DATA_DIR, 'douyin_videos')
DOCS_DIR = os.path.join(BASE_DIR, 'docs')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
WORKSPACE_DIR = os.path.dirname(BASE_DIR)

# ============ 环境变量（import时自动设置，幂等）============
def _setup_env():
    # cron环境PATH极简，补齐常见工具路径
    extra_paths = ['/usr/local/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin']
    current = os.environ.get('PATH', '')
    for p in reversed(extra_paths):
        if p not in current.split(os.pathsep):
            current = p + os.pathsep + current
    os.environ['PATH'] = current

    os.environ.setdefault('GH_CONFIG_DIR', os.path.join(WORKSPACE_DIR, '.gh'))
    os.environ.setdefault('LARKSUITE_CLI_CONFIG_DIR', os.path.join(WORKSPACE_DIR, '.feishu_cli'))
    os.environ.setdefault('LARKSUITE_CLI_DATA_DIR', os.path.join(WORKSPACE_DIR, '.feishu_cli'))
    os.environ.setdefault('HOME', '/root')
    os.environ.setdefault('NODE_NO_WARNINGS', '1')

_setup_env()

# ============ B站采集策略 ============
HIGH_FREQ_DAYS = 14     # 发布<=14天：每小时
DAILY_FREQ_DAYS = 30    # 发布14-30天：每天；>30天归档

# ============ 抖音频率分级 ============
DOUYIN_HOURLY_MAX_AGE_DAYS = 3
DOUYIN_EVERY4H_MAX_AGE_DAYS = 14
DOUYIN_DAILY_MAX_AGE_DAYS = 30

# ============ 账号 ============
ACCOUNTS = {
    'bidao': {'uid': '254463269', 'name': '毕导'},
    'erjiedao': {'uid': '489763089', 'name': '毕的二阶导'},
}

# ============ 飞书 ============
FEISHU_BASE_TOKEN = 'CZwHbS7d2alENJsYoJicXOLgnIe'
FEISHU_BILIBILI_TABLE = 'tblMJtSgWy5EFZrH'
FEISHU_DOUYIN_TABLE = 'tblLKeLyl0Bu65y8'

# ============ B站API ============
BILI_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com'
}
