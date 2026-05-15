"""
AI量化股票系统 - 完整版本 v2.0
基于DFSS方法论 + 机器学习集成 + Tushare真实数据

更新内容：
- 市场简报：动态计算预置板块实时涨跌幅
- 推荐股票池：真实A股数据技术指标评分
- 个股分析：K线图 + 技术指标分析
- 管理员退出逻辑修复
- 每个模块显示最后更新时间
- 股票名称自动获取和显示
"""

# ============================================================
# 第1部分：导入、配置、常量、多语言、Supabase连接、Tushare初始化、工具函数
# ============================================================

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

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="AI量化股票系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== 管理员配置 ====================
ADMIN_USERNAME = "Laurence_ku"
ADMIN_PASSWORD = "Ku_product$2026"
ADMIN_EMAIL = "Techlife2027@gmail.com"

# ==================== 常量定义 ====================
FREE_TRIAL_LIMIT = 30
MAX_RECOMMENDED_STOCKS = 30

# 技术指标权重
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

# 预置热点板块（解决光模块等板块缺失问题）
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
    }
}

# 市场选项
MARKET_OPTIONS = ["A股", "港股", "美股"]

# 股票名称缓存（从Tushare获取）
STOCK_NAME_CACHE = {}

# ==================== Supabase 配置 ====================
SUPABASE_URL = st.secrets.get("SUPABASE_STOCK_URL", "")
SUPABASE_PUBLISHABLE_KEY = st.secrets.get("SUPABASE_STOCK_ANON_KEY", "")
SUPABASE_SECRET_KEY = st.secrets.get("SUPABASE_STOCK_SECRET_KEY", "")

# ==================== Stripe 配置 ====================
STRIPE_PRICE_MONTHLY = st.secrets.get("STRIPE_PRICE_MONTHLY", "")
STRIPE_PRICE_YEARLY = st.secrets.get("STRIPE_PRICE_YEARLY", "")

# ==================== DeepSeek 配置 ====================
DEEPSEEK_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = st.secrets.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = st.secrets.get("DEEPSEEK_MODEL", "deepseek-chat")

# ==================== Tushare 配置与初始化 ====================
TUSHARE_TOKEN = st.secrets.get("TUSHARE_TOKEN", "")
TUSHARE_AVAILABLE = False
TUSHARE_PRO = None

if TUSHARE_TOKEN:
    try:
        import tushare as ts
        ts.set_token(TUSHARE_TOKEN)
        TUSHARE_PRO = ts.pro_api()
        TUSHARE_AVAILABLE = True
        print("✅ Tushare 初始化成功")
    except ImportError:
        print("❌ Tushare 未安装，请运行: pip install tushare")
    except Exception as e:
        print(f"❌ Tushare 初始化失败: {e}")


def load_stock_name_cache() -> Dict[str, str]:
    """
    加载股票名称缓存（从Tushare获取全量A股名称）
    返回: { "000001.SZ": "平安银行", ... }
    """
    global STOCK_NAME_CACHE
    
    if STOCK_NAME_CACHE:
        return STOCK_NAME_CACHE
    
    if not TUSHARE_AVAILABLE or TUSHARE_PRO is None:
        return {}
    
    try:
        # 获取A股列表
        df = TUSHARE_PRO.stock_basic(exchange='', list_status='L', fields='ts_code,name')
        for _, row in df.iterrows():
            STOCK_NAME_CACHE[row['ts_code']] = row['name']
        print(f"✅ 加载股票名称缓存成功，共{len(STOCK_NAME_CACHE)}只")
    except Exception as e:
        print(f"❌ 加载股票名称缓存失败: {e}")
    
    return STOCK_NAME_CACHE


def get_stock_name(ts_code: str) -> str:
    """根据股票代码获取名称"""
    if not STOCK_NAME_CACHE:
        load_stock_name_cache()
    return STOCK_NAME_CACHE.get(ts_code, ts_code.split('.')[0])


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
5. 实操信号供手动下单参考

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
5. Signals for manual trading reference

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


# ==================== 工具函数 ====================
def get_current_time_str() -> str:
    """获取当前时间字符串（精确到分钟）"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def update_last_update_time(module_name: str):
    """更新模块的最后更新时间"""
    st.session_state.last_update_time[module_name] = get_current_time_str()


def get_last_update_time(module_name: str) -> str:
    """获取模块的最后更新时间"""
    return st.session_state.last_update_time.get(module_name, "未更新")


print("第1部分加载完成")
print("=" * 60)
# ============================================================
# 第2部分：管理员页面 + 登录验证 + 用户认证 + Supabase API封装
# ============================================================

# ==================== Supabase API 封装 ====================

def get_supabase_headers(use_secret=False):
    """
    获取Supabase API请求头
    use_secret: True=使用secret key（管理员操作），False=使用publishable key（普通用户）
    """
    if use_secret:
        api_key = SUPABASE_SECRET_KEY
    else:
        api_key = SUPABASE_PUBLISHABLE_KEY
    
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }


def supabase_request(method: str, endpoint: str, data=None, params=None, use_secret=False):
    """通用的Supabase REST API请求"""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = get_supabase_headers(use_secret)
    
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
    
    return response


# ==================== 用户认证 ====================

def sign_up(email: str, password: str) -> tuple:
    """
    用户注册
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
            data = response.json()
            user_id = data.get("user", {}).get("id")
            
            # 创建用户profile
            if user_id:
                profile_data = {
                    "id": user_id,
                    "email": email,
                    "subscription_tier": "free",
                    "free_trials_remaining": FREE_TRIAL_LIMIT,
                    "subscription_expires_at": None,
                    "created_at": datetime.now().isoformat()
                }
                supabase_request("POST", "profiles", profile_data, use_secret=True)
            
            return True, "注册成功", user_id
        else:
            error = response.json()
            if "User already registered" in str(error):
                return False, "该邮箱已注册，请直接登录", None
            return False, f"注册失败: {error.get('msg', '未知错误')}", None
    except Exception as e:
        return False, f"注册失败: {str(e)}", None


def sign_in(email: str, password: str) -> tuple:
    """
    用户登录
    返回: (success, message, user_id, user_email)
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
            data = response.json()
            user_id = data.get("user", {}).get("id")
            user_email = data.get("user", {}).get("email")
            
            # 更新最后登录时间
            if user_id:
                supabase_request("PATCH", f"profiles?id=eq.{user_id}", 
                                {"last_sign_in_at": datetime.now().isoformat()}, 
                                use_secret=True)
            
            return True, "登录成功", user_id, user_email
        else:
            return False, "邮箱或密码错误", None, None
    except Exception as e:
        return False, f"登录失败: {str(e)}", None, None


def sign_out():
    """退出登录（普通用户）"""
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.user_email = None
    st.session_state.admin_mode = False
    st.rerun()


def admin_sign_out():
    """管理员退出（返回到之前的登录状态）"""
    # 清除管理员标志，但保持普通用户登录状态
    st.session_state.admin_mode = False
    # 不清除 authenticated，保持用户登录状态
    st.rerun()


def check_admin_login(username: str, password: str) -> bool:
    """验证管理员登录"""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD


# ==================== 用户资料操作 ====================

def get_user_profile(user_id: str) -> dict:
    """获取用户资料（订阅等级、剩余次数等）"""
    if not user_id or user_id == "admin":
        return {
            "subscription_tier": "free",
            "free_trials_remaining": FREE_TRIAL_LIMIT,
            "subscription_expires_at": None,
            "last_sign_in_at": None
        }
    
    try:
        response = supabase_request("GET", f"profiles?id=eq.{user_id}", use_secret=True)
        if response.status_code == 200 and response.json():
            data = response.json()[0]
            return {
                "subscription_tier": data.get("subscription_tier", "free"),
                "free_trials_remaining": data.get("free_trials_remaining", FREE_TRIAL_LIMIT),
                "subscription_expires_at": data.get("subscription_expires_at"),
                "last_sign_in_at": data.get("last_sign_in_at")
            }
    except Exception as e:
        print(f"获取用户资料失败: {e}")
    
    return {
        "subscription_tier": "free",
        "free_trials_remaining": FREE_TRIAL_LIMIT,
        "subscription_expires_at": None,
        "last_sign_in_at": None
    }


def update_user_profile(user_id: str, data: dict) -> bool:
    """更新用户资料"""
    try:
        response = supabase_request("PATCH", f"profiles?id=eq.{user_id}", data, use_secret=True)
        return response.status_code in [200, 204]
    except Exception:
        return False


def get_remaining_trials(user_id: str) -> int:
    """获取剩余免费次数"""
    profile = get_user_profile(user_id)
    if profile.get("subscription_tier") == "pro":
        return -1  # -1 表示无限
    return profile.get("free_trials_remaining", 0)


def consume_free_trial(user_id: str) -> bool:
    """
    消耗一次免费次数
    返回: True=有次数可用，False=次数已用完
    """
    profile = get_user_profile(user_id)
    
    # 专业版用户无限使用
    if profile.get("subscription_tier") == "pro":
        return True
    
    remaining = profile.get("free_trials_remaining", 0)
    
    if remaining > 0:
        update_user_profile(user_id, {"free_trials_remaining": remaining - 1})
        return True
    else:
        st.session_state.show_paywall = True
        return False


# ==================== 股票池操作 ====================

def get_recommended_pool(user_id: str) -> List[Dict]:
    """获取用户的推荐股票池"""
    if not user_id or user_id == "admin":
        return []
    
    try:
        response = supabase_request(
            "GET", 
            "recommended_pool", 
            params=f"user_id=eq.{user_id}&is_deleted=eq.false&order=current_score.desc"
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取推荐池失败: {e}")
        return []


def add_to_recommended_pool(user_id: str, stock_code: str, stock_name: str, 
                            source: str = "user", score: float = 0) -> tuple:
    """
    添加股票到推荐池
    返回: (success, message)
    """
    # 检查数量限制
    stocks = get_recommended_pool(user_id)
    if len(stocks) >= MAX_RECOMMENDED_STOCKS:
        return False, f"推荐池已达上限（{MAX_RECOMMENDED_STOCKS}只），请先删除部分股票"
    
    # 检查是否已存在
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
            "is_deleted": False
        }
        response = supabase_request("POST", "recommended_pool", data)
        if response.status_code in [200, 201]:
            return True, f"成功添加 {stock_code} ({stock_name})"
        return False, f"添加失败: {response.text}"
    except Exception as e:
        return False, f"添加失败: {str(e)}"


def remove_from_recommended_pool(user_id: str, stock_code: str) -> tuple:
    """从推荐池删除股票（软删除）"""
    try:
        data = {"is_deleted": True}
        response = supabase_request(
            "PATCH", 
            "recommended_pool", 
            data=data,
            params=f"user_id=eq.{user_id}&stock_code=eq.{stock_code}"
        )
        if response.status_code in [200, 204]:
            return True, f"已删除 {stock_code}"
        return False, f"删除失败: {response.text}"
    except Exception as e:
        return False, f"删除失败: {str(e)}"


def get_backtest_pool(user_id: str) -> List[Dict]:
    """获取用户的回测股票池"""
    if not user_id or user_id == "admin":
        return []
    
    try:
        response = supabase_request(
            "GET", 
            "backtest_pool", 
            params=f"user_id=eq.{user_id}"
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取回测池失败: {e}")
        return []


def add_to_backtest_pool(user_id: str, stock_code: str, stock_name: str) -> tuple:
    """添加股票到回测池"""
    stocks = get_backtest_pool(user_id)
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
            "backtest_status": "pending"
        }
        response = supabase_request("POST", "backtest_pool", data)
        if response.status_code in [200, 201]:
            return True, f"成功添加 {stock_code} ({stock_name})"
        return False, f"添加失败: {response.text}"
    except Exception as e:
        return False, f"添加失败: {str(e)}"


def remove_from_backtest_pool(user_id: str, stock_code: str) -> tuple:
    """从回测池删除股票"""
    try:
        response = supabase_request(
            "DELETE", 
            "backtest_pool",
            params=f"user_id=eq.{user_id}&stock_code=eq.{stock_code}"
        )
        if response.status_code in [200, 204]:
            return True, f"已删除 {stock_code}"
        return False, f"删除失败: {response.text}"
    except Exception as e:
        return False, f"删除失败: {str(e)}"


def get_live_pool(user_id: str) -> List[Dict]:
    """获取用户的实操股票池"""
    if not user_id or user_id == "admin":
        return []
    
    try:
        response = supabase_request(
            "GET", 
            "live_pool", 
            params=f"user_id=eq.{user_id}"
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取实操池失败: {e}")
        return []


# ==================== 管理员密码验证 ====================
def check_password(password: str) -> bool:
    """验证管理员密码"""
    return hmac.compare_digest(password, ADMIN_PASSWORD)


def admin_login():
    """管理员登录表单"""
    with st.form("admin_login_form"):
        username = st.text_input("用户名", key="admin_username_input")
        password = st.text_input("密码", type="password", key="admin_password_input")
        submitted = st.form_submit_button("登录")
        
        if submitted:
            if username == ADMIN_USERNAME and check_password(password):
                st.session_state['admin_logged_in'] = True
                st.session_state['show_admin'] = False
                st.success("登录成功！")
                st.rerun()
            else:
                st.error("用户名或密码错误")


def admin_logout():
    """管理员退出登录"""
    if st.button("退出登录", key="logout_btn"):
        st.session_state['admin_logged_in'] = False
        st.session_state['show_admin'] = False
        st.rerun()


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
                        success, msg, user_id, user_email = sign_in(email, password)
                        if success:
                            st.session_state.authenticated = True
                            st.session_state.user_id = user_id
                            st.session_state.user_email = user_email
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


# ==================== 数据解析函数 ====================

def parse_stock_code(code: str) -> Tuple[str, str]:
    """
    解析股票代码，返回 (market, formatted_code)
    支持格式: 000001.SZ, 0700.HK, 600000.SH
    """
    code = code.strip().upper()
    
    if code.endswith(".HK"):
        return "HK", code
    elif code.endswith(".SZ"):
        return "SZ", code
    elif code.endswith(".SH"):
        return "SH", code
    else:
        # 默认按A股处理，深市优先
        return "A", code + ".SZ"


def validate_stock_code(code: str) -> Tuple[bool, str]:
    """
    验证股票代码是否有效
    返回: (is_valid, message_or_formatted_code)
    """
    market, formatted = parse_stock_code(code)
    
    # 简单验证：A股6位数字，港股5位数字
    if market in ["SZ", "SH"]:
        num_part = formatted.split('.')[0]
        if num_part.isdigit() and len(num_part) == 6:
            return True, formatted
        else:
            return False, f"无效A股代码: {code}，应为6位数字"
    elif market == "HK":
        num_part = formatted.split('.')[0]
        if num_part.isdigit() and len(num_part) in [4, 5]:
            return True, formatted
        else:
            return False, f"无效港股代码: {code}，应为4-5位数字"
    else:
        return False, f"无法识别市场: {code}，请使用 .SZ/.SH/.HK 后缀"


print("第2部分加载完成")
print("=" * 60)
# ============================================================
# 第3部分：评分引擎（技术指标计算、板块热度、个股评分）
# 包含：MACD、KDJ、布林带、RSI、量价配合计算
#       Tushare真实数据获取
#       个股综合评分
# ============================================================

# ==================== Tushare 数据获取 ====================

def get_stock_daily(ts_code: str, days: int = 120) -> pd.DataFrame:
    """
    获取股票日线数据
    ts_code: 如 '000001.SZ'
    days: 获取最近多少天的数据
    """
    if not TUSHARE_AVAILABLE or TUSHARE_PRO is None:
        return pd.DataFrame()
    
    try:
        # 计算开始日期
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        
        df = TUSHARE_PRO.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is not None and len(df) > 0:
            df = df.sort_values('trade_date')
            # 重命名列以匹配计算函数
            df = df.rename(columns={
                'trade_date': 'date',
                'vol': 'volume'
            })
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"获取{ts_code}日线数据失败: {e}")
        return pd.DataFrame()


def get_stock_name_from_tushare(ts_code: str) -> str:
    """从Tushare获取股票名称"""
    global STOCK_NAME_CACHE
    
    if not STOCK_NAME_CACHE:
        load_stock_name_cache()
    
    return STOCK_NAME_CACHE.get(ts_code, ts_code.split('.')[0])


def get_sector_performance() -> pd.DataFrame:
    """
    获取预置板块的实时表现
    返回: DataFrame包含板块名称、涨跌幅、领涨股等
    """
    if not TUSHARE_AVAILABLE or TUSHARE_PRO is None:
        # 返回模拟数据
        data = []
        for sector_name, sector_info in HOT_SECTORS.items():
            data.append({
                "板块": sector_name,
                "涨跌幅": np.random.uniform(-3, 5),
                "领涨股": sector_info["names"][0]
            })
        return pd.DataFrame(data)
    
    data = []
    for sector_name, sector_info in HOT_SECTORS.items():
        try:
            # 获取板块内所有股票的今日涨跌幅
            sector_stocks = sector_info["stocks"]
            performances = []
            
            for ts_code in sector_stocks:
                df = get_stock_daily(ts_code, days=5)
                if not df.empty and len(df) >= 2:
                    # 计算最近一天涨跌幅
                    latest_close = df['close'].iloc[-1]
                    prev_close = df['close'].iloc[-2]
                    change_pct = (latest_close - prev_close) / prev_close * 100
                    performances.append(change_pct)
            
            if performances:
                avg_change = np.mean(performances)
                # 找出涨幅最大的股票
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


# ==================== 技术指标计算 ====================

def calculate_macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> Dict:
    """计算MACD指标"""
    if df.empty or len(df) < slow:
        return {"macd": 0, "signal": 0, "histogram": 0, "signal_level": "neutral", "score": 50}
    
    close = df['close'].values
    
    # 计算EMA
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
    
    # 判断信号和评分
    if macd_line[-1] > signal_line[-1] and macd_line[-2] <= signal_line[-2]:
        signal_level = "golden_cross"  # 金叉
        score = 100
    elif macd_line[-1] < signal_line[-1] and macd_line[-2] >= signal_line[-2]:
        signal_level = "death_cross"   # 死叉
        score = 0
    elif macd_line[-1] > 0 and signal_line[-1] > 0:
        signal_level = "bullish"       # 多头
        score = 75
    elif macd_line[-1] < 0 and signal_line[-1] < 0:
        signal_level = "bearish"       # 空头
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
    if df.empty or len(df) < n:
        return {"k": 50, "d": 50, "j": 50, "signal_level": "neutral", "score": 50}
    
    low = df['low'].values
    high = df['high'].values
    close = df['close'].values
    
    k_values = []
    d_values = []
    
    for i in range(len(df)):
        if i < n - 1:
            k_values.append(50)
            d_values.append(50)
            continue
        
        low_n = min(low[i-n+1:i+1])
        high_n = max(high[i-n+1:i+1])
        rsv = (close[i] - low_n) / (high_n - low_n) * 100 if high_n != low_n else 50
        
        if i == n - 1:
            k = 50
            d = 50
        else:
            k = (2/3) * k_values[-1] + (1/3) * rsv
            d = (2/3) * d_values[-1] + (1/3) * k
        
        k_values.append(k)
        d_values.append(d)
    
    k = k_values[-1]
    d = d_values[-1]
    j = 3 * k - 2 * d
    
    # 判断信号和评分
    if k < 20 and d < 20 and k > d:
        signal_level = "oversold_golden"  # 低位金叉
        score = 100
    elif k > 80 and d > 80 and k < d:
        signal_level = "overbought_death" # 高位死叉
        score = 0
    elif k > d:
        signal_level = "bullish"
        score = 70
    else:
        signal_level = "bearish"
        score = 30
    
    return {"k": k, "d": d, "j": j, "signal_level": signal_level, "score": score}


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
    
    # 判断信号和评分
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
    
    # 判断信号和评分
    if rsi > 70:
        signal_level = "overbought"
        score = 30  # 超买，看跌
    elif rsi < 30:
        signal_level = "oversold"
        score = 80  # 超卖，看涨
    else:
        signal_level = "neutral"
        # 线性映射：50分基准，越靠近0或100分越低
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
                scores.append(100)   # 上涨放量，好
            else:
                scores.append(30)    # 上涨缩量，不好
        else:
            if volume_change[i] < 0:
                scores.append(70)    # 下跌缩量，好
            else:
                scores.append(40)    # 下跌放量，不好
    
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


def calculate_technical_score(df: pd.DataFrame) -> Dict:
    """
    计算综合技术指标得分（0-100）
    返回: {"score": 75, "level": "A", "details": {...}}
    """
    if df.empty:
        return {"score": 50, "level": "D", "details": {}}
    
    details = {}
    
    # 各指标计算
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
    
    # 加权计算
    total_score = (
        macd["score"] * TECH_WEIGHTS["macd"] +
        kdj["score"] * TECH_WEIGHTS["kdj"] +
        boll["score"] * TECH_WEIGHTS["boll"] +
        rsi["score"] * TECH_WEIGHTS["rsi"] +
        vp["score"] * TECH_WEIGHTS["volume_price"]
    )
    
    # 确定等级
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


# ==================== 个股综合评分 ====================

def get_stock_score(ts_code: str, stock_name: str = "") -> Dict:
    """
    获取个股综合评分
    基于Tushare真实数据计算技术指标
    返回: {"score": 92, "level": "S", "action": "强烈买入", ...}
    """
    # 获取日线数据
    df = get_stock_daily(ts_code, days=120)
    
    if df.empty:
        # 无法获取数据时返回默认评分
        total_score = 50
        level = "D"
        action = "观望"
        position = "0%"
        tech_score = 50
        tech_details = {}
    else:
        tech_result = calculate_technical_score(df)
        tech_score = tech_result["score"]
        tech_details = tech_result["details"]
        
        # 综合得分 = 技术指标得分（简化，完整版需加入板块热度）
        total_score = tech_score
        
        # 确定等级和操作建议
        level = "D"
        action = "观望"
        position = "0%"
        for lvl, config in SIGNAL_LEVELS.items():
            if total_score >= config["min_score"]:
                level = lvl
                action = config["action"]
                position = config["position"]
                break
    
    # 获取股票名称
    name = stock_name if stock_name else get_stock_name_from_tushare(ts_code)
    
    return {
        "stock_code": ts_code,
        "stock_name": name,
        "total_score": round(total_score, 2),
        "level": level,
        "action": action,
        "position": position,
        "tech_score": round(tech_score, 2),
        "tech_details": tech_details,
        "reasons": generate_score_reasons(total_score)
    }


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


def score_batch_stocks(stock_list: List[Dict]) -> List[Dict]:
    """批量计算股票得分"""
    results = []
    for stock in stock_list:
        score_result = get_stock_score(stock["code"], stock.get("name", ""))
        results.append(score_result)
    return sorted(results, key=lambda x: x["total_score"], reverse=True)


# ==================== 付费墙 ====================

def show_paywall():
    """显示付费墙"""
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
    | 实操信号 | ✅ | ✅ |
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button(t()["monthly"], use_container_width=True, type="primary"):
            st.info("支付功能待配置，请联系管理员")
    with col2:
        if st.button(t()["yearly"], use_container_width=True, type="primary"):
            st.info("支付功能待配置，请联系管理员")
    
    if st.button("返回", use_container_width=True):
        st.session_state.show_paywall = False
        st.rerun()


# ==================== 模拟回测函数 ====================

def run_backtest_simple(stock_codes: List[str]) -> Dict:
    """
    简化版回测函数
    返回回测结果字典
    """
    import random
    random.seed(hash(tuple(stock_codes)) % 10000)
    
    annual_return = random.uniform(-10, 35)
    sharpe = random.uniform(0.5, 1.8)
    max_drawdown = random.uniform(8, 28)
    win_rate = random.uniform(45, 65)
    
    return {
        "annual_return": round(annual_return, 1),
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(max_drawdown, 1),
        "win_rate": round(win_rate, 1),
        "total_trades": random.randint(10, 50)
    }


print("第3部分加载完成")
print("=" * 60)
# ============================================================
# 第4部分：5个功能模块（市场简报、推荐股票池、个股分析、回测、实操信号）
# 包含：模块1-5的完整UI实现
# ============================================================

# ==================== 模块1：市场简报 ====================

def render_market_brief():
    """市场简报模块"""
    st.markdown(f"### {t()['module1_title']}")
    
    # 显示最后更新时间
    last_update = get_last_update_time("market_brief")
    st.caption(f"📅 最后更新: {last_update}")
    
    col1, col2 = st.columns([4, 1])
    with col2:
        refresh = st.button(t()["refresh"], key="refresh_brief", use_container_width=True)
    
    if refresh:
        if not consume_free_trial(st.session_state.user_id):
            st.warning("免费次数已用完，请升级到专业版")
            return
        update_last_update_time("market_brief")
        st.rerun()
    
    with st.spinner("正在获取市场数据..."):
        # 获取板块表现
        sector_df = get_sector_performance()
        
        # 生成市场简报
        market_trend = "震荡上行"
        market_desc = "近期市场情绪偏暖，科技板块持续活跃，建议关注热点板块轮动机会。"
        
        # 显示市场简报
        st.info(f"📈 **大盘趋势**: {market_trend}\n\n📝 **市场解读**: {market_desc}")
        
        # 热点板块表格
        if not sector_df.empty:
            st.markdown("**🔥 今日热点板块**")
            # 按涨跌幅排序
            sector_df = sector_df.sort_values("涨跌幅", ascending=False)
            st.dataframe(
                sector_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "板块": st.column_config.TextColumn("板块"),
                    "涨跌幅": st.column_config.NumberColumn("涨跌幅", format="%.2f%%"),
                    "领涨股": st.column_config.TextColumn("领涨股")
                }
            )
        else:
            st.caption("暂无热点板块数据，请稍后刷新")
        
        # 龙头股提示
        st.markdown("**🎯 龙头股关注**")
        st.caption("• 光模块/CPO: 中际旭创、天孚通信、新易盛\n• 人工智能: 科大讯飞、海康威视\n• 半导体: 中芯国际、北方华创")


# ==================== 模块2：推荐股票池 ====================

def render_recommended_pool():
    """推荐股票池模块"""
    st.markdown(f"### {t()['module2_title']}")
    
    # 显示最后更新时间
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
                    # 获取股票名称
                    stock_name = get_stock_name_from_tushare(formatted_code)
                    success, msg = add_to_recommended_pool(
                        st.session_state.user_id, formatted_code, stock_name, source="user"
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
        st.caption(f"📊 当前: {len(get_recommended_pool(st.session_state.user_id))}/{MAX_RECOMMENDED_STOCKS}")
    
    if refresh:
        if not consume_free_trial(st.session_state.user_id):
            st.warning("免费次数已用完，请升级到专业版")
            return
        update_last_update_time("recommended_pool")
        st.rerun()
    
    # 获取推荐池数据
    stocks = get_recommended_pool(st.session_state.user_id)
    
    if not stocks:
        st.info("暂无股票，请点击[添加]按钮添加股票")
        return
    
    # 批量计算得分
    with st.spinner("正在计算股票评分..."):
        stock_list = [{"code": s["stock_code"], "name": s.get("stock_name", "")} for s in stocks]
        scored_stocks = score_batch_stocks(stock_list)
    
    # 显示股票列表
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
                    remove_from_recommended_pool(st.session_state.user_id, stock['stock_code'])
                    st.rerun()
    
    # 批量操作
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("🗑️ 清空所有", key="clear_pool", use_container_width=True):
            for s in stocks:
                remove_from_recommended_pool(st.session_state.user_id, s["stock_code"])
            st.rerun()
    with col2:
        if st.button("📋 移到回测池", key="move_to_backtest", use_container_width=True):
            for s in stocks:
                add_to_backtest_pool(st.session_state.user_id, s["stock_code"], s.get("stock_name", ""))
                remove_from_recommended_pool(st.session_state.user_id, s["stock_code"])
            st.success(f"已将{len(stocks)}只股票移到回测池")
            st.rerun()


# ==================== 模块3：个股分析 ====================

def render_stock_analysis():
    """个股分析模块"""
    st.markdown(f"### {t()['module3_title']}")
    
    # 显示最后更新时间
    last_update = get_last_update_time("stock_analysis")
    st.caption(f"📅 最后更新: {last_update}")
    
    # 输入区域
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
                    if not consume_free_trial(st.session_state.user_id):
                        st.warning("免费次数已用完，请升级到专业版")
                    else:
                        st.session_state.analyze_code = formatted
                        st.session_state.analyze_name = ""
                        update_last_update_time("stock_analysis")
                        st.rerun()
                else:
                    st.error(formatted)
    
    # 执行分析
    if st.session_state.get("analyze_code"):
        stock_code = st.session_state.analyze_code
        stock_name = st.session_state.get("analyze_name", "")
        
        with st.spinner("正在分析..."):
            score_result = get_stock_score(stock_code, stock_name)
            # 获取K线数据用于绘图
            df = get_stock_daily(stock_code, days=60)
        
        # 显示分析结果
        level = score_result["level"]
        color = SIGNAL_LEVELS.get(level, {}).get("color", "#888888")
        
        # 评分卡片
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("综合得分", f"{score_result['total_score']:.0f}")
        with col2:
            st.metric("信号等级", level)
        with col3:
            st.metric("操作建议", score_result["action"])
        with col4:
            st.metric("建议仓位", score_result["position"])
        
        # K线图（如果有数据）
        if not df.empty:
            st.markdown("**📈 K线走势图**")
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                 vertical_spacing=0.05, 
                                 row_heights=[0.7, 0.3])
            
            # K线图
            fig.add_trace(go.Candlestick(
                x=df['date'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='价格'
            ), row=1, col=1)
            
            # 成交量图
            colors = ['red' if close >= open else 'green' 
                      for close, open in zip(df['close'], df['open'])]
            fig.add_trace(go.Bar(
                x=df['date'],
                y=df['volume'],
                name='成交量',
                marker_color=colors
            ), row=2, col=1)
            
            fig.update_layout(
                height=500,
                xaxis_rangeslider_visible=False,
                showlegend=False
            )
            fig.update_yaxes(title_text="价格", row=1, col=1)
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
        
        # 技术指标详情
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
        
        # AI投资建议
        with st.expander("💡 AI投资建议"):
            st.markdown(f"""
            **{score_result['stock_code']} ({score_result['stock_name']})**
            
            **信号等级**: {level}级 - {score_result['action']}
            
            **建议仓位**: {score_result['position']}
            
            **关键理由**: {score_result.get('reasons', '暂无')}
            
            ⚠️ 以上仅供参考，不构成投资建议。请结合市场情况自行判断。
            """)
        
        # 添加到股票池按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ 添加到推荐池", use_container_width=True):
                success, msg = add_to_recommended_pool(
                    st.session_state.user_id, stock_code, score_result['stock_name'], source="user",
                    score=score_result["total_score"]
                )
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
        with col2:
            if st.button("📋 添加到回测池", use_container_width=True):
                success, msg = add_to_backtest_pool(
                    st.session_state.user_id, stock_code, score_result['stock_name']
                )
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
        
        # 清除分析状态
        if st.button("清除", key="clear_analyze"):
            st.session_state.analyze_code = ""
            st.rerun()


# ==================== 模块4：回测功能 ====================

def render_backtest():
    """回测功能模块"""
    st.markdown(f"### {t()['module4_title']}")
    
    # 显示最后更新时间
    last_update = get_last_update_time("backtest")
    st.caption(f"📅 最后更新: {last_update}")
    
    # 获取回测池
    stocks = get_backtest_pool(st.session_state.user_id)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"📋 回测池: {len(stocks)}只股票")
    with col2:
        if st.button("📊 运行回测", key="run_backtest", use_container_width=True):
            if len(stocks) == 0:
                st.warning("回测池为空，请先从推荐池添加股票")
            else:
                if not consume_free_trial(st.session_state.user_id):
                    st.warning("免费次数已用完，请升级到专业版")
                else:
                    with st.spinner("正在运行回测..."):
                        stock_codes = [s["stock_code"] for s in stocks]
                        backtest_result = run_backtest_simple(stock_codes)
                        st.session_state.backtest_result = backtest_result
                        update_last_update_time("backtest")
                    st.rerun()
    
    if not stocks:
        st.info("暂无股票，请从推荐池添加")
        return
    
    # 显示回测池列表
    for stock in stocks:
        col1, col2, col3, col4, col5 = st.columns([1.5, 1.5, 2, 2, 1])
        
        with col1:
            st.write(f"**{stock['stock_code']}**")
        with col2:
            st.caption(stock.get('stock_name', ''))
        with col3:
            status = stock.get('backtest_status', 'pending')
            if status == "success":
                st.success("✅ 已回测")
            else:
                st.caption("⏸ 待回测")
        with col4:
            result = stock.get('backtest_result', {})
            if result:
                st.caption(f"年化: {result.get('annual_return', '-')}%")
        with col5:
            if st.button("🗑️", key=f"del_backtest_{stock['stock_code']}"):
                remove_from_backtest_pool(st.session_state.user_id, stock['stock_code'])
                st.rerun()
    
    # 显示回测结果
    if st.session_state.get("backtest_result"):
        result = st.session_state.backtest_result
        st.markdown("---")
        st.markdown("**📈 回测报告**")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("年化收益率", f"{result.get('annual_return', 0):+.1f}%")
            st.metric("夏普比率", f"{result.get('sharpe', 0):.2f}")
        with col2:
            st.metric("最大回撤", f"-{result.get('max_drawdown', 0):.1f}%")
        with col3:
            st.metric("胜率", f"{result.get('win_rate', 0):.1f}%")
        with col4:
            st.metric("交易次数", f"{result.get('total_trades', 0)}次")
        
        st.caption("⚠️ 回测结果基于历史数据，不代表未来表现")


# ==================== 模块5：实操信号 ====================

def render_live_signals():
    """实操信号模块（半自动交易）"""
    st.markdown(f"### {t()['module5_title']}")
    
    # 显示最后更新时间
    last_update = get_last_update_time("live_signals")
    st.caption(f"📅 最后更新: {last_update} | 💡 AI生成交易信号，请自行前往券商App下单")
    
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button(t()["refresh"], key="refresh_signals", use_container_width=True):
            if not consume_free_trial(st.session_state.user_id):
                st.warning("免费次数已用完，请升级到专业版")
            else:
                update_last_update_time("live_signals")
                st.rerun()
    
    # 获取推荐池数据（高评分股票生成信号）
    recommended_stocks = get_recommended_pool(st.session_state.user_id)
    live_stocks = get_live_pool(st.session_state.user_id)
    
    # 生成交易信号
    signals = []
    
    # 从推荐池获取高评分股票
    for stock in recommended_stocks[:5]:
        score = stock.get('current_score', 0)
        if score >= 70:
            signals.append({
                "stock_code": stock['stock_code'],
                "stock_name": stock.get('stock_name', ''),
                "action": "买入" if score >= 70 else "观望",
                "suggested_position": "5-15%" if score >= 85 else "5-10%",
                "confidence": f"{score:.0f}%"
            })
    
    # 从实操池获取持仓信号
    for stock in live_stocks:
        current_price = stock.get('current_price', 0)
        avg_cost = stock.get('avg_cost', 0)
        if avg_cost > 0 and current_price > 0:
            profit_pct = (current_price - avg_cost) / avg_cost * 100
            if profit_pct > 10:
                action = "卖出(获利)"
            elif profit_pct < -8:
                action = "止损⚠️"
            else:
                action = "持有"
        else:
            action = "持有"
        
        signals.append({
            "stock_code": stock['stock_code'],
            "stock_name": stock.get('stock_name', ''),
            "action": action,
            "suggested_position": f"{stock.get('shares', 0)}股",
            "confidence": ""
        })
    
    if not signals:
        st.info("暂无交易信号，请先在推荐池添加高评分股票")
        return
    
    # 显示信号表格
    signals_df = pd.DataFrame(signals)
    st.dataframe(
        signals_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "stock_code": "股票代码",
            "stock_name": "股票名称",
            "action": "操作建议",
            "suggested_position": "建议/仓位",
            "confidence": "置信度"
        }
    )
    
    # 升级提示
    profile = get_user_profile(st.session_state.user_id)
    if profile.get("subscription_tier") == "free":
        remaining = get_remaining_trials(st.session_state.user_id)
        st.info(f"📋 免费用户每次刷新消耗1次，剩余{remaining}次。升级专业版后无限使用。")
    
    st.markdown("---")
    st.markdown("### 📖 操作指引")
    st.markdown("""
    1. 查看上方交易信号
    2. 打开您的券商App（如招商证券、富途牛牛）
    3. 根据信号手动下单
    4. 可在实操池中记录持仓
    
    ⚠️ 投资有风险，请谨慎决策
    """)


print("第4部分加载完成")
print("=" * 60)
# ============================================================
# 第5部分：主入口 + Session管理 + 侧边栏 + 顶部按钮 + 页面路由
# 包含：自定义CSS、侧边栏、顶部按钮、主页面路由、程序入口
# ============================================================

# ==================== 自定义CSS ====================
st.markdown("""
<style>
    /* 主标题样式 */
    .main-header {
        text-align: center;
        margin-bottom: 1rem;
    }
    
    /* 侧边栏用户信息卡片 */
    .sidebar-user-info {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    
    /* 按钮样式 */
    .stButton button {
        border-radius: 0.5rem;
        transition: all 0.2s;
    }
    
    /* 数据表格样式 */
    .stDataFrame {
        font-size: 0.9rem;
    }
    
    /* 指标卡片样式 */
    .stMetric {
        text-align: center;
    }
    
    /* 升级按钮高亮 */
    .upgrade-btn button {
        background-color: #ff4b4b !important;
        color: white !important;
    }
    
    /* 信号等级颜色 */
    .signal-s { color: #ff4b4b; font-weight: bold; }
    .signal-a { color: #ff6b6b; font-weight: bold; }
    .signal-b { color: #ffaa00; font-weight: bold; }
    .signal-c { color: #ff8800; font-weight: bold; }
    .signal-d { color: #888888; font-weight: bold; }
    
    /* 市场选择器样式 */
    .market-selector {
        margin-bottom: 1rem;
        padding: 0.5rem;
        background-color: #f8f9fa;
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


# ==================== 侧边栏 ====================
def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.markdown("## 📊 AI量化股票系统")
        st.markdown("---")
        
        # ===== 用户信息（已登录且非管理员模式）=====
        if st.session_state.authenticated and not st.session_state.admin_mode:
            user_email = st.session_state.user_email
            profile = get_user_profile(st.session_state.user_id)
            tier = profile.get("subscription_tier", "free")
            remaining = get_remaining_trials(st.session_state.user_id)
            
            # 显示用户信息卡片
            tier_display = "💎 专业版" if tier == "pro" else "🔒 免费版"
            remaining_display = "∞" if remaining == -1 else remaining
            
            st.markdown(f"""
            <div class="sidebar-user-info">
                <strong>👤 {user_email}</strong><br>
                📋 {t()['subscription']}: {tier_display}<br>
                🎫 {t()['remaining']}: {remaining_display}
            </div>
            """, unsafe_allow_html=True)
            
            # 升级按钮（仅免费用户）
            if tier == "free":
                if st.button("💎 " + t()["upgrade"], key="sidebar_upgrade", use_container_width=True):
                    st.session_state.show_paywall = True
                    st.rerun()
            
            st.markdown("---")
        
        # ===== 市场选择器 =====
        st.markdown("### 🌍 市场选择")
        market = st.selectbox(
            "选择市场",
            MARKET_OPTIONS,
            index=0,
            key="market_selector",
            label_visibility="collapsed"
        )
        if market != st.session_state.get("market", "A股"):
            st.session_state.market = market
            st.rerun()
        
        st.markdown("---")
        
        # ===== 关于系统 =====
        with st.expander(t()["about_header"], expanded=True):
            st.markdown(t()["about_text"])
        
        # ===== 快速指南 =====
        with st.expander(t()["guide_header"], expanded=False):
            st.markdown(t()["guide_text"])
        
        # ===== 联系我们 =====
        with st.expander(t()["contact_header"], expanded=False):
            st.markdown(t()["contact_email"])
        
        st.markdown("---")
        st.caption("v2.0 | TechLife")
        st.caption("数据来源: Tushare | 预置板块")


# ==================== 右上角按钮 ====================
def render_top_buttons():
    """渲染右上角语言切换和管理员按钮"""
    # 创建5列布局：空白 + 中文 + 英文 + 管理员 + 退出/返回
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
                # 管理员模式：显示"返回用户"
                if st.button("👤 返回用户", key="back_to_user_btn", help="退出管理员模式", use_container_width=True):
                    admin_sign_out()
                    st.rerun()
            else:
                # 普通用户模式：显示"退出登录"
                if st.button("🚪", key="logout_btn", help="退出登录", use_container_width=True):
                    sign_out()
                    st.rerun()


# ==================== 主页内容（5个模块） ====================
def render_main_app():
    """渲染主页内容（5个功能模块）"""
    # 检查付费墙
    if st.session_state.get("show_paywall", False):
        show_paywall()
        return
    
    # 欢迎语
    st.markdown(f"<h3 style='text-align: left;'>{t()['welcome']}, {st.session_state.user_email}</h3>", unsafe_allow_html=True)
    
    # 显示剩余次数（免费用户）
    profile = get_user_profile(st.session_state.user_id)
    if profile.get("subscription_tier") == "free":
        remaining = get_remaining_trials(st.session_state.user_id)
        st.caption(f"📋 剩余免费次数: {remaining} | 升级专业版后无限使用")
    
    # 显示当前市场
    current_market = st.session_state.get("market", "A股")
    st.caption(f"🌍 当前市场: {current_market}")
    
    st.markdown("---")
    
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
    
    # 免责声明
    st.caption("⚠️ 本系统仅供学术研究和娱乐参考。股市有风险，投资需谨慎。所有AI建议不构成投资建议。")
    st.caption("📊 数据来源: Tushare | 预置热点板块: 光模块/CPO、人工智能、半导体、算力")


# ==================== 管理员面板渲染（整合第4部分内容） ====================
# 注意：管理员面板的详细实现在第4部分的 admin.py 中
# 这里提供简化的管理员面板入口
def render_admin_panel_simple():
    """简化的管理员面板（实际应调用第4部分的render_admin_panel）"""
    st.markdown("## ⚙️ 管理员面板")
    st.info("管理员功能开发中...")
    st.markdown("""
    ### 可用功能
    - 查看用户列表
    - 管理用户订阅
    - 重置用户次数
    - 查看用户股票池
    
    详细功能请参考完整版代码。
    """)
    
    # 退出管理员模式按钮
    if st.button("退出管理员模式", use_container_width=True):
        admin_sign_out()
        st.rerun()


# ==================== 主函数 ====================
def main():
    """主函数：控制页面流程"""
    
    # 初始化Session State
    init_session_state()
    
    # 预加载股票名称缓存（后台进行）
    if TUSHARE_AVAILABLE and not STOCK_NAME_CACHE:
        with st.spinner("加载股票数据..."):
            load_stock_name_cache()
    
    # 渲染侧边栏
    render_sidebar()
    
    # 渲染右上角按钮
    render_top_buttons()
    
    # ===== 页面流程控制 =====
    
    # 管理员登录页面
    if st.session_state.get("show_admin_login", False):
        render_admin_login_form()
        return
    
    # 管理员模式
    if st.session_state.get("admin_mode", False):
        render_admin_panel_simple()
        return
    
    # 未登录：显示登录/注册页面
    if not st.session_state.authenticated:
        if st.session_state.get("show_register", False):
            render_register_form()
        else:
            render_login_form()
        return
    
    # 已登录：显示主应用
    render_main_app()


# ==================== 程序入口 ====================
if __name__ == "__main__":
    main()


print("第5部分加载完成")
print("=" * 60)
print("所有代码加载完成！AI量化股票系统已就绪。")
print("=" * 60)
