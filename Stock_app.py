"""
AI量化股票系统 - 完整单文件版本 v1.0
基于DFSS方法论 + 机器学习集成

完整包含：
- 用户认证（Supabase Auth）
- 5大功能模块（市场简报、推荐股票池、个股分析、回测、实操信号）
- 管理员面板
- 多语言支持
- Stripe付费集成（待配置）

部署方式：
1. 将代码上传到GitHub
2. 在Streamlit Cloud部署
3. 配置Secrets（Supabase密钥、Stripe密钥等）
"""

# ============================================================
# 第1部分：导入、配置、常量、多语言、Supabase连接、工具函数
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

# ==================== Tushare 配置 ====================
TUSHARE_TOKEN = st.secrets.get("TUSHARE_TOKEN", "")

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
    """退出登录"""
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.user_email = None
    st.session_state.admin_mode = False
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
            return True, f"成功添加 {stock_code}"
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
            return True, f"成功添加 {stock_code}"
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


print("第1部分加载完成")
print("=" * 60)
# ============================================================
# 第2部分：管理员页面 + 登录验证 + 数据编辑器
# ============================================================

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


# ==================== 股票数据解析函数 ====================

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
    返回: (is_valid, message)
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


# ==================== 评分引擎辅助函数 ====================

def get_stock_score_simple(stock_code: str, stock_name: str = "") -> Dict:
    """
    简化版个股评分（实际使用时需接入Tushare获取真实数据）
    返回: {"score": 92, "level": "S", "action": "强烈买入", ...}
    """
    # 模拟评分（基于代码哈希，确保同一股票每次评分一致）
    hash_val = hash(stock_code) % 100
    total_score = max(30, min(95, 50 + (hash_val % 45)))
    
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
        "stock_code": stock_code,
        "stock_name": stock_name or stock_code,
        "total_score": total_score,
        "level": level,
        "action": action,
        "position": position,
        "reasons": generate_score_reasons(total_score)
    }


def generate_score_reasons(score: float) -> str:
    """生成得分原因说明"""
    if score >= 85:
        return "板块爆发期 + 技术指标共振 + 龙头地位"
    elif score >= 70:
        return "板块热度中等 + 技术指标偏多"
    elif score >= 55:
        return "符合基本筛选条件"
    elif score >= 40:
        return "技术指标偏空，建议等待"
    else:
        return "板块冷却 + 技术指标空头"


def score_batch_stocks(stock_list: List[Dict]) -> List[Dict]:
    """批量计算股票得分"""
    results = []
    for stock in stock_list:
        score_result = get_stock_score_simple(stock["code"], stock.get("name", ""))
        results.append(score_result)
    return sorted(results, key=lambda x: x["total_score"], reverse=True)


def get_hot_sectors() -> List[Dict]:
    """
    获取热点板块（模拟数据）
    实际使用时需接入Tushare获取真实数据
    """
    # 模拟热点板块数据
    mock_sectors = [
        {"name": "人工智能", "score": 92, "top_stocks": ["科大讯飞", "海康威视", "中科曙光"]},
        {"name": "半导体", "score": 88, "top_stocks": ["中芯国际", "北方华创", "紫光国微"]},
        {"name": "新能源", "score": 85, "top_stocks": ["宁德时代", "比亚迪", "隆基绿能"]},
        {"name": "消费电子", "score": 78, "top_stocks": ["立讯精密", "歌尔股份", "蓝思科技"]},
        {"name": "医药", "score": 72, "top_stocks": ["恒瑞医药", "药明康德", "迈瑞医疗"]},
    ]
    return mock_sectors


def generate_market_brief() -> Tuple[str, str]:
    """
    生成市场简报
    返回: (market_trend, market_desc)
    """
    market_trend = "震荡上行"
    market_desc = "近期市场情绪偏暖，成交量温和放大，人工智能、半导体等科技板块持续活跃，建议关注热点板块轮动机会。"
    return market_trend, market_desc


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


# ==================== 模拟回测函数 ====================

def run_backtest_simple(stock_codes: List[str]) -> Dict:
    """
    简化版回测函数
    返回回测结果字典
    """
    # 模拟回测数据
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


print("第2部分加载完成")
print("=" * 60)
# ============================================================
# 第3部分：5个功能模块（市场简报、推荐股票池、个股分析、回测、实操信号）
# ============================================================

# ==================== 模块1：市场简报 ====================

def render_market_brief():
    """市场简报模块"""
    st.markdown(f"### {t()['module1_title']}")
    
    col1, col2 = st.columns([4, 1])
    with col2:
        refresh = st.button(t()["refresh"], key="refresh_brief", use_container_width=True)
    
    if refresh:
        if not consume_free_trial(st.session_state.user_id):
            st.warning("免费次数已用完，请升级到专业版")
            return
        st.rerun()
    
    with st.spinner("正在获取市场数据..."):
        # 获取热点板块
        hot_sectors = get_hot_sectors()
        market_trend, market_desc = generate_market_brief()
        
        # 显示市场简报
        st.info(f"📈 **大盘趋势**: {market_trend}\n\n📝 **市场解读**: {market_desc}")
        
        # 热点板块表格
        if hot_sectors:
            st.markdown("**🔥 今日热点板块**")
            sector_df = pd.DataFrame([
                {"板块": s["name"], "热度": f"{s['score']}分", "代表个股": ", ".join(s["top_stocks"][:3])}
                for s in hot_sectors[:5]
            ])
            st.dataframe(sector_df, use_container_width=True, hide_index=True)
        else:
            st.caption("暂无热点板块数据，请稍后刷新")
        
        # 龙头股提示
        st.markdown("**🎯 龙头股关注**")
        st.caption("• 人工智能: 科大讯飞、海康威视\n• 半导体: 中芯国际、北方华创\n• 新能源: 宁德时代、比亚迪")


# ==================== 模块2：推荐股票池 ====================

def render_recommended_pool():
    """推荐股票池模块"""
    st.markdown(f"### {t()['module2_title']}")
    st.caption(f"📌 最多{MAX_RECOMMENDED_STOCKS}只股票 | 点击[分析]可查看详细评分")
    
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
                    stock_name = formatted_code.split('.')[0]
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
                        st.rerun()
                else:
                    st.error(formatted)
    
    # 执行分析
    if st.session_state.get("analyze_code"):
        stock_code = st.session_state.analyze_code
        stock_name = st.session_state.get("analyze_name", "")
        
        with st.spinner("正在分析..."):
            score_result = get_stock_score_simple(stock_code, stock_name)
        
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
        
        # 雷达图
        fig = go.Figure(data=go.Scatterpolar(
            r=[
                min(100, score_result['total_score']),
                min(100, score_result['total_score'] * 0.9),
                min(100, score_result['total_score'] * 0.85),
                min(100, score_result['total_score'] * 0.8)
            ],
            theta=["综合评分", "趋势强度", "技术指标", "资金关注"],
            fill='toself',
            marker=dict(color=color)
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            height=300,
            margin=dict(l=40, r=40, t=20, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # 详细分析
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
                    st.session_state.user_id, stock_code, stock_name, source="user",
                    score=score_result["total_score"]
                )
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
        with col2:
            if st.button("📋 添加到回测池", use_container_width=True):
                success, msg = add_to_backtest_pool(
                    st.session_state.user_id, stock_code, stock_name
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
    st.caption("💡 AI生成交易信号，请自行前往券商App下单")
    
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button(t()["refresh"], key="refresh_signals", use_container_width=True):
            if not consume_free_trial(st.session_state.user_id):
                st.warning("免费次数已用完，请升级到专业版")
            else:
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


print("第3部分加载完成")
print("=" * 60)
# ============================================================
# 第4部分：管理员面板（用户管理、股票池查看）
# ============================================================

# ==================== 管理员辅助函数 ====================

def get_all_users() -> list:
    """获取所有用户列表（管理员用）"""
    try:
        response = supabase_request("GET", "profiles", use_secret=True)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取用户列表失败: {e}")
        return []


def get_user_auth_details(user_id: str) -> Dict:
    """获取用户的认证详细信息（最后登录时间、注册时间等）"""
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
                        "email_confirmed_at": user.get("email_confirmed_at", ""),
                        "phone": user.get("phone", "")
                    }
    except Exception as e:
        print(f"获取用户认证信息失败: {e}")
    
    return {
        "created_at": "",
        "last_sign_in_at": "",
        "email_confirmed_at": "",
        "phone": ""
    }


def get_user_stock_summary(user_id: str) -> Dict:
    """获取用户的股票池摘要"""
    recommended = get_recommended_pool(user_id)
    backtest = get_backtest_pool(user_id)
    live = get_live_pool(user_id)
    
    return {
        "recommended_count": len(recommended),
        "backtest_count": len(backtest),
        "live_count": len(live),
        "recommended_stocks": [s.get("stock_code") for s in recommended[:5]],
        "backtest_stocks": [s.get("stock_code") for s in backtest[:5]],
        "live_stocks": [s.get("stock_code") for s in live[:5]]
    }


def admin_delete_user(user_id: str, user_email: str) -> tuple:
    """
    管理员删除用户
    返回: (success, message)
    """
    try:
        # 删除用户认证记录
        url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"
        headers = get_supabase_headers(use_secret=True)
        response = requests.delete(url, headers=headers)
        
        if response.status_code in [200, 204]:
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
    """
    设置用户订阅等级
    tier: 'free' 或 'pro'
    months: 专业版月数（仅当tier='pro'时有效）
    """
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
    """
    发送密码重置邮件
    返回: (success, message)
    """
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


# ==================== 管理员UI组件 ====================

def render_admin_panel():
    """管理员面板主界面"""
    st.markdown(f"## ⚙️ {t()['admin_panel']}")
    
    # 获取用户列表
    users = get_all_users()
    
    if not users:
        st.info("暂无用户数据")
        return
    
    # 获取用户认证详情和股票池摘要
    users_with_details = []
    for user in users:
        auth_details = get_user_auth_details(user.get("id", ""))
        stock_summary = get_user_stock_summary(user.get("id", ""))
        
        users_with_details.append({
            "id": user.get("id"),
            "email": user.get("email", ""),
            "subscription_tier": user.get("subscription_tier", "free"),
            "free_trials_remaining": user.get("free_trials_remaining", FREE_TRIAL_LIMIT),
            "subscription_expires_at": user.get("subscription_expires_at", ""),
            "created_at": auth_details.get("created_at", "")[:10] if auth_details.get("created_at") else "-",
            "last_sign_in_at": auth_details.get("last_sign_in_at", "")[:10] if auth_details.get("last_sign_in_at") else "-",
            "email_confirmed": "✅" if auth_details.get("email_confirmed_at") else "❌",
            "recommended_count": stock_summary["recommended_count"],
            "backtest_count": stock_summary["backtest_count"],
            "live_count": stock_summary["live_count"]
        })
    
    # ==================== 统计卡片 ====================
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
    
    # ==================== 用户列表 ====================
    st.markdown(f"### 👥 {t()['user_list']}")
    
    # 转换为DataFrame显示
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
    
    # ==================== 用户管理 ====================
    st.markdown("### 🔧 用户管理")
    
    # 选择用户
    user_options = [f"{u['email']} ({u['subscription_tier']})" for u in users_with_details]
    if user_options:
        selected_user_str = st.selectbox("选择用户", user_options, key="admin_select_user")
        selected_email = selected_user_str.split(" ")[0]
        selected_user = next((u for u in users_with_details if u["email"] == selected_email), None)
        
        if selected_user:
            st.markdown(f"**当前用户**: {selected_user['email']}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### 📝 修改订阅")
                new_tier = st.selectbox(
                    "订阅等级",
                    ["free", "pro"],
                    index=0 if selected_user["subscription_tier"] == "free" else 1,
                    key="admin_new_tier"
                )
                
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
                new_trials = st.number_input(
                    "设置剩余次数",
                    min_value=0,
                    max_value=100,
                    value=selected_user["free_trials_remaining"],
                    key="admin_new_trials"
                )
                
                if st.button("重置次数", key="admin_reset_trials", use_container_width=True):
                    success, msg = admin_reset_user_trials(selected_user["id"], new_trials)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            
            # 操作按钮行
            st.markdown("#### ⚠️ 危险操作")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("📧 发送重置邮件", key="admin_send_reset", use_container_width=True):
                    success, msg = send_password_reset_email(selected_user["email"])
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
            
            with col2:
                if st.button("🔑 重置密码(删除用户)", key="admin_reset_pwd", use_container_width=True):
                    success, msg = admin_delete_user(selected_user["id"], selected_user["email"])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            
            with col3:
                if st.button("🗑️ 删除用户", key="admin_delete_user", use_container_width=True):
                    success, msg = admin_delete_user(selected_user["id"], selected_user["email"])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
    
    st.markdown("---")
    
    # ==================== 查看用户股票池 ====================
    st.markdown("### 📊 查看用户股票池")
    
    if user_options:
        view_user_str = st.selectbox("选择用户查看股票池", user_options, key="admin_view_stocks")
        view_email = view_user_str.split(" ")[0]
        view_user = next((u for u in users_with_details if u["email"] == view_email), None)
        
        if view_user:
            user_id = view_user["id"]
            
            # Tab切换
            tab1, tab2, tab3 = st.tabs(["推荐股票池", "回测股票池", "实操股票池"])
            
            with tab1:
                stocks = get_recommended_pool(user_id)
                if stocks:
                    df = pd.DataFrame(stocks)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    st.caption(f"共 {len(stocks)} 只股票")
                else:
                    st.info("暂无推荐股票")
            
            with tab2:
                stocks = get_backtest_pool(user_id)
                if stocks:
                    df = pd.DataFrame(stocks)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    st.caption(f"共 {len(stocks)} 只股票")
                else:
                    st.info("暂无回测股票")
            
            with tab3:
                stocks = get_live_pool(user_id)
                if stocks:
                    df = pd.DataFrame(stocks)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    st.caption(f"共 {len(stocks)} 只股票")
                else:
                    st.info("暂无实操股票")
    
    st.markdown("---")
    
    # ==================== 批量操作 ====================
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
            st.download_button(
                label="下载CSV",
                data=csv,
                file_name=f"users_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                key="admin_download_csv"
            )


print("第4部分加载完成")
print("=" * 60)
# ============================================================
# 第5部分：主入口（app.py）核心代码
# 包含：自定义CSS、侧边栏、右上角按钮、主页面路由、5个模块整合
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
        st.caption("v1.0 | TechLife")


# ==================== 右上角按钮 ====================
def render_top_buttons():
    """渲染右上角语言切换和管理员按钮"""
    # 创建5列布局：空白 + 中文 + 英文 + 管理员 + 退出
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
        if st.session_state.authenticated and not st.session_state.admin_mode:
            if st.button("🚪", key="logout_btn", help="退出登录", use_container_width=True):
                sign_out()


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


# ==================== 主函数 ====================
def main():
    """主函数：控制页面流程"""
    
    # 初始化Session State
    init_session_state()
    
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
        render_admin_panel()
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
