#!/usr/bin/env python
"""
每日定时任务：更新所有用户的龙头股缓存
运行环境：GitHub Actions
"""

import os
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests

# ==================== 配置 ====================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")

BEIJING_TZ = timezone(timedelta(hours=8))
PAGE_SIZE = 1000
MAX_SECTORS_PER_USER = 10
MAX_MEMBERS_PER_SECTOR = 30  # 扩大候选池，避免只看前 10 只

TUSHARE_PRO = None

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    print("❌ 缺少 Supabase 配置")
    sys.exit(1)

if not TUSHARE_TOKEN:
    print("⚠️ Tushare Token 未配置，将无法获取股票涨跌幅")


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def beijing_trade_date(days_ago: int = 0) -> str:
    return (beijing_now() - timedelta(days=days_ago)).strftime("%Y%m%d")


def encode_eq(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def get_supabase_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def init_tushare():
    """初始化一次 Tushare Pro，避免每只股票重复 set_token"""
    global TUSHARE_PRO
    if not TUSHARE_TOKEN:
        return False
    try:
        import tushare as ts

        ts.set_token(TUSHARE_TOKEN)
        TUSHARE_PRO = ts.pro_api()
        print("✅ Tushare 初始化成功")
        return True
    except Exception as e:
        print(f"❌ Tushare 初始化失败: {e}")
        TUSHARE_PRO = None
        return False


def supabase_get_all(path_with_query: str) -> List[Dict]:
    """带分页拉取 PostgREST 结果，避免默认 1000 行截断"""
    headers = get_supabase_headers()
    results: List[Dict] = []
    offset = 0

    while True:
        sep = "&" if "?" in path_with_query else "?"
        url = (
            f"{SUPABASE_URL}/rest/v1/{path_with_query}"
            f"{sep}limit={PAGE_SIZE}&offset={offset}"
        )
        response = requests.get(url, headers=headers, timeout=60)
        if response.status_code != 200:
            print(f"Supabase GET 失败 [{response.status_code}]: {url} -> {response.text[:200]}")
            break
        batch = response.json()
        if not isinstance(batch, list):
            break
        results.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.05)

    return results


def get_all_users() -> List[Dict]:
    try:
        return supabase_get_all("user_settings?select=user_id")
    except Exception as e:
        print(f"获取用户列表失败: {e}")
        return []


def get_user_preset_sectors(user_id: str) -> List[Dict]:
    try:
        return supabase_get_all(
            f"user_preset_sectors?user_id=eq.{encode_eq(user_id)}&select=*"
        )
    except Exception as e:
        print(f"获取用户预设板块失败: {e}")
        return []


def get_user_sector_stocks(user_id: str, sector_name: str) -> List[Dict]:
    try:
        return supabase_get_all(
            f"user_sector_stocks?user_id=eq.{encode_eq(user_id)}"
            f"&sector_name=eq.{encode_eq(sector_name)}&order=rank.asc"
        )
    except Exception as e:
        print(f"获取成分股失败 {sector_name}: {e}")
        return []


def get_stock_name(ts_code: str) -> str:
    try:
        headers = get_supabase_headers()
        url = (
            f"{SUPABASE_URL}/rest/v1/stock_basic_cache"
            f"?ts_code=eq.{encode_eq(ts_code)}&select=name&limit=1"
        )
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200 and response.json():
            return response.json()[0]["name"]
        return ts_code.split(".")[0]
    except Exception:
        return ts_code.split(".")[0]


def batch_get_pct_chg(ts_codes: List[str], lookback_days: int = 10) -> Dict[str, float]:
    """
    批量获取近一日涨跌幅。优先用 pct_chg 字段；否则用收盘价计算。
    返回 {ts_code: pct_chg}
    """
    result = {code: 0.0 for code in ts_codes}
    if not TUSHARE_PRO or not ts_codes:
        return result

    end_date = beijing_trade_date(0)
    start_date = beijing_trade_date(lookback_days)
    # Tushare daily 的 ts_code 支持逗号拼接，但单次不宜过长
    chunk_size = 50

    for i in range(0, len(ts_codes), chunk_size):
        chunk = ts_codes[i : i + chunk_size]
        codes_str = ",".join(chunk)
        try:
            df = TUSHARE_PRO.daily(
                ts_code=codes_str, start_date=start_date, end_date=end_date
            )
            time.sleep(0.35)
            if df is None or df.empty:
                continue

            for code in chunk:
                sub = df[df["ts_code"] == code].sort_values("trade_date")
                if sub.empty:
                    continue
                if "pct_chg" in sub.columns and len(sub) >= 1:
                    # 取最近一个交易日的官方涨跌幅
                    result[code] = round(float(sub["pct_chg"].iloc[-1]), 2)
                elif len(sub) >= 2:
                    c0 = float(sub["close"].iloc[-2])
                    c1 = float(sub["close"].iloc[-1])
                    if c0:
                        result[code] = round((c1 - c0) / c0 * 100, 2)
        except Exception as e:
            print(f"批量获取涨跌幅失败 ({codes_str[:40]}...): {e}")
            time.sleep(1)

    return result


def save_leader_stocks_to_cache(
    user_id: str,
    sector_name: str,
    leader_code: str,
    leader_name: str,
    leader_pct: float,
) -> bool:
    try:
        headers = get_supabase_headers()
        encoded_name = encode_eq(sector_name)
        delete_url = (
            f"{SUPABASE_URL}/rest/v1/user_leader_stocks_cache"
            f"?user_id=eq.{encode_eq(user_id)}&sector_name=eq.{encoded_name}"
        )
        requests.delete(delete_url, headers=headers, timeout=30)

        data = {
            "user_id": user_id,
            "sector_name": sector_name,
            "leader_code": leader_code,
            "leader_name": leader_name,
            "leader_pct": round(leader_pct, 2),
            "calculated_at": beijing_now().isoformat(),
        }
        url = f"{SUPABASE_URL}/rest/v1/user_leader_stocks_cache"
        response = requests.post(url, headers=headers, json=data, timeout=30)
        return response.status_code in (200, 201)
    except Exception as e:
        print(f"保存龙头股失败: {e}")
        return False


def update_user_leader_stocks(user_id: str) -> Tuple[bool, int]:
    try:
        preset_sectors = get_user_preset_sectors(user_id)
        if not preset_sectors:
            print(f"用户 {user_id[:8]} 没有预设板块")
            return True, 0

        updated_count = 0

        for sector in preset_sectors[:MAX_SECTORS_PER_USER]:
            sector_name = sector.get("sector_name")
            if not sector_name:
                continue

            print(f"  处理板块: {sector_name}")
            members = get_user_sector_stocks(user_id, sector_name)
            if not members:
                print(f"    ⚠️ 板块 {sector_name} 无成分股数据，跳过")
                continue

            members = members[:MAX_MEMBERS_PER_SECTOR]
            print(f"    📊 候选成分股: {len(members)} 只")

            codes = []
            name_map: Dict[str, str] = {}
            for member in members:
                ts_code = member.get("stock_code")
                if not ts_code:
                    continue
                codes.append(ts_code)
                stock_name = member.get("stock_name")
                if not stock_name or stock_name == ts_code:
                    stock_name = get_stock_name(ts_code)
                name_map[ts_code] = stock_name

            pct_map = batch_get_pct_chg(codes)
            stock_performance = [
                {
                    "code": code,
                    "name": name_map.get(code, code.split(".")[0]),
                    "pct_chg": pct_map.get(code, 0.0),
                }
                for code in codes
            ]

            if not stock_performance:
                print("    ⚠️ 无有效成分股数据")
                continue

            stock_performance.sort(key=lambda x: x.get("pct_chg", 0), reverse=True)
            leader = stock_performance[0]

            if save_leader_stocks_to_cache(
                user_id,
                sector_name,
                leader["code"],
                leader["name"],
                leader["pct_chg"],
            ):
                updated_count += 1
                print(f"    ✅ 龙头股: {leader['name']} ({leader['pct_chg']:.2f}%)")
            else:
                print("    ❌ 保存失败")

        return True, updated_count

    except Exception as e:
        print(f"更新用户 {user_id} 龙头股失败: {e}")
        import traceback

        traceback.print_exc()
        return False, 0


def main():
    print("=" * 50)
    print(f"开始每日定时任务: {beijing_now()}")
    print("=" * 50)

    init_tushare()

    users = get_all_users()
    if not users:
        print("❌ 没有找到任何用户")
        sys.exit(1)

    print(f"📊 找到 {len(users)} 个用户")

    success_count = 0
    total_updated = 0

    for user in users:
        user_id = user.get("user_id")
        if not user_id or user_id == "admin":
            continue

        print(f"\n🔄 处理用户: {str(user_id)[:8]}...")
        success, updated = update_user_leader_stocks(user_id)
        if success:
            success_count += 1
            total_updated += updated

    print("\n" + "=" * 50)
    print("✅ 定时任务完成")
    print(f"   成功处理用户: {success_count}/{len(users)}")
    print(f"   更新龙头股数: {total_updated}")
    print("=" * 50)


if __name__ == "__main__":
    main()
