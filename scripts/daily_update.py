#!/usr/bin/env python
"""
每日定时任务：更新所有用户的龙头股缓存
运行环境：GitHub Actions
"""

import requests
import json
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

# ==================== 配置 ====================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    print("❌ 缺少 Supabase 配置")
    sys.exit(1)

if not TUSHARE_TOKEN:
    print("⚠️ Tushare Token 未配置，将无法获取股票涨跌幅")
    # 不退出，继续运行（成分股可能从数据库获取，但涨跌幅无法计算）


# ==================== Supabase 函数 ====================

def get_supabase_headers(use_secret=True):
    """获取 Supabase 请求头"""
    if use_secret:
        return {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": "application/json"
        }
    return {
        "apikey": SUPABASE_SECRET_KEY,
        "Content-Type": "application/json"
    }


def get_all_users() -> List[Dict]:
    """获取所有用户列表"""
    try:
        headers = get_supabase_headers(use_secret=True)
        url = f"{SUPABASE_URL}/rest/v1/user_settings?select=user_id"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取用户列表失败: {e}")
        return []


def get_user_preset_sectors(user_id: str) -> List[Dict]:
    """获取用户的预设板块"""
    try:
        headers = get_supabase_headers(use_secret=True)
        url = f"{SUPABASE_URL}/rest/v1/user_preset_sectors?user_id=eq.{user_id}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取用户预设板块失败: {e}")
        return []


def get_user_sector_stocks(user_id: str, sector_name: str) -> List[Dict]:
    """从数据库获取用户指定板块的成分股"""
    try:
        headers = get_supabase_headers(use_secret=True)
        import urllib.parse
        encoded_name = urllib.parse.quote(sector_name)
        url = f"{SUPABASE_URL}/rest/v1/user_sector_stocks?user_id=eq.{user_id}&sector_name=eq.{encoded_name}&order=rank.asc"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取成分股失败 {sector_name}: {e}")
        return []


def get_stock_name(ts_code: str) -> str:
    """获取股票名称"""
    try:
        headers = get_supabase_headers(use_secret=False)
        url = f"{SUPABASE_URL}/rest/v1/stock_basic_cache?ts_code=eq.{ts_code}&select=name"
        response = requests.get(url, headers=headers)
        if response.status_code == 200 and response.json():
            return response.json()[0]['name']
        return ts_code.split('.')[0]
    except:
        return ts_code.split('.')[0]


def get_stock_pct_chg(ts_code: str, days: int = 5) -> float:
    """获取股票最近涨跌幅"""
    if not TUSHARE_TOKEN:
        return 0
    
    try:
        import tushare as ts
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
        
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        
        if df is not None and not df.empty and len(df) >= 2:
            df = df.sort_values('trade_date')
            pct_chg = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
            return round(pct_chg, 2)
        return 0
    except Exception as e:
        print(f"获取股票涨跌幅失败 {ts_code}: {e}")
        return 0


def save_leader_stocks_to_cache(user_id: str, sector_name: str, leader_code: str, leader_name: str, leader_pct: float):
    """保存龙头股到缓存"""
    try:
        headers = get_supabase_headers(use_secret=True)
        
        # 先删除旧记录
        import urllib.parse
        encoded_name = urllib.parse.quote(sector_name)
        delete_url = f"{SUPABASE_URL}/rest/v1/user_leader_stocks_cache?user_id=eq.{user_id}&sector_name=eq.{encoded_name}"
        requests.delete(delete_url, headers=headers)
        
        # 插入新记录
        data = {
            "user_id": user_id,
            "sector_name": sector_name,
            "leader_code": leader_code,
            "leader_name": leader_name,
            "leader_pct": round(leader_pct, 2),
            "calculated_at": datetime.now().isoformat()
        }
        url = f"{SUPABASE_URL}/rest/v1/user_leader_stocks_cache"
        response = requests.post(url, headers=headers, json=data)
        return response.status_code in [200, 201]
    except Exception as e:
        print(f"保存龙头股失败: {e}")
        return False


def update_user_leader_stocks(user_id: str) -> Tuple[bool, int]:
    """更新单个用户的龙头股缓存"""
    try:
        preset_sectors = get_user_preset_sectors(user_id)
        if not preset_sectors:
            print(f"用户 {user_id[:8]} 没有预设板块")
            return True, 0
        
        updated_count = 0
        
        for sector in preset_sectors[:10]:
            sector_name = sector.get('sector_name')
            if not sector_name:
                continue
            
            print(f"  处理板块: {sector_name}")
            
            # 从数据库获取该板块的成分股
            members = get_user_sector_stocks(user_id, sector_name)
            
            if not members:
                print(f"    ⚠️ 板块 {sector_name} 无成分股数据，跳过")
                continue
            
            print(f"    📊 获取到 {len(members)} 只成分股")
            
            # 计算每只股票的涨跌幅
            stock_performance = []
            for member in members[:10]:
                ts_code = member.get('stock_code')
                stock_name = member.get('stock_name')
                if not ts_code:
                    continue
                
                # 获取股票名称（如果为空）
                if not stock_name or stock_name == ts_code:
                    stock_name = get_stock_name(ts_code)
                
                # 计算涨跌幅
                pct_chg = get_stock_pct_chg(ts_code, days=5)
                stock_performance.append({
                    "code": ts_code,
                    "name": stock_name,
                    "pct_chg": pct_chg
                })
            
            if stock_performance:
                # 按涨跌幅排序，取第一名作为龙头股
                stock_performance.sort(key=lambda x: x.get('pct_chg', 0), reverse=True)
                leader = stock_performance[0]
                
                if save_leader_stocks_to_cache(user_id, sector_name, leader['code'], leader['name'], leader['pct_chg']):
                    updated_count += 1
                    print(f"    ✅ 龙头股: {leader['name']} ({leader['pct_chg']:.2f}%)")
                else:
                    print(f"    ❌ 保存失败")
            else:
                print(f"    ⚠️ 无有效成分股数据")
        
        return True, updated_count
        
    except Exception as e:
        print(f"更新用户 {user_id} 龙头股失败: {e}")
        import traceback
        traceback.print_exc()
        return False, 0


# ==================== 主函数 ====================

def main():
    print("=" * 50)
    print(f"开始每日定时任务: {datetime.now()}")
    print("=" * 50)
    
    # 获取所有用户
    users = get_all_users()
    if not users:
        print("❌ 没有找到任何用户")
        sys.exit(1)
    
    print(f"📊 找到 {len(users)} 个用户")
    
    success_count = 0
    total_updated = 0
    
    for user in users:
        user_id = user.get('user_id')
        if not user_id or user_id == "admin":
            continue
        
        print(f"\n🔄 处理用户: {user_id[:8]}...")
        success, updated = update_user_leader_stocks(user_id)
        if success:
            success_count += 1
            total_updated += updated
    
    print("\n" + "=" * 50)
    print(f"✅ 定时任务完成")
    print(f"   成功处理用户: {success_count}/{len(users)}")
    print(f"   更新龙头股数: {total_updated}")
    print("=" * 50)


if __name__ == "__main__":
    main()
