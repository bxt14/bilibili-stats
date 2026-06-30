#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并CSV历史粉丝数据到growth_all.json
CSV格式: 时间,粉丝总数 (日期格式: 2025/12/1)
growth_all.json格式: [{timestamp, date, time, accounts: {bidao: {name, fans}, erjiedao: {name, fans}}}]
"""
import json
import csv
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def parse_csv(filepath):
    """解析CSV文件，返回日期->粉丝数映射"""
    data = {}
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader)  # 跳过表头
        for row in reader:
            if len(row) < 2:
                continue
            date_str = row[0].strip()
            fans = int(row[1].strip())
            # 统一日期格式: 2025/12/1 -> 2025-12-01
            try:
                dt = datetime.strptime(date_str, '%Y/%m/%d')
                date_key = dt.strftime('%Y-%m-%d')
                data[date_key] = fans
            except ValueError:
                print(f"跳过无法解析的日期: {date_str}")
    return data

def date_to_timestamp(date_str):
    """将YYYY-MM-DD日期转为时间戳"""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return int(dt.timestamp())

def main():
    # 加载现有growth_all.json
    growth_file = os.path.join(DATA_DIR, 'growth_all.json')
    with open(growth_file, 'r', encoding='utf-8') as f:
        growth_data = json.load(f)
    
    print(f"现有数据: {len(growth_data)} 条")
    if growth_data:
        print(f"  最早日期: {growth_data[0]['date']}")
        print(f"  最晚日期: {growth_data[-1]['date']}")
    
    # 解析CSV文件
    bidao_csv = os.path.join(DATA_DIR, '毕导之前的粉丝数据_1780159637469_0_gwpe.csv')
    erjie_csv = os.path.join(DATA_DIR, '毕的二阶导之前的粉丝数据_1780159637469_1_ylgk.csv')
    
    bidao_history = parse_csv(bidao_csv)
    erjie_history = parse_csv(erjie_csv)
    
    print(f"\n毕导CSV数据: {len(bidao_history)} 条")
    print(f"  最早: {min(bidao_history.keys())}, 最晚: {max(bidao_history.keys())}")
    print(f"二阶导CSV数据: {len(erjie_history)} 条")
    print(f"  最早: {min(erjie_history.keys())}, 最晚: {max(erjie_history.keys())}")
    
    # 获取现有数据中的日期集合
    existing_dates = set(item['date'] for item in growth_data)
    
    # 找出所有需要添加的日期（CSV中有但growth_all中没有的）
    all_csv_dates = sorted(set(list(bidao_history.keys()) + list(erjie_history.keys())))
    new_dates = [d for d in all_csv_dates if d not in existing_dates]
    
    print(f"\n需新增日期: {len(new_dates)} 条")
    if new_dates:
        print(f"  从 {new_dates[0]} 到 {new_dates[-1]}")
    
    # 也要更新已有日期中粉丝为0的记录（如二阶导早期数据为0）
    updated_count = 0
    for item in growth_data:
        date = item['date']
        # 更新毕导数据
        if date in bidao_history and item['accounts']['bidao']['fans'] == 0:
            item['accounts']['bidao']['fans'] = bidao_history[date]
            updated_count += 1
        # 更新二阶导数据
        if date in erjie_history and item['accounts']['erjiedao']['fans'] == 0:
            item['accounts']['erjiedao']['fans'] = erjie_history[date]
            updated_count += 1
    
    print(f"更新已有0值记录: {updated_count} 条")
    
    # 创建新的历史数据条目
    new_entries = []
    for date in new_dates:
        bidao_fans = bidao_history.get(date, 0)
        erjie_fans = erjie_history.get(date, 0)
        entry = {
            "timestamp": date_to_timestamp(date),
            "date": date,
            "time": "09:00",
            "accounts": {
                "bidao": {
                    "name": "毕导",
                    "fans": bidao_fans
                },
                "erjiedao": {
                    "name": "毕的二阶导",
                    "fans": erjie_fans
                }
            }
        }
        new_entries.append(entry)
    
    # 合并：先加历史数据，再加现有数据
    combined = new_entries + growth_data
    
    # 按日期排序
    combined.sort(key=lambda x: x['date'])
    
    # 去重（同一日期保留后一条，因为现有数据可能更准确）
    seen = {}
    for item in combined:
        seen[item['date']] = item
    combined = sorted(seen.values(), key=lambda x: x['date'])
    
    print(f"\n合并后总数: {len(combined)} 条")
    print(f"  最早: {combined[0]['date']}")
    print(f"  最晚: {combined[-1]['date']}")
    
    # 验证：打印几个关键数据点
    print(f"\n验证数据点:")
    for item in combined[:3]:
        print(f"  {item['date']}: 毕导={item['accounts']['bidao']['fans']}, 二阶导={item['accounts']['erjiedao']['fans']}")
    # 打印交接点附近的数据
    for item in combined:
        if item['date'] in ['2026-04-11', '2026-04-12', '2026-04-13']:
            print(f"  {item['date']}: 毕导={item['accounts']['bidao']['fans']}, 二阶导={item['accounts']['erjiedao']['fans']}")
    
    # 备份原文件
    backup_file = growth_file + '.bak'
    os.rename(growth_file, backup_file)
    print(f"\n原文件已备份到: {backup_file}")
    
    # 写入新文件
    with open(growth_file, 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    print(f"新文件已写入: {growth_file}")
    
    print("\n✅ 合并完成!")

if __name__ == '__main__':
    main()
