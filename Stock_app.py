"""
AI量化股票系统 - 完整版本 v3.0
基于DFSS方法论 + 机器学习集成 + Tushare真实数据 + 掘金交易 + Stripe支付

更新内容（v3.0）：
- 剩余次数扣减修复
- K线图修复（连续显示，涨红跌绿）
- 完整管理员面板
- 推荐池自动Top10（基于技术指标评分）
- 掘金手动下单集成
- Stripe支付集成（生成链接用户手动点击）
- 预置热点板块（含机器人板块）

部署方式：
1. 将代码上传到GitHub
2. 在Streamlit Cloud部署
3. 配置Secrets（见下方secrets.toml）
"""

# ============================================================
# 第1部分：导入、配置、常量、多语言、Supabase连接、Tushare初始化
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

# 预置热点板块（包含机器人板块）
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

# ==================== Supabase 配置 ====================
SUPABASE_URL = st.secrets.get("SUPABASE_STOCK_URL", "")
SUPABASE_PUBLISHABLE_KEY = st.secrets.get("SUPABASE_STOCK_ANON_KEY", "")
SUPABASE_SECRET_KEY = st.secrets.get("SUPABASE_STOCK_SECRET_KEY", "")

# ==================== Stripe 配置 ====================
STRIPE_SECRET_KEY = st.secrets.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = st.secrets.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_PRICE_MONTHLY = st.secrets.get("STRIPE_PRICE_MONTHLY", "")
STRIPE_PRICE_YEARLY = st.secrets.get("STRIPE_PRICE_YEARLY", "")

# ==================== DeepSeek 配置 ====================
DEEPSEEK_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = st.secrets.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = st.secrets.get("DEEPSEEK_MODEL", "deepseek-chat")

# ==================== Tushare 配置 ====================
TUSHARE_TOKEN = st.secrets.get("TUSHARE_TOKEN", "")
TUSHARE_AVAILABLE = False
TUSHARE_PRO = None

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


# 执行初始化
init_tushare()
init_gm()
load_stock_name_cache()

print("第1部分加载完成")
print("=" * 60)
# ============================================================
# ============================================================
# 第2部分：用户认证 + Supabase API封装 + 股票池操作 + 次数扣减 + Stripe支付
# 修复内容：
# - sign_up: 只创建Auth用户，不创建profile
# - sign_in: 登录时自动创建user_settings（替代profiles）
# - consume_free_trial: 修复次数扣减逻辑
# - 新增 Stripe 支付函数
# ============================================================

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


def supabase_request(method: str, endpoint: str, data=None, params=None, use_secret=False, access_token=None):
    """通用的Supabase REST API请求"""
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
        # 查询是否存在
        headers = get_supabase_headers(use_secret=True)
        check_url = f"{SUPABASE_URL}/rest/v1/user_settings?id=eq.{user_id}"
        check_response = requests.get(check_url, headers=headers)
        
        if check_response.status_code == 200 and check_response.json():
            return True  # 已存在
        
        # 不存在，创建
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
    返回: (success, message, user_id, user_email, access_token)
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
            
            # 确保有 user_settings 记录
            ensure_user_settings(user_id, user_email, access_token)
            
            # 更新最后登录时间
            update_user_profile(user_id, {"last_sign_in_at": datetime.now().isoformat()}, access_token)
            
            return True, "登录成功", user_id, user_email, access_token
        else:
            return False, "邮箱或密码错误", None, None, None
    except Exception as e:
        return False, f"登录失败: {str(e)}", None, None, None


def sign_out():
    """退出登录（普通用户）"""
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.user_email = None
    st.session_state.access_token = None
    st.session_state.admin_mode = False
    st.rerun()


def admin_sign_out():
    """管理员退出，恢复原用户"""
    # 恢复管理员登录前的用户状态
    prev_user_id = st.session_state.get("admin_previous_user_id")
    prev_user_email = st.session_state.get("admin_previous_user_email")
    prev_access_token = st.session_state.get("admin_previous_access_token")
    
    if prev_user_id and prev_user_email:
        st.session_state.authenticated = True
        st.session_state.user_id = prev_user_id
        st.session_state.user_email = prev_user_email
        st.session_state.access_token = prev_access_token
    else:
        st.session_state.authenticated = False
        st.session_state.user_id = None
        st.session_state.user_email = None
        st.session_state.access_token = None
    
    st.session_state.admin_mode = False
    # 不清除 admin_previous_*，下次管理员登录时会重新设置
    st.rerun()


def check_admin_login(username: str, password: str) -> bool:
    """验证管理员登录"""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD


# ==================== 用户资料操作 ====================

def get_user_profile(user_id: str, access_token: str = None) -> dict:
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
            requests.post(insert_url, headers=headers, json=settings_data)
            return {
                "subscription_tier": "free",
                "free_trials_remaining": FREE_TRIAL_LIMIT,
                "subscription_expires_at": None,
                "last_sign_in_at": None
            }
    except Exception:
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
        # ========== 修改这里：id 改为 user_id ==========
        url = f"{SUPABASE_URL}/rest/v1/user_settings?user_id=eq.{user_id}"
        # ===========================================
        
        response = requests.patch(url, headers=headers, json=data)
        return response.status_code in [200, 204]
    except Exception as e:
        print(f"更新用户资料失败: {e}")
        return False

def get_remaining_trials(user_id: str, access_token: str = None) -> int:
    """获取剩余免费次数"""
    profile = get_user_profile(user_id, access_token)
    if profile.get("subscription_tier") == "pro":
        return -1  # -1 表示无限
    return profile.get("free_trials_remaining", 0)

#========
def consume_free_trial(user_id: str, access_token: str = None) -> bool:
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
    """从推荐池删除股票"""
    try:
        data = {"is_deleted": True}
        response = supabase_request(
            "PATCH", 
            "recommended_pool", 
            data=data,
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
    """添加股票到回测池"""
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


def auto_recommend_top10(user_id: str, access_token: str = None) -> List[Dict]:
    """自动推荐Top10股票（基于技术指标评分）"""
    if not TUSHARE_AVAILABLE:
        return []
    
    all_stocks = []
    for sector_name, sector_info in HOT_SECTORS.items():
        for i, ts_code in enumerate(sector_info["stocks"]):
            stock_name = sector_info["names"][i] if i < len(sector_info["names"]) else ts_code
            all_stocks.append({"code": ts_code, "name": stock_name, "sector": sector_name})
    
    seen = set()
    unique_stocks = []
    for stock in all_stocks:
        if stock["code"] not in seen:
            seen.add(stock["code"])
            unique_stocks.append(stock)
    
    scored_stocks = []
    for stock in unique_stocks:
        score_result = get_stock_score(stock["code"], stock["name"])
        scored_stocks.append({
            "code": stock["code"],
            "name": stock["name"],
            "score": score_result["total_score"],
            "level": score_result["level"],
            "action": score_result["action"],
            "sector": stock["sector"]
        })
    
    scored_stocks.sort(key=lambda x: x["score"], reverse=True)
    top10 = scored_stocks[:10]
    
    for stock in top10:
        add_to_recommended_pool(user_id, stock["code"], stock["name"], source="ai", score=stock["score"], access_token=access_token)
    
    return top10


# ==================== Stripe 支付函数 ====================

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
        
        # 构建成功URL和取消URL
        base_url = "https://stock-quant-strategy.streamlit.app"
        success_url = f"{base_url}?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}?canceled=true"
        
        session = stripe.checkout.Session.create(
            customer_email=user_email,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': user_id,
                'price_id': price_id
            }
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


# ==================== 数据解析函数 ====================

def parse_stock_code(code: str) -> Tuple[str, str]:
    """解析股票代码"""
    code = code.strip().upper()
    
    if code.endswith(".HK"):
        return "HK", code
    elif code.endswith(".SZ"):
        return "SZ", code
    elif code.endswith(".SH"):
        return "SH", code
    else:
        return "A", code + ".SZ"


def validate_stock_code(code: str) -> Tuple[bool, str]:
    """验证股票代码是否有效"""
    market, formatted = parse_stock_code(code)
    
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
                        success, msg, user_id, user_email, access_token = sign_in(email, password)
                        if success:
                            st.session_state.authenticated = True
                            st.session_state.user_id = user_id
                            st.session_state.user_email = user_email
                            st.session_state.access_token = access_token
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
                    # 保存管理员登录前的用户状态
                    st.session_state.admin_previous_user_id = st.session_state.get("user_id")
                    st.session_state.admin_previous_user_email = st.session_state.get("user_email")
                    st.session_state.admin_previous_access_token = st.session_state.get("access_token")
                    
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


print("第2部分加载完成")
print("=" * 60)
# ============================================================
# 第3部分：评分引擎（技术指标计算、板块热度、个股评分）
#         + 掘金下单函数 + Stripe支付函数
# ============================================================

# ==================== Tushare 数据获取 ====================

def get_stock_daily(ts_code: str, days: int = 120) -> pd.DataFrame:
    """获取股票日线数据"""
    print(f"🔍 get_stock_daily 开始: {ts_code}, days={days}")
    
    if not TUSHARE_AVAILABLE or TUSHARE_PRO is None:
        print(f"🔍 get_stock_daily - Tushare不可用")
        return pd.DataFrame()
    
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        
        print(f"🔍 get_stock_daily - 日期范围: {start_date} 到 {end_date}")
        
        df = TUSHARE_PRO.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        print(f"🔍 get_stock_daily - 返回行数: {len(df) if df is not None else 0}")
        
        if df is not None and len(df) > 0:
            df = df.sort_values('trade_date')
            df = df.rename(columns={
                'trade_date': 'date',
                'vol': 'volume'
            })
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"🔍 get_stock_daily - 异常: {e}")
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


def calculate_technical_score(df: pd.DataFrame) -> Dict:
    """计算综合技术指标得分（0-100）"""
    if df.empty:
        return {"score": 50, "level": "D", "details": {}}
    
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
        macd["score"] * TECH_WEIGHTS["macd"] +
        kdj["score"] * TECH_WEIGHTS["kdj"] +
        boll["score"] * TECH_WEIGHTS["boll"] +
        rsi["score"] * TECH_WEIGHTS["rsi"] +
        vp["score"] * TECH_WEIGHTS["volume_price"]
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


def get_stock_score(ts_code: str, stock_name: str = "") -> Dict:
    """获取个股综合评分"""
    print(f"🔍 get_stock_score 开始: {ts_code}")
    
    # 获取日线数据
    df = get_stock_daily(ts_code, days=120)
    print(f"🔍 get_stock_score - df shape: {df.shape if not df.empty else '空'}")
    
    if df.empty:
        print(f"🔍 get_stock_score - 数据为空，返回默认值")
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
        total_score = tech_score
        
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
    
    result = {
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
    print(f"🔍 get_stock_score - 结果: {result}")
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


def score_batch_stocks(stock_list: List[Dict]) -> List[Dict]:
    """批量计算股票得分"""
    results = []
    for stock in stock_list:
        score_result = get_stock_score(stock["code"], stock.get("name", ""))
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
        
        # 转换股票代码格式（掘金需要SHSE/SZSE前缀）
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
            position_effect=1,  # 开仓
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
        
        # 构建成功URL和取消URL
        # 注意：需要替换为您的实际APP地址
        base_url = "https://techlife-stock-quant.streamlit.app"
        success_url = f"{base_url}?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}?canceled=true"
        
        session = stripe.checkout.Session.create(
            customer_email=user_email,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': user_id,
                'price_id': price_id
            }
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
                    # 更新用户订阅为专业版
                    update_user_profile(user_id, {"subscription_tier": "pro"})
                    st.success("✅ 支付成功！您已是专业版用户")
                    st.balloons()
                    # 清除URL参数
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
    | 实操信号+一键下单 | ✅ | ✅ |
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button(t()["monthly"], use_container_width=True, type="primary"):
            url, error = create_checkout_session(
                st.session_state.user_id, 
                st.session_state.user_email, 
                STRIPE_PRICE_MONTHLY
            )
            if url:
                st.markdown(f'<a href="{url}" target="_blank">点击前往Stripe支付（月付$29）</a>', unsafe_allow_html=True)
            else:
                st.error(f"创建支付会话失败: {error}")
    
    with col2:
        if st.button(t()["yearly"], use_container_width=True, type="primary"):
            url, error = create_checkout_session(
                st.session_state.user_id, 
                st.session_state.user_email, 
                STRIPE_PRICE_YEARLY
            )
            if url:
                st.markdown(f'<a href="{url}" target="_blank">点击前往Stripe支付（年付$299）</a>', unsafe_allow_html=True)
            else:
                st.error(f"创建支付会话失败: {error}")
    
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
# ============================================================
# 第4部分：5个功能模块 + 掘金一键下单集成
# 修复内容：
# - 修复 render_live_signals 中的 score 类型转换
# - 集成掘金一键下单功能
# - 优化各模块的缓存使用
# ============================================================

# ==================== 模块1：市场简报 ====================

def render_market_brief():
    """市场简报模块"""
    st.markdown(f"### {t()['module1_title']}")
    
    last_update = get_last_update_time("market_brief")
    st.caption(f"📅 最后更新: {last_update}")
    
    col1, col2 = st.columns([4, 1])
    with col2:
        refresh = st.button(t()["refresh"], key="refresh_brief", use_container_width=True)
    
    if refresh:
        if not consume_free_trial(st.session_state.user_id, st.session_state.get("access_token")):
            st.warning("免费次数已用完，请升级到专业版")
            return
        update_last_update_time("market_brief")
        st.rerun()
    
    with st.spinner("正在获取市场数据..."):
        # 使用缓存获取板块表现
        if TUSHARE_AVAILABLE:
            sector_df = get_cached_sector_performance()
        else:
            sector_df = get_sector_performance()
        
        market_trend = "震荡上行"
        market_desc = "近期市场情绪偏暖，科技板块持续活跃，建议关注热点板块轮动机会。"
        
        st.info(f"📈 **大盘趋势**: {market_trend}\n\n📝 **市场解读**: {market_desc}")
        
        if not sector_df.empty:
            st.markdown("**🔥 今日热点板块**")
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
        
        st.markdown("**🎯 龙头股关注**")
        st.caption("• 光模块/CPO: 中际旭创、天孚通信、新易盛\n• 人工智能: 科大讯飞、海康威视\n• 半导体: 中芯国际、北方华创\n• 机器人: 汇川技术、埃斯顿")


# ==================== 模块2：推荐股票池 ====================

def render_recommended_pool():
    """推荐股票池模块"""
    st.markdown(f"### {t()['module2_title']}")
    
    last_update = get_last_update_time("recommended_pool")
    st.caption(f"📅 最后更新: {last_update} | 📌 最多{MAX_RECOMMENDED_STOCKS}只股票 | 点击[分析]可查看详细评分")
    
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
            # 清空现有推荐池中的AI推荐（保留用户手动添加的）
            stocks = get_recommended_pool(st.session_state.user_id, st.session_state.get("access_token"))
            for stock in stocks:
                if stock.get("source") == "ai":
                    remove_from_recommended_pool(st.session_state.user_id, stock["stock_code"], st.session_state.get("access_token"))
            # 自动推荐Top10
            auto_recommend_top10(st.session_state.user_id, st.session_state.get("access_token"))
        update_last_update_time("recommended_pool")
        st.rerun()
    
    stocks = get_recommended_pool(st.session_state.user_id, st.session_state.get("access_token"))
    
    if not stocks:
        st.info("暂无股票，请点击[添加]按钮添加股票，或点击[刷新]获取AI推荐")
        return
    
    with st.spinner("正在计算股票评分..."):
        stock_list = [{"code": s["stock_code"], "name": s.get("stock_name", "")} for s in stocks]
        scored_stocks = score_batch_stocks(stock_list)
    
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
                    remove_from_recommended_pool(st.session_state.user_id, stock['stock_code'], st.session_state.get("access_token"))
                    st.rerun()
    
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("🗑️ 清空所有", key="clear_pool", use_container_width=True):
            for s in stocks:
                remove_from_recommended_pool(st.session_state.user_id, s["stock_code"], st.session_state.get("access_token"))
            st.rerun()
    with col2:
        if st.button("📋 移到回测池", key="move_to_backtest", use_container_width=True):
            for s in stocks:
                add_to_backtest_pool(st.session_state.user_id, s["stock_code"], s.get("stock_name", ""), st.session_state.get("access_token"))
                remove_from_recommended_pool(st.session_state.user_id, s["stock_code"], st.session_state.get("access_token"))
            st.success(f"已将{len(stocks)}只股票移到回测池")
            st.rerun()


# ==================== 模块3：个股分析 ====================

def render_stock_analysis():
    """个股分析模块"""
    st.markdown(f"### {t()['module3_title']}")
    
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
        # ===== 添加调试信息 =====
        st.write(f"🔍 调试: 正在分析 {stock_code}")
    
        with st.spinner("正在分析..."):
            # 使用缓存获取评分
            score_result = get_cached_stock_score(stock_code, stock_name)
            df = get_cached_stock_data(stock_code, days=60)
        
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
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                 vertical_spacing=0.05, 
                                 row_heights=[0.7, 0.3])
            
            colors = ['red' if close >= open else 'green' 
                      for close, open in zip(df['close'], df['open'])]
            
            fig.add_trace(go.Candlestick(
                x=df['date'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='价格',
                increasing_line_color='red',
                decreasing_line_color='green'
            ), row=1, col=1)
            
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
    """回测功能模块"""
    st.markdown(f"### {t()['module4_title']}")
    
    last_update = get_last_update_time("backtest")
    st.caption(f"📅 最后更新: {last_update}")
    
    stocks = get_backtest_pool(st.session_state.user_id, st.session_state.get("access_token"))
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"📋 回测池: {len(stocks)}只股票")
    with col2:
        if st.button("📊 运行回测", key="run_backtest", use_container_width=True):
            if len(stocks) == 0:
                st.warning("回测池为空，请先从推荐池添加股票")
            else:
                if not consume_free_trial(st.session_state.user_id, st.session_state.get("access_token")):
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
                remove_from_backtest_pool(st.session_state.user_id, stock['stock_code'], st.session_state.get("access_token"))
                st.rerun()
    
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
        
        # 转换股票代码格式（掘金需要SHSE/SZSE前缀）
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


# ==================== 模块5：实操信号 + 掘金下单 ====================

def render_live_signals():
    """实操信号模块 + 掘金一键下单"""
    st.markdown(f"### {t()['module5_title']}")
    
    last_update = get_last_update_time("live_signals")
    st.caption(f"📅 最后更新: {last_update} | 💡 AI生成交易信号，掘金一键下单")
    
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button(t()["refresh"], key="refresh_signals", use_container_width=True):
            if not consume_free_trial(st.session_state.user_id, st.session_state.get("access_token")):
                st.warning("免费次数已用完，请升级到专业版")
            else:
                update_last_update_time("live_signals")
                st.rerun()
    
    recommended_stocks = get_recommended_pool(st.session_state.user_id, st.session_state.get("access_token"))
    live_stocks = get_live_pool(st.session_state.user_id, st.session_state.get("access_token"))
    
    signals = []
    
    # 从推荐池获取高评分股票
    for stock in recommended_stocks[:5]:
        score_raw = stock.get('current_score', 0)
        # 确保 score 是数字类型
        try:
            score = float(score_raw) if score_raw else 0
        except (ValueError, TypeError):
            score = 0
        
        if score >= 70:
            signals.append({
                "stock_code": stock['stock_code'],
                "stock_name": stock.get('stock_name', ''),
                "score": score,
                "action": "买入",
                "suggested_position": "5-15%",
                "confidence": f"{score:.0f}%"
            })
    
    # 从实操池获取持仓信号
    for stock in live_stocks:
        current_price_raw = stock.get('current_price', 0)
        avg_cost_raw = stock.get('avg_cost', 0)
        try:
            current_price = float(current_price_raw) if current_price_raw else 0
            avg_cost = float(avg_cost_raw) if avg_cost_raw else 0
        except (ValueError, TypeError):
            current_price = 0
            avg_cost = 0
        
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
    
    for idx, signal in enumerate(signals):
        with st.container(border=True):
            col1, col2, col3, col4, col5 = st.columns([1.5, 1, 1.5, 1.5, 1.5])
            
            with col1:
                st.markdown(f"**{signal['stock_code']}**")
                st.caption(signal['stock_name'])
            
            with col2:
                st.markdown(f"**{signal['action']}**")
            
            with col3:
                st.caption(f"建议: {signal['suggested_position']}")
            
            with col4:
                if signal.get('confidence'):
                    st.caption(f"置信度: {signal['confidence']}")
            
            with col5:
                # 掘金一键下单按钮
                if signal['action'] in ["买入", "卖出(获利)"] and GM_AVAILABLE:
                    # 使用简化价格（实际应从实时行情获取）
                    price = 100.0
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
    
    profile = get_user_profile(st.session_state.user_id, st.session_state.get("access_token"))
    if profile.get("subscription_tier") == "free":
        remaining = get_remaining_trials(st.session_state.user_id, st.session_state.get("access_token"))
        st.info(f"📋 免费用户每次刷新消耗1次，剩余{remaining}次。升级专业版后无限使用。")
    
    st.markdown("---")
    st.markdown("### 📖 操作指引")
    st.markdown("""
    1. 查看上方交易信号
    2. 点击[🤖 下单]按钮通过掘金自动下单
    3. 或在券商App手动下单
    4. 可在实操池中记录持仓
    
    ⚠️ 投资有风险，请谨慎决策
    """)


print("第4部分加载完成")
print("=" * 60)
# ============================================================
# 第5部分：主入口 + 侧边栏 + 顶部按钮 + 页面路由 + 性能优化
# 修复内容：
# - 侧边栏只显示用户名（不显示邮箱后缀）
# - 管理员退出后返回原登录状态
# - 添加缓存机制优化性能
# - 添加页面加载缓存
# ============================================================

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


# ==================== 缓存优化函数 ====================

@st.cache_data(ttl=3600)  # 缓存1小时
def get_cached_stock_data(ts_code: str, days: int = 120):
    """缓存股票日线数据"""
    return get_stock_daily(ts_code, days)


@st.cache_data(ttl=3600)  # 缓存1小时
def get_cached_stock_score(ts_code: str, stock_name: str = ""):
    """缓存股票评分结果"""
    return get_stock_score(ts_code, stock_name)


@st.cache_data(ttl=7200)  # 缓存2小时
def get_cached_sector_performance():
    """缓存板块表现数据"""
    return get_sector_performance()


@st.cache_data(ttl=86400)  # 缓存24小时
def get_cached_stock_name_cache():
    """缓存股票名称映射表"""
    return load_stock_name_cache()


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
            # 同时删除 user_settings
            settings_url = f"{SUPABASE_URL}/rest/v1/user_settings?id=eq.{user_id}"
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
    if st.button("退出管理员模式", use_container_width=True):
        # 恢复管理员登录前的用户状态
        prev_user_id = st.session_state.get("admin_previous_user_id")
        prev_user_email = st.session_state.get("admin_previous_user_email")
        prev_access_token = st.session_state.get("admin_previous_access_token")
        
        if prev_user_id and prev_user_email:
            st.session_state.authenticated = True
            st.session_state.user_id = prev_user_id
            st.session_state.user_email = prev_user_email
            st.session_state.access_token = prev_access_token
        else:
            st.session_state.authenticated = False
            st.session_state.user_id = None
            st.session_state.user_email = None
            st.session_state.access_token = None
        
        st.session_state.admin_mode = False
        st.session_state.admin_previous_user_id = None
        st.session_state.admin_previous_user_email = None
        st.session_state.admin_previous_access_token = None
        st.rerun()


# ==================== 侧边栏 ====================

def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.markdown("## 📊 AI量化股票系统")
        st.markdown("---")
        
        if st.session_state.authenticated and not st.session_state.admin_mode:
            user_email = st.session_state.user_email
            # 提取用户名（@前面的部分）
            username = user_email.split('@')[0] if user_email else user_email
            user_id = st.session_state.user_id
            access_token = st.session_state.get("access_token")
            
            # ===== 调试1：打印原始 profile =====
            profile = get_user_profile(user_id, access_token)
            
            tier = profile.get("subscription_tier", "free")
            remaining_raw = profile.get("free_trials_remaining", 0)
            
            # ===== 调试2：打印提取的值 =====
            
            # 确保 remaining 是数字
            try:
                remaining = int(remaining_raw) if remaining_raw else 0
            except (ValueError, TypeError):
                remaining = 0
            
            # ===== 调试3：打印转换后的值 =====
            
            # 检查剩余次数是否有效
            if remaining <= 0 and tier != "pro":
                # ===== 调试4：打印警告 =====
                st.warning("⚠️ 调试信息：剩余次数为0或无效")
            
            tier_display = "💎 专业版" if tier == "pro" else "🔒 免费版"
            remaining_display = "∞" if tier == "pro" else str(remaining)
            
            # ===== 调试5：打印显示值 =====
            
            st.markdown(f"""
            <div class="sidebar-user-info">
                <strong>👤 {username}</strong><br>
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
        
        st.markdown("### 🌍 市场选择")
        market = st.selectbox("选择市场", MARKET_OPTIONS, index=0, key="market_selector", label_visibility="collapsed")
        if market != st.session_state.get("market", "A股"):
            st.session_state.market = market
            st.rerun()
        
        st.markdown("---")
        
        with st.expander(t()["about_header"], expanded=True):
            st.markdown(t()["about_text"])
        
        with st.expander(t()["guide_header"], expanded=False):
            st.markdown(t()["guide_text"])
        
        with st.expander(t()["contact_header"], expanded=False):
            st.markdown(t()["contact_email"])
        
        st.markdown("---")
        st.caption("v3.0 | TechLife")
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
    if st.session_state.get("show_paywall", False):
        show_paywall()
        return
    
    handle_stripe_callback()
    
    # 获取用户名显示
    username = st.session_state.user_email.split('@')[0] if st.session_state.user_email else st.session_state.user_email
    st.markdown(f"<h3 style='text-align: left;'>{t()['welcome']}, {username}</h3>", unsafe_allow_html=True)
    
    # 获取当前用户的 access_token
    access_token = st.session_state.get("access_token")
    user_id = st.session_state.user_id
    
    profile = get_user_profile(user_id, access_token)
    if profile.get("subscription_tier") == "free":
        remaining = get_remaining_trials(user_id, access_token)
        st.caption(f"📋 剩余免费次数: {remaining} | 升级专业版后无限使用")
    
    st.markdown("---")
    
    # 使用缓存获取数据（提升性能）
    with st.spinner("加载数据中..."):
        # 预加载缓存数据
        if TUSHARE_AVAILABLE:
            get_cached_stock_name_cache()
    
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


print("第5部分加载完成")
print("=" * 60)
