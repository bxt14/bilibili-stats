#!/usr/bin/env python3
"""清理Chrome CDP中的残留标签页，只保留about:blank"""
import json
import sys

try:
    import requests
except ImportError:
    print("需要requests库")
    sys.exit(1)

CDP_PORT = 9222

def cleanup_tabs():
    try:
        resp = requests.get(f'http://localhost:{CDP_PORT}/json/list', timeout=5)
        tabs = resp.json()
    except Exception as e:
        print(f"无法连接Chrome CDP: {e}")
        return False
    
    closed = 0
    kept = 0
    blank_count = 0
    for tab in tabs:
        url = tab.get('url', '')
        tab_id = tab.get('id', '')
        tab_type = tab.get('type', '')
        
        # 跳过非page/service_worker类型（保留其他内部类型）
        if tab_type not in ('page', 'service_worker'):
            kept += 1
            continue
        
        # 关闭service_worker残留标签（如sw.js）
        if tab_type == 'service_worker':
            try:
                close_resp = requests.get(f'http://localhost:{CDP_PORT}/json/close/{tab_id}', timeout=5)
                if close_resp.ok:
                    closed += 1
                    print(f"  已关闭service_worker: {url[:80]}")
                else:
                    # service_worker可能无法通过/json/close/关闭，忽略
                    kept += 1
            except:
                kept += 1
            continue
        
        # 只保留第一个about:blank标签页，关闭多余的
        if url == 'about:blank' and blank_count < 1:
            blank_count += 1
            kept += 1
            continue
        
        # 关闭其他标签页
        try:
            close_resp = requests.get(f'http://localhost:{CDP_PORT}/json/close/{tab_id}', timeout=5)
            if close_resp.ok:
                closed += 1
                print(f"  已关闭: {url[:80]}")
            else:
                print(f"  关闭失败: {url[:80]}")
        except Exception as e:
            print(f"  关闭异常: {e}")
    
    print(f"\n清理完成: 关闭 {closed} 个标签页, 保留 {kept} 个")
    return True

if __name__ == '__main__':
    print(f"Chrome标签页清理: 开始")
    cleanup_tabs()
