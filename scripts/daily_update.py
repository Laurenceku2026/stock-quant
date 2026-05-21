#!/usr/bin/env python
"""
每日定时任务：更新所有用户的龙头股缓存
运行环境：GitHub Actions
"""

import requests
import json
import sys
import os
from datetime import datetime
from typing import List, Dict, Tuple

# ==================== 配置 ====================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    print("❌ 缺少 Supabase 配置")
    sys.exit(1)

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

def get_stock_daily(ts_code: str, days: int = 5) -> Dict:
    """获取股票日线数据（简化版）"""
    try:
        import tushare as ts
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
        
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        
        if df is not None and not df.empty:
            df = df.sort_values('trade_date')
            return {
                "close": df['close'].tolist(),
                "trade_date": df['trade_date'].tolist()
            }
        return {}
    except Exception as e:
        print(f"获取股票数据失败 {ts_code}: {e}")
        return {}

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

def save_leader_stocks_to_cache(user_id: str, sector_name: str, leader_code: str, leader_name: str, leader_pct: float):
    """保存龙头股到缓存"""
    try:
        headers = get_supabase_headers(use_secret=True)
        
        # 先删除旧记录
        delete_url = f"{SUPABASE_URL}/rest/v1/user_leader_stocks_cache?user_id=eq.{user_id}&sector_name=eq.{sector_name}"
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
            return True, 0
        
        updated_count = 0
        for sector in preset_sectors[:10]:
            sector_name = sector.get('sector_name')
            if not sector_name:
                continue
            
            # 这里需要获取板块成分股和计算龙头股
            # 简化版：使用预置数据
            from datetime import timedelta
            
            # 获取板块成分股（从预置数据）
            hot_sectors = {
                "光模块/CPO": ["300308.SZ", "300394.SZ", "300502.SZ", "688313.SH", "301191.SZ"],
                "人工智能": ["002230.SZ", "002415.SZ", "300058.SZ", "002920.SZ"],
                "半导体": ["688981.SH", "002371.SZ", "603986.SH", "300782.SZ"],
                "算力": ["000977.SZ", "603019.SH", "300442.SZ", "002281.SZ"],
                "机器人": ["300024.SZ", "300124.SZ", "002747.SZ", "688017.SH", "300161.SZ"]
            }
            
            stocks = hot_sectors.get(sector_name, [])
            if not stocks:
                continue
            
            # 计算每只股票的涨跌幅
            stock_performance = []
            for ts_code in stocks[:10]:
                try:
                    import tushare as ts
                    ts.set_token(TUSHARE_TOKEN)
                    pro = ts.pro_api()
                    
                    end_date = datetime.now().strftime("%Y%m%d")
                    start_date = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d")
                    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                    
                    if df is not None and not df.empty and len(df) >= 2:
                        df = df.sort_values('trade_date')
                        pct_chg = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
                        stock_name = get_stock_name(ts_code)
                        stock_performance.append({
                            "code": ts_code,
                            "name": stock_name,
                            "pct_chg": pct_chg
                        })
                    else:
                        stock_name = get_stock_name(ts_code)
                        stock_performance.append({
                            "code": ts_code,
                            "name": stock_name,
                            "pct_chg": 0
                        })
                except Exception as e:
                    print(f"处理股票 {ts_code} 失败: {e}")
                    stock_performance.append({
                        "code": ts_code,
                        "name": ts_code,
                        "pct_chg": 0
                    })
            
            if stock_performance:
                stock_performance.sort(key=lambda x: x.get('pct_chg', 0), reverse=True)
                leader = stock_performance[0]
                if save_leader_stocks_to_cache(user_id, sector_name, leader['code'], leader['name'], leader['pct_chg']):
                    updated_count += 1
                    print(f"✅ 用户 {user_id[:8]} 板块 {sector_name} 龙头股: {leader['name']} ({leader['pct_chg']:.2f}%)")
        
        return True, updated_count
        
    except Exception as e:
        print(f"更新用户 {user_id} 龙头股失败: {e}")
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
