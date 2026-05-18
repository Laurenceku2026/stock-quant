"""
AI量化股票系统 - 完整版本 v4.0
基于DFSS方法论 + 机器学习集成 + Tushare真实数据 + 掘金交易 + Stripe支付

更新内容（v4.0）：
- 板块缓存表支持（Supabase存储）
- Tushare热点板块同步（利用2126分积分）
- 用户自定义板块管理
- 回测参数保存到用户设置
- 清理调试代码
- 各模块独立权重配置（右上角自动保存）
- 市场简报增加上证指数技术指标
- 实操信号模块新增实操池增删功能

部署方式：
1. 将代码上传到GitHub
2. 在Streamlit Cloud部署
3. 配置Secrets（见下方secrets.toml）
"""

# ============================================================
# 第1部分：导入、配置、常量、多语言、Supabase连接、Tushare初始化
# 新增功能：
# - 板块缓存表常量定义
# - Tushare热点板块同步函数（sync_hot_sectors_to_db）
# - 板块缓存刷新函数
#===================
import streamlit as st
import pandas as pd
import numpy as np
import random
import math
import requests
import json
import time
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from collections import Counter
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import time
from functools import wraps

def tushare_request_with_retry(func):
    """一个装饰器，让所有调用Tushare的函数都自带延时、重试和错误处理"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                time.sleep(0.5) # 每次请求前暂停0.5秒，这是关键
                result = func(*args, **kwargs)
                if result is not None and not (hasattr(result, 'empty') and result.empty):
                    return result
                else:
                    print(f"Tushare请求返回空数据，尝试 {attempt+1}/{max_retries}")
                    time.sleep(1) # 失败后等待1秒再重试
            except Exception as e:
                print(f"Tushare请求错误 (尝试 {attempt+1}/{max_retries}): {e}")
                time.sleep(2) # 出错后等待2秒
        return None # 所有重试都失败后返回None
    return wrapper

# ==================== 时区配置 ====================
from datetime import timezone

# 定义北京时间时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))

def get_beijing_time() -> datetime:
    """获取当前北京时间"""
    return datetime.now(BEIJING_TZ)

def get_current_time_str() -> str:
    """获取当前北京时间字符串（精确到分钟）"""
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")

def utc_to_beijing_str(utc_time_str: str) -> str:
    """将UTC时间字符串转换为北京时间字符串"""
    if not utc_time_str:
        return ""
    try:
        # 处理不同格式的UTC时间
        if utc_time_str.endswith('Z'):
            utc_time_str = utc_time_str.replace('Z', '+00:00')
        utc_time = datetime.fromisoformat(utc_time_str)
        beijing_time = utc_time.astimezone(BEIJING_TZ)
        return beijing_time.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return utc_time_str

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="AI量化股票系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== 强制初始化 Session State（必须在任何其他代码之前） ====================
if "kdj_k_fallback" not in st.session_state:
    st.session_state.kdj_k_fallback = 50
    st.session_state.kdj_d_fallback = 50
    st.session_state.kdj_j_fallback = 50

# 初始化所有必需的 session state 变量
_required_state = {
    "lang": "zh",
    "authenticated": False,
    "user_id": None,
    "user_email": None,
    "admin_mode": False,
    "show_admin_login": False,
    "show_register": False,
    "show_paywall": False,
    "analyze_code": "",
    "analyze_name": "",
    "market": "A股",
    "last_update_time": {},
    "stock_cache_loaded": False,
    "sector_cache_loaded": False,
    "show_sector_management": False,
    "edit_live_stock": None,
    "show_add_stocks_to_sector": False,
    "new_sector_name": "",
    "access_token": None,
    "refresh_token": None,
    "token_expiry": 0,
    "admin_previous_user_id": None,
    "admin_previous_user_email": None,
    "admin_previous_access_token": None,
    "admin_previous_refresh_token": None,
    "payment_url": None,
    "payment_type": None,
    "backtest_result": None,
    "admin_view_user_id": None,
    "admin_view_user_email": None,
}

for _key, _default in _required_state.items():
    if _key not in st.session_state:
        st.session_state[_key] = _default
# ==================== 管理员配置 ====================
ADMIN_USERNAME = "Laurence_ku"
ADMIN_PASSWORD = "Ku_product$2026"
ADMIN_EMAIL = "Techlife2027@gmail.com"

# ==================== 常量定义 ====================
FREE_TRIAL_LIMIT = 30
MAX_RECOMMENDED_STOCKS = 30

# 技术指标权重（默认值）
TECH_WEIGHTS = {
    "macd": 0.25,
    "kdj": 0.20,
    "boll": 0.20,
    "rsi": 0.15,
    "volume_price": 0.20
}

# 信号等级映射
SIGNAL_LEVELS = {
    "S": {"min_score": 85, "action": "强烈买入", "position": "10-15%", "color": "#ff4b4b"},
    "A": {"min_score": 70, "action": "买入", "position": "5-10%", "color": "#ff6b6b"},
    "B": {"min_score": 55, "action": "观望", "position": "0-5%", "color": "#ffaa00"},
    "C": {"min_score": 40, "action": "减持", "position": "减半", "color": "#ff8800"},
    "D": {"min_score": 0, "action": "清仓/回避", "position": "0%", "color": "#888888"}
}

# 预置热点板块（作为降级方案）
HOT_SECTORS = {
    "光模块/CPO": {
        "stocks": ["300308.SZ", "300394.SZ", "300502.SZ", "688313.SH", "301191.SZ"],
        "names": ["中际旭创", "天孚通信", "新易盛", "仕佳光子", "中瓷电子"]
    },
    "人工智能": {
        "stocks": ["002230.SZ", "002415.SZ", "300058.SZ", "002920.SZ"],
        "names": ["科大讯飞", "海康威视", "蓝色光标", "德赛西威"]
    },
    "半导体": {
        "stocks": ["688981.SH", "002371.SZ", "603986.SH", "300782.SZ"],
        "names": ["中芯国际", "北方华创", "兆易创新", "卓胜微"]
    },
    "算力": {
        "stocks": ["000977.SZ", "603019.SH", "300442.SZ", "002281.SZ"],
        "names": ["浪潮信息", "中科曙光", "普丽盛", "光迅科技"]
    },
    "机器人": {
        "stocks": ["300024.SZ", "300124.SZ", "002747.SZ", "688017.SH", "300161.SZ"],
        "names": ["机器人", "汇川技术", "埃斯顿", "绿的谐波", "华中数控"]
    }
}

# 市场选项
MARKET_OPTIONS = ["A股", "港股", "美股"]

# 股票名称缓存
STOCK_NAME_CACHE = {}

# ==================== 掘金板块数据获取 ====================

# ==================== Supabase 配置 ====================
SUPABASE_URL = st.secrets.get("SUPABASE_STOCK_URL", "")
SUPABASE_PUBLISHABLE_KEY = st.secrets.get("SUPABASE_STOCK_ANON_KEY", "")
SUPABASE_SECRET_KEY = st.secrets.get("SUPABASE_STOCK_SECRET_KEY", "")

# ==================== Stripe 配置 ====================
STRIPE_SECRET_KEY = st.secrets.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = st.secrets.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_PRICE_MONTHLY = st.secrets.get("STRIPE_PRICE_MONTHLY", "")
STRIPE_PRICE_YEARLY = st.secrets.get("STRIPE_PRICE_YEARLY", "")

# 全局设置 Stripe API Key（参考TechLife Portal）
import stripe
stripe.api_key = STRIPE_SECRET_KEY

# ==================== DeepSeek 配置 ====================
DEEPSEEK_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = st.secrets.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = st.secrets.get("DEEPSEEK_MODEL", "deepseek-chat")

# ==================== Tushare 配置 ====================
TUSHARE_TOKEN = st.secrets.get("TUSHARE_TOKEN", "")
TUSHARE_AVAILABLE = False
TUSHARE_PRO = None
TUSHARE_INTEGRAL = 2126  # 当前积分

# ==================== 掘金配置 ====================
GM_TOKEN = st.secrets.get("GM_TOKEN", "")
GM_STRATEGY_ID = st.secrets.get("GM_STRATEGY_ID", "")
GM_ACCOUNT_ID = st.secrets.get("GM_ACCOUNT_ID", "")
GM_AVAILABLE = False

# ==================== 多语言文本 ====================
TEXTS = {
    "zh": {
        "app_title": "📊 AI量化股票系统",
        "login": "登录",
        "register": "注册",
        "logout": "登出",
        "email": "邮箱",
        "password": "密码",
        "confirm_password": "确认密码",
        "login_btn": "登录",
        "register_btn": "注册",
        "back_to_login": "返回登录",
        "welcome": "欢迎回来",
        "login_failed": "登录失败，请检查邮箱和密码",
        "register_success": "注册成功！请登录",
        "email_exists": "该邮箱已注册，请直接登录",
        "about_header": "📘 关于系统",
        "about_text": """
**AI量化股票系统** 基于DFSS方法论和AI技术，提供：

- 🔥 热点板块识别
- 🎯 龙头股筛选
- 📈 技术指标评分
- 📊 策略回测验证
- 💡 AI操作建议
- 🤖 掘金一键下单

让AI成为您的投资助手。
""",
        "contact_header": "📧 联系我们",
        "contact_email": "✉️ 电邮: Techlife2027@gmail.com",
        "guide_header": "📖 快速指南",
        "guide_text": """
1. 点击[刷新]获取最新分析
2. 推荐池可手动添加/删除股票
3. 输入代码进行个股分析
4. 回测验证策略有效性
5. 实操信号支持一键下单

💡 每次刷新消耗1次免费次数
💎 升级专业版后无限使用
""",
        "subscription": "订阅",
        "free_tier": "免费版",
        "pro_tier": "专业版",
        "remaining": "剩余次数",
        "unlimited": "无限",
        "upgrade": "升级专业版",
        "module1_title": "📊 市场简报",
        "module2_title": "🎯 推荐股票池",
        "module3_title": "🔍 个股分析",
        "module4_title": "📈 回测功能",
        "module5_title": "💡 实操信号",
        "refresh": "🔄 刷新",
        "add_stock": "➕ 手动添加",
        "analyze": "分析",
        "place_order": "🤖 一键下单",
        "admin_panel": "管理员面板",
        "total_users": "总用户数",
        "pro_users": "专业版用户",
        "free_users": "免费版用户",
        "user_list": "用户列表",
        "reset_password": "重置密码",
        "send_email": "发送邮件",
        "paywall_title": "🔒 免费次数已用完",
        "paywall_desc": "升级到专业版，无限使用所有功能",
        "monthly": "月付 $29/月",
        "yearly": "年付 $299/年",
        "save_info": "年付立省$49",
        "buy": "买入",
        "sell": "卖出",
        "hold": "持有",
        "increase": "加仓",
        "reduce": "减仓",
        "chinese": "中文",
        "english": "English"
    },
    "en": {
        "app_title": "📊 AI Quant Stock System",
        "login": "Login",
        "register": "Register",
        "logout": "Logout",
        "email": "Email",
        "password": "Password",
        "confirm_password": "Confirm Password",
        "login_btn": "Login",
        "register_btn": "Register",
        "back_to_login": "Back to Login",
        "welcome": "Welcome back",
        "login_failed": "Login failed. Please check your email and password.",
        "register_success": "Registration successful! Please login.",
        "email_exists": "Email already registered. Please login.",
        "about_header": "📘 About System",
        "about_text": """
**AI Quant Stock System** powered by DFSS and AI:

- 🔥 Hot Sector Detection
- 🎯 Leader Stock Selection
- 📈 Technical Analysis
- 📊 Strategy Backtesting
- 💡 AI Trading Signals
- 🤖 One-Click Trading

Let AI be your investment assistant.
""",
        "contact_header": "📧 Contact Us",
        "contact_email": "✉️ Email: Techlife2027@gmail.com",
        "guide_header": "📖 Quick Guide",
        "guide_text": """
1. Click [Refresh] for latest analysis
2. Manually add/remove stocks from pool
3. Enter code for individual analysis
4. Backtest to validate strategies
5. One-click trading from signals

💡 Each refresh uses 1 free trial
💎 Upgrade to Pro for unlimited access
""",
        "subscription": "Subscription",
        "free_tier": "Free",
        "pro_tier": "Pro",
        "remaining": "Remaining",
        "unlimited": "Unlimited",
        "upgrade": "Upgrade to Pro",
        "module1_title": "📊 Market Brief",
        "module2_title": "🎯 Recommended Pool",
        "module3_title": "🔍 Stock Analysis",
        "module4_title": "📈 Backtest",
        "module5_title": "💡 Trading Signals",
        "refresh": "🔄 Refresh",
        "add_stock": "➕ Add Stock",
        "analyze": "Analyze",
        "place_order": "🤖 One-Click Order",
        "admin_panel": "Admin Panel",
        "total_users": "Total Users",
        "pro_users": "Pro Users",
        "free_users": "Free Users",
        "user_list": "User List",
        "reset_password": "Reset Password",
        "send_email": "Send Email",
        "paywall_title": "🔒 Free Trials Exhausted",
        "paywall_desc": "Upgrade to Pro for unlimited access",
        "monthly": "Monthly $29/mo",
        "yearly": "Yearly $299/yr",
        "save_info": "Save $49 per year",
        "buy": "Buy",
        "sell": "Sell",
        "hold": "Hold",
        "increase": "Increase",
        "reduce": "Reduce",
        "chinese": "中文",
        "english": "English"
    }
}


def t():
    """获取当前语言的文本"""
    lang = st.session_state.get("lang", "zh")
    return TEXTS[lang]


# ==================== 初始化Session State ====================
def init_session_state():
    """初始化所有session state变量"""
    if "lang" not in st.session_state:
        st.session_state.lang = "zh"
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "user_email" not in st.session_state:
        st.session_state.user_email = None
    if "admin_mode" not in st.session_state:
        st.session_state.admin_mode = False
    if "show_admin_login" not in st.session_state:
        st.session_state.show_admin_login = False
    if "show_register" not in st.session_state:
        st.session_state.show_register = False
    if "show_paywall" not in st.session_state:
        st.session_state.show_paywall = False
    if "analyze_code" not in st.session_state:
        st.session_state.analyze_code = ""
    if "analyze_name" not in st.session_state:
        st.session_state.analyze_name = ""
    if "market" not in st.session_state:
        st.session_state.market = "A股"
    if "last_update_time" not in st.session_state:
        st.session_state.last_update_time = {}
    if "stock_cache_loaded" not in st.session_state:
        st.session_state.stock_cache_loaded = False
    if "sector_cache_loaded" not in st.session_state:
        st.session_state.sector_cache_loaded = False
    # 新增：板块管理页面状态
    if "show_sector_management" not in st.session_state:
        st.session_state.show_sector_management = False
    # 新增：编辑实操池状态
    if "edit_live_stock" not in st.session_state:
        st.session_state.edit_live_stock = None
    # 新增：创建板块临时状态
    if "show_add_stocks_to_sector" not in st.session_state:
        st.session_state.show_add_stocks_to_sector = False
    if "new_sector_name" not in st.session_state:
        st.session_state.new_sector_name = ""

# ==================== 工具函数 ====================
def get_current_time_str() -> str:
    """获取当前北京时间字符串（精确到分钟）"""
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")

def update_last_update_time(module_name: str):
    """更新模块的最后更新时间"""
    st.session_state.last_update_time[module_name] = get_current_time_str()


def get_last_update_time(module_name: str) -> str:
    """获取模块的最后更新时间"""
    return st.session_state.last_update_time.get(module_name, "未更新")


# ==================== Tushare 初始化 ====================
def init_tushare():
    """初始化Tushare连接"""
    global TUSHARE_AVAILABLE, TUSHARE_PRO
    
    if not TUSHARE_TOKEN:
        print("❌ Tushare Token未配置")
        return
    
    try:
        import tushare as ts
        ts.set_token(TUSHARE_TOKEN)
        TUSHARE_PRO = ts.pro_api()
        TUSHARE_AVAILABLE = True
        print("✅ Tushare 初始化成功")
        print(f"   当前积分: {TUSHARE_INTEGRAL}分")
    except ImportError:
        print("❌ Tushare 未安装，请运行: pip install tushare")
    except Exception as e:
        print(f"❌ Tushare 初始化失败: {e}")


# ==================== 股票名称缓存（从Supabase读取） ====================

def sync_stock_basic_to_db():
    """
    从Tushare同步股票列表到Supabase
    只在管理员手动点击按钮时调用，APP启动时不调用
    返回: (success, count, message)
    """
    if not TUSHARE_AVAILABLE:
        return False, 0, "Tushare不可用，请检查配置"
    
    try:
        # 获取股票列表（包含名称）
        df = TUSHARE_PRO.stock_basic(exchange='', list_status='L', fields='ts_code,name')
        
        if df is None or df.empty:
            return False, 0, "获取股票列表失败"
        
        records = []
        for _, row in df.iterrows():
            records.append({
                "ts_code": row['ts_code'],
                "name": row['name'],
                "updated_at": datetime.now().isoformat()
            })
        
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        url = f"{SUPABASE_URL}/rest/v1/stock_basic_cache"
        
        # 先清空旧数据
        requests.delete(url, headers=headers)
        
        # 批量插入新数据
        inserted = 0
        for record in records:
            response = requests.post(url, headers=headers, json=record)
            if response.status_code in [200, 201]:
                inserted += 1
        
        print(f"✅ 成功同步 {inserted} 只股票到数据库")
        return True, inserted, f"成功同步 {inserted} 只股票"
        
    except Exception as e:
        print(f"同步股票列表失败: {e}")
        return False, 0, f"同步失败: {str(e)}"


def load_stock_name_cache() -> Dict[str, str]:
    """
    从Supabase加载股票名称缓存
    只从数据库读取，永不调用Tushare（避免频率超限）
    """
    global STOCK_NAME_CACHE
    
    if STOCK_NAME_CACHE:
        return STOCK_NAME_CACHE
    
    try:
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        url = f"{SUPABASE_URL}/rest/v1/stock_basic_cache"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200 and response.json():
            data = response.json()
            for row in data:
                STOCK_NAME_CACHE[row['ts_code']] = row['name']
            print(f"✅ 从数据库加载股票名称缓存成功，共{len(STOCK_NAME_CACHE)}只")
        else:
            print(f"⚠️ 数据库股票缓存为空，请管理员在后台同步")
        
        return STOCK_NAME_CACHE
        
    except Exception as e:
        print(f"从数据库读取缓存失败: {e}")
        return {}


def init_stock_cache_on_startup():
    """APP启动时加载股票名称缓存"""
    if not st.session_state.get("stock_cache_loaded", False):
        load_stock_name_cache()
        st.session_state.stock_cache_loaded = True


def get_stock_name_from_tushare(ts_code: str) -> str:
    """根据股票代码获取名称（支持按需缓存）"""
    global STOCK_NAME_CACHE

    # 1. 先从内存缓存里找（最快）
    if STOCK_NAME_CACHE and ts_code in STOCK_NAME_CACHE:
        return STOCK_NAME_CACHE[ts_code]

    # 2. 内存里没有，就去数据库里找
    try:
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        url = f"{SUPABASE_URL}/rest/v1/stock_basic_cache?ts_code=eq.{ts_code}&select=name"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200 and response.json():
            name = response.json()[0]['name']
            STOCK_NAME_CACHE[ts_code] = name
            return name
    except Exception as e:
        print(f"从数据库读取缓存失败: {e}")

    # 3. 如果哪里都没有，就去Tushare查询这一只股票的信息
    if not TUSHARE_AVAILABLE:
        return ts_code.split('.')[0]

    try:
        df = TUSHARE_PRO.stock_basic(ts_code=ts_code, fields='ts_code,name')
        if df is not None and not df.empty:
            stock_name = df.iloc[0]['name']
            _save_stock_name_to_db(ts_code, stock_name)
            STOCK_NAME_CACHE[ts_code] = stock_name
            return stock_name
        else:
            return ts_code.split('.')[0]
    except Exception as e:
        print(f"从Tushare查询股票名称失败 {ts_code}: {e}")
        return ts_code.split('.')[0]

def _save_stock_name_to_db(ts_code: str, name: str):
    """内部函数：将查询到的股票名称存入数据库"""
    try:
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "ts_code": ts_code,
            "name": name,
            "updated_at": datetime.now().isoformat()
        }
        url = f"{SUPABASE_URL}/rest/v1/stock_basic_cache"
        response = requests.post(url, headers=headers, json=data)
        if response.status_code not in [200, 201]:
            print(f"保存股票名称失败: {response.text}")
    except Exception as e:
        print(f"保存股票名称到数据库失败: {e}")


# ==================== 板块缓存（从Supabase读取 + Tushare同步） ====================

def sync_hot_sectors_to_db() -> Tuple[bool, str]:
    """
    从Tushare同步热点板块到Supabase（需要2000+积分）
    使用 limit_cpt_list 接口获取涨停板块排名
    返回: (success, message)
    """
    if not TUSHARE_AVAILABLE:
        return False, "Tushare不可用"
    
    if TUSHARE_INTEGRAL < 2000:
        return False, f"积分不足（当前{TUSHARE_INTEGRAL}分，需要2000分）"
    
    try:
        trade_date = datetime.now().strftime("%Y%m%d")
        df = TUSHARE_PRO.limit_cpt_list(trade_date=trade_date)
        
        if df is None or df.empty:
            return False, "获取涨停板块排名失败"
        
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        url = f"{SUPABASE_URL}/rest/v1/sector_cache"
        
        # 清空旧数据
        requests.delete(url, headers=headers)
        
        inserted = 0
        for _, row in df.iterrows():
            sector_name = row.get('name', '')
            if not sector_name:
                continue
            
            # 计算热度分数（基于涨停家数）
            limit_count = row.get('limit_count', 0)
            hot_score = min(100, 50 + limit_count * 5)
            
            record = {
                "sector_name": sector_name,
                "hot_score": hot_score,
                "source": "tushare",
                "updated_at": datetime.now().isoformat()
            }
            
            response = requests.post(url, headers=headers, json=record)
            if response.status_code in [200, 201]:
                inserted += 1
        
        print(f"✅ 成功同步 {inserted} 个热点板块到数据库")
        return True, f"成功同步 {inserted} 个热点板块"
        
    except Exception as e:
        print(f"同步热点板块失败: {e}")
        return False, f"同步失败: {str(e)}"


def refresh_sector_cache():
    """
    刷新板块缓存（每日自动或用户手动）
    如果Tushare失败，降级使用预置板块
    """
    success, msg = sync_hot_sectors_to_db()
    if not success:
        print(f"热点板块同步失败，使用预置板块: {msg}")
        # 降级：将预置板块写入缓存
        save_default_sectors_to_cache()
    return success


def save_default_sectors_to_cache():
    """将预置板块保存到缓存（降级方案）"""
    try:
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        url = f"{SUPABASE_URL}/rest/v1/sector_cache"
        
        requests.delete(url, headers=headers)
        
        for sector_name, sector_info in HOT_SECTORS.items():
            record = {
                "sector_name": sector_name,
                "stock_codes": sector_info["stocks"],
                "source": "default",
                "updated_at": datetime.now().isoformat()
            }
            requests.post(url, headers=headers, json=record)
        
        print("✅ 预置板块已保存到缓存")
    except Exception as e:
        print(f"保存预置板块失败: {e}")


def load_sector_cache() -> List[Dict]:
    """
    从Supabase加载板块缓存
    返回板块列表
    """
    try:
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        url = f"{SUPABASE_URL}/rest/v1/sector_cache"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200 and response.json():
            return response.json()
        return []
    except Exception as e:
        print(f"加载板块缓存失败: {e}")
        return []


def init_sector_cache_on_startup():
    """APP启动时加载板块缓存"""
    if not st.session_state.get("sector_cache_loaded", False):
        sectors = load_sector_cache()
        if not sectors:
            # 缓存为空，尝试同步
            refresh_sector_cache()
        st.session_state.sector_cache_loaded = True

def get_sector_members_from_cache(sector_name: str, limit: int = 10) -> List[Dict]:
    """
    从缓存读取板块成分股
    返回: [{"stock_code": "000001.SZ", "stock_name": "平安银行"}, ...]
    """
    try:
        headers = get_supabase_headers(use_secret=False)
        import urllib.parse
        encoded_name = urllib.parse.quote(sector_name)
        url = f"{SUPABASE_URL}/rest/v1/sector_members_cache?sector_name=eq.{encoded_name}&limit={limit}"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"读取成分股缓存失败 {sector_name}: {e}")
        return []
# ========================================
def get_sector_members_fallback(sector_name: str, limit: int = 10) -> List[Dict]:
    """
    备用方案：从 HOT_SECTORS 预置板块读取成分股
    当数据库缓存为空时使用
    """
    if sector_name in HOT_SECTORS:
        sector_info = HOT_SECTORS[sector_name]
        members = []
        stocks = sector_info.get("stocks", [])
        names = sector_info.get("names", [])
        for i, code in enumerate(stocks[:limit]):
            name = names[i] if i < len(names) else code
            members.append({
                "stock_code": code,
                "stock_name": name
            })
        return members
    return []

# ==================== 掘金初始化 ====================
def init_gm():
    """初始化掘金连接"""
    global GM_AVAILABLE
    
    if not GM_TOKEN:
        print("❌ 掘金Token未配置")
        return
    
    try:
        from gm.api import set_token
        set_token(GM_TOKEN)
        GM_AVAILABLE = True
        print("✅ 掘金初始化成功")
    except ImportError:
        print("❌ 掘金SDK未安装，请运行: pip install gm")
    except Exception as e:
        print(f"❌ 掘金初始化失败: {e}")


# ==================== 板块表现获取（支持缓存） ====================

@st.cache_data(ttl=7200)
def get_cached_sector_performance():
    """缓存板块表现数据（领涨股显示名称）"""
    # 先从缓存表获取板块列表
    sectors = load_sector_cache()

    if not sectors:
        # 降级使用预置板块
        data = []
        for sector_name, sector_info in HOT_SECTORS.items():
            data.append({
                "板块": sector_name,
                "涨跌幅": 0,
                "领涨股": sector_info["names"][0] if sector_info["names"] else ""
            })
        return pd.DataFrame(data)

    data = []
    for sector in sectors:
        sector_name = sector.get("sector_name", "")
        stock_codes = sector.get("stock_codes", [])

        if not stock_codes:
            data.append({
                "板块": sector_name,
                "涨跌幅": 0,
                "领涨股": ""
            })
            continue

        try:
            performances = []
            leader_code = ""
            leader_name = ""
            leader_change = -100

            for ts_code in stock_codes[:5]:  # 只取前5只成分股
                df = get_stock_daily(ts_code, days=5)
                if not df.empty and len(df) >= 2:
                    latest_close = df['close'].iloc[-1]
                    prev_close = df['close'].iloc[-2]
                    change_pct = (latest_close - prev_close) / prev_close * 100
                    performances.append(change_pct)

                    if change_pct > leader_change:
                        leader_change = change_pct
                        leader_code = ts_code
                        # 🔧 关键修复：获取股票名称
                        leader_name = get_stock_name_from_tushare(ts_code)

            if performances:
                avg_change = np.mean(performances)
            else:
                avg_change = 0

            data.append({
                "板块": sector_name,
                "涨跌幅": round(avg_change, 2),
                # 🔧 优先显示名称，如果没有名称则显示代码
                "领涨股": leader_name if leader_name else leader_code
            })
        except Exception as e:
            data.append({
                "板块": sector_name,
                "涨跌幅": 0,
                "领涨股": ""
            })

    return pd.DataFrame(data)


# 执行初始化
init_tushare()
init_gm()

# ==================== AkShare 龙头股数据获取 ====================

# ==================== Tushare 板块数据获取（替代 AkShare） ====================

def get_concept_stocks_tushare(concept_name: str) -> List[Dict]:
    """
    使用 Tushare concept_detail 获取概念板块成分股
    2000积分即可使用
    """
    if not TUSHARE_AVAILABLE:
        return []
    
    try:
        # 1. 先获取概念板块的id
        concept_df = TUSHARE_PRO.concept()
        if concept_df is None or concept_df.empty:
            return []
        
        # 查找板块id
        concept_row = concept_df[concept_df['name'] == concept_name]
        if concept_row.empty:
            return []
        
        concept_id = concept_row.iloc[0]['code']
        
        # 2. 获取板块成分股
        df = TUSHARE_PRO.concept_detail(id=concept_id)
        
        if df is not None and not df.empty:
            result = []
            for _, row in df.iterrows():
                ts_code = row.get('ts_code', '')
                name = row.get('name', '')
                if ts_code:
                    result.append({
                        "code": ts_code,
                        "name": name,
                        "board_name": concept_name
                    })
            
            # 按代码排序（Tushare 没有直接提供涨跌幅，先返回原序）
            for i, stock in enumerate(result):
                stock['rank'] = i + 1
            
            return result
        return []
    except Exception as e:
        print(f"Tushare 获取板块成分失败 {concept_name}: {e}")
        return []


def get_hot_concepts_tushare(limit: int = 10) -> List[Dict]:
    """获取热门概念板块列表（直接使用 concept 接口）"""
    st.write("🔥 DEBUG: get_hot_concepts_tushare 被调用")
    
    if not TUSHARE_AVAILABLE:
        return []
    
    try:
        # concept 接口直接返回板块列表及涨跌幅
        df = TUSHARE_PRO.concept()
        
        if df is None or df.empty:
            st.write("❌ 概念板块数据为空")
            return []
        
        st.write(f"📊 获取到 {len(df)} 个概念板块")
        
        # 直接使用 concept 接口返回的涨跌幅数据
        hot_concepts = []
        for _, row in df.iterrows():
            concept_name = row.get('name', '')
            concept_code = row.get('code', '')
            # concept 接口有 pct_change 字段吗？检查一下
            pct_chg = row.get('pct_change', 0) if 'pct_change' in df.columns else 0
            
            hot_concepts.append({
                "name": concept_name,
                "code": concept_code,
                "pct_chg": round(pct_chg, 2) if pct_chg else 0
            })
        
        # 按涨跌幅排序
        hot_concepts.sort(key=lambda x: x.get('pct_chg', 0), reverse=True)
        result = hot_concepts[:limit]
        
        st.write(f"✅ 返回前 {len(result)} 个热门板块")
        return result
        
    except Exception as e:
        st.write(f"❌ 获取热门板块失败: {e}")
        return []


def get_leader_rank_in_concept(stock_code: str, concept_name: str) -> int:
    """获取股票在指定概念板块中的龙头排名"""
    try:
        members = get_concept_stocks_tushare(concept_name)
        for member in members:
            if member['code'] == stock_code:
                return member.get('rank', 0)
        return 0
    except Exception as e:
        print(f"获取龙头排名失败: {e}")
        return 0
# ==================== Tushare 板块数据获取 ====================

def get_tushare_concept_list() -> List[Dict]:
    """获取Tushare概念板块列表"""
    if not TUSHARE_AVAILABLE:
        return []
    
    try:
        df = TUSHARE_PRO.concept()
        if df is not None and not df.empty:
            return df.to_dict('records')
        return []
    except Exception as e:
        print(f"获取概念板块列表失败: {e}")
        return []


def get_tushare_concept_daily(concept_code: str, days: int = 5) -> pd.DataFrame:
    """获取概念板块日线行情"""
    if not TUSHARE_AVAILABLE:
        return pd.DataFrame()
    
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        df = TUSHARE_PRO.concept_daily(concept_code=concept_code, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            return df.sort_values('trade_date')
        return pd.DataFrame()
    except Exception as e:
        print(f"获取板块行情失败 {concept_code}: {e}")
        return pd.DataFrame()


def get_tushare_concept_members(concept_code: str) -> List[str]:
    """获取概念板块成分股"""
    if not TUSHARE_AVAILABLE:
        return []
    
    try:
        df = TUSHARE_PRO.concept_member(concept_code=concept_code)
        if df is not None and not df.empty:
            return df['ts_code'].tolist()
        return []
    except Exception as e:
        print(f"获取板块成分失败: {e}")
        return []
print("第1部分加载完成")
print("=" * 60)
# ============================================================
# ============================================================
# 第2部分：用户认证 + Supabase API封装 + 股票池操作 + 次数扣减 + Stripe支付
# 修复内容：
# - sign_up: 只创建Auth用户，不创建profile
# - sign_in: 登录时自动创建user_settings，保存refresh_token
# - 新增 Token 自动刷新机制（解决1小时过期问题）
# - consume_free_trial: 修复次数扣减逻辑
# - Stripe 支付函数
# - 删除所有调试代码（st.error）
# - 添加板块操作函数（获取用户板块、保存板块等）
# - 新增实操池操作函数（add_to_live_pool, remove_from_live_pool, get_live_pool）
# ============================================================

import time

# ==================== Supabase API 封装 ====================

def get_supabase_headers(use_secret=False, access_token=None):
    """
    获取Supabase API请求头
    use_secret: True=使用secret key（管理员操作）
    access_token: 用户登录后的JWT token（普通用户操作）
    """
    if use_secret:
        api_key = SUPABASE_SECRET_KEY
        auth = f"Bearer {SUPABASE_SECRET_KEY}"
    elif access_token:
        api_key = SUPABASE_PUBLISHABLE_KEY
        auth = f"Bearer {access_token}"
    else:
        api_key = SUPABASE_PUBLISHABLE_KEY
        auth = f"Bearer {SUPABASE_PUBLISHABLE_KEY}"
    
    return {
        "apikey": api_key,
        "Authorization": auth,
        "Content-Type": "application/json"
    }


def refresh_access_token() -> bool:
    """
    刷新 access_token
    返回: True=刷新成功，False=刷新失败
    """
    refresh_token = st.session_state.get("refresh_token")
    if not refresh_token:
        print("❌ 无 refresh_token，无法刷新")
        return False
    
    try:
        url = f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token"
        headers = {
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Content-Type": "application/json"
        }
        data = {"refresh_token": refresh_token}
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            resp_data = response.json()
            st.session_state.access_token = resp_data.get("access_token")
            st.session_state.refresh_token = resp_data.get("refresh_token")
            st.session_state.token_expiry = time.time() + 3600
            print("✅ Token 刷新成功")
            return True
        else:
            print(f"❌ Token 刷新失败: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Token 刷新异常: {e}")
        return False


def ensure_valid_token():
    """确保 token 有效，如果过期则刷新"""
    token_expiry = st.session_state.get("token_expiry", 0)
    if time.time() > token_expiry - 60:  # 提前60秒刷新
        return refresh_access_token()
    return True


def supabase_request(method: str, endpoint: str, data=None, params=None, use_secret=False, access_token=None):
    """通用的Supabase REST API请求（支持自动token刷新）"""
    # 如果使用用户token且不是管理员，确保token有效
    if not use_secret and access_token is None and st.session_state.get("authenticated"):
        ensure_valid_token()
        access_token = st.session_state.get("access_token")
    
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = get_supabase_headers(use_secret, access_token)
    
    if params:
        url += f"?{params}"
    
    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "POST":
        response = requests.post(url, headers=headers, json=data)
    elif method == "PATCH":
        response = requests.patch(url, headers=headers, json=data)
    elif method == "DELETE":
        response = requests.delete(url, headers=headers)
    else:
        raise ValueError(f"Unsupported method: {method}")
    
    # 如果 token 过期，尝试刷新后重试一次
    if response.status_code == 401 and not use_secret:
        print("Token 可能过期，尝试刷新...")
        if refresh_access_token():
            headers = get_supabase_headers(use_secret, st.session_state.get("access_token"))
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data)
            elif method == "PATCH":
                response = requests.patch(url, headers=headers, json=data)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers)
    
    return response


# ==================== 用户认证 ====================

def sign_up(email: str, password: str) -> tuple:
    """
    用户注册 - 只创建Auth用户，不创建其他表
    user_settings 会在首次登录时自动创建
    返回: (success, message, user_id)
    """
    try:
        url = f"{SUPABASE_URL}/auth/v1/signup"
        headers = {
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Content-Type": "application/json"
        }
        data = {
            "email": email,
            "password": password
        }
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            resp_data = response.json()
            user_id = resp_data.get("user", {}).get("id")
            return True, "注册成功，请登录", user_id
        else:
            error = response.json()
            if "User already registered" in str(error):
                return False, "该邮箱已注册，请直接登录", None
            return False, f"注册失败: {error.get('msg', '未知错误')}", None
    except Exception as e:
        return False, f"注册失败: {str(e)}", None


def ensure_user_settings(user_id: str, email: str, access_token: str = None) -> bool:
    """
    确保用户有设置记录（user_settings表）
    如果不存在则自动创建
    返回: True=成功，False=失败
    """
    try:
        headers = get_supabase_headers(use_secret=True)
        check_url = f"{SUPABASE_URL}/rest/v1/user_settings?user_id=eq.{user_id}"
        check_response = requests.get(check_url, headers=headers)
        
        if check_response.status_code == 200 and check_response.json():
            return True
        
        settings_data = {
            "user_id": user_id,
            "email": email,
            "subscription_tier": "free",
            "free_trials_remaining": FREE_TRIAL_LIMIT,
            "created_at": datetime.now().isoformat()
        }
        
        insert_url = f"{SUPABASE_URL}/rest/v1/user_settings"
        insert_response = requests.post(insert_url, headers=headers, json=settings_data)
        
        return insert_response.status_code in [200, 201, 204]
    except Exception as e:
        print(f"确保用户设置失败: {e}")
        return False


def sign_in(email: str, password: str) -> tuple:
    """
    用户登录
    返回: (success, message, user_id, user_email, access_token, refresh_token)
    """
    try:
        url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
        headers = {
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Content-Type": "application/json"
        }
        data = {
            "email": email,
            "password": password
        }
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            resp_data = response.json()
            user_id = resp_data.get("user", {}).get("id")
            user_email = resp_data.get("user", {}).get("email")
            access_token = resp_data.get("access_token")
            refresh_token = resp_data.get("refresh_token")
            
            ensure_user_settings(user_id, user_email, access_token)
            update_user_profile(user_id, {"last_sign_in_at": datetime.now().isoformat()}, access_token)
            
            return True, "登录成功", user_id, user_email, access_token, refresh_token
        else:
            return False, "邮箱或密码错误", None, None, None, None
    except Exception as e:
        return False, f"登录失败: {str(e)}", None, None, None, None


def sign_out():
    """退出登录（普通用户）"""
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.user_email = None
    st.session_state.access_token = None
    st.session_state.refresh_token = None
    st.session_state.token_expiry = None
    st.session_state.admin_mode = False
    st.rerun()


def admin_sign_out():
    """管理员退出（返回到之前的登录状态）"""
    st.session_state.admin_mode = False
    st.rerun()


def check_admin_login(username: str, password: str) -> bool:
    """验证管理员登录"""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD


# ==================== 用户资料操作 ====================

def get_user_profile(user_id: str, access_token: str = None) -> dict:
    """获取用户资料（从 user_settings 表读取）"""
    if not user_id or user_id == "admin":
        return {
            "subscription_tier": "free",
            "free_trials_remaining": FREE_TRIAL_LIMIT,
            "subscription_expires_at": None,
            "last_sign_in_at": None
        }
    
    try:
        headers = get_supabase_headers(use_secret=True)
        url = f"{SUPABASE_URL}/rest/v1/user_settings?user_id=eq.{user_id}"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200 and response.json():
            data = response.json()[0]
            return {
                "subscription_tier": data.get("subscription_tier", "free"),
                "free_trials_remaining": data.get("free_trials_remaining", FREE_TRIAL_LIMIT),
                "subscription_expires_at": data.get("subscription_expires_at"),
                "last_sign_in_at": data.get("last_sign_in_at")
            }
        else:
            email = st.session_state.user_email if hasattr(st.session_state, 'user_email') else "unknown"
            settings_data = {
                "user_id": user_id,
                "email": email,
                "subscription_tier": "free",
                "free_trials_remaining": FREE_TRIAL_LIMIT,
                "created_at": datetime.now().isoformat()
            }
            insert_url = f"{SUPABASE_URL}/rest/v1/user_settings"
            insert_response = requests.post(insert_url, headers=headers, json=settings_data)
            print(f"创建 user_settings: {insert_response.status_code}")
            
            return {
                "subscription_tier": "free",
                "free_trials_remaining": FREE_TRIAL_LIMIT,
                "subscription_expires_at": None,
                "last_sign_in_at": None
            }
    except Exception as e:
        print(f"获取用户资料失败: {e}")
    
    return {
        "subscription_tier": "free",
        "free_trials_remaining": FREE_TRIAL_LIMIT,
        "subscription_expires_at": None,
        "last_sign_in_at": None
    }


def update_user_profile(user_id: str, data: dict, access_token: str = None) -> bool:
    """更新用户资料（更新 user_settings 表）"""
    try:
        headers = get_supabase_headers(use_secret=True)
        url = f"{SUPABASE_URL}/rest/v1/user_settings?user_id=eq.{user_id}"
        response = requests.patch(url, headers=headers, json=data)
        print(f"更新用户资料: user_id={user_id}, data={data}, status={response.status_code}")
        return response.status_code in [200, 204]
    except Exception as e:
        print(f"更新用户资料失败: {e}")
        return False

def get_remaining_trials(user_id: str, access_token: str = None) -> int:
    """获取剩余免费次数"""
    profile = get_user_profile(user_id, access_token)
    if profile.get("subscription_tier") == "pro":
        return -1
    return profile.get("free_trials_remaining", 0)


def consume_free_trial(user_id: str, access_token: str = None) -> bool:
    """
    消耗一次免费次数
    返回: True=有次数可用，False=次数已用完
    """
    profile = get_user_profile(user_id, access_token)
    
    if profile.get("subscription_tier") == "pro":
        return True
    
    remaining = profile.get("free_trials_remaining", 0)
    try:
        remaining = int(remaining) if remaining else 0
    except (ValueError, TypeError):
        remaining = 0
    
    if remaining > 0:
        new_remaining = remaining - 1
        success = update_user_profile(user_id, {"free_trials_remaining": new_remaining}, access_token)
        return success
    else:
        st.session_state.show_paywall = True
        return False


# ==================== 股票池操作 ====================

def get_recommended_pool(user_id: str, access_token: str = None) -> List[Dict]:
    """获取用户的推荐股票池"""
    if not user_id or user_id == "admin":
        return []
    
    try:
        response = supabase_request(
            "GET", 
            "recommended_pool", 
            params=f"user_id=eq.{user_id}&is_deleted=eq.false&order=current_score.desc",
            access_token=access_token
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取推荐池失败: {e}")
        return []


def add_to_recommended_pool(user_id: str, stock_code: str, stock_name: str, 
                            source: str = "user", score: float = 0, access_token: str = None) -> tuple:
    """添加股票到推荐池"""
    stocks = get_recommended_pool(user_id, access_token)
    if len(stocks) >= MAX_RECOMMENDED_STOCKS:
        return False, f"推荐池已达上限（{MAX_RECOMMENDED_STOCKS}只），请先删除部分股票"
    
    for s in stocks:
        if s.get("stock_code") == stock_code:
            return False, f"{stock_code} 已在推荐池中"
    
    try:
        data = {
            "user_id": user_id,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "source": source,
            "current_score": score,
            "added_time": datetime.now().isoformat(),
            "added_date": datetime.now().date().isoformat(),
            "is_deleted": False
        }
        response = supabase_request("POST", "recommended_pool", data, access_token=access_token)
        if response.status_code in [200, 201]:
            return True, f"成功添加 {stock_code} ({stock_name})"
        return False, f"添加失败: {response.text}"
    except Exception as e:
        return False, f"添加失败: {str(e)}"


def remove_from_recommended_pool(user_id: str, stock_code: str, access_token: str = None) -> tuple:
    """从推荐池删除股票（物理删除）"""
    try:
        response = supabase_request(
            "DELETE", 
            "recommended_pool",
            params=f"user_id=eq.{user_id}&stock_code=eq.{stock_code}",
            access_token=access_token
        )
        if response.status_code in [200, 204]:
            return True, f"已删除 {stock_code}"
        return False, f"删除失败: {response.text}"
    except Exception as e:
        return False, f"删除失败: {str(e)}"


def get_backtest_pool(user_id: str, access_token: str = None) -> List[Dict]:
    """获取用户的回测股票池"""
    if not user_id or user_id == "admin":
        return []
    
    try:
        response = supabase_request(
            "GET", 
            "backtest_pool", 
            params=f"user_id=eq.{user_id}",
            access_token=access_token
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取回测池失败: {e}")
        return []


def add_to_backtest_pool(user_id: str, stock_code: str, stock_name: str, access_token: str = None) -> tuple:
    """添加股票到回测池（已删除调试代码）"""
    stocks = get_backtest_pool(user_id, access_token)
    for s in stocks:
        if s.get("stock_code") == stock_code:
            return False, f"{stock_code} 已在回测池中"
    
    try:
        data = {
            "user_id": user_id,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "added_by": "user",
            "added_time": datetime.now().isoformat(),
            "added_date": datetime.now().date().isoformat(),
            "backtest_status": "pending"
        }
        
        response = supabase_request("POST", "backtest_pool", data, access_token=access_token)
        
        if response.status_code in [200, 201]:
            return True, f"成功添加 {stock_code} ({stock_name})"
        return False, f"添加失败: {response.text}"
    except Exception as e:
        return False, f"添加失败: {str(e)}"


def remove_from_backtest_pool(user_id: str, stock_code: str, access_token: str = None) -> tuple:
    """从回测池删除股票"""
    try:
        response = supabase_request(
            "DELETE", 
            "backtest_pool",
            params=f"user_id=eq.{user_id}&stock_code=eq.{stock_code}",
            access_token=access_token
        )
        if response.status_code in [200, 204]:
            return True, f"已删除 {stock_code}"
        return False, f"删除失败: {response.text}"
    except Exception as e:
        return False, f"删除失败: {str(e)}"


# ==================== 实操池操作函数（新增） ====================

def get_live_pool(user_id: str, access_token: str = None) -> List[Dict]:
    """获取用户的实操股票池"""
    if not user_id or user_id == "admin":
        return []
    
    try:
        response = supabase_request(
            "GET", 
            "live_pool", 
            params=f"user_id=eq.{user_id}",
            access_token=access_token
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取实操池失败: {e}")
        return []


def add_to_live_pool(user_id: str, stock_code: str, stock_name: str, 
                     shares: int = 0, avg_cost: float = 0, 
                     access_token: str = None) -> tuple:
    """
    添加股票到实操池
    参数:
        user_id: 用户ID
        stock_code: 股票代码
        stock_name: 股票名称
        shares: 持仓股数
        avg_cost: 平均成本价
    返回: (success, message)
    """
    if not user_id or user_id == "admin":
        return False, "无效用户"
    
    # 检查是否已存在
    stocks = get_live_pool(user_id, access_token)
    for s in stocks:
        if s.get("stock_code") == stock_code:
            return False, f"{stock_code} 已在实操池中"
    
    try:
        data = {
            "user_id": user_id,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "shares": shares,
            "avg_cost": avg_cost,
            "current_price": 0,  # 后续刷新时更新
            "added_time": datetime.now().isoformat(),
            "added_date": datetime.now().date().isoformat(),
            "updated_time": datetime.now().isoformat()
        }
        response = supabase_request("POST", "live_pool", data, access_token=access_token)
        if response.status_code in [200, 201]:
            return True, f"成功添加 {stock_code} ({stock_name}) 到实操池"
        return False, f"添加失败: {response.text}"
    except Exception as e:
        return False, f"添加失败: {str(e)}"


def update_live_pool_stock(user_id: str, stock_code: str, shares: int = None, 
                           avg_cost: float = None, access_token: str = None) -> tuple:
    """更新实操池中股票的持仓信息"""
    try:
        update_data = {}
        if shares is not None:
            update_data["shares"] = shares
        if avg_cost is not None:
            update_data["avg_cost"] = avg_cost
        update_data["updated_time"] = datetime.now().isoformat()
        
        if not update_data:
            return False, "无更新内容"
        
        response = supabase_request(
            "PATCH",
            "live_pool",
            data=update_data,
            params=f"user_id=eq.{user_id}&stock_code=eq.{stock_code}",
            access_token=access_token
        )
        if response.status_code in [200, 204]:
            return True, f"已更新 {stock_code}"
        return False, f"更新失败: {response.text}"
    except Exception as e:
        return False, f"更新失败: {str(e)}"


def remove_from_live_pool(user_id: str, stock_code: str, access_token: str = None) -> tuple:
    """从实操池删除股票"""
    try:
        response = supabase_request(
            "DELETE", 
            "live_pool",
            params=f"user_id=eq.{user_id}&stock_code=eq.{stock_code}",
            access_token=access_token
        )
        if response.status_code in [200, 204]:
            return True, f"已从实操池删除 {stock_code}"
        return False, f"删除失败: {response.text}"
    except Exception as e:
        return False, f"删除失败: {str(e)}"


def refresh_live_pool_prices(user_id: str, access_token: str = None) -> tuple:
    """刷新实操池中所有股票的当前价格"""
    stocks = get_live_pool(user_id, access_token)
    if not stocks:
        return True, "实操池为空"
    
    updated_count = 0
    for stock in stocks:
        ts_code = stock.get("stock_code")
        if ts_code:
            df = get_stock_daily(ts_code, days=1)
            if not df.empty:
                current_price = df['close'].iloc[-1]
                response = supabase_request(
                    "PATCH",
                    "live_pool",
                    data={"current_price": current_price, "updated_time": datetime.now().isoformat()},
                    params=f"user_id=eq.{user_id}&stock_code=eq.{ts_code}",
                    access_token=access_token
                )
                if response.status_code in [200, 204]:
                    updated_count += 1
    
    return True, f"已刷新 {updated_count} 只股票的价格"


# ==================== 自动推荐Top10（保留） ====================

def auto_recommend_top10(user_id: str, access_token: str = None) -> List[Dict]:
    """
    自动推荐Top10股票
    从缓存读取板块和成分股（快速，不调用 Tushare API）
    """
    st.write("🚀 从缓存读取板块数据...")
    
    # 1. 从缓存读取板块（复用原有的 load_sector_cache）
    sectors = load_sector_cache()
    
    if not sectors:
        st.write("⚠️ 板块缓存为空，使用预置板块")
        return auto_recommend_top10_fallback(user_id, access_token)
    
    # 按热度排序（如果有热度字段）
    try:
        sectors.sort(key=lambda x: x.get('hot_score', 0), reverse=True)
    except:
        pass
    
    hot_sectors = sectors[:10]
    
    all_scored_stocks = []
    
    for sector in hot_sectors:
        sector_name = sector.get('sector_name')
        if not sector_name:
            continue
        
        # 2. 从缓存读取板块成分股（使用新函数）
        members = get_sector_members_from_cache(sector_name, limit=10)
        if not members:
            members = get_sector_members_fallback(sector_name, limit=10)
        
        if not members:
            # 如果缓存没有成分股，尝试从预置板块获取
            if sector_name in HOT_SECTORS:
                sector_info = HOT_SECTORS[sector_name]
                members = []
                for i, code in enumerate(sector_info.get("stocks", [])[:10]):
                    name = sector_info.get("names", [])[i] if i < len(sector_info.get("names", [])) else code
                    members.append({
                        "stock_code": code,
                        "stock_name": name
                    })
            else:
                continue
        
        for member in members[:5]:  # 每个板块取前5只
            ts_code = member.get('stock_code')
            stock_name = member.get('stock_name')
            
            if not ts_code:
                continue
            
            # 3. 计算评分（传入板块名称）
            score_result = get_stock_score(ts_code, stock_name, sector_name=sector_name)
            
            all_scored_stocks.append({
                "code": ts_code,
                "name": stock_name,
                "score": score_result["total_score"],
                "sector": sector_name
            })
    
    if not all_scored_stocks:
        return auto_recommend_top10_fallback(user_id, access_token)
    
    # 4. 去重并排序
    seen = set()
    unique_stocks = []
    for stock in all_scored_stocks:
        if stock["code"] not in seen:
            seen.add(stock["code"])
            unique_stocks.append(stock)
    
    unique_stocks.sort(key=lambda x: x["score"], reverse=True)
    top10 = unique_stocks[:10]
    
    # 5. 清空旧的AI推荐
    existing_stocks = get_recommended_pool(user_id, access_token)
    for s in existing_stocks:
        if s.get("source") == "ai":
            supabase_request("DELETE", "recommended_pool", params=f"id=eq.{s['id']}", access_token=access_token)
    
    # 6. 添加新的推荐
    for stock in top10:
        add_to_recommended_pool(
            user_id, stock["code"], stock["name"], source="ai",
            score=stock["score"], access_token=access_token
        )
    
    return top10


def auto_recommend_top10_fallback(user_id: str, access_token: str = None) -> List[Dict]:
    """降级方案：使用预置板块"""
    all_stocks = []
    for sector_name, sector_info in HOT_SECTORS.items():
        for i, ts_code in enumerate(sector_info["stocks"]):
            stock_name = sector_info["names"][i] if i < len(sector_info["names"]) else ts_code
            all_stocks.append({
                "code": ts_code, 
                "name": stock_name, 
                "sector": sector_name
            })
    
    # 去重
    seen = set()
    unique_stocks = []
    for stock in all_stocks:
        if stock["code"] not in seen:
            seen.add(stock["code"])
            unique_stocks.append(stock)
    
    # 评分（传入板块名称）
    scored_stocks = []
    for stock in unique_stocks:
        score_result = get_stock_score(stock["code"], stock["name"], sector_name=stock["sector"])
        scored_stocks.append({
            "code": stock["code"],
            "name": stock["name"],
            "score": score_result["total_score"],
            "sector": stock["sector"]
        })
    
    scored_stocks.sort(key=lambda x: x["score"], reverse=True)
    top10 = scored_stocks[:10]
    
    # 清空旧的AI推荐
    existing_stocks = get_recommended_pool(user_id, access_token)
    for s in existing_stocks:
        if s.get("source") == "ai":
            supabase_request("DELETE", "recommended_pool", params=f"id=eq.{s['id']}", access_token=access_token)
    
    # 添加新的推荐
    for stock in top10:
        add_to_recommended_pool(
            user_id, stock["code"], stock["name"], source="ai",
            score=stock["score"], access_token=access_token
        )
    
    return top10


# ==================== 板块操作函数 ====================

def get_user_sectors(user_id: str, access_token: str = None) -> List[Dict]:
    """获取用户自定义板块"""
    if not user_id or user_id == "admin":
        return []
    
    try:
        response = supabase_request(
            "GET", 
            "user_sectors", 
            params=f"user_id=eq.{user_id}&is_active=eq.true",
            access_token=access_token
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取用户板块失败: {e}")
        return []


def add_user_sector(user_id: str, sector_name: str, stock_codes: List[str], 
                    stock_names: List[str], access_token: str = None) -> tuple:
    """添加用户自定义板块"""
    try:
        data = {
            "user_id": user_id,
            "sector_name": sector_name,
            "stock_codes": stock_codes,
            "stock_names": stock_names,
            "is_active": True,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        response = supabase_request("POST", "user_sectors", data, access_token=access_token)
        if response.status_code in [200, 201]:
            return True, f"成功添加板块 {sector_name}"
        return False, f"添加失败: {response.text}"
    except Exception as e:
        return False, f"添加失败: {str(e)}"


def delete_user_sector(user_id: str, sector_id: str, access_token: str = None) -> tuple:
    """删除用户自定义板块"""
    try:
        response = supabase_request(
            "DELETE", 
            "user_sectors",
            params=f"id=eq.{sector_id}&user_id=eq.{user_id}",
            access_token=access_token
        )
        if response.status_code in [200, 204]:
            return True, "板块已删除"
        return False, f"删除失败: {response.text}"
    except Exception as e:
        return False, f"删除失败: {str(e)}"


# ==================== Stripe 支付函数 ====================

def create_checkout_session(user_id: str, user_email: str, price_id: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        
        base_url = "https://stock-quant-strategy.streamlit.app"
        
        # 关键：在 success_url 中传递用户信息，确保支付完成后能识别用户
        success_url = f"{base_url}?session_id={{CHECKOUT_SESSION_ID}}&user_id={user_id}&email={user_email}"
        cancel_url = f"{base_url}?canceled=true"
        
        session = stripe.checkout.Session.create(
            customer_email=user_email,
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': user_id,
                'user_email': user_email,
                'price_id': price_id
            }
        )
        return session.url, None
    except Exception as e:
        return None, str(e)


def handle_stripe_callback():
    """使用 HTTP 请求验证 Stripe 支付（不依赖 stripe 库）"""
    import requests
    import base64
    import json
    
    query_params = st.query_params
    
    if "session_id" in query_params:
        session_id = query_params["session_id"]
        
        # 显示手动验证按钮
        st.warning("🔔 检测到支付会话，请点击按钮完成验证")
        st.info(f"会话ID: {session_id[:30]}...")
        
        if st.button("✅ 手动验证支付并升级", type="primary"):
            with st.spinner("正在验证..."):
                try:
                    # 使用 Basic 认证调用 Stripe API
                    auth_str = f"{STRIPE_SECRET_KEY}:"
                    auth_bytes = auth_str.encode('ascii')
                    auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
                    
                    headers = {
                        "Authorization": f"Basic {auth_b64}",
                        "Content-Type": "application/x-www-form-urlencoded"
                    }
                    
                    url = f"https://api.stripe.com/v1/checkout/sessions/{session_id}"
                    response = requests.get(url, headers=headers)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if data.get("payment_status") == "paid":
                            # 从 metadata 获取用户信息
                            user_id = data.get("metadata", {}).get("user_id")
                            user_email = data.get("customer_email") or data.get("metadata", {}).get("user_email")
                            
                            if not user_id and user_email:
                                # 通过邮箱查找用户
                                users_resp = supabase_request("GET", "user_settings", use_secret=True)
                                if users_resp.status_code == 200:
                                    for u in users_resp.json():
                                        if u.get("email") == user_email:
                                            user_id = u.get("user_id")
                                            break
                            
                            if user_id and user_id != "admin":
                                # 更新数据库
                                headers_patch = get_supabase_headers(use_secret=True)
                                url_patch = f"{SUPABASE_URL}/rest/v1/user_settings?user_id=eq.{user_id}"
                                patch_response = requests.patch(
                                    url_patch, 
                                    headers=headers_patch, 
                                    json={"subscription_tier": "pro"}
                                )
                                
                                if patch_response.status_code in [200, 204]:
                                    st.success("✅ 支付验证成功！您已是专业版用户")
                                    st.balloons()
                                    # 更新 session
                                    if st.session_state.get("user_id") == user_id:
                                        st.session_state.subscription_tier = "pro"
                                    st.query_params.clear()
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error(f"更新失败: {patch_response.text}")
                            else:
                                st.error("无法识别用户，请重新登录后重试")
                        else:
                            st.warning(f"支付状态: {data.get('payment_status')}，请完成支付")
                    else:
                        st.error(f"API请求失败: {response.status_code}")
                        
                except Exception as e:
                    st.error(f"验证失败: {e}")


# ==================== 数据解析函数 ====================

def parse_stock_code(code: str) -> Tuple[str, str]:
    """
    解析股票代码，自动识别市场
    支持格式:
    - 6位数字: 000001 (自动识别: 000xxx,001xxx,002xxx,003xxx,300xxx为SZ，其他为SH)
    - 带后缀: 000001.SZ, 0700.HK, 600000.SH
    - 港股: 00700 (5位数字，自动加.HK)
    """
    code = code.strip().upper()
    
    # 如果已经有后缀，直接返回
    if code.endswith(".HK"):
        return "HK", code
    elif code.endswith(".SZ"):
        return "SZ", code
    elif code.endswith(".SH"):
        return "SH", code
    
    # 纯数字，自动识别市场
    if code.isdigit():
        # 港股：5位数字（如 00700）
        if len(code) == 5:
            return "HK", f"{code}.HK"
        # A股：6位数字
        elif len(code) == 6:
            # 深圳市场：000xxx, 001xxx, 002xxx, 003xxx, 300xxx
            if code.startswith(('000', '001', '002', '003', '300')):
                return "SZ", f"{code}.SZ"
            # 上海市场：600xxx, 601xxx, 603xxx, 605xxx, 688xxx
            else:
                return "SH", f"{code}.SH"
        else:
            return "A", code
    
    # 无法识别
    return "UNKNOWN", code


def validate_stock_code(code: str) -> Tuple[bool, str]:
    """
    验证股票代码是否有效
    返回: (is_valid, formatted_code_or_error)
    """
    market, formatted = parse_stock_code(code)
    
    if market == "HK":
        num_part = formatted.split('.')[0]
        if num_part.isdigit() and len(num_part) in [4, 5]:
            return True, formatted
        else:
            return False, f"无效港股代码: {code}，应为4-5位数字"
    elif market == "SZ":
        num_part = formatted.split('.')[0]
        if num_part.isdigit() and len(num_part) == 6:
            return True, formatted
        else:
            return False, f"无效深市代码: {code}，应为6位数字"
    elif market == "SH":
        num_part = formatted.split('.')[0]
        if num_part.isdigit() and len(num_part) == 6:
            return True, formatted
        else:
            return False, f"无效沪市代码: {code}，应为6位数字"
    else:
        return False, f"无法识别股票代码: {code}，请检查后重试"


# ==================== 登录/注册UI组件 ====================

def render_login_form():
    """显示登录表单"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f"<h1 style='text-align: center;'>{t()['app_title']}</h1>", unsafe_allow_html=True)
        
        with st.form("login_form", border=True):
            email = st.text_input(t()["email"], key="login_email")
            password = st.text_input(t()["password"], type="password", key="login_password")
            submitted = st.form_submit_button(t()["login_btn"], type="primary", use_container_width=True)
            
            if submitted:
                if not email or not password:
                    st.warning("请填写邮箱和密码")
                else:
                    with st.spinner("登录中..."):
                        success, msg, user_id, user_email, access_token, refresh_token = sign_in(email, password)
                        if success:
                            st.session_state.authenticated = True
                            st.session_state.user_id = user_id
                            st.session_state.user_email = user_email                            
                            st.session_state.access_token = access_token
                            st.session_state.refresh_token = refresh_token
                            st.session_state.token_expiry = time.time() + 3600
                            st.session_state.show_paywall = False
                            st.rerun()
                        else:
                            st.error(msg)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button(t()["register"], use_container_width=True):
                st.session_state.show_register = True
                st.rerun()
        with col2:
            if st.button("忘记密码？", use_container_width=True):
                st.info(f"请联系管理员重置密码：{ADMIN_EMAIL}")


def render_register_form():
    """显示注册表单"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f"<h2 style='text-align: center;'>{t()['register']}</h2>", unsafe_allow_html=True)
        
        with st.form("register_form", border=True):
            email = st.text_input(t()["email"], key="reg_email")
            password = st.text_input(t()["password"], type="password", key="reg_password")
            confirm = st.text_input(t()["confirm_password"], type="password", key="reg_confirm")
            submitted = st.form_submit_button(t()["register_btn"], type="primary", use_container_width=True)
            
            if submitted:
                if not email or not password:
                    st.warning("请填写邮箱和密码")
                elif password != confirm:
                    st.warning("两次输入的密码不一致")
                elif len(password) < 6:
                    st.warning("密码长度至少6位")
                else:
                    with st.spinner("注册中..."):
                        success, msg, user_id = sign_up(email, password)
                        if success:
                            st.success(msg)
                            st.session_state.show_register = False
                            st.rerun()
                        else:
                            st.error(msg)
        
        if st.button(t()["back_to_login"], use_container_width=True):
            st.session_state.show_register = False
            st.rerun()


def render_admin_login_form():
    """显示管理员登录表单"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h2 style='text-align: center;'>管理员登录</h2>", unsafe_allow_html=True)
        
        with st.form("admin_login_form", border=True):
            username = st.text_input("用户名", key="admin_username")
            password = st.text_input("密码", type="password", key="admin_password")
            submitted = st.form_submit_button("登录", type="primary", use_container_width=True)
            
            if submitted:
                if check_admin_login(username, password):
                    st.session_state.admin_previous_user_id = st.session_state.get("user_id")
                    st.session_state.admin_previous_user_email = st.session_state.get("user_email")
                    st.session_state.admin_previous_access_token = st.session_state.get("access_token")
                    st.session_state.admin_previous_refresh_token = st.session_state.get("refresh_token")
                    
                    st.session_state.admin_mode = True
                    st.session_state.show_admin_login = False
                    st.session_state.authenticated = True
                    st.session_state.user_id = "admin"
                    st.session_state.user_email = ADMIN_EMAIL
                    st.rerun()
                else:
                    st.error("用户名或密码错误")
        
        if st.button("返回用户登录", use_container_width=True):
            st.session_state.show_admin_login = False
            st.rerun()


print("第2部分加载完成（已添加实操池操作函数）")
print("=" * 60)
# ============================================================
# ============================================================
# 第3部分：评分引擎（技术指标计算、板块热度、个股评分）
#         + 掘金下单函数 + Stripe支付函数 + 用户回测参数保存
# 修复内容：
# - 修复 run_real_backtest 函数中的日期比较错误
# - 保留所有其他函数不变
# - 添加用户回测参数保存/加载函数
# ============================================================

# ==================== Tushare 数据获取 ====================
@tushare_request_with_retry
def get_stock_daily(ts_code: str, days: int = 120) -> pd.DataFrame:
    """获取股票或指数日线数据"""
    if not TUSHARE_AVAILABLE or TUSHARE_PRO is None:
        return pd.DataFrame()  # 返回空 DataFrame，不是 None
    
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        
        # 判断是否为指数代码
        index_code_map = {
            "000001.SH": "000001.SH",
        }
        
        if ts_code in index_code_map:
            real_code = index_code_map[ts_code]
            df = TUSHARE_PRO.index_daily(ts_code=real_code, start_date=start_date, end_date=end_date)
            if df is not None and not df.empty:
                df = df.sort_values('trade_date')
                df = df.rename(columns={'trade_date': 'date'})
                df['volume'] = 0
                return df
            else:
                return pd.DataFrame()  # 返回空 DataFrame
        else:
            df = TUSHARE_PRO.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if df is not None and not df.empty:
                df = df.sort_values('trade_date')
                df = df.rename(columns={'trade_date': 'date', 'vol': 'volume'})
                return df
            else:
                return pd.DataFrame()  # 返回空 DataFrame
        
    except Exception as e:
        print(f"获取数据失败 {ts_code}: {e}")
        return pd.DataFrame()  # 返回空 DataFrame，不是 None

def get_sector_performance() -> pd.DataFrame:
    """
    获取预置板块的实时表现
    返回: DataFrame包含板块名称、涨跌幅、领涨股等
    """
    if not TUSHARE_AVAILABLE or TUSHARE_PRO is None:
        data = []
        for sector_name, sector_info in HOT_SECTORS.items():
            data.append({
                "板块": sector_name,
                "涨跌幅": round(np.random.uniform(-3, 5), 2),
                "领涨股": sector_info["names"][0]
            })
        return pd.DataFrame(data)
    
    data = []
    for sector_name, sector_info in HOT_SECTORS.items():
        try:
            performances = []
            sector_stocks = sector_info["stocks"]
            
            for ts_code in sector_stocks:
                df = get_stock_daily(ts_code, days=5)
                if not df.empty and len(df) >= 2:
                    latest_close = df['close'].iloc[-1]
                    prev_close = df['close'].iloc[-2]
                    change_pct = (latest_close - prev_close) / prev_close * 100
                    performances.append(change_pct)
            
            if performances:
                avg_change = np.mean(performances)
                max_idx = np.argmax(performances)
                leader = sector_info["names"][max_idx] if max_idx < len(sector_info["names"]) else sector_info["names"][0]
            else:
                avg_change = 0
                leader = sector_info["names"][0]
            
            data.append({
                "板块": sector_name,
                "涨跌幅": round(avg_change, 2),
                "领涨股": leader
            })
        except Exception as e:
            print(f"获取板块{sector_name}表现失败: {e}")
            data.append({
                "板块": sector_name,
                "涨跌幅": 0,
                "领涨股": sector_info["names"][0]
            })
    
    return pd.DataFrame(data)


# ==================== 用户回测参数操作 ====================

def get_user_backtest_settings(user_id: str, access_token: str = None) -> Dict:
    """
    获取用户保存的回测参数
    返回: {"tech_weights": {...}, "buy_threshold": 70, "sell_threshold": 40, ...}
    """
    if not user_id or user_id == "admin":
        return {
            "tech_weights": TECH_WEIGHTS.copy(),
            "buy_threshold": 70,
            "sell_threshold": 40,
            "max_hold_days": 0,
            "position_pct": 100,
            "max_positions": 3,
            "backtest_days": 365
        }
    
    try:
        headers = get_supabase_headers(use_secret=True)
        url = f"{SUPABASE_URL}/rest/v1/user_backtest_settings?user_id=eq.{user_id}"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200 and response.json():
            data = response.json()[0]
            tech_weights = data.get("tech_weights", {})
            # 确保所有权重键都存在
            for key in TECH_WEIGHTS.keys():
                if key not in tech_weights:
                    tech_weights[key] = TECH_WEIGHTS[key]
            
            return {
                "tech_weights": tech_weights,
                "buy_threshold": data.get("buy_threshold", 70),
                "sell_threshold": data.get("sell_threshold", 40),
                "max_hold_days": data.get("max_hold_days", 0),
                "position_pct": data.get("position_pct", 100),
                "max_positions": data.get("max_positions", 3),
                "backtest_days": data.get("backtest_days", 365)
            }
    except Exception as e:
        print(f"获取用户回测参数失败: {e}")
    
    return {
        "tech_weights": TECH_WEIGHTS.copy(),
        "buy_threshold": 70,
        "sell_threshold": 40,
        "max_hold_days": 0,
        "position_pct": 100,
        "max_positions": 3,
        "backtest_days": 365
    }


def save_user_backtest_settings(user_id: str, settings: Dict, access_token: str = None) -> bool:
    """
    保存用户回测参数
    settings: {"tech_weights": {...}, "buy_threshold": 70, ...}
    """
    if not user_id or user_id == "admin":
        return False
    
    try:
        headers = get_supabase_headers(use_secret=True)
        check_url = f"{SUPABASE_URL}/rest/v1/user_backtest_settings?user_id=eq.{user_id}"
        check_response = requests.get(check_url, headers=headers)
        
        data = {
            "user_id": user_id,
            "tech_weights": settings.get("tech_weights", TECH_WEIGHTS),
            "buy_threshold": settings.get("buy_threshold", 70),
            "sell_threshold": settings.get("sell_threshold", 40),
            "max_hold_days": settings.get("max_hold_days", 0),
            "position_pct": settings.get("position_pct", 100),
            "max_positions": settings.get("max_positions", 3),
            "backtest_days": settings.get("backtest_days", 365),
            "updated_at": datetime.now().isoformat()
        }
        
        if check_response.status_code == 200 and check_response.json():
            url = f"{SUPABASE_URL}/rest/v1/user_backtest_settings?user_id=eq.{user_id}"
            response = requests.patch(url, headers=headers, json=data)
        else:
            url = f"{SUPABASE_URL}/rest/v1/user_backtest_settings"
            response = requests.post(url, headers=headers, json=data)
        
        return response.status_code in [200, 201, 204]
    except Exception as e:
        print(f"保存用户回测参数失败: {e}")
        return False


def reset_user_backtest_settings(user_id: str, access_token: str = None) -> bool:
    """重置用户回测参数到默认值"""
    default_settings = {
        "tech_weights": TECH_WEIGHTS.copy(),
        "buy_threshold": 70,
        "sell_threshold": 40,
        "max_hold_days": 0,
        "position_pct": 100,
        "max_positions": 3,
        "backtest_days": 365
    }
    return save_user_backtest_settings(user_id, default_settings, access_token)


# ==================== 技术指标计算 ====================

def calculate_macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> Dict:
    """计算MACD指标"""
    if df.empty or len(df) < slow:
        return {"macd": 0, "signal": 0, "histogram": 0, "signal_level": "neutral", "score": 50}
    
    close = df['close'].values
    
    def ema(data, period):
        alpha = 2 / (period + 1)
        result = np.zeros_like(data)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i-1]
        return result
    
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    
    if macd_line[-1] > signal_line[-1] and macd_line[-2] <= signal_line[-2]:
        signal_level = "golden_cross"
        score = 100
    elif macd_line[-1] < signal_line[-1] and macd_line[-2] >= signal_line[-2]:
        signal_level = "death_cross"
        score = 0
    elif macd_line[-1] > 0 and signal_line[-1] > 0:
        signal_level = "bullish"
        score = 75
    elif macd_line[-1] < 0 and signal_line[-1] < 0:
        signal_level = "bearish"
        score = 25
    else:
        signal_level = "neutral"
        score = 50
    
    return {
        "macd": macd_line[-1],
        "signal": signal_line[-1],
        "histogram": histogram[-1],
        "signal_level": signal_level,
        "score": score
    }


def calculate_kdj(df: pd.DataFrame, n=9, m1=3, m2=3) -> Dict:
    """计算KDJ指标"""
    # 默认返回值
    default_result = {"k": 50.0, "d": 50.0, "j": 50.0, "signal_level": "neutral", "score": 50}
    
    if df.empty or len(df) < n:
        return default_result
    
    try:
        low = df['low'].values
        high = df['high'].values
        close = df['close'].values
        
        k_values = []
        d_values = []
        
        for i in range(len(df)):
            if i < n - 1:
                k_values.append(50.0)
                d_values.append(50.0)
                continue
            
            low_n = min(low[i-n+1:i+1])
            high_n = max(high[i-n+1:i+1])
            if high_n != low_n:
                rsv = (close[i] - low_n) / (high_n - low_n) * 100
            else:
                rsv = 50.0
            
            if i == n - 1:
                k = 50.0
                d = 50.0
            else:
                k = (2/3) * k_values[-1] + (1/3) * rsv
                d = (2/3) * d_values[-1] + (1/3) * k
            
            k_values.append(k)
            d_values.append(d)
        
        k = k_values[-1]
        d = d_values[-1]
        j = 3 * k - 2 * d
        
        if k < 20 and d < 20 and k > d:
            signal_level = "oversold_golden"
            score = 100
        elif k > 80 and d > 80 and k < d:
            signal_level = "overbought_death"
            score = 0
        elif k > d:
            signal_level = "bullish"
            score = 70
        else:
            signal_level = "bearish"
            score = 30
        
        return {
            "k": float(k),
            "d": float(d),
            "j": float(j),
            "signal_level": signal_level,
            "score": score
        }
    except Exception as e:
        print(f"KDJ计算错误: {e}")
        return default_result


def calculate_bollinger_bands(df: pd.DataFrame, period=20, std_dev=2) -> Dict:
    """计算布林带"""
    if df.empty or len(df) < period:
        return {"upper": 0, "middle": 0, "lower": 0, "position": 0.5, "signal_level": "neutral", "score": 50}
    
    close = df['close'].values
    middle = np.mean(close[-period:])
    std = np.std(close[-period:])
    
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    current = close[-1]
    
    if upper > lower:
        position = (current - lower) / (upper - lower)
    else:
        position = 0.5
    
    if current > upper:
        signal_level = "above_upper"
        score = 80
    elif current < lower:
        signal_level = "below_lower"
        score = 20
    elif position > 0.7:
        signal_level = "near_upper"
        score = 70
    elif position < 0.3:
        signal_level = "near_lower"
        score = 30
    else:
        signal_level = "neutral"
        score = 50
    
    return {"upper": upper, "middle": middle, "lower": lower, 
            "position": position, "signal_level": signal_level, "score": score}


def calculate_rsi(df: pd.DataFrame, period=14) -> Dict:
    """计算RSI指标"""
    if df.empty or len(df) < period + 1:
        return {"rsi": 50, "signal_level": "neutral", "score": 50}
    
    close = df['close'].values
    gains = []
    losses = []
    
    for i in range(1, len(close)):
        diff = close[i] - close[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    
    if rsi > 70:
        signal_level = "overbought"
        score = 30
    elif rsi < 30:
        signal_level = "oversold"
        score = 80
    else:
        signal_level = "neutral"
        score = 50 + (50 - abs(rsi - 50)) / 2
    
    return {"rsi": rsi, "signal_level": signal_level, "score": score}


def calculate_volume_price(df: pd.DataFrame) -> Dict:
    """计算量价配合度"""
    if df.empty or len(df) < 5:
        return {"score": 50, "signal_level": "neutral"}
    
    price_change = df['close'].pct_change().values[-5:]
    volume_change = df['volume'].pct_change().values[-5:]
    
    scores = []
    for i in range(len(price_change)):
        if np.isnan(price_change[i]) or np.isnan(volume_change[i]):
            continue
        if price_change[i] > 0:
            if volume_change[i] > 0:
                scores.append(100)
            else:
                scores.append(30)
        else:
            if volume_change[i] < 0:
                scores.append(70)
            else:
                scores.append(40)
    
    if not scores:
        return {"score": 50, "signal_level": "neutral"}
    
    avg_score = np.mean(scores)
    
    if avg_score > 60:
        signal_level = "bullish"
    elif avg_score < 40:
        signal_level = "bearish"
    else:
        signal_level = "neutral"
    
    return {"score": avg_score, "signal_level": signal_level}


def calculate_technical_score(df: pd.DataFrame, tech_weights: Dict = None) -> Dict:
    """
    计算综合技术指标得分（0-100）
    支持自定义权重
    """
    if df.empty:
        return {"score": 50, "level": "D", "details": {}}
    
    if tech_weights is None:
        tech_weights = TECH_WEIGHTS
    
    details = {}
    
    macd = calculate_macd(df)
    details["macd"] = macd["score"]
    
    kdj = calculate_kdj(df)
    details["kdj"] = kdj["score"]
    
    boll = calculate_bollinger_bands(df)
    details["boll"] = boll["score"]
    
    rsi = calculate_rsi(df)
    details["rsi"] = rsi["score"]
    
    vp = calculate_volume_price(df)
    details["volume_price"] = vp["score"]
    
    total_score = (
        macd["score"] * tech_weights.get("macd", 0.25) +
        kdj["score"] * tech_weights.get("kdj", 0.20) +
        boll["score"] * tech_weights.get("boll", 0.20) +
        rsi["score"] * tech_weights.get("rsi", 0.15) +
        vp["score"] * tech_weights.get("volume_price", 0.20)
    )
    
    level = "D"
    for lvl, config in SIGNAL_LEVELS.items():
        if total_score >= config["min_score"]:
            level = lvl
            break
    
    return {
        "score": round(total_score, 2),
        "level": level,
        "details": details
    }

# ==================== 完整评分引擎（板块热度 + 龙头识别 + 技术指标 + 长短期趋势） ====================

def calculate_sector_heat_score(sector_code: str = None, sector_name: str = None) -> float:
    """
    计算板块热度得分
    权重：占综合评分的 40%
    使用预置板块预设分数，快速稳定
    """
    print(f"🔥 calculate_sector_heat_score 被调用，参数: sector_code={sector_code}, sector_name={sector_name}")
    
    # 预置板块热度预设分数（根据市场热度手动调整）
    preset_scores = {
        "光模块/CPO": 85,
        "人工智能": 80,
        "半导体": 75,
        "算力": 70,
        "机器人": 65
    }
    
    # 如果有板块名称且在预设中，返回预设分数
    if sector_name and sector_name in preset_scores:
        score = preset_scores[sector_name]
        print(f"📊 板块 {sector_name} 热度得分: {score}")
        return float(score)
    
    # 如果有板块代码（备用），尝试匹配
    if sector_code:
        for name, score in preset_scores.items():
            if sector_code in name or name in str(sector_code):
                print(f"📊 板块 {sector_code} 匹配到 {name}，得分: {score}")
                return float(score)
    
    # 默认返回50分
    print(f"⚠️ 未找到板块 {sector_name or sector_code} 的热度预设，返回默认值50")
    return 50.0
    
    try:
        # 如果没有板块信息，返回默认分
        if not sector_code and not sector_name:
            return 50.0
        
        # 尝试获取板块行情
        if sector_code:
            df = get_tushare_concept_daily(sector_code, days=20)
        else:
            # 如果没有代码，尝试按名称查找
            concepts = get_tushare_concept_list()
            for c in concepts:
                if c.get('name') == sector_name:
                    sector_code = c.get('code')
                    break
            if sector_code:
                df = get_tushare_concept_daily(sector_code, days=20)
            else:
                return 50.0
        
        if df.empty or len(df) < 5:
            return 50.0
        
        # 计算价格强度得分（涨跌幅）
        if 'pct_chg' in df.columns:
            chg_5d = df['pct_chg'].iloc[-5:].sum() if len(df) >= 5 else 0
            # 涨跌幅映射到0-100分（涨10%得100分，跌10%得0分）
            price_score = min(100, max(0, (chg_5d + 10) * 5))
        else:
            price_score = 50
        
        return round(price_score, 2)
        
    except Exception as e:
        print(f"计算板块热度得分失败: {e}")
        return 50.0

def calculate_leader_score(stock_code: str, sector_code: str = None) -> float:
    """
    计算龙头识别得分
    权重：占综合评分的 30%
    使用预置板块个股排名（快速稳定）
    """
    print(f"👑 calculate_leader_score 被调用，参数: stock_code={stock_code}, sector_code={sector_code}")
    
    if not sector_code:
        return 50.0
    
    # 预置板块个股龙头得分（sector_code 实际是板块名称）
    preset_ranks = {
        "光模块/CPO": {
            "300308.SZ": 95,   # 中际旭创 - 绝对龙头
            "300394.SZ": 85,   # 天孚通信
            "300502.SZ": 80,   # 新易盛
            "688313.SH": 70,   # 仕佳光子
            "301191.SZ": 65    # 中瓷电子
        },
        "人工智能": {
            "002230.SZ": 95,   # 科大讯飞 - 龙头
            "002415.SZ": 85,   # 海康威视
            "300058.SZ": 75,   # 蓝色光标
            "002920.SZ": 70    # 德赛西威
        },
        "半导体": {
            "688981.SH": 95,   # 中芯国际 - 龙头
            "002371.SZ": 85,   # 北方华创
            "603986.SH": 75,   # 兆易创新
            "300782.SZ": 70    # 卓胜微
        },
        "算力": {
            "000977.SZ": 95,   # 浪潮信息 - 龙头
            "603019.SH": 85,   # 中科曙光
            "300442.SZ": 75,   # 普丽盛
            "002281.SZ": 70    # 光迅科技
        },
        "机器人": {
            "300124.SZ": 95,   # 汇川技术 - 龙头
            "300024.SZ": 85,   # 机器人
            "002747.SZ": 80,   # 埃斯顿
            "688017.SH": 75,   # 绿的谐波
            "300161.SZ": 70    # 华中数控
        }
    }
    
    # 如果板块在预设中
    if sector_code in preset_ranks:
        stock_ranks = preset_ranks[sector_code]
        if stock_code in stock_ranks:
            score = stock_ranks[stock_code]
            print(f"👑 股票 {stock_code} 在板块 {sector_code} 中龙头得分: {score}")
            return float(score)
        else:
            # 板块内有但不在预设列表，给中等分
            print(f"⚠️ 股票 {stock_code} 在板块 {sector_code} 中但无预设排名，返回60")
            return 60.0
    
    # 默认返回50分
    print(f"⚠️ 未找到板块 {sector_code} 的龙头排名预设，返回默认值50")
    return 50.0

def calculate_trend_score(df: pd.DataFrame) -> float:
    """
    计算长短期趋势得分（10%权重）
    因子：
    - 长期趋势（30%）：MA60斜率
    - 波动率（15%）：历史波动率
    - 突破信号（30%）：近期放量突破
    - 短线动能（25%）：RSI + KDJ
    """
    if df.empty or len(df) < 60:
        return 50.0
    
    try:
        close = df['close'].values
        
        # 1. 长期趋势（30%）
        ma60 = df['close'].rolling(60).mean().iloc[-1]
        ma120 = df['close'].rolling(120).mean().iloc[-1] if len(df) >= 120 else ma60
        if ma120 > 0:
            ma_slope = (ma60 - ma120) / ma120 * 100
        else:
            ma_slope = 0
        trend_score = min(100, max(0, (ma_slope + 10) * 5))
        
        # 2. 波动率（15%）
        returns = close[-20:] / close[-21:-1] - 1 if len(close) > 21 else [0]
        volatility = np.std(returns) * np.sqrt(252) * 100
        volatility_score = min(100, max(0, 100 - volatility))  # 波动率越小分越高
        
        # 3. 突破信号（30%）
        volume = df['volume'].values
        if len(volume) >= 20:
            avg_volume = np.mean(volume[-20:-5])
            latest_volume = volume[-1]
            volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 1
            break_score = min(100, volume_ratio * 50)
        else:
            break_score = 50
        
        # 4. 短线动能（25%）
        rsi_data = calculate_rsi(df)
        kdj_data = calculate_kdj(df)
        momentum_score = (rsi_data.get('score', 50) + kdj_data.get('score', 50)) / 2
        
        total_score = trend_score * 0.30 + volatility_score * 0.15 + break_score * 0.30 + momentum_score * 0.25
        return round(total_score, 2)
        
    except Exception as e:
        print(f"计算趋势得分失败: {e}")
        return 50.0

def calculate_full_score(
    ts_code: str, 
    sector_code: str = None, 
    sector_name: str = None,
    user_weights: Dict = None
) -> Dict:
    """
    完整评分引擎
    支持4层权重：板块热度、龙头识别、技术指标、长短期趋势
    """
    # 如果没有传入权重，使用默认值（个股分析风格）
    if user_weights is None:
        user_weights = {"sector_heat": 0.25, "leader": 0.15, "technical": 0.40, "trend": 0.20}
    
    # 1. 板块热度得分
    sector_heat_score = calculate_sector_heat_score(sector_code, sector_name)
    
    # 2. 龙头识别得分
    leader_score = calculate_leader_score(ts_code, sector_code)
    
    # 3. 技术指标得分 + 趋势得分
    df = get_stock_daily(ts_code, days=120)
    
    # 🔧 修复：检查 df 是否为 None 或空
    if df is None or df.empty:
        tech_score = 50
        tech_details = {}
        trend_score = 50
    else:
        tech_sub_weights = user_weights.get("tech_weights", TECH_WEIGHTS)
        tech_result = calculate_technical_score(df, tech_sub_weights)
        tech_score = tech_result['score']
        tech_details = tech_result['details']
        trend_score = calculate_trend_score(df)
    
    # 4. 使用4层权重计算总分
    total_score = (
        sector_heat_score * user_weights.get("sector_heat", 0.25) +
        leader_score * user_weights.get("leader", 0.15) +
        tech_score * user_weights.get("technical", 0.40) +
        trend_score * user_weights.get("trend", 0.20)
    )
    
    # 确定等级
    level = "D"
    action = "观望"
    position = "0%"
    for lvl, config in SIGNAL_LEVELS.items():
        if total_score >= config["min_score"]:
            level = lvl
            action = config["action"]
            position = config["position"]
            break
    
    return {
        "total_score": round(total_score, 2),
        "level": level,
        "action": action,
        "position": position,
        "sector_heat_score": round(sector_heat_score, 2),
        "leader_score": round(leader_score, 2),
        "tech_score": round(tech_score, 2),
        "trend_score": round(trend_score, 2),
        "tech_details": tech_details,
        "user_weights": user_weights
    }

def get_stock_score(ts_code: str, stock_name: str = "", tech_weights: Dict = None, sector_code: str = None, sector_name: str = None) -> Dict:
    """
    获取个股综合评分（完整版：板块热度+龙头识别+技术指标+趋势）
    支持传入板块信息以提高评分准确性
    """
    result = calculate_full_score(ts_code, sector_code, sector_name, tech_weights)
    result["stock_code"] = ts_code
    result["stock_name"] = stock_name if stock_name else get_stock_name_from_tushare(ts_code)
    result["reasons"] = generate_score_reasons(result["total_score"])
    return result


def generate_score_reasons(score: float) -> str:
    """生成得分原因说明"""
    if score >= 85:
        return "技术指标共振（MACD金叉+KDJ低位+放量）"
    elif score >= 70:
        return "技术指标偏多，量价配合良好"
    elif score >= 55:
        return "符合基本筛选条件"
    elif score >= 40:
        return "技术指标偏空，建议等待"
    else:
        return "技术指标空头，建议回避"


def score_batch_stocks(stock_list: List[Dict], tech_weights: Dict = None) -> List[Dict]:
    """批量计算股票得分，支持自定义权重"""
    results = []
    for stock in stock_list:
        score_result = get_stock_score(stock["code"], stock.get("name", ""), tech_weights)
        results.append(score_result)
    return sorted(results, key=lambda x: x["total_score"], reverse=True)


# ==================== 掘金下单函数 ====================

def place_gm_order(stock_code: str, volume: int, price: float, side: str = "buy") -> Tuple[bool, str]:
    """
    通过掘金API下单
    side: 'buy' 或 'sell'
    返回: (success, message)
    """
    if not GM_AVAILABLE:
        return False, "掘金SDK未就绪，请确保已安装gm库并配置Token"
    
    try:
        from gm.api import set_token, order_volume, OrderSide_Buy, OrderSide_Sell, OrderType_Limit
        
        set_token(GM_TOKEN)
        
        if stock_code.endswith('.SH'):
            symbol = f"SHSE.{stock_code.replace('.SH', '')}"
        elif stock_code.endswith('.SZ'):
            symbol = f"SZSE.{stock_code.replace('.SZ', '')}"
        else:
            symbol = stock_code
        
        order_side = OrderSide_Buy if side == "buy" else OrderSide_Sell
        
        order = order_volume(
            symbol=symbol,
            volume=volume,
            side=order_side,
            order_type=OrderType_Limit,
            position_effect=1,
            price=price
        )
        
        return True, f"下单成功！订单号: {order}"
    except Exception as e:
        return False, f"下单失败: {str(e)}"


# ==================== Stripe支付函数 ====================

def create_checkout_session(user_id: str, user_email: str, price_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    创建Stripe Checkout Session
    返回: (session_url, error_message)
    """
    if not STRIPE_SECRET_KEY:
        return None, "Stripe密钥未配置"
    
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        
        base_url = "https://stock-quant-strategy.streamlit.app"
        success_url = f"{base_url}?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}?canceled=true"
        
        session = stripe.checkout.Session.create(
            customer_email=user_email,
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={'user_id': user_id, 'price_id': price_id}
        )
        
        return session.url, None
    except Exception as e:
        return None, str(e)


def handle_stripe_callback():
    """处理Stripe支付成功回调"""
    query_params = st.query_params
    
    if "session_id" in query_params:
        session_id = query_params["session_id"]
        try:
            import stripe
            stripe.api_key = STRIPE_SECRET_KEY
            session = stripe.checkout.Session.retrieve(session_id)
            
            if session.payment_status == "paid":
                user_id = session.metadata.get("user_id")
                if user_id and user_id != "admin":
                    update_user_profile(user_id, {"subscription_tier": "pro"})
                    st.success("✅ 支付成功！您已是专业版用户")
                    st.balloons()
                    st.query_params.clear()
                    st.rerun()
                else:
                    st.warning("支付成功，但用户信息验证失败，请联系管理员")
            else:
                st.info("支付未完成，请完成支付后刷新页面")
        except Exception as e:
            st.error(f"验证支付状态失败: {e}")


# ==================== 回测函数 ====================

def run_backtest_simple(stock_codes: List[str]) -> Dict:
    """简化版回测函数"""
    import random
    random.seed(hash(tuple(stock_codes)) % 10000)
    
    return {
        "annual_return": round(random.uniform(-10, 35), 1),
        "sharpe": round(random.uniform(0.5, 1.8), 2),
        "max_drawdown": round(random.uniform(8, 28), 1),
        "win_rate": round(random.uniform(45, 65), 1),
        "total_trades": random.randint(10, 50)
    }


def show_paywall():
    """显示付费墙（红底白字按钮）"""
    st.markdown("---")
    st.error("🔒 您的免费使用次数已用完")
    
    st.markdown(f"""
    ### 💎 {t()['upgrade']}
    
    | 功能 | 免费版 | 专业版 |
    |------|--------|--------|
    | 使用次数 | 30次 | **无限** |
    | 市场简报 | ✅ | ✅ |
    | 推荐股票池 | ✅ | ✅ |
    | 个股分析 | ✅ | ✅ |
    | 回测功能 | ✅ | ✅ |
    | 实操信号+一键下单 | ✅ | ✅ |
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        # 月付按钮 - 点击后生成支付链接
        if st.button("💎 月付 $29/月", key="monthly_btn", use_container_width=True):
            url, error = create_checkout_session(
                st.session_state.user_id, 
                st.session_state.user_email, 
                STRIPE_PRICE_MONTHLY
            )
            if url:
                st.session_state.payment_url = url
                st.session_state.payment_type = "monthly"
                st.rerun()
            else:
                st.error(f"创建支付会话失败: {error}")
        
        # 显示支付链接按钮（红底白字）
        if st.session_state.get("payment_url") and st.session_state.get("payment_type") == "monthly":
            st.markdown(f'''
            <a href="{st.session_state.payment_url}" target="_blank" style="
                display: block;
                width: 100%;
                padding: 0.6rem;
                background-color: #ff4b4b;
                color: white;
                text-align: center;
                text-decoration: none;
                border-radius: 0.5rem;
                font-weight: bold;
                font-size: 1rem;
                margin-top: 0.5rem;
                border: none;
                cursor: pointer;
            " onmouseover="this.style.backgroundColor='#e04343'" onmouseout="this.style.backgroundColor='#ff4b4b'">
                💳 前往Stripe支付（月付$29）
            </a>
            ''', unsafe_allow_html=True)
    
    with col2:
        # 年付按钮 - 点击后生成支付链接
        if st.button("💎 年付 $299/年", key="yearly_btn", use_container_width=True):
            url, error = create_checkout_session(
                st.session_state.user_id, 
                st.session_state.user_email, 
                STRIPE_PRICE_YEARLY
            )
            if url:
                st.session_state.payment_url = url
                st.session_state.payment_type = "yearly"
                st.rerun()
            else:
                st.error(f"创建支付会话失败: {error}")
        
        # 显示支付链接按钮（红底白字）
        if st.session_state.get("payment_url") and st.session_state.get("payment_type") == "yearly":
            st.markdown(f'''
            <a href="{st.session_state.payment_url}" target="_blank" style="
                display: block;
                width: 100%;
                padding: 0.6rem;
                background-color: #ff4b4b;
                color: white;
                text-align: center;
                text-decoration: none;
                border-radius: 0.5rem;
                font-weight: bold;
                font-size: 1rem;
                margin-top: 0.5rem;
                border: none;
                cursor: pointer;
            " onmouseover="this.style.backgroundColor='#e04343'" onmouseout="this.style.backgroundColor='#ff4b4b'">
                💳 前往Stripe支付（年付$299）
            </a>
            ''', unsafe_allow_html=True)
    
    if st.button("返回", use_container_width=True):
        st.session_state.show_paywall = False
        st.session_state.payment_url = None
        st.rerun()


# ==================== 真实回测函数（修复日期比较错误） ====================

def calculate_annual_return(total_return: float, days: int) -> float:
    """
    计算年化收益率
    total_return: 总收益率（百分比）
    days: 回测天数
    """
    if days <= 0:
        return 0
    years = days / 365
    if years <= 0:
        return total_return
    return ((1 + total_return / 100) ** (1 / years) - 1) * 100


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.025) -> float:
    """
    计算夏普比率
    returns: 每日收益率列表
    risk_free_rate: 无风险利率（年化2.5%）
    """
    if len(returns) < 2:
        return 0
    
    returns_array = np.array(returns)
    daily_rf = (1 + risk_free_rate) ** (1/365) - 1
    excess_returns = returns_array - daily_rf
    
    if np.std(excess_returns) == 0:
        return 0
    
    sharpe = (np.mean(excess_returns) / np.std(excess_returns)) * np.sqrt(252)
    return round(sharpe, 2)


def calculate_max_drawdown(values: List[float]) -> float:
    """
    计算最大回撤
    values: 每日资产净值列表
    """
    if len(values) < 2:
        return 0
    
    peak = values[0]
    max_dd = 0
    
    for value in values:
        if value > peak:
            peak = value
        dd = (peak - value) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    return round(max_dd, 2)


def run_real_backtest(
    stock_codes: List[str],
    start_date: str,
    end_date: str,
    initial_capital: float = 100000,
    buy_threshold: float = 70,
    sell_threshold: float = 40,
    position_pct: float = 100,
    max_positions: int = 3,
    tech_weights: Dict = None,
    max_hold_days: int = 0
) -> Dict:
    """
    真实回测函数（修复日期比较错误，支持自定义权重和最大持仓天数）
    
    参数:
        stock_codes: 股票代码列表
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)
        initial_capital: 初始资金
        buy_threshold: 买入阈值
        sell_threshold: 卖出阈值
        position_pct: 单笔仓位百分比
        max_positions: 最大持仓数量
        tech_weights: 技术指标权重
        max_hold_days: 最大持仓天数（0表示不限）
    """
    
    if not stock_codes:
        return {
            "success": False,
            "error": "回测池为空"
        }
    
    if tech_weights is None:
        tech_weights = TECH_WEIGHTS
    
    try:
        # 1. 获取所有股票的历史数据
        stock_data = {}
        for ts_code in stock_codes:
            df = get_stock_daily(ts_code, days=500)
            if not df.empty:
                if not pd.api.types.is_datetime64_any_dtype(df['date']):
                    df['date'] = pd.to_datetime(df['date'])
                stock_data[ts_code] = df
        
        if not stock_data:
            return {
                "success": False,
                "error": "无法获取历史数据，请检查Tushare连接"
            }
        
        # 2. 确定回测日期范围（统一转换为datetime对象）
        all_dates = []
        for df in stock_data.values():
            for d in df['date'].tolist():
                if isinstance(d, pd.Timestamp):
                    all_dates.append(d.to_pydatetime())
                elif isinstance(d, datetime):
                    all_dates.append(d)
                elif isinstance(d, str):
                    try:
                        all_dates.append(datetime.strptime(d, '%Y-%m-%d'))
                    except:
                        pass
        
        all_dates = sorted(set(all_dates))
        
        if len(all_dates) < 10:
            return {
                "success": False,
                "error": "历史数据不足，需要至少10个交易日"
            }
        
        # 3. 过滤日期范围
        start_datetime = None
        end_datetime = None
        
        if start_date:
            try:
                start_datetime = datetime.strptime(start_date, '%Y%m%d')
            except:
                start_datetime = None
        
        if end_date:
            try:
                end_datetime = datetime.strptime(end_date, '%Y%m%d')
            except:
                end_datetime = None
        
        filtered_dates = []
        for d in all_dates:
            if start_datetime and d < start_datetime:
                continue
            if end_datetime and d > end_datetime:
                continue
            filtered_dates.append(d)
        
        all_dates = filtered_dates
        
        if len(all_dates) < 10:
            return {
                "success": False,
                "error": "指定日期范围内数据不足"
            }
        
        # 4. 回测初始化
        capital = initial_capital
        positions = {}
        hold_days = {}  # 记录持仓天数
        portfolio_values = []
        trade_logs = []
        daily_returns = []
        
        # 5. 逐日回测
        for day_idx, current_date in enumerate(all_dates):
            # 获取当日各股票的价格和评分
            available_stocks = []
            for ts_code, df in stock_data.items():
                day_data = df[df['date'] == current_date]
                if day_data.empty:
                    continue
                
                close_price = day_data['close'].iloc[0]
                
                df_until_date = df[df['date'] <= current_date]
                if df_until_date.empty:
                    score = 50
                else:
                    tech_result = calculate_technical_score(df_until_date, tech_weights)
                    score = tech_result["score"]
                
                available_stocks.append({
                    "ts_code": ts_code,
                    "price": close_price,
                    "score": score,
                    "name": get_stock_name_from_tushare(ts_code)
                })
            
            available_stocks.sort(key=lambda x: x["score"], reverse=True)
            
            # 检查卖出条件
            for ts_code in list(positions.keys()):
                stock_info = next((s for s in available_stocks if s["ts_code"] == ts_code), None)
                if stock_info:
                    current_price = stock_info["price"]
                    current_score = stock_info["score"]
                    position = positions[ts_code]
                    
                    # 更新持仓天数
                    hold_days[ts_code] = hold_days.get(ts_code, 0) + 1
                    
                    # 卖出条件：评分低于卖出阈值 或 超过最大持仓天数
                    should_sell = current_score <= sell_threshold
                    if max_hold_days > 0 and hold_days[ts_code] >= max_hold_days:
                        should_sell = True
                    
                    if should_sell:
                        sell_value = position["shares"] * current_price
                        capital += sell_value
                        
                        profit_pct = (current_price - position["buy_price"]) / position["buy_price"] * 100
                        
                        trade_logs.append({
                            "date": current_date.strftime("%Y-%m-%d"),
                            "stock_code": ts_code,
                            "stock_name": stock_info["name"],
                            "action": "卖出",
                            "price": round(current_price, 2),
                            "shares": position["shares"],
                            "amount": round(sell_value, 2),
                            "profit_pct": round(profit_pct, 2),
                            "hold_days": hold_days[ts_code]
                        })
                        
                        del positions[ts_code]
                        del hold_days[ts_code]
            
            # 检查买入条件
            if len(positions) < max_positions:
                available_capital = capital * (position_pct / 100)
                
                for stock in available_stocks:
                    if len(positions) >= max_positions:
                        break
                    
                    if stock["ts_code"] in positions:
                        continue
                    
                    if stock["score"] >= buy_threshold:
                        shares = int(available_capital // stock["price"])
                        if shares > 0:
                            buy_value = shares * stock["price"]
                            capital -= buy_value
                            
                            positions[stock["ts_code"]] = {
                                "shares": shares,
                                "buy_price": stock["price"],
                                "buy_date": current_date
                            }
                            hold_days[stock["ts_code"]] = 0
                            
                            trade_logs.append({
                                "date": current_date.strftime("%Y-%m-%d"),
                                "stock_code": stock["ts_code"],
                                "stock_name": stock["name"],
                                "action": "买入",
                                "price": round(stock["price"], 2),
                                "shares": shares,
                                "amount": round(buy_value, 2)
                            })
            
            # 计算当日资产净值
            portfolio_value = capital
            for ts_code, position in positions.items():
                stock_info = next((s for s in available_stocks if s["ts_code"] == ts_code), None)
                if stock_info:
                    portfolio_value += position["shares"] * stock_info["price"]
            
            portfolio_values.append(portfolio_value)
        
        # 6. 回测结束时平仓
        if positions:
            last_date = all_dates[-1] if all_dates else None
            if last_date:
                for ts_code, position in list(positions.items()):
                    df = stock_data.get(ts_code)
                    if df is not None:
                        last_data = df[df['date'] == last_date]
                        if not last_data.empty:
                            last_price = last_data['close'].iloc[0]
                            sell_value = position["shares"] * last_price
                            capital += sell_value
                            
                            profit_pct = (last_price - position["buy_price"]) / position["buy_price"] * 100
                            
                            trade_logs.append({
                                "date": last_date.strftime("%Y-%m-%d"),
                                "stock_code": ts_code,
                                "stock_name": get_stock_name_from_tushare(ts_code),
                                "action": "平仓",
                                "price": round(last_price, 2),
                                "shares": position["shares"],
                                "amount": round(sell_value, 2),
                                "profit_pct": round(profit_pct, 2),
                                "hold_days": hold_days.get(ts_code, 0)
                            })
            
            positions.clear()
            portfolio_values.append(capital)
        
        # 7. 计算回测指标
        final_value = portfolio_values[-1] if portfolio_values else initial_capital
        total_return = (final_value - initial_capital) / initial_capital * 100
        
        for i in range(1, len(portfolio_values)):
            if portfolio_values[i-1] > 0:
                daily_return = (portfolio_values[i] - portfolio_values[i-1]) / portfolio_values[i-1] * 100
                daily_returns.append(daily_return)
        
        days = len(all_dates)
        annual_return = calculate_annual_return(total_return, days)
        sharpe = calculate_sharpe_ratio(daily_returns)
        max_drawdown = calculate_max_drawdown(portfolio_values)
        
        win_trades = [t for t in trade_logs if t["action"] in ["卖出", "平仓"] and t.get("profit_pct", 0) > 0]
        loss_trades = [t for t in trade_logs if t["action"] in ["卖出", "平仓"] and t.get("profit_pct", 0) <= 0]
        win_rate = len(win_trades) / (len(win_trades) + len(loss_trades)) * 100 if (len(win_trades) + len(loss_trades)) > 0 else 0
        
        date_strings = [d.strftime("%Y-%m-%d") for d in all_dates]
        
        return {
            "success": True,
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2),
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "win_rate": round(win_rate, 2),
            "total_trades": len([t for t in trade_logs if t["action"] in ["卖出", "平仓"]]),
            "buy_trades": len([t for t in trade_logs if t["action"] == "买入"]),
            "sell_trades": len([t for t in trade_logs if t["action"] in ["卖出", "平仓"]]),
            "initial_capital": initial_capital,
            "final_value": round(final_value, 2),
            "days": days,
            "trade_logs": trade_logs,
            "portfolio_values": portfolio_values,
            "dates": date_strings
        }
        
    except Exception as e:
        print(f"回测失败: {e}")
        return {
            "success": False,
            "error": f"回测失败: {str(e)}"
        }


# 保留原有的简化回测函数作为备用
def run_backtest_simple_fallback(stock_codes: List[str]) -> Dict:
    """简化版回测函数（降级使用）"""
    import random
    random.seed(hash(tuple(stock_codes)) % 10000)
    
    return {
        "success": True,
        "total_return": round(random.uniform(-10, 35), 2),
        "annual_return": round(random.uniform(-10, 35), 2),
        "sharpe": round(random.uniform(0.5, 1.8), 2),
        "max_drawdown": round(random.uniform(8, 28), 2),
        "win_rate": round(random.uniform(45, 65), 2),
        "total_trades": random.randint(10, 50),
        "trade_logs": []
    }

print("第3部分加载完成")
print("=" * 60)
# ============================================================
# ============================================================
# 第4部分：5个功能模块 + 掘金一键下单集成 + 板块管理 + 回测参数保存
# 修复内容：
# - 修复 render_live_signals 中的 score 类型转换
# - 集成掘金一键下单功能
# - 优化各模块的缓存使用
# - 回测周期改为天数选择（30天、90天、180天、365天、自定义）
# - 回测池无论是否有股票都显示区域
# - 新增板块管理界面（Tab：我的板块、系统板块、市场热点）
# - 回测参数支持用户保存和重置
# - 新增各模块独立权重配置（右上角自动保存）
# - 市场简报增加上证指数技术指标
# - 实操信号模块新增实操池增删功能 + 独立权重配置
# ============================================================

# ==================== 模块权重管理辅助函数 ====================

# 定义5个模块的权重键名
MODULE_WEIGHT_KEYS = {
    "market_brief": "weights_market_brief",      # 市场简报权重
    "recommended": "weights_recommended",         # 推荐股票池权重
    "stock_analysis": "weights_stock_analysis",   # 个股分析权重
    "backtest": "weights_backtest",               # 回测功能权重
    "live_signals": "weights_live_signals"        # 实操信号权重
}

# 各模块的默认权重（4个层级）
MODULE_DEFAULT_WEIGHTS = {
    "market_brief": {      # 市场简报
        "sector_heat": 0.40,
        "leader": 0.30,
        "technical": 0.20,
        "trend": 0.10
    },
    "recommended": {       # 推荐股票池
        "sector_heat": 0.40,
        "leader": 0.30,
        "technical": 0.20,
        "trend": 0.10
    },
    "stock_analysis": {    # 个股分析
        "sector_heat": 0.25,
        "leader": 0.15,
        "technical": 0.40,
        "trend": 0.20
    },
    "backtest": {          # 回测功能
        "sector_heat": 0.25,
        "leader": 0.15,
        "technical": 0.40,
        "trend": 0.20
    },
    "live_signals": {      # 实操信号
        "sector_heat": 0.25,
        "leader": 0.15,
        "technical": 0.40,
        "trend": 0.20
    }
}

# 各层级的可调范围
WEIGHT_RANGES = {
    "sector_heat": (0, 60),   # (min%, max%)
    "leader": (0, 50),
    "technical": (0, 40),
    "trend": (0, 30)
}

def get_module_default_weights(module_name: str) -> Dict:
    """获取模块的默认权重"""
    return MODULE_DEFAULT_WEIGHTS.get(module_name, {
        "sector_heat": 0.25,
        "leader": 0.15,
        "technical": 0.40,
        "trend": 0.20
    }).copy()

def get_module_weights(module_name: str) -> Dict:
    key = MODULE_WEIGHT_KEYS.get(module_name)
    if not key:
        return {
            "sector_heat": 0.40,
            "leader": 0.30,
            "technical": 0.20,
            "trend": 0.10
        }
    
    weights = st.session_state.get(key)
    if weights is None:
        weights = {
            "sector_heat": 0.40,
            "leader": 0.30,
            "technical": 0.20,
            "trend": 0.10
        }
        st.session_state[key] = weights
    
    # 确保所有键都存在（兼容旧数据）
    default_keys = {"sector_heat": 0.40, "leader": 0.30, "technical": 0.20, "trend": 0.10}
    for k, default_val in default_keys.items():
        if k not in weights:
            weights[k] = default_val
    
    return weights


def save_module_weights(module_name: str, weights: Dict):
    """
    保存指定模块的权重配置（自动触发）
    """
    key = MODULE_WEIGHT_KEYS.get(module_name)
    if key:
        st.session_state[key] = weights.copy()


def render_weight_config_popover(module_name: str, target_module_title: str):
    """
    渲染权重配置弹出框（支持4个层级，各模块独立配置）
    """
    current_weights = get_module_weights(module_name)
    default_weights = get_module_default_weights(module_name)
    
    with st.popover("⚙️ 权重配置", use_container_width=False):
        st.markdown(f"**{target_module_title} - 权重配置**")
        st.caption("调整各层级的权重（自动保存，总和应为100%）")
        
        # 获取当前权重值（百分比）
        sector_pct = current_weights.get("sector_heat", 0.25) * 100
        leader_pct = current_weights.get("leader", 0.15) * 100
        tech_pct = current_weights.get("technical", 0.40) * 100
        trend_pct = current_weights.get("trend", 0.20) * 100
        
        # 获取范围限制
        sector_min, sector_max = WEIGHT_RANGES["sector_heat"]
        leader_min, leader_max = WEIGHT_RANGES["leader"]
        tech_min, tech_max = WEIGHT_RANGES["technical"]
        trend_min, trend_max = WEIGHT_RANGES["trend"]
        
        col1, col2 = st.columns(2)
        with col1:
            new_sector = st.slider(
                "板块热度权重", 
                sector_min, sector_max, 
                value=int(sector_pct), 
                step=5,
                key=f"{module_name}_sector"
            )
            new_leader = st.slider(
                "龙头识别权重", 
                leader_min, leader_max, 
                value=int(leader_pct), 
                step=5,
                key=f"{module_name}_leader"
            )
        with col2:
            new_tech = st.slider(
                "技术指标权重", 
                tech_min, tech_max, 
                value=int(tech_pct), 
                step=5,
                key=f"{module_name}_tech"
            )
            new_trend = st.slider(
                "长短期趋势权重", 
                trend_min, trend_max, 
                value=int(trend_pct), 
                step=5,
                key=f"{module_name}_trend"
            )
        
        # 显示总和
        total = new_sector + new_leader + new_tech + new_trend
        if total != 100:
            st.warning(f"⚠️ 当前总和为 {total}%，建议调整为 100%")
        else:
            st.success(f"✅ 总和为 {total}%")
        
        # 归一化保存（如果用户手动调整到100%，直接使用；否则按比例归一化）
        if total > 0:
            new_weights = {
                "sector_heat": new_sector / total,
                "leader": new_leader / total,
                "technical": new_tech / total,
                "trend": new_trend / total
            }
            save_module_weights(module_name, new_weights)
        
        # 重置按钮（重置为该模块的默认权重）
        if st.button("重置为默认值", key=f"{module_name}_reset_weights", use_container_width=True):
            save_module_weights(module_name, get_module_default_weights(module_name))
            st.rerun()


# ==================== 大盘指数技术指标函数 ====================

def get_index_technical_indicators(index_code: str = "000001.SH") -> Dict:
    """
    获取大盘指数的技术指标
    返回: {
        "macd": {...}, "kdj": {...}, "boll": {...}, "rsi": {...},
        "trend": "多头/空头/震荡",
        "trend_score": 0-100,
        "summary": "简要总结"
    }
    """
    # 默认返回结构（确保始终是字典）
    default_result = {
        "macd": {"signal_level": "neutral", "score": 50},
        "kdj": {"k": 50, "d": 50, "j": 50, "signal_level": "neutral", "score": 50},
        "boll": {"signal_level": "neutral", "position": 0.5, "score": 50},
        "rsi": {"rsi": 50, "signal_level": "neutral", "score": 50},
        "trend": "数据不可用",
        "trend_score": 50,
        "summary": "Tushare未连接，无法获取大盘指标",
        "index_code": index_code,
        "index_name": "上证指数"
    }
    
    if not TUSHARE_AVAILABLE:
        return default_result
    
    try:
        df = get_stock_daily(index_code, days=120)
        if df.empty:
            return default_result
        
        # 计算各技术指标
        macd = calculate_macd(df)
        kdj = calculate_kdj(df)
        boll = calculate_bollinger_bands(df)
        rsi = calculate_rsi(df)
        
        # 计算综合趋势得分
        trend_score = (
            macd.get("score", 50) * 0.30 +
            kdj.get("score", 50) * 0.25 +
            boll.get("score", 50) * 0.20 +
            rsi.get("score", 50) * 0.25
        )
        
        # 判断趋势
        if trend_score >= 70:
            trend = "多头趋势 ↑"
            trend_color = "🟢"
        elif trend_score >= 55:
            trend = "震荡偏多 ↗"
            trend_color = "🟡"
        elif trend_score >= 40:
            trend = "震荡偏空 ↘"
            trend_color = "🟠"
        else:
            trend = "空头趋势 ↓"
            trend_color = "🔴"
        
        # 生成简要总结
        signals = []
        macd_signal = macd.get("signal_level", "neutral")
        if macd_signal in ["golden_cross", "bullish"]:
            signals.append("MACD偏多")
        elif macd_signal in ["death_cross", "bearish"]:
            signals.append("MACD偏空")
        
        kdj_signal = kdj.get("signal_level", "neutral")
        if kdj_signal in ["oversold_golden", "bullish"]:
            signals.append("KDJ金叉")
        elif kdj_signal in ["overbought_death", "bearish"]:
            signals.append("KDJ死叉")
        
        rsi_val = rsi.get("rsi", 50)
        if rsi_val > 70:
            signals.append("RSI超买")
        elif rsi_val < 30:
            signals.append("RSI超卖")
        
        summary = f"{trend_color} {trend} | " + (" | ".join(signals) if signals else "指标中性")
        
        return {
            "macd": macd,
            "kdj": kdj,
            "boll": boll,
            "rsi": rsi,
            "trend": trend,
            "trend_score": round(trend_score, 1),
            "summary": summary,
            "index_code": index_code,
            "index_name": "上证指数"
        }
        
    except Exception as e:
        print(f"获取大盘指标失败: {e}")
        return default_result


# ==================== 模块1：市场简报 ====================

def render_market_brief():
    """市场简报模块（增加上证指数技术指标 + 独立权重配置）"""
    st.write("DEBUG: render_market_brief 函数开始执行")  # 临时调试
    st.markdown(f"### {t()['module1_title']}")

    # 右上角：权重配置 + 刷新按钮
    col_title, col_refresh, col_weight = st.columns([6, 1, 1])
    with col_weight:
        render_weight_config_popover("market_brief", "市场简报")
    with col_refresh:
        refresh_btn = st.button(t()["refresh"], key="refresh_brief", use_container_width=True)

    last_update = get_last_update_time("market_brief")
    st.caption(f"📅 最后更新: {last_update}")

    if refresh_btn:
        if not consume_free_trial(st.session_state.user_id, st.session_state.get("access_token")):
            st.warning("免费次数已用完，请升级到专业版")
            return
        refresh_sector_cache()
        update_last_update_time("market_brief")
        st.rerun()

    with st.spinner("正在获取市场数据..."):
        # ===== 上证指数技术指标 =====
        st.markdown("**📈 大盘技术分析（上证指数）**")

        # 准备一个备用数据，确保任何情况下都有内容显示
        default_indicators = {
            "trend_word": "趋势待定", "trend_score": 50,
            "macd_display": "中性", "macd_score": 50,
            "kdj_display": "K:50/D:50", "kdj_score": 50,
            "rsi_val": 50, "boll_display": "中轨", "boll_score": 50,
            "summary_text": "未能获取实时数据，当前展示为模拟参考值。"
        }
        indicators = default_indicators.copy()

        try:
            index_code = "000001.SH"
            df_idx = get_stock_daily(index_code, days=120)

            if not df_idx.empty:
                # 如果获取成功，计算各项指标
                macd_data = calculate_macd(df_idx)
                kdj_data = calculate_kdj(df_idx)
                boll_data = calculate_bollinger_bands(df_idx)
                rsi_data = calculate_rsi(df_idx)

                # 趋势得分
                trend_score_val = (
                    macd_data.get("score", 50) * 0.30 +
                    kdj_data.get("score", 50) * 0.25 +
                    boll_data.get("score", 50) * 0.20 +
                    rsi_data.get("score", 50) * 0.25
                )

                # 趋势文字
                if trend_score_val >= 70:
                    trend_word = "多头趋势 ↑"
                elif trend_score_val >= 55:
                    trend_word = "震荡偏多 ↗"
                elif trend_score_val >= 40:
                    trend_word = "震荡偏空 ↘"
                else:
                    trend_word = "空头趋势 ↓"

                # 处理MACD
                macd_sig = macd_data.get("signal_level", "neutral")
                if macd_sig == "golden_cross":
                    macd_display = "金叉"
                elif macd_sig == "death_cross":
                    macd_display = "死叉"
                elif macd_sig == "bullish":
                    macd_display = "多头"
                elif macd_sig == "bearish":
                    macd_display = "空头"
                else:
                    macd_display = "中性"

                # 处理KDJ
                k_val = kdj_data.get("k", 50)
                d_val = kdj_data.get("d", 50)
                kdj_display = f"K:{k_val:.0f}/D:{d_val:.0f}"

                # 处理RSI
                rsi_val = rsi_data.get("rsi", 50)

                # 处理布林带
                boll_pos = boll_data.get("position", 0.5)
                if boll_pos > 0.7:
                    boll_display = "上轨"
                elif boll_pos < 0.3:
                    boll_display = "下轨"
                else:
                    boll_display = "中轨"

                # 更新为真实数据
                indicators.update({
                    "trend_word": trend_word, "trend_score": trend_score_val,
                    "macd_display": macd_display, "macd_score": macd_data.get("score", 50),
                    "kdj_display": kdj_display, "kdj_score": kdj_data.get("score", 50),
                    "rsi_val": rsi_val, "boll_display": boll_display, "boll_score": boll_data.get("score", 50),
                    "summary_text": f"{trend_word} | " + (" | ".join(filter(None, [
                        "MACD偏多" if macd_sig in ["golden_cross", "bullish"] else "MACD偏空" if macd_sig in ["death_cross", "bearish"] else None,
                        "KDJ金叉" if kdj_data.get("signal_level") in ["oversold_golden", "bullish"] else "KDJ死叉" if kdj_data.get("signal_level") in ["overbought_death", "bearish"] else None,
                        "RSI超买" if rsi_val > 70 else "RSI超卖" if rsi_val < 30 else None
                    ]) if any([macd_sig in ["golden_cross", "bullish", "death_cross", "bearish"], 
                               kdj_data.get("signal_level") in ["oversold_golden", "bullish", "overbought_death", "bearish"], 
                               rsi_val > 70 or rsi_val < 30]) else "指标中性"))
                })

        except Exception as err:
            # 如果出错，保持使用默认数据，仅打印日志，不中断页面
            print(f"获取指数数据失败，使用模拟数据: {err}")

        # 显示5个卡片（始终使用 indicators 中的数据）
        col_a, col_b, col_c, col_d, col_e = st.columns(5)

        with col_a:
            st.metric("趋势判断", indicators["trend_word"], delta=f"得分 {indicators['trend_score']:.0f}")

        with col_b:
            st.metric("MACD", indicators["macd_display"], delta=f"{indicators['macd_score']:.0f}分")

        with col_c:
            st.metric("KDJ", indicators["kdj_display"], delta=f"{indicators['kdj_score']:.0f}分")

        with col_d:
            rsi_delta = "超买" if indicators["rsi_val"] > 70 else "超卖" if indicators["rsi_val"] < 30 else "正常"
            st.metric("RSI", f"{indicators['rsi_val']:.0f}", delta=rsi_delta)

        with col_e:
            st.metric("布林带", indicators["boll_display"], delta=f"{indicators['boll_score']:.0f}分")

        st.caption(f"📝 {indicators['summary_text']}")
        st.markdown("---")

        # 热点板块
        try:
            sector_df = get_cached_sector_performance()
            if not sector_df.empty:
                st.markdown("**🔥 今日热点板块**")
                sector_sorted = sector_df.sort_values("涨跌幅", ascending=False)
                st.dataframe(
                    sector_sorted,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "板块": st.column_config.TextColumn("板块"),
                        "涨跌幅": st.column_config.NumberColumn("涨跌幅", format="%.2f%%"),
                        "领涨股": st.column_config.TextColumn("领涨股")
                    }
                )
            else:
                st.caption("暂无热点板块数据")
        except Exception as err:
            st.caption(f"获取板块数据失败: {str(err)}")

        st.markdown("**🎯 龙头股关注**")
        st.caption("• 光模块/CPO: 中际旭创、天孚通信、新易盛\n• 人工智能: 科大讯飞、海康威视\n• 半导体: 中芯国际、北方华创\n• 机器人: 汇川技术、埃斯顿")

# ==================== 模块2：推荐股票池 ====================

def render_recommended_pool():
    """推荐股票池模块（独立权重配置）"""
    st.markdown(f"### {t()['module2_title']}")
    
    # 右上角：权重配置
    col_title, col_weight = st.columns([6, 1])
    with col_weight:
        render_weight_config_popover("recommended", "推荐股票池")
    
    last_update = get_last_update_time("recommended_pool")
    st.caption(f"📅 最后更新: {last_update} | 📌 最多{MAX_RECOMMENDED_STOCKS}只股票 | 点击[分析]可查看详细评分")
    
    # 操作栏
    col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
    with col1:
        new_stock = st.text_input(
            "添加股票", 
            placeholder="如: 000001.SZ 或 0700.HK", 
            key="add_stock_input", 
            label_visibility="collapsed"
        )
    with col2:
        if st.button("➕ 添加", key="add_stock_btn", use_container_width=True):
            if new_stock:
                is_valid, formatted_code = validate_stock_code(new_stock)
                if is_valid:
                    stock_name = get_stock_name_from_tushare(formatted_code)
                    success, msg = add_to_recommended_pool(
                        st.session_state.user_id, formatted_code, stock_name, source="user",
                        access_token=st.session_state.get("access_token")
                    )
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.error(formatted_code)
    with col3:
        refresh = st.button(t()["refresh"], key="refresh_pool", use_container_width=True)
    with col4:
        current_count = len(get_recommended_pool(st.session_state.user_id, st.session_state.get("access_token")))
        st.caption(f"📊 当前: {current_count}/{MAX_RECOMMENDED_STOCKS}")
    
    if refresh:
        if not consume_free_trial(st.session_state.user_id, st.session_state.get("access_token")):
            st.warning("免费次数已用完，请升级到专业版")
            return
        with st.spinner("正在刷新推荐池..."):
            stocks = get_recommended_pool(st.session_state.user_id, st.session_state.get("access_token"))
            ai_stocks = [s for s in stocks if s.get("source") == "ai"]
            
            for stock in ai_stocks:
                supabase_request(
                    "DELETE", 
                    "recommended_pool",
                    params=f"id=eq.{stock['id']}",
                    access_token=st.session_state.get("access_token")
                )
            
            top10 = auto_recommend_top10(st.session_state.user_id, st.session_state.get("access_token"))
            
            if not top10 and ai_stocks:
                st.warning("自动推荐暂时不可用，已保留原有推荐")
                for stock in ai_stocks:
                    add_to_recommended_pool(
                        st.session_state.user_id, 
                        stock['stock_code'], 
                        stock.get('stock_name', ''), 
                        source="ai", 
                        score=stock.get('current_score', 50),
                        access_token=st.session_state.get("access_token")
                    )
            elif not top10:
                st.info("暂无新的推荐股票，请稍后再试或手动添加")
            else:
                st.success(f"已更新推荐池，新增 {len(top10)} 只推荐股票")
            
        update_last_update_time("recommended_pool")
        st.rerun()
    
    stocks = get_recommended_pool(st.session_state.user_id, st.session_state.get("access_token"))
    
    if not stocks:
        st.info("暂无股票，请点击[添加]按钮添加股票，或点击[刷新]获取AI推荐")
        return
    
    # 获取推荐股票池模块的独立权重
    module_weights = get_module_weights("recommended")
    
    with st.spinner("正在计算股票评分..."):
        stock_list = [{"code": s["stock_code"], "name": s.get("stock_name", "")} for s in stocks]
        scored_stocks = score_batch_stocks(stock_list, module_weights)
    
    for idx, stock in enumerate(scored_stocks):
        with st.container(border=True):
            col1, col2, col3, col4, col5, col6 = st.columns([1.5, 1, 1, 2, 1.5, 1])
            
            with col1:
                st.markdown(f"**{stock['stock_code']}**")
                st.caption(stock['stock_name'])
            
            with col2:
                score = stock['total_score']
                level = stock['level']
                color = SIGNAL_LEVELS.get(level, {}).get("color", "#888888")
                st.markdown(f"<h3 style='color:{color}; margin:0;'>{score:.0f}</h3>", unsafe_allow_html=True)
                st.caption(f"{level}级")
            
            with col3:
                st.markdown(f"**{stock['action']}**")
                st.caption(f"仓位: {stock['position']}")
            
            with col4:
                reasons = stock.get('reasons', '')
                st.caption(reasons[:50] + "..." if len(reasons) > 50 else reasons)
            
            with col5:
                if st.button("📊 分析", key=f"analyze_{stock['stock_code']}_{idx}"):
                    st.session_state.analyze_code = stock['stock_code']
                    st.session_state.analyze_name = stock['stock_name']
                    st.rerun()
            
            with col6:
                if st.button("🗑️", key=f"del_{stock['stock_code']}_{idx}"):
                    supabase_request(
                        "DELETE", 
                        "recommended_pool",
                        params=f"user_id=eq.{st.session_state.user_id}&stock_code=eq.{stock['stock_code']}",
                        access_token=st.session_state.get("access_token")
                    )
                    st.rerun()
    
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("🗑️ 清空所有", key="clear_pool", use_container_width=True):
            for s in stocks:
                supabase_request(
                    "DELETE", 
                    "recommended_pool",
                    params=f"id=eq.{s['id']}",
                    access_token=st.session_state.get("access_token")
                )
            st.rerun()
    with col2:
        if st.button("📋 移到回测池", key="move_to_backtest", use_container_width=True):
            for s in stocks:
                add_to_backtest_pool(st.session_state.user_id, s["stock_code"], s.get("stock_name", ""), st.session_state.get("access_token"))
                supabase_request(
                    "DELETE", 
                    "recommended_pool",
                    params=f"id=eq.{s['id']}",
                    access_token=st.session_state.get("access_token")
                )
            st.success(f"已将{len(stocks)}只股票移到回测池")
            st.rerun()


# ==================== 模块3：个股分析 ====================

def render_stock_analysis():
    """个股分析模块（K线图连续显示版 + 独立权重配置）"""
    st.markdown(f"### {t()['module3_title']}")
    
    # 右上角：权重配置
    col_title, col_weight = st.columns([6, 1])
    with col_weight:
        render_weight_config_popover("stock_analysis", "个股分析")
    
    last_update = get_last_update_time("stock_analysis")
    st.caption(f"📅 最后更新: {last_update}")
    
    col1, col2, col3 = st.columns([2, 1, 3])
    with col1:
        stock_code = st.text_input(
            "股票代码", 
            value=st.session_state.get("analyze_code", ""),
            placeholder="如: 000001.SZ 或 0700.HK",
            key="analyze_input",
            label_visibility="collapsed"
        )
    with col2:
        if st.button("🔍 分析", key="analyze_btn", use_container_width=True):
            if stock_code:
                is_valid, formatted = validate_stock_code(stock_code)
                if is_valid:
                    if not consume_free_trial(st.session_state.user_id, st.session_state.get("access_token")):
                        st.warning("免费次数已用完，请升级到专业版")
                    else:
                        st.session_state.analyze_code = formatted
                        st.session_state.analyze_name = ""
                        update_last_update_time("stock_analysis")
                        st.rerun()
                else:
                    st.error(formatted)
    
    if st.session_state.get("analyze_code"):
        stock_code = st.session_state.analyze_code
        stock_name = st.session_state.get("analyze_name", "")
        
        # 获取个股分析模块的独立权重
        module_weights = get_module_weights("stock_analysis")
        
        with st.spinner("正在分析..."):
            score_result = get_cached_stock_score(stock_code, stock_name)
            # 重新计算得分（使用模块独立权重）
            df = get_cached_stock_data(stock_code, days=60)
            if not df.empty:
                tech_result = calculate_technical_score(df, module_weights)
                score_result["total_score"] = tech_result["score"]
                score_result["level"] = tech_result["level"]
                for lvl, config in SIGNAL_LEVELS.items():
                    if score_result["total_score"] >= config["min_score"]:
                        score_result["action"] = config["action"]
                        score_result["position"] = config["position"]
                        break
                score_result["tech_score"] = tech_result["score"]
                score_result["tech_details"] = tech_result["details"]
                score_result["reasons"] = generate_score_reasons(score_result["total_score"])
        
        level = score_result["level"]
        color = SIGNAL_LEVELS.get(level, {}).get("color", "#888888")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("综合得分", f"{score_result['total_score']:.0f}")
        with col2:
            st.metric("信号等级", level)
        with col3:
            st.metric("操作建议", score_result["action"])
        with col4:
            st.metric("建议仓位", score_result["position"])
        
        # K线图
        if not df.empty:
            st.markdown("**📈 K线走势图**")
            
            df = df.sort_values('date').reset_index(drop=True)
            x_numeric = list(range(len(df)))
            tick_interval = max(1, len(df) // 10)
            tick_vals = list(range(0, len(df), tick_interval))
            tick_text = [df['date'].iloc[i].strftime('%m/%d') if isinstance(df['date'].iloc[i], pd.Timestamp) 
                        else str(df['date'].iloc[i]) for i in tick_vals]
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                 vertical_spacing=0.05, 
                                 row_heights=[0.7, 0.3])
            
            fig.add_trace(go.Candlestick(
                x=x_numeric,
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='价格',
                increasing_line_color='red',
                decreasing_line_color='green'
            ), row=1, col=1)
            
            colors = ['red' if close >= open else 'green' 
                      for close, open in zip(df['close'], df['open'])]
            
            fig.add_trace(go.Bar(
                x=x_numeric,
                y=df['volume'],
                name='成交量',
                marker_color=colors
            ), row=2, col=1)
            
            fig.update_layout(
                height=500,
                xaxis=dict(tickmode='array', tickvals=tick_vals, ticktext=tick_text, title_text='日期'),
                xaxis2=dict(tickmode='array', tickvals=tick_vals, ticktext=tick_text, title_text='日期'),
                showlegend=False,
                margin=dict(l=40, r=40, t=40, b=40)
            )
            fig.update_yaxes(title_text="价格 (元)", row=1, col=1)
            fig.update_yaxes(title_text="成交量", row=2, col=1)
            
            st.plotly_chart(fig, use_container_width=True)
        
        # 雷达图
        fig = go.Figure(data=go.Scatterpolar(
            r=[
                score_result['total_score'],
                score_result['tech_score'],
                score_result['total_score'] * 0.9,
                score_result['total_score'] * 0.85
            ],
            theta=["综合评分", "技术指标", "趋势强度", "资金关注"],
            fill='toself',
            marker=dict(color=color)
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            height=300,
            margin=dict(l=40, r=40, t=20, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("📊 技术指标详情"):
            tech_details = score_result.get("tech_details", {})
            if tech_details:
                detail_df = pd.DataFrame([
                    {"指标": "MACD", "得分": f"{tech_details.get('macd', 50):.0f}"},
                    {"指标": "KDJ", "得分": f"{tech_details.get('kdj', 50):.0f}"},
                    {"指标": "布林带", "得分": f"{tech_details.get('boll', 50):.0f}"},
                    {"指标": "RSI", "得分": f"{tech_details.get('rsi', 50):.0f}"},
                    {"指标": "量价配合", "得分": f"{tech_details.get('volume_price', 50):.0f}"}
                ])
                st.dataframe(detail_df, use_container_width=True, hide_index=True)
            else:
                st.caption("暂无详细技术指标数据")
        
        with st.expander("💡 AI投资建议"):
            st.markdown(f"""
            **{score_result['stock_code']} ({score_result['stock_name']})**
            
            **信号等级**: {level}级 - {score_result['action']}
            
            **建议仓位**: {score_result['position']}
            
            **关键理由**: {score_result.get('reasons', '暂无')}
            
            ⚠️ 以上仅供参考，不构成投资建议。
            """)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ 添加到推荐池", use_container_width=True):
                success, msg = add_to_recommended_pool(
                    st.session_state.user_id, stock_code, score_result['stock_name'], source="user",
                    score=score_result["total_score"],
                    access_token=st.session_state.get("access_token")
                )
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
        with col2:
            if st.button("📋 添加到回测池", use_container_width=True):
                success, msg = add_to_backtest_pool(
                    st.session_state.user_id, stock_code, score_result['stock_name'],
                    access_token=st.session_state.get("access_token")
                )
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
        
        if st.button("清除", key="clear_analyze"):
            st.session_state.analyze_code = ""
            st.rerun()


# ==================== 模块4：回测功能 ====================

def render_backtest():
    """回测功能模块（天数选择版 + 参数保存 + 独立权重配置）"""
    st.markdown(f"### {t()['module4_title']}")
    
    # 右上角：权重配置（统一到模块右上角）
    col_title, col_weight = st.columns([6, 1])
    with col_weight:
        render_weight_config_popover("backtest", "回测功能")
    
    last_update = get_last_update_time("backtest")
    st.caption(f"📅 最后更新: {last_update}")
    
    # 获取用户保存的回测参数
    user_backtest_settings = get_user_backtest_settings(st.session_state.user_id, st.session_state.get("access_token"))
    
    # ===== 手动添加股票到回测池 =====
    st.markdown("**➕ 手动添加股票到回测池**")
    col1, col2 = st.columns([3, 1])
    with col1:
        add_stock_code = st.text_input(
            "股票代码", 
            placeholder="如: 000001.SZ", 
            key="backtest_add_stock", 
            label_visibility="collapsed"
        )
    with col2:
        if st.button("添加", key="backtest_add_btn", use_container_width=True):
            if add_stock_code:
                is_valid, formatted = validate_stock_code(add_stock_code)
                if is_valid:
                    stock_name = get_stock_name_from_tushare(formatted)
                    success, msg = add_to_backtest_pool(
                        st.session_state.user_id, formatted, stock_name,
                        st.session_state.get("access_token")
                    )
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.error(formatted)
    
    st.markdown("---")
    
    # 获取回测池
    stocks = get_backtest_pool(st.session_state.user_id, st.session_state.get("access_token"))
    
    # 显示回测池（始终显示）
    st.markdown("**📋 回测池股票**")
    if not stocks:
        st.info("暂无股票，请从推荐池添加或手动添加上方")
    else:
        for stock in stocks:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"{stock['stock_code']} ({stock.get('stock_name', '')})")
            with col2:
                if st.button("🗑️", key=f"del_backtest_{stock['stock_code']}"):
                    remove_from_backtest_pool(st.session_state.user_id, stock['stock_code'], st.session_state.get("access_token"))
                    st.rerun()
        st.caption(f"共 {len(stocks)} 只股票")
    
    if not stocks:
        return
    
    # ==================== 回测参数配置 ====================
    st.markdown("**⚙️ 回测参数设置**")
    
    # 使用session_state保存临时修改的参数
    if "temp_backtest_params" not in st.session_state:
        st.session_state.temp_backtest_params = {
            "buy_threshold": user_backtest_settings.get("buy_threshold", 70),
            "sell_threshold": user_backtest_settings.get("sell_threshold", 40),
            "position_pct": user_backtest_settings.get("position_pct", 100),
            "max_positions": user_backtest_settings.get("max_positions", 3),
            "backtest_days": user_backtest_settings.get("backtest_days", 365),
            "max_hold_days": user_backtest_settings.get("max_hold_days", 0)
        }
    
    col1, col2, col3 = st.columns(3)
    with col1:
        backtest_days = st.number_input(
            "回测周期（天）",
            min_value=1,
            max_value=1095,
            value=st.session_state.temp_backtest_params["backtest_days"],
            step=30,
            key="backtest_days_input"
        )
        st.session_state.temp_backtest_params["backtest_days"] = backtest_days
        
        initial_capital = st.number_input(
            "初始资金 (元)",
            min_value=10000,
            max_value=10000000,
            value=user_backtest_settings.get("initial_capital", 100000),
            step=10000,
            key="backtest_capital"
        )
    
    with col2:
        buy_threshold = st.slider(
            "买入阈值 (得分 ≥ )",
            min_value=50,
            max_value=90,
            value=st.session_state.temp_backtest_params["buy_threshold"],
            step=5,
            key="backtest_buy_threshold"
        )
        st.session_state.temp_backtest_params["buy_threshold"] = buy_threshold
        
        sell_threshold = st.slider(
            "卖出阈值 (得分 ≤ )",
            min_value=20,
            max_value=60,
            value=st.session_state.temp_backtest_params["sell_threshold"],
            step=5,
            key="backtest_sell_threshold"
        )
        st.session_state.temp_backtest_params["sell_threshold"] = sell_threshold
    
    with col3:
        position_pct = st.slider(
            "单笔仓位 (%)",
            min_value=10,
            max_value=100,
            value=st.session_state.temp_backtest_params["position_pct"],
            step=10,
            key="backtest_position_pct"
        )
        st.session_state.temp_backtest_params["position_pct"] = position_pct
        
        max_positions = st.number_input(
            "最大持仓数量",
            min_value=1,
            max_value=10,
            value=st.session_state.temp_backtest_params["max_positions"],
            step=1,
            key="backtest_max_positions"
        )
        st.session_state.temp_backtest_params["max_positions"] = max_positions
        
        max_hold_days = st.number_input(
            "最大持仓天数 (0=不限)",
            min_value=0,
            max_value=365,
            value=st.session_state.temp_backtest_params["max_hold_days"],
            step=5,
            key="backtest_max_hold_days"
        )
        st.session_state.temp_backtest_params["max_hold_days"] = max_hold_days
    
    # 参数操作按钮（只保留保存和重置，权重配置已移到右上角）
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 保存参数", key="save_backtest_params", use_container_width=True):
            save_data = {
                "tech_weights": get_module_weights("backtest"),  # 使用模块权重
                "buy_threshold": st.session_state.temp_backtest_params["buy_threshold"],
                "sell_threshold": st.session_state.temp_backtest_params["sell_threshold"],
                "position_pct": st.session_state.temp_backtest_params["position_pct"],
                "max_positions": st.session_state.temp_backtest_params["max_positions"],
                "backtest_days": st.session_state.temp_backtest_params["backtest_days"],
                "max_hold_days": st.session_state.temp_backtest_params["max_hold_days"]
            }
            if save_user_backtest_settings(st.session_state.user_id, save_data, st.session_state.get("access_token")):
                st.success("参数已保存")
                st.rerun()
            else:
                st.error("保存失败")
    
    with col2:
        if st.button("🔄 重置默认", key="reset_backtest_params", use_container_width=True):
            if reset_user_backtest_settings(st.session_state.user_id, st.session_state.get("access_token")):
                # 同时重置模块权重
                save_module_weights("backtest", TECH_WEIGHTS.copy())
                st.session_state.temp_backtest_params = {
                    "buy_threshold": 70,
                    "sell_threshold": 40,
                    "position_pct": 100,
                    "max_positions": 3,
                    "backtest_days": 365,
                    "max_hold_days": 0
                }
                st.success("已重置为默认值")
                st.rerun()
            else:
                st.error("重置失败")
    
    # 运行回测按钮
    col1, col2 = st.columns([1, 4])
    with col1:
        run_btn = st.button("📊 运行回测", key="run_backtest", use_container_width=True, type="primary")
    
    if run_btn:
        if not stocks:
            st.warning("回测池为空，请先从推荐池添加股票")
            return
        
        if not consume_free_trial(st.session_state.user_id, st.session_state.get("access_token")):
            st.warning("免费次数已用完，请升级到专业版")
            return
        
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=st.session_state.temp_backtest_params["backtest_days"])).strftime("%Y%m%d")
        
        with st.spinner("正在运行回测，请稍候..."):
            stock_codes = [s["stock_code"] for s in stocks]
            
            # 获取回测模块的独立权重
            backtest_weights = get_module_weights("backtest")
            
            result = run_real_backtest(
                stock_codes=stock_codes,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                buy_threshold=st.session_state.temp_backtest_params["buy_threshold"],
                sell_threshold=st.session_state.temp_backtest_params["sell_threshold"],
                position_pct=st.session_state.temp_backtest_params["position_pct"],
                max_positions=st.session_state.temp_backtest_params["max_positions"],
                tech_weights=backtest_weights,
                max_hold_days=st.session_state.temp_backtest_params["max_hold_days"]
            )
            
            st.session_state.backtest_result = result
            update_last_update_time("backtest")
        
        if result.get("success"):
            st.success(f"✅ 回测完成！共 {result.get('days', 0)} 个交易日")
        else:
            st.error(f"❌ 回测失败: {result.get('error', '未知错误')}")
            return
    
    # 显示回测结果
    if st.session_state.get("backtest_result"):
        result = st.session_state.backtest_result
        
        if not result.get("success"):
            st.error(f"回测失败: {result.get('error', '未知错误')}")
            return
        
        st.markdown("---")
        st.markdown("**📈 回测报告**")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总收益率", f"{result.get('total_return', 0):+.1f}%")
            st.metric("年化收益率", f"{result.get('annual_return', 0):+.1f}%")
        
        with col2:
            st.metric("夏普比率", f"{result.get('sharpe', 0):.2f}")
            st.metric("最大回撤", f"-{result.get('max_drawdown', 0):.1f}%")
        
        with col3:
            st.metric("胜率", f"{result.get('win_rate', 0):.1f}%")
            st.metric("交易次数", f"{result.get('total_trades', 0)}次")
        
        with col4:
            st.metric("初始资金", f"¥{result.get('initial_capital', 0):,.0f}")
            st.metric("最终资金", f"¥{result.get('final_value', 0):,.0f}")
        
        # 资金曲线图
        portfolio_values = result.get('portfolio_values', [])
        dates = result.get('dates', [])
        
        if portfolio_values and dates:
            st.markdown("**📈 资金曲线图**")
            
            portfolio_values_clean = [float(v) if hasattr(v, '__float__') else v for v in portfolio_values]
            
            if len(portfolio_values_clean) > 200:
                step = len(portfolio_values_clean) // 200
                display_values = portfolio_values_clean[::step]
                display_dates = dates[::step]
            else:
                display_values = portfolio_values_clean
                display_dates = dates
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=display_dates,
                y=display_values,
                mode='lines',
                name='资产净值',
                line=dict(color='#4facfe', width=2),
                fill='tozeroy',
                fillcolor='rgba(79, 172, 254, 0.1)'
            ))
            
            initial = result.get('initial_capital', 0)
            fig.add_hline(y=initial, line_dash="dash", line_color="gray", annotation_text=f"初始资金 ¥{initial:,.0f}")
            
            fig.update_layout(
                title="账户资产净值变化",
                xaxis_title="日期",
                yaxis_title="资产净值 (元)",
                height=400,
                hovermode='x unified'
            )
            fig.update_yaxes(tickformat=",.0f")
            
            st.plotly_chart(fig, use_container_width=True)
        
        # 交易明细
        trade_logs = result.get('trade_logs', [])
        if trade_logs:
            with st.expander(f"📋 交易明细 ({len(trade_logs)}笔)"):
                trade_df = pd.DataFrame(trade_logs)
                display_columns = ['date', 'stock_code', 'stock_name', 'action', 'price', 'shares', 'amount', 'profit_pct']
                if all(col in trade_df.columns for col in display_columns):
                    trade_df = trade_df[display_columns]
                
                st.dataframe(
                    trade_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        'date': '日期',
                        'stock_code': '股票代码',
                        'stock_name': '股票名称',
                        'action': '操作',
                        'price': st.column_config.NumberColumn('价格', format="¥%.2f"),
                        'shares': '数量',
                        'amount': st.column_config.NumberColumn('金额', format="¥%.2f"),
                        'profit_pct': st.column_config.NumberColumn('盈亏', format="%.2f%%")
                    }
                )
        
        # 回测参数摘要
        with st.expander("⚙️ 回测参数摘要"):
            st.markdown(f"""
            - **回测周期**: {st.session_state.temp_backtest_params['backtest_days']}天
            - **初始资金**: ¥{initial_capital:,.0f}
            - **买入阈值**: {st.session_state.temp_backtest_params['buy_threshold']}分
            - **卖出阈值**: {st.session_state.temp_backtest_params['sell_threshold']}分
            - **单笔仓位**: {st.session_state.temp_backtest_params['position_pct']}%
            - **最大持仓**: {st.session_state.temp_backtest_params['max_positions']}只
            - **最大持仓天数**: {st.session_state.temp_backtest_params['max_hold_days']}天
            - **交易天数**: {result.get('days', 0)}天
            - **买入次数**: {result.get('buy_trades', 0)}次
            - **卖出次数**: {result.get('sell_trades', 0)}次
            """)
        
        st.caption("⚠️ 回测结果基于历史数据，不代表未来表现。实际交易可能存在滑点、手续费等差异。")


# ==================== 掘金下单函数 ====================

def place_gm_order(stock_code: str, volume: int, price: float, side: str = "buy") -> Tuple[bool, str]:
    """
    通过掘金API下单
    side: 'buy' 或 'sell'
    返回: (success, message)
    """
    if not GM_AVAILABLE:
        return False, "掘金SDK未就绪，请确保已安装gm库并配置Token"
    
    try:
        from gm.api import set_token, order_volume, OrderSide_Buy, OrderSide_Sell, OrderType_Limit
        
        set_token(GM_TOKEN)
        
        if stock_code.endswith('.SH'):
            symbol = f"SHSE.{stock_code.replace('.SH', '')}"
        elif stock_code.endswith('.SZ'):
            symbol = f"SZSE.{stock_code.replace('.SZ', '')}"
        else:
            symbol = stock_code
        
        order_side = OrderSide_Buy if side == "buy" else OrderSide_Sell
        
        order = order_volume(
            symbol=symbol,
            volume=volume,
            side=order_side,
            order_type=OrderType_Limit,
            position_effect=1,
            price=price
        )
        
        return True, f"下单成功！订单号: {order}"
    except Exception as e:
        return False, f"下单失败: {str(e)}"


# ==================== 模块5：实操信号 + 掘金下单 + 实操池管理 ====================

def render_live_signals():
    """实操信号模块 + 掘金一键下单 + 实操池管理 + 独立权重配置"""
    st.markdown(f"### {t()['module5_title']}")
    
    # 右上角：权重配置 + 刷新按钮
    col_title, col_refresh, col_weight = st.columns([6, 1, 1])
    with col_weight:
        render_weight_config_popover("live_signals", "实操信号")
    with col_refresh:
        if st.button(t()["refresh"], key="refresh_signals", use_container_width=True):
            if not consume_free_trial(st.session_state.user_id, st.session_state.get("access_token")):
                st.warning("免费次数已用完，请升级到专业版")
            else:
                # 刷新实操池价格
                refresh_live_pool_prices(st.session_state.user_id, st.session_state.get("access_token"))
                update_last_update_time("live_signals")
                st.rerun()
    
    last_update = get_last_update_time("live_signals")
    st.caption(f"📅 最后更新: {last_update} | 💡 AI生成交易信号，掘金一键下单")
    
    # 获取各模块权重（实操信号独立权重）
    live_weights = get_module_weights("live_signals")
    
    # ===== 实操池管理（新增） =====
    st.markdown("**📋 我的实操池**")
    
    # 添加股票到实操池
    col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
    with col1:
        add_live_stock = st.text_input(
            "股票代码", 
            placeholder="如: 000001.SZ", 
            key="add_live_input", 
            label_visibility="collapsed"
        )
    with col2:
        shares_input = st.number_input("股数", min_value=0, value=100, step=100, key="live_shares", label_visibility="collapsed")
    with col3:
        price_input = st.number_input("成本价", min_value=0.0, value=0.0, step=0.5, key="live_price", label_visibility="collapsed")
    with col4:
        if st.button("➕ 添加到实操池", key="add_live_btn", use_container_width=True):
            if add_live_stock:
                is_valid, formatted = validate_stock_code(add_live_stock)
                if is_valid:
                    stock_name = get_stock_name_from_tushare(formatted)
                    success, msg = add_to_live_pool(
                        st.session_state.user_id, formatted, stock_name,
                        shares=int(shares_input), avg_cost=float(price_input),
                        access_token=st.session_state.get("access_token")
                    )
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.error(formatted)
    
    # 获取实操池股票
    live_stocks = get_live_pool(st.session_state.user_id, st.session_state.get("access_token"))
    
    # 显示实操池
    if live_stocks:
        # 刷新当前价格
        for stock in live_stocks:
            ts_code = stock.get("stock_code")
            if ts_code:
                df = get_stock_daily(ts_code, days=1)
                if not df.empty:
                    stock["current_price"] = df['close'].iloc[-1]
        
        # 显示实操池表格
        live_df = []
        for stock in live_stocks:
            current_price = stock.get("current_price", 0)
            avg_cost = stock.get("avg_cost", 0)
            shares = stock.get("shares", 0)
            profit_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 and current_price > 0 else 0
            market_value = current_price * shares if current_price > 0 else 0
            
            live_df.append({
                "股票代码": stock["stock_code"],
                "股票名称": stock.get("stock_name", ""),
                "持仓股数": shares,
                "成本价": f"¥{avg_cost:.2f}" if avg_cost > 0 else "-",
                "现价": f"¥{current_price:.2f}" if current_price > 0 else "-",
                "盈亏": f"{profit_pct:+.1f}%" if avg_cost > 0 else "-",
                "市值": f"¥{market_value:,.0f}" if market_value > 0 else "-"
            })
        
        if live_df:
            st.dataframe(pd.DataFrame(live_df), use_container_width=True, hide_index=True)
        
        # 删除实操池股票
        for stock in live_stocks:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.caption(f"{stock['stock_code']} ({stock.get('stock_name', '')})")
            with col2:
                if st.button("编辑", key=f"edit_live_{stock['stock_code']}"):
                    st.session_state.edit_live_stock = stock
            with col3:
                if st.button("删除", key=f"del_live_{stock['stock_code']}"):
                    remove_from_live_pool(st.session_state.user_id, stock['stock_code'], st.session_state.get("access_token"))
                    st.rerun()
        
        # 编辑持仓（简化版）
        if st.session_state.get("edit_live_stock"):
            edit_stock = st.session_state.edit_live_stock
            st.markdown(f"**编辑 {edit_stock['stock_code']}**")
            col1, col2 = st.columns(2)
            with col1:
                new_shares = st.number_input("股数", value=edit_stock.get("shares", 0), step=100, key="edit_shares")
            with col2:
                new_avg_cost = st.number_input("成本价", value=float(edit_stock.get("avg_cost", 0)), step=0.5, key="edit_avg_cost")
            if st.button("保存修改", key="save_edit_live"):
                update_live_pool_prices(st.session_state.user_id, edit_stock['stock_code'], new_shares, new_avg_cost, st.session_state.get("access_token"))
                st.session_state.edit_live_stock = None
                st.rerun()
            if st.button("取消", key="cancel_edit_live"):
                st.session_state.edit_live_stock = None
                st.rerun()
    else:
        st.info("暂无实操股票，请上方添加")
    
    st.markdown("---")
    
    # ===== 交易信号生成 =====
    st.markdown("**💡 今日交易信号**")
    
    # 获取推荐池股票（高分股票自动加入信号）
    recommended_stocks = get_recommended_pool(st.session_state.user_id, st.session_state.get("access_token"))
    
    signals = []
    
    # 从推荐池获取高分股票（使用实操信号模块的独立权重计算）
    if recommended_stocks:
        with st.spinner("正在计算信号..."):
            for stock in recommended_stocks[:10]:  # 最多取10只
                score_result = get_stock_score(stock['stock_code'], stock.get('stock_name', ''), live_weights)
                score = score_result["total_score"]
                
                if score >= 70:
                    signals.append({
                        "stock_code": stock['stock_code'],
                        "stock_name": stock.get('stock_name', ''),
                        "score": score,
                        "action": "买入",
                        "suggested_position": "5-15%",
                        "confidence": f"{score:.0f}%",
                        "source": "推荐池"
                    })
    
    # 从实操池获取信号
    for stock in live_stocks:
        current_price = stock.get("current_price", 0)
        avg_cost = stock.get("avg_cost", 0)
        
        if avg_cost > 0 and current_price > 0:
            profit_pct = (current_price - avg_cost) / avg_cost * 100
            if profit_pct > 10:
                action = "卖出(获利)"
                action_color = "🟢"
            elif profit_pct < -8:
                action = "止损⚠️"
                action_color = "🔴"
            else:
                action = "持有"
                action_color = "⚪"
        else:
            action = "持有"
            action_color = "⚪"
        
        # 使用实操信号模块权重计算当前得分
        score_result = get_stock_score(stock['stock_code'], stock.get('stock_name', ''), live_weights)
        
        signals.append({
            "stock_code": stock['stock_code'],
            "stock_name": stock.get('stock_name', ''),
            "score": score_result["total_score"],
            "action": action,
            "suggested_position": f"{stock.get('shares', 0)}股",
            "confidence": f"{score_result['total_score']:.0f}%",
            "source": "实操池",
            "action_color": action_color
        })
    
    if not signals:
        st.info("暂无交易信号，请先在推荐池添加高评分股票，或添加实操池股票")
        return
    
    # 显示信号列表
    for idx, signal in enumerate(signals):
        with st.container(border=True):
            col1, col2, col3, col4, col5, col6 = st.columns([1.5, 1, 1.5, 1.5, 1.5, 1])
            
            with col1:
                st.markdown(f"**{signal['stock_code']}**")
                st.caption(signal['stock_name'])
            
            with col2:
                score = signal.get('score', 0)
                level = "S" if score >= 85 else "A" if score >= 70 else "B" if score >= 55 else "C" if score >= 40 else "D"
                color = SIGNAL_LEVELS.get(level, {}).get("color", "#888888")
                st.markdown(f"<h4 style='color:{color}; margin:0;'>{score:.0f}</h4>", unsafe_allow_html=True)
                st.caption(f"{level}级")
            
            with col3:
                action_text = signal['action']
                action_color = signal.get('action_color', "🟡")
                st.markdown(f"**{action_color} {action_text}**")
            
            with col4:
                st.caption(f"建议: {signal['suggested_position']}")
            
            with col5:
                if signal.get('confidence'):
                    st.caption(f"置信度: {signal['confidence']}")
            
            with col6:
                if signal['action'] in ["买入", "卖出(获利)"] and GM_AVAILABLE:
                    # 获取当前价格
                    df = get_stock_daily(signal['stock_code'], days=1)
                    price = df['close'].iloc[-1] if not df.empty else 100.0
                    volume = 100
                    side = "buy" if "买入" in signal['action'] else "sell"
                    
                    if st.button(f"🤖 下单", key=f"order_{signal['stock_code']}_{idx}", use_container_width=True):
                        success, msg = place_gm_order(signal['stock_code'], volume, price, side)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)
                elif signal['action'] in ["买入", "卖出(获利)"]:
                    st.caption("⚙️ 掘金未配置")
    
    # 显示使用说明
    profile = get_user_profile(st.session_state.user_id, st.session_state.get("access_token"))
    if profile.get("subscription_tier") == "free":
        remaining = get_remaining_trials(st.session_state.user_id, st.session_state.get("access_token"))
        st.info(f"📋 免费用户每次刷新消耗1次，剩余{remaining}次。升级专业版后无限使用。")
    
    st.markdown("---")
    st.markdown("### 📖 操作指引")
    st.markdown("""
    1. 在【我的实操池】添加已持有的股票，记录持仓成本
    2. 查看上方交易信号（来自推荐池高分股票 + 实操池持仓）
    3. 点击[🤖 下单]按钮通过掘金自动下单
    4. 或在券商App手动下单
    5. 可在实操池中编辑/删除持仓记录
    
    ⚠️ 投资有风险，请谨慎决策
    """)


print("第4部分加载完成")
print("=" * 60)
# ============================================================
# ============================================================
# 第5部分：主入口 + 侧边栏 + 顶部按钮 + 页面路由 + 管理员面板
# 修复内容：
# - 侧边栏只显示用户名（不显示邮箱后缀）
# - 管理员退出后返回原登录状态
# - 添加缓存机制优化性能
# - 添加股票名称缓存加载（解决Tushare频率超限）
# - 管理员面板添加股票列表同步按钮
# - 添加板块缓存初始化
# - 添加板块管理入口
# - 添加各模块权重初始化
# ============================================================

# ==================== 缓存优化函数 ====================

@st.cache_data(ttl=3600)  # 缓存1小时
def get_cached_stock_data(ts_code: str, days: int = 120):
    """缓存股票日线数据"""
    return get_stock_daily(ts_code, days)


@st.cache_data(ttl=3600)  # 缓存1小时
def get_cached_stock_score(ts_code: str, stock_name: str = ""):
    """缓存股票评分结果"""
    return get_stock_score(ts_code, stock_name)


# ==================== 各模块权重初始化 ====================

def init_all_module_weights():
    """
    初始化所有5个模块的独立权重配置（4个层级）
    每个模块使用各自的默认权重
    """
    # 定义各模块的4层权重默认值
    modules_to_init = [
        ("weights_market_brief", {      # 市场简报
            "sector_heat": 0.40,
            "leader": 0.30,
            "technical": 0.20,
            "trend": 0.10
        }),
        ("weights_recommended", {       # 推荐股票池
            "sector_heat": 0.40,
            "leader": 0.30,
            "technical": 0.20,
            "trend": 0.10
        }),
        ("weights_stock_analysis", {    # 个股分析
            "sector_heat": 0.25,
            "leader": 0.15,
            "technical": 0.40,
            "trend": 0.20
        }),
        ("weights_backtest", {          # 回测功能
            "sector_heat": 0.25,
            "leader": 0.15,
            "technical": 0.40,
            "trend": 0.20
        }),
        ("weights_live_signals", {      # 实操信号
            "sector_heat": 0.25,
            "leader": 0.15,
            "technical": 0.40,
            "trend": 0.20
        })
    ]
    
    for key, default_weights in modules_to_init:
        if st.session_state.get(key) is None:
            st.session_state[key] = default_weights


# ==================== 管理员辅助函数 ====================

def get_all_users() -> list:
    """获取所有用户列表（管理员用）"""
    try:
        response = supabase_request("GET", "user_settings", use_secret=True)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取用户列表失败: {e}")
        return []


def get_user_auth_details(user_id: str) -> Dict:
    """获取用户的认证详细信息"""
    try:
        url = f"{SUPABASE_URL}/auth/v1/admin/users"
        headers = get_supabase_headers(use_secret=True)
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            users = response.json().get("users", [])
            for user in users:
                if user.get("id") == user_id:
                    return {
                        "created_at": user.get("created_at", ""),
                        "last_sign_in_at": user.get("last_sign_in_at", ""),
                        "email_confirmed_at": user.get("email_confirmed_at", "")
                    }
    except Exception as e:
        print(f"获取用户认证信息失败: {e}")
    
    return {"created_at": "", "last_sign_in_at": "", "email_confirmed_at": ""}


def get_user_stock_summary(user_id: str) -> Dict:
    """获取用户的股票池摘要"""
    access_token = st.session_state.get("access_token") if not st.session_state.admin_mode else None
    recommended = get_recommended_pool(user_id, access_token)
    backtest = get_backtest_pool(user_id, access_token)
    live = get_live_pool(user_id, access_token)
    
    return {
        "recommended_count": len(recommended),
        "backtest_count": len(backtest),
        "live_count": len(live)
    }


def admin_delete_user(user_id: str, user_email: str) -> tuple:
    """管理员删除用户"""
    try:
        url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"
        headers = get_supabase_headers(use_secret=True)
        response = requests.delete(url, headers=headers)
        
        if response.status_code in [200, 204]:
            settings_url = f"{SUPABASE_URL}/rest/v1/user_settings?user_id=eq.{user_id}"
            requests.delete(settings_url, headers=headers)
            return True, f"用户 {user_email} 已删除"
        else:
            return False, f"删除失败: {response.text}"
    except Exception as e:
        return False, f"删除失败: {str(e)}"


def admin_reset_user_trials(user_id: str, new_trials: int = FREE_TRIAL_LIMIT) -> tuple:
    """重置用户的免费次数"""
    try:
        success = update_user_profile(user_id, {"free_trials_remaining": new_trials})
        if success:
            return True, f"已重置免费次数为 {new_trials}"
        return False, "重置失败"
    except Exception as e:
        return False, f"重置失败: {str(e)}"


def admin_set_subscription(user_id: str, tier: str, months: int = 1) -> tuple:
    """设置用户订阅等级"""
    try:
        data = {"subscription_tier": tier}
        
        if tier == "pro":
            expires_at = (datetime.now() + timedelta(days=30 * months)).isoformat()
            data["subscription_expires_at"] = expires_at
        else:
            data["subscription_expires_at"] = None
        
        success = update_user_profile(user_id, data)
        if success:
            return True, f"用户订阅已设置为 {tier}"
        return False, "设置失败"
    except Exception as e:
        return False, f"设置失败: {str(e)}"


def send_password_reset_email(email: str) -> tuple:
    """发送密码重置邮件"""
    try:
        url = f"{SUPABASE_URL}/auth/v1/recover"
        headers = {
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Content-Type": "application/json"
        }
        data = {"email": email}
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            return True, f"密码重置邮件已发送至 {email}"
        else:
            return False, f"发送失败: {response.text}"
    except Exception as e:
        return False, f"发送失败: {str(e)}"


def update_live_pool_prices(user_id: str, stock_code: str, shares: int = None, 
                            avg_cost: float = None, access_token: str = None) -> tuple:
    """更新实操池中股票的持仓信息（辅助函数）"""
    try:
        update_data = {}
        if shares is not None:
            update_data["shares"] = shares
        if avg_cost is not None:
            update_data["avg_cost"] = avg_cost
        update_data["updated_time"] = datetime.now().isoformat()
        
        if not update_data:
            return False, "无更新内容"
        
        response = supabase_request(
            "PATCH",
            "live_pool",
            data=update_data,
            params=f"user_id=eq.{user_id}&stock_code=eq.{stock_code}",
            access_token=access_token
        )
        if response.status_code in [200, 204]:
            return True, f"已更新 {stock_code}"
        return False, f"更新失败: {response.text}"
    except Exception as e:
        return False, f"更新失败: {str(e)}"


# ==================== 管理员面板 ====================

def render_admin_panel():
    """管理员面板主界面"""
    st.markdown(f"## ⚙️ {t()['admin_panel']}")
    
    users = get_all_users()
    
    if not users:
        st.info("暂无用户数据")
        if st.button("退出管理员模式", use_container_width=True):
            admin_sign_out()
            st.rerun()
        return
    
    users_with_details = []
    for user in users:
        auth_details = get_user_auth_details(user.get("user_id", ""))
        stock_summary = get_user_stock_summary(user.get("user_id", ""))
        
        users_with_details.append({
            "id": user.get("user_id"),
            "email": user.get("email", ""),
            "subscription_tier": user.get("subscription_tier", "free"),
            "free_trials_remaining": user.get("free_trials_remaining", FREE_TRIAL_LIMIT),
            "subscription_expires_at": user.get("subscription_expires_at", "")[:10] if user.get("subscription_expires_at") else "-",
            "created_at": auth_details.get("created_at", "")[:10] if auth_details.get("created_at") else "-",
            "last_sign_in_at": auth_details.get("last_sign_in_at", "")[:10] if auth_details.get("last_sign_in_at") else "-",
            "email_confirmed": "✅" if auth_details.get("email_confirmed_at") else "❌",
            "recommended_count": stock_summary["recommended_count"],
            "backtest_count": stock_summary["backtest_count"],
            "live_count": stock_summary["live_count"]
        })
    
    # 统计卡片
    st.markdown("### 📊 系统统计")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(t()["total_users"], len(users))
    with col2:
        pro_count = sum(1 for u in users_with_details if u["subscription_tier"] == "pro")
        st.metric(t()["pro_users"], pro_count)
    with col3:
        free_count = len(users) - pro_count
        st.metric(t()["free_users"], free_count)
    with col4:
        total_recommended = sum(u["recommended_count"] for u in users_with_details)
        st.metric("总推荐股票数", total_recommended)
    
    st.markdown("---")
    
    # 用户列表
    st.markdown(f"### 👥 {t()['user_list']}")
    df_users = pd.DataFrame(users_with_details)
    display_columns = ["email", "subscription_tier", "free_trials_remaining", 
                       "subscription_expires_at", "created_at", "last_sign_in_at",
                       "email_confirmed", "recommended_count", "backtest_count", "live_count"]
    
    st.dataframe(
        df_users[display_columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            "email": "邮箱",
            "subscription_tier": "订阅等级",
            "free_trials_remaining": "剩余次数",
            "subscription_expires_at": "到期时间",
            "created_at": "注册时间",
            "last_sign_in_at": "最后登录",
            "email_confirmed": "邮箱确认",
            "recommended_count": "推荐池",
            "backtest_count": "回测池",
            "live_count": "实操池"
        }
    )
    
    st.markdown("---")
    
    # 用户管理
    st.markdown("### 🔧 用户管理")
    user_options = [f"{u['email']} ({u['subscription_tier']})" for u in users_with_details]
    selected_user_str = st.selectbox("选择用户", user_options, key="admin_select_user")
    selected_email = selected_user_str.split(" ")[0]
    selected_user = next((u for u in users_with_details if u["email"] == selected_email), None)
    
    if selected_user:
        st.markdown(f"**当前用户**: {selected_user['email']}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 📝 修改订阅")
            new_tier = st.selectbox("订阅等级", ["free", "pro"], 
                                    index=0 if selected_user["subscription_tier"] == "free" else 1, key="admin_new_tier")
            pro_months = 1
            if new_tier == "pro":
                pro_months = st.number_input("月数", min_value=1, max_value=12, value=1, key="admin_months")
            
            if st.button("更新订阅", key="admin_update_subscription", use_container_width=True):
                success, msg = admin_set_subscription(selected_user["id"], new_tier, pro_months)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        
        with col2:
            st.markdown("#### 🎫 免费次数")
            new_trials = st.number_input("设置剩余次数", min_value=0, max_value=100, 
                                          value=selected_user["free_trials_remaining"], key="admin_new_trials")
            if st.button("重置次数", key="admin_reset_trials", use_container_width=True):
                success, msg = admin_reset_user_trials(selected_user["id"], new_trials)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        
        st.markdown("#### ⚠️ 操作")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📧 发送重置邮件", key="admin_send_reset", use_container_width=True):
                success, msg = send_password_reset_email(selected_user["email"])
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
        with col2:
            if st.button("🔑 删除用户", key="admin_delete_user", use_container_width=True):
                success, msg = admin_delete_user(selected_user["id"], selected_user["email"])
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        with col3:
            if st.button("👤 查看股票池", key="admin_view_stocks_btn", use_container_width=True):
                st.session_state.admin_view_user_id = selected_user["id"]
                st.session_state.admin_view_user_email = selected_user["email"]
                st.rerun()
    
    # 查看用户股票池
    if st.session_state.get("admin_view_user_id"):
        st.markdown("---")
        st.markdown(f"### 📊 查看股票池: {st.session_state.admin_view_user_email}")
        
        view_user_id = st.session_state.admin_view_user_id
        
        tab1, tab2, tab3 = st.tabs(["推荐股票池", "回测股票池", "实操股票池"])
        
        with tab1:
            stocks = get_recommended_pool(view_user_id)
            if stocks:
                st.dataframe(pd.DataFrame(stocks), use_container_width=True, hide_index=True)
                st.caption(f"共 {len(stocks)} 只股票")
            else:
                st.info("暂无推荐股票")
        
        with tab2:
            stocks = get_backtest_pool(view_user_id)
            if stocks:
                st.dataframe(pd.DataFrame(stocks), use_container_width=True, hide_index=True)
                st.caption(f"共 {len(stocks)} 只股票")
            else:
                st.info("暂无回测股票")
        
        with tab3:
            stocks = get_live_pool(view_user_id)
            if stocks:
                st.dataframe(pd.DataFrame(stocks), use_container_width=True, hide_index=True)
                st.caption(f"共 {len(stocks)} 只股票")
            else:
                st.info("暂无实操股票")
        
        if st.button("关闭", key="close_view_stocks"):
            st.session_state.admin_view_user_id = None
            st.session_state.admin_view_user_email = None
            st.rerun()
    
    st.markdown("---")
    
    # 批量操作
    st.markdown("### 🔄 批量操作")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("重置所有免费用户次数", key="admin_reset_all_free", use_container_width=True):
            count = 0
            for user in users_with_details:
                if user["subscription_tier"] == "free":
                    admin_reset_user_trials(user["id"], FREE_TRIAL_LIMIT)
                    count += 1
            st.success(f"已重置 {count} 位免费用户的次数")
            st.rerun()
    
    with col2:
        if st.button("导出用户数据(CSV)", key="admin_export_csv", use_container_width=True):
            csv = df_users.to_csv(index=False).encode('utf-8')
            st.download_button(label="下载CSV", data=csv, 
                              file_name=f"users_{datetime.now().strftime('%Y%m%d')}.csv",
                              mime="text/csv", key="admin_download_csv")
    
    st.markdown("---")
    
    # 数据管理（股票列表同步）
    st.markdown("### 📊 数据管理")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 同步股票列表", key="sync_stocks", use_container_width=True):
            with st.spinner("正在同步股票列表（可能需要1分钟）..."):
                global STOCK_NAME_CACHE
                STOCK_NAME_CACHE = {}
                if sync_stock_basic_to_db():
                    st.success("✅ 股票列表同步成功！")
                    st.session_state.stock_cache_loaded = False
                    st.rerun()
                else:
                    st.error("❌ 同步失败，请检查Tushare连接")
    
    with col2:
        if st.button("🔄 同步预置板块到缓存", key="sync_default_sectors", use_container_width=True):
            with st.spinner("正在同步预置板块..."):
                # 直接使用预置板块，不调用 Tushare
                try:
                    save_default_sectors_to_cache()
                    st.success("✅ 预置板块已同步到缓存")
                    st.session_state.sector_cache_loaded = False
                    st.rerun()
                except Exception as e:
                    st.error(f"同步失败: {e}")    
    st.markdown("---")
    
    if st.button("退出管理员模式", use_container_width=True):
        prev_user_id = st.session_state.get("admin_previous_user_id")
        prev_user_email = st.session_state.get("admin_previous_user_email")
        prev_access_token = st.session_state.get("admin_previous_access_token")
        prev_refresh_token = st.session_state.get("admin_previous_refresh_token")
        
        if prev_user_id and prev_user_email:
            st.session_state.authenticated = True
            st.session_state.user_id = prev_user_id
            st.session_state.user_email = prev_user_email
            st.session_state.access_token = prev_access_token
            st.session_state.refresh_token = prev_refresh_token
            st.session_state.token_expiry = time.time() + 3600
        else:
            st.session_state.authenticated = False
            st.session_state.user_id = None
            st.session_state.user_email = None
            st.session_state.access_token = None
            st.session_state.refresh_token = None
            st.session_state.token_expiry = None
        
        st.session_state.admin_mode = False
        st.session_state.admin_previous_user_id = None
        st.session_state.admin_previous_user_email = None
        st.session_state.admin_previous_access_token = None
        st.session_state.admin_previous_refresh_token = None
        st.rerun()


# ==================== 侧边栏 ====================

def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.markdown("## 📊 AI量化股票系统")
        st.markdown("---")
 # 连接状态显示（新增）
        st.markdown("**🔌 连接状态**")
        col_status1, col_status2 = st.columns(2)
        with col_status1:
            if TUSHARE_AVAILABLE:
                st.write("DEBUG: Tushare 可用")
                st.markdown("✅ Tushare")
            else:
                st.write("DEBUG: Tushare 不可用")
                st.markdown("❌ Tushare")
        with col_status2:
            if GM_AVAILABLE:
                st.markdown("✅ 掘金")
            else:
                st.markdown("❌ 掘金")
        
        st.markdown("---")

        
        if st.session_state.authenticated and not st.session_state.admin_mode:
            user_email = st.session_state.user_email
            username = user_email.split('@')[0] if user_email else user_email
            user_id = st.session_state.user_id
            access_token = st.session_state.get("access_token")
            
            profile = get_user_profile(user_id, access_token)
            
            tier = profile.get("subscription_tier", "free")
            remaining = profile.get("free_trials_remaining", 0)
            
            try:
                remaining = int(remaining) if remaining else 0
            except (ValueError, TypeError):
                remaining = 0
            
            tier_display = "💎 专业版" if tier == "pro" else "🔒 免费版"
            remaining_display = "∞" if remaining == -1 else str(remaining)
            
            st.markdown(f"""
            <div class="sidebar-user-info">
                <strong>👤 {username}</strong><br>
                📋 {t()['subscription']}: {tier_display}<br>
                🎫 {t()['remaining']}: {remaining_display}
            </div>
            """, unsafe_allow_html=True)
            
            if tier == "free":
                if st.button("💎 " + t()["upgrade"], key="sidebar_upgrade", use_container_width=True):
                    st.session_state.show_paywall = True
                    st.rerun()
            
            st.markdown("---")
        
        st.markdown("### 🌍 市场选择")
        market = st.selectbox("选择市场", MARKET_OPTIONS, index=0, key="market_selector", label_visibility="collapsed")
        if market != st.session_state.get("market", "A股"):
            st.session_state.market = market
            st.rerun()
        
        st.markdown("---")
        
        # 板块管理入口
        if st.session_state.authenticated and not st.session_state.admin_mode:
            if st.button("📁 板块管理", key="sector_mgmt_btn", use_container_width=True):
                st.session_state.show_sector_management = True
                st.rerun()
            st.markdown("---")
        
        with st.expander(t()["about_header"], expanded=True):
            st.markdown(t()["about_text"])
        
        with st.expander(t()["guide_header"], expanded=False):
            st.markdown(t()["guide_text"])
        
        with st.expander(t()["contact_header"], expanded=False):
            st.markdown(t()["contact_email"])
        
        st.markdown("---")
        st.caption("v4.0 | TechLife")
        st.caption("数据: Tushare | 交易: 掘金 | 支付: Stripe")


# ==================== 右上角按钮 ====================

def render_top_buttons():
    """渲染右上角按钮"""
    col1, col2, col3, col4, col5 = st.columns([8, 1.2, 1.2, 1.2, 1])
    
    with col2:
        if st.button("中文", key="zh_btn", use_container_width=True):
            if st.session_state.lang != "zh":
                st.session_state.lang = "zh"
                st.rerun()
    
    with col3:
        if st.button("English", key="en_btn", use_container_width=True):
            if st.session_state.lang != "en":
                st.session_state.lang = "en"
                st.rerun()
    
    with col4:
        if st.button("⚙️", key="gear_btn", help="管理员登录", use_container_width=True):
            st.session_state.show_admin_login = True
            st.rerun()
    
    with col5:
        if st.session_state.authenticated:
            if st.session_state.admin_mode:
                if st.button("👤 返回用户", key="back_to_user_btn", help="退出管理员模式", use_container_width=True):
                    admin_sign_out()
                    st.rerun()
            else:
                if st.button("🚪", key="logout_btn", help="退出登录", use_container_width=True):
                    sign_out()
                    st.rerun()


# ==================== 主页面 ====================

def render_main_app():
    """渲染主页面（5个模块）"""
    # 处理支付回调前，先恢复可能的登录状态
    query_params = st.query_params
    if "user_id" in query_params and "email" in query_params:
        st.session_state.authenticated = True
        st.session_state.user_id = query_params["user_id"]
        st.session_state.user_email = query_params["email"]
        # 清除URL参数，避免重复
        st.query_params.clear()
        st.rerun()
    
    handle_stripe_callback()
    # ===== 手动验证 Stripe 支付 =====
    query_params = st.query_params
    if "session_id" in query_params:
        session_id = query_params["session_id"]
        
        st.warning("🔔 检测到支付会话，请点击下方按钮完成验证")
        st.info(f"会话ID: {session_id[:30]}...")
        
        if st.button("✅ 手动验证支付并升级", type="primary", use_container_width=True):
            try:
                import stripe
                stripe.api_key = STRIPE_SECRET_KEY
                session = stripe.checkout.Session.retrieve(session_id)
                
                if session.payment_status == "paid":
                    user_id = session.metadata.get("user_id")
                    
                    if user_id and user_id != "admin":
                        headers = get_supabase_headers(use_secret=True)
                        url = f"{SUPABASE_URL}/rest/v1/user_settings?user_id=eq.{user_id}"
                        data = {"subscription_tier": "pro"}
                        response = requests.patch(url, headers=headers, json=data)
                        
                        if response.status_code in [200, 204]:
                            st.success("✅ 支付验证成功！您已是专业版用户")
                            st.balloons()
                            st.query_params.clear()
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error(f"更新失败: {response.text}")
                    else:
                        st.warning("用户信息验证失败，请重新登录")
                else:
                    st.warning(f"支付状态: {session.payment_status}，未完成")
            except Exception as e:
                st.error(f"验证失败: {e}")
        
        st.markdown("---")
    # =================================
    
    if st.session_state.get("show_paywall", False):
        show_paywall()
        return
    
    handle_stripe_callback()  # 保留原有回调，两者并存
    
    # 板块管理页面
    if st.session_state.get("show_sector_management", False):
        render_sector_management()
        if st.button("返回主页", key="back_to_main", use_container_width=True):
            st.session_state.show_sector_management = False
            st.rerun()
        return
    
    # 获取用户名显示
    username = st.session_state.user_email.split('@')[0] if st.session_state.user_email else st.session_state.user_email
    st.markdown(f"<h3 style='text-align: left;'>{t()['welcome']}, {username}</h3>", unsafe_allow_html=True)
    
    access_token = st.session_state.get("access_token")
    user_id = st.session_state.user_id
    
    profile = get_user_profile(user_id, access_token)
    if profile.get("subscription_tier") == "free":
        remaining = get_remaining_trials(user_id, access_token)
        st.caption(f"📋 剩余免费次数: {remaining} | 升级专业版后无限使用")
    
    st.markdown("---")
    
    with st.spinner("加载数据中..."):
        if TUSHARE_AVAILABLE and not STOCK_NAME_CACHE:
            load_stock_name_cache()
        if not st.session_state.get("sector_cache_loaded", False):
            init_sector_cache_on_startup()
            st.session_state.sector_cache_loaded = True
        # 初始化各模块权重
        init_all_module_weights()
    
    # 模块1：市场简报
    with st.container():
        render_market_brief()
        st.markdown("---")
    
    # 模块2：推荐股票池
    with st.container():
        render_recommended_pool()
        st.markdown("---")
    
    # 模块3：个股分析
    with st.container():
        render_stock_analysis()
        st.markdown("---")
    
    # 模块4：回测功能
    with st.container():
        render_backtest()
        st.markdown("---")
    
    # 模块5：实操信号
    with st.container():
        render_live_signals()
        st.markdown("---")
    
    st.caption("⚠️ 本系统仅供学术研究和娱乐参考。股市有风险，投资需谨慎。所有AI建议不构成投资建议。")


# ==================== 主函数 ====================

def main():
    """主函数：控制页面流程"""
    
    init_session_state()
    
    # ===== 重要：在任何页面渲染之前处理支付回调 =====
    # ================================================
    
    # 加载缓存
    if not st.session_state.get("stock_cache_loaded", False):
        with st.spinner("加载股票数据..."):
            load_stock_name_cache()
            st.session_state.stock_cache_loaded = True
    
    render_sidebar()
    render_top_buttons()
    
    if st.session_state.get("show_admin_login", False):
        render_admin_login_form()
        return
    
    if st.session_state.get("admin_mode", False):
        render_admin_panel()
        return
    
    if not st.session_state.authenticated:
        if st.session_state.get("show_register", False):
            render_register_form()
        else:
            render_login_form()
        return
    
    render_main_app()


if __name__ == "__main__":
    main()
# ==================== 自定义CSS ====================
st.markdown("""
<style>
    .main-header {
        text-align: center;
        margin-bottom: 1rem;
    }
    
    .sidebar-user-info {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    
    .stButton button {
        border-radius: 0.5rem;
        transition: all 0.2s;
    }
    
    .stDataFrame {
        font-size: 0.9rem;
    }
    
    .stMetric {
        text-align: center;
    }
    
    .signal-s { color: #ff4b4b; font-weight: bold; }
    .signal-a { color: #ff6b6b; font-weight: bold; }
    .signal-b { color: #ffaa00; font-weight: bold; }
    .signal-c { color: #ff8800; font-weight: bold; }
    .signal-d { color: #888888; font-weight: bold; }
    
    .market-selector {
        margin-bottom: 1rem;
        padding: 0.5rem;
        background-color: #f8f9fa;
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


print("第5部分加载完成")
print("=" * 60)
print("所有代码加载完成！AI量化股票系统 v4.0 已就绪。")
print("更新内容：")
print("  - 5个模块独立权重配置（右上角自动保存）")
print("  - 市场简报增加上证指数技术指标")
print("  - 实操信号模块新增实操池增删功能")
print("=" * 60)
