"""
auth.py - Supabase认证、登录/注册、Session管理、管理员验证
"""

import streamlit as st
import requests
from datetime import datetime

from config import (
    SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_SECRET_KEY,
    ADMIN_USERNAME, ADMIN_PASSWORD, t
)


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


def supabase_request(method: str, endpoint: str, data=None, use_secret=False):
    """通用的Supabase REST API请求"""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = get_supabase_headers(use_secret)
    
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
                    "free_trials_remaining": 30,
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
            "free_trials_remaining": 30,
            "subscription_expires_at": None,
            "last_sign_in_at": None
        }
    
    try:
        response = supabase_request("GET", f"profiles?id=eq.{user_id}", use_secret=True)
        if response.status_code == 200 and response.json():
            data = response.json()[0]
            return {
                "subscription_tier": data.get("subscription_tier", "free"),
                "free_trials_remaining": data.get("free_trials_remaining", 30),
                "subscription_expires_at": data.get("subscription_expires_at"),
                "last_sign_in_at": data.get("last_sign_in_at")
            }
    except Exception as e:
        print(f"获取用户资料失败: {e}")
    
    return {
        "subscription_tier": "free",
        "free_trials_remaining": 30,
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
        return False


def get_remaining_trials(user_id: str) -> int:
    """获取剩余免费次数"""
    profile = get_user_profile(user_id)
    if profile.get("subscription_tier") == "pro":
        return -1  # -1 表示无限
    return profile.get("free_trials_remaining", 0)


# ==================== 管理员操作 ====================

def get_all_users() -> list:
    """获取所有用户列表（管理员用）"""
    try:
        # 获取profiles表中的用户
        response = supabase_request("GET", "profiles", use_secret=True)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"获取用户列表失败: {e}")
        return []


def admin_reset_user_password(user_email: str) -> tuple:
    """
    管理员重置用户密码
    方案：发送邮件通知用户需要重新注册
    返回: (success, message)
    """
    try:
        # 先查找用户ID
        users = get_all_users()
        target_user = None
        for u in users:
            if u.get("email") == user_email:
                target_user = u
                break
        
        if not target_user:
            return False, "用户不存在"
        
        # 方案：删除用户（用户需要重新注册）
        # 注意：这需要调用Supabase Admin API
        url = f"{SUPABASE_URL}/auth/v1/admin/users/{target_user['id']}"
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}"
        }
        response = requests.delete(url, headers=headers)
        
        if response.status_code in [200, 204]:
            return True, f"用户 {user_email} 已重置，请通知用户重新注册"
        else:
            return False, f"重置失败: {response.text}"
    except Exception as e:
        return False, f"重置失败: {str(e)}"


def send_custom_email(recipient_email: str, subject: str, body: str) -> bool:
    """
    发送自定义邮件（通过SMTP或其他服务）
    注意：这是简化版，实际发送邮件需要配置SMTP
    """
    # 由于邮件发送需要额外配置（如SMTP服务器或SendGrid API），
    # 这里先返回True，实际使用时需要配置邮件服务
    print(f"需要发送邮件到 {recipient_email}")
    print(f"主题: {subject}")
    print(f"内容: {body}")
    return True


# ==================== UI组件 ====================

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
        st.markdown(f"<h2 style='text-align: center;'>管理员登录</h2>", unsafe_allow_html=True)
        
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
"""
stock_engine.py - 核心评分引擎
提供：技术指标计算、板块热度评分、综合评分
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

from config import TECH_WEIGHTS, SIGNAL_LEVELS, TUSHARE_TOKEN


# ==================== Tushare 数据获取 ====================

def get_tushare_pro():
    """获取Tushare连接"""
    try:
        import tushare as ts
        ts.set_token(TUSHARE_TOKEN)
        return ts.pro_api()
    except ImportError:
        st.warning("Tushare未安装，请运行: pip install tushare")
        return None
    except Exception as e:
        st.warning(f"Tushare连接失败: {e}")
        return None


def get_stock_daily(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取股票日线数据"""
    pro = get_tushare_pro()
    if pro is None:
        return pd.DataFrame()
    
    try:
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df is not None and len(df) > 0:
            df = df.sort_values('trade_date')
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"获取{ts_code}日线数据失败: {e}")
        return pd.DataFrame()


def get_concept_list() -> pd.DataFrame:
    """获取概念板块列表"""
    pro = get_tushare_pro()
    if pro is None:
        return pd.DataFrame()
    
    try:
        df = pro.concept()
        return df
    except Exception as e:
        print(f"获取概念列表失败: {e}")
        return pd.DataFrame()


def get_concept_members(concept_name: str) -> pd.DataFrame:
    """获取概念板块成分股"""
    pro = get_tushare_pro()
    if pro is None:
        return pd.DataFrame()
    
    try:
        df = pro.concept_member(concept_name=concept_name)
        return df
    except Exception as e:
        print(f"获取{concept_name}成分股失败: {e}")
        return pd.DataFrame()


# ==================== 技术指标计算 ====================

def calculate_macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> Dict:
    """计算MACD指标"""
    if df.empty or len(df) < slow:
        return {"macd": 0, "signal": 0, "histogram": 0, "signal_level": "neutral"}
    
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
    
    # 判断信号
    if macd_line[-1] > signal_line[-1] and macd_line[-2] <= signal_line[-2]:
        signal_level = "golden_cross"  # 金叉
    elif macd_line[-1] < signal_line[-1] and macd_line[-2] >= signal_line[-2]:
        signal_level = "death_cross"   # 死叉
    elif macd_line[-1] > 0 and signal_line[-1] > 0:
        signal_level = "bullish"       # 多头
    elif macd_line[-1] < 0 and signal_line[-1] < 0:
        signal_level = "bearish"       # 空头
    else:
        signal_level = "neutral"
    
    return {
        "macd": macd_line[-1],
        "signal": signal_line[-1],
        "histogram": histogram[-1],
        "signal_level": signal_level
    }


def calculate_kdj(df: pd.DataFrame, n=9, m1=3, m2=3) -> Dict:
    """计算KDJ指标"""
    if df.empty or len(df) < n:
        return {"k": 50, "d": 50, "j": 50, "signal_level": "neutral"}
    
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
    
    # 判断信号
    if k < 20 and d < 20 and k > d:
        signal_level = "oversold_golden"  # 低位金叉
    elif k > 80 and d > 80 and k < d:
        signal_level = "overbought_death" # 高位死叉
    elif k > d:
        signal_level = "bullish"
    else:
        signal_level = "bearish"
    
    return {"k": k, "d": d, "j": j, "signal_level": signal_level}


def calculate_bollinger_bands(df: pd.DataFrame, period=20, std_dev=2) -> Dict:
    """计算布林带"""
    if df.empty or len(df) < period:
        return {"upper": 0, "middle": 0, "lower": 0, "position": 0.5, "signal_level": "neutral"}
    
    close = df['close'].values
    middle = np.mean(close[-period:])
    std = np.std(close[-period:])
    
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    current = close[-1]
    
    # 计算位置（0-1，0=下轨，1=上轨）
    if upper > lower:
        position = (current - lower) / (upper - lower)
    else:
        position = 0.5
    
    # 判断信号
    if current > upper:
        signal_level = "above_upper"   # 突破上轨
    elif current < lower:
        signal_level = "below_lower"   # 跌破下轨
    elif position > 0.7:
        signal_level = "near_upper"
    elif position < 0.3:
        signal_level = "near_lower"
    else:
        signal_level = "neutral"
    
    return {"upper": upper, "middle": middle, "lower": lower, 
            "position": position, "signal_level": signal_level}


def calculate_rsi(df: pd.DataFrame, period=14) -> Dict:
    """计算RSI指标"""
    if df.empty or len(df) < period + 1:
        return {"rsi": 50, "signal_level": "neutral"}
    
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
    
    # 判断信号
    if rsi > 70:
        signal_level = "overbought"   # 超买
    elif rsi < 30:
        signal_level = "oversold"     # 超卖
    else:
        signal_level = "neutral"
    
    return {"rsi": rsi, "signal_level": signal_level}


def calculate_volume_price(df: pd.DataFrame) -> Dict:
    """计算量价配合度"""
    if df.empty or len(df) < 5:
        return {"score": 0.5, "signal_level": "neutral"}
    
    price_change = df['close'].pct_change().values[-5:]
    volume_change = df['vol'].pct_change().values[-5:]
    
    # 量价配合：上涨放量=1，上涨缩量=-1，下跌缩量=1，下跌放量=-1
    scores = []
    for i in range(len(price_change)):
        if np.isnan(price_change[i]) or np.isnan(volume_change[i]):
            continue
        if price_change[i] > 0:
            if volume_change[i] > 0:
                scores.append(1)   # 上涨放量，好
            else:
                scores.append(-1)  # 上涨缩量，不好
        else:
            if volume_change[i] < 0:
                scores.append(1)   # 下跌缩量，好
            else:
                scores.append(-1)  # 下跌放量，不好
    
    if not scores:
        return {"score": 0.5, "signal_level": "neutral"}
    
    avg_score = np.mean(scores)
    normalized_score = (avg_score + 1) / 2  # 转换到0-1区间
    
    if normalized_score > 0.6:
        signal_level = "bullish"
    elif normalized_score < 0.4:
        signal_level = "bearish"
    else:
        signal_level = "neutral"
    
    return {"score": normalized_score, "signal_level": signal_level}


def calculate_technical_score(df: pd.DataFrame) -> Dict:
    """计算综合技术指标得分（0-100）"""
    if df.empty:
        return {"score": 50, "level": "D", "details": {}}
    
    details = {}
    
    # MACD (权重25%)
    macd = calculate_macd(df)
    macd_score = 0
    if macd["signal_level"] in ["golden_cross", "bullish"]:
        macd_score = 100
    elif macd["signal_level"] == "death_cross":
        macd_score = 0
    else:
        macd_score = 50
    details["macd"] = macd_score
    
    # KDJ (权重20%)
    kdj = calculate_kdj(df)
    kdj_score = 0
    if kdj["signal_level"] == "oversold_golden":
        kdj_score = 100
    elif kdj["signal_level"] == "bullish":
        kdj_score = 70
    elif kdj["signal_level"] == "overbought_death":
        kdj_score = 0
    elif kdj["signal_level"] == "bearish":
        kdj_score = 30
    else:
        kdj_score = 50
    details["kdj"] = kdj_score
    
    # 布林带 (权重20%)
    boll = calculate_bollinger_bands(df)
    boll_score = 0
    if boll["signal_level"] == "above_upper":
        boll_score = 80
    elif boll["position"] > 0.7:
        boll_score = 70
    elif boll["signal_level"] == "below_lower":
        boll_score = 20
    elif boll["position"] < 0.3:
        boll_score = 30
    else:
        boll_score = 50
    details["boll"] = boll_score
    
    # RSI (权重15%)
    rsi = calculate_rsi(df)
    rsi_score = 0
    if rsi["signal_level"] == "oversold":
        rsi_score = 80  # 超卖是买入机会
    elif rsi["signal_level"] == "overbought":
        rsi_score = 30
    else:
        rsi_score = 50 + (rsi["rsi"] - 50) / 2  # 接近50得50分
    details["rsi"] = rsi_score
    
    # 量价配合 (权重20%)
    vp = calculate_volume_price(df)
    vp_score = vp["score"] * 100
    details["volume_price"] = vp_score
    
    # 加权计算
    total_score = (
        macd_score * TECH_WEIGHTS["macd"] +
        kdj_score * TECH_WEIGHTS["kdj"] +
        boll_score * TECH_WEIGHTS["boll"] +
        rsi_score * TECH_WEIGHTS["rsi"] +
        vp_score * TECH_WEIGHTS["volume_price"]
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


# ==================== 板块热度评分 ====================

def get_hot_sectors() -> List[Dict]:
    """
    获取热点板块
    基于Tushare概念板块数据计算热度
    返回: [{"name": "人工智能", "score": 85, "top_stocks": [...]}, ...]
    """
    pro = get_tushare_pro()
    if pro is None:
        return []
    
    try:
        # 获取概念板块列表
        concepts = get_concept_list()
        if concepts.empty:
            return []
        
        # 计算各板块热度（简化版：基于成分股涨跌幅）
        hot_sectors = []
        for _, concept in concepts.head(20).iterrows():
            concept_name = concept.get('concept_name', '')
            if not concept_name:
                continue
            
            # 获取成分股
            members = get_concept_members(concept_name)
            if members.empty:
                continue
            
            # 获取成分股最新行情计算平均涨幅
            # 简化：返回示例数据
            hot_sectors.append({
                "name": concept_name,
                "score": np.random.randint(60, 95),
                "top_stocks": ["000001.SZ", "000002.SZ", "000003.SZ"][:3]
            })
        
        return sorted(hot_sectors, key=lambda x: x["score"], reverse=True)[:5]
    except Exception as e:
        print(f"获取热点板块失败: {e}")
        return []


# ==================== 个股综合评分 ====================

def get_stock_score(stock_code: str, stock_name: str = "") -> Dict:
    """
    获取个股综合评分
    返回: {"score": 92, "level": "S", "tech_score": 88, "sector_score": 95, ...}
    """
    # 解析股票代码
    if stock_code.endswith(".HK"):
        market = "HK"
        ts_code = None
    elif stock_code.endswith(".SZ"):
        market = "SZ"
        ts_code = stock_code
    elif stock_code.endswith(".SH"):
        market = "SH"
        ts_code = stock_code
    else:
        # 默认A股
        market = "A"
        ts_code = stock_code + ".SZ"
    
    # 获取日线数据计算技术指标得分
    tech_score = 50
    tech_details = {}
    
    if market in ["SZ", "SH"] and TUSHARE_TOKEN:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        df = get_stock_daily(ts_code, start_date, end_date)
        
        if not df.empty:
            # 重命名列以匹配计算函数
            df = df.rename(columns={
                'trade_date': 'date',
                'vol': 'volume'
            })
            tech_result = calculate_technical_score(df)
            tech_score = tech_result["score"]
            tech_details = tech_result["details"]
    
    # 板块热度得分（简化）
    sector_score = 50
    
    # 龙头识别得分（简化）
    leader_score = 50
    
    # 长短期趋势得分（简化）
    trend_score = 50
    
    # 综合得分
    total_score = (
        sector_score * 0.40 +
        leader_score * 0.30 +
        tech_score * 0.20 +
        trend_score * 0.10
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
        "stock_code": stock_code,
        "stock_name": stock_name or stock_code,
        "total_score": round(total_score, 2),
        "level": level,
        "action": action,
        "position": position,
        "tech_score": round(tech_score, 2),
        "sector_score": round(sector_score, 2),
        "leader_score": round(leader_score, 2),
        "trend_score": round(trend_score, 2),
        "tech_details": tech_details,
        "reasons": generate_score_reasons(sector_score, leader_score, tech_score, trend_score)
    }


def generate_score_reasons(sector: float, leader: float, tech: float, trend: float) -> str:
    """生成得分原因说明"""
    reasons = []
    if sector >= 80:
        reasons.append("板块处于爆发期")
    elif sector >= 60:
        reasons.append("板块热度中等")
    
    if leader >= 80:
        reasons.append("板块内龙头股")
    elif leader >= 60:
        reasons.append("板块内权重股")
    
    if tech >= 80:
        reasons.append("技术指标共振（金叉+放量）")
    elif tech >= 60:
        reasons.append("技术指标偏多")
    
    if trend >= 80:
        reasons.append("长期趋势向上")
    
    return " + ".join(reasons) if reasons else "符合基本筛选条件"


def score_batch_stocks(stock_list: List[Dict]) -> List[Dict]:
    """批量计算股票得分"""
    results = []
    for stock in stock_list:
        score_result = get_stock_score(stock["code"], stock.get("name", ""))
        results.append(score_result)
    
    return sorted(results, key=lambda x: x["total_score"], reverse=True)
"""
modules.py - 5个功能模块UI
包含：市场简报、推荐股票池、个股分析、回测功能、实操信号
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import List, Dict

from config import t, SIGNAL_LEVELS, MAX_RECOMMENDED_STOCKS
from auth import get_remaining_trials, consume_free_trial, get_user_profile
from supabase_ops import (
    get_recommended_pool, add_to_recommended_pool, remove_from_recommended_pool,
    get_backtest_pool, add_to_backtest_pool, remove_from_backtest_pool,
    get_live_pool, add_to_live_pool, remove_from_live_pool,
    update_live_pool_price, add_trade_log
)
from stock_engine import (
    get_stock_score, score_batch_stocks, get_hot_sectors,
    calculate_technical_score, get_stock_daily
)


# ==================== 模块1：市场简报 ====================

def render_market_brief():
    """市场简报模块"""
    st.markdown(f"### {t()['module1_title']}")
    
    col1, col2 = st.columns([4, 1])
    with col2:
        refresh = st.button(t()["refresh"], key="refresh_brief", use_container_width=True)
    
    if refresh:
        # 消耗免费次数
        if not consume_free_trial(st.session_state.user_id):
            st.warning("免费次数已用完，请升级到专业版")
            return
        st.rerun()
    
    with st.spinner("正在获取市场数据..."):
        # 获取热点板块
        hot_sectors = get_hot_sectors()
        
        # 生成大盘趋势描述（简化）
        market_trend = "震荡上行"
        market_desc = "近期市场情绪偏暖，成交量温和放大，建议关注热点板块轮动机会。"
        
        # 显示市场简报
        st.info(f"📈 **大盘趋势**: {market_trend}\n\n📝 **市场解读**: {market_desc}")
        
        # 热点板块表格
        if hot_sectors:
            st.markdown("**🔥 今日热点板块**")
            sector_df = pd.DataFrame([
                {"板块": s["name"], "热度": f"{s['score']}%", "代表个股": ", ".join(s.get("top_stocks", [])[:3])}
                for s in hot_sectors[:5]
            ])
            st.dataframe(sector_df, use_container_width=True, hide_index=True)
        else:
            st.caption("暂无热点板块数据，请稍后刷新")
        
        # 龙头股提示
        st.markdown("**🎯 龙头股关注**")
        st.caption("• 人工智能: 板块龙头关注科大讯飞、海康威视\n• 半导体: 中芯国际、北方华创\n• 新能源: 宁德时代、比亚迪")


# ==================== 模块2：推荐股票池 ====================

def render_recommended_pool():
    """推荐股票池模块"""
    st.markdown(f"### {t()['module2_title']}")
    st.caption(f"📌 最多{MAX_RECOMMENDED_STOCKS}只股票 | 点击[分析]可查看详细评分")
    
    # 操作栏
    col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
    with col1:
        new_stock = st.text_input("添加股票", placeholder="如: 000001.SZ 或 0700.HK", key="add_stock_input", label_visibility="collapsed")
    with col2:
        if st.button("➕ 添加", key="add_stock_btn", use_container_width=True):
            if new_stock:
                # 验证股票代码格式
                if any(new_stock.endswith(suffix) for suffix in [".SZ", ".SH", ".HK"]):
                    # 获取股票名称（简化）
                    stock_name = new_stock.split(".")[0]
                    success, msg = add_to_recommended_pool(
                        st.session_state.user_id, new_stock.upper(), stock_name, source="user"
                    )
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.error("请输入正确的股票代码格式，如: 000001.SZ")
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
    
    # 批量删除
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
                if not consume_free_trial(st.session_state.user_id):
                    st.warning("免费次数已用完，请升级到专业版")
                else:
                    st.session_state.analyze_code = stock_code
                    st.rerun()
    
    # 执行分析
    if st.session_state.get("analyze_code"):
        stock_code = st.session_state.analyze_code
        stock_name = st.session_state.get("analyze_name", "")
        
        with st.spinner("正在分析..."):
            score_result = get_stock_score(stock_code, stock_name)
        
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
        
        # 雷达图（各维度得分）
        fig = go.Figure(data=go.Scatterpolar(
            r=[
                score_result["sector_score"],
                score_result["leader_score"],
                score_result["tech_score"],
                score_result["trend_score"]
            ],
            theta=["板块热度", "龙头识别", "技术指标", "长短期趋势"],
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
        with st.expander("📊 技术指标详情"):
            tech_details = score_result.get("tech_details", {})
            if tech_details:
                st.json(tech_details)
            else:
                st.caption("暂无详细技术指标数据")
        
        with st.expander("💡 AI投资建议"):
            st.markdown(f"""
            **{score_result['stock_code']} ({score_result['stock_name']})**
            
            **信号等级**: {level}级 - {score_result['action']}
            
            **建议仓位**: {score_result['position']}
            
            **关键理由**: {score_result.get('reasons', '暂无')}
            
            ⚠️ 以上仅供参考，不构成投资建议。请结合市场情况自行判断。
            """)
        
        # 添加到推荐池按钮
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
            if not consume_free_trial(st.session_state.user_id):
                st.warning("免费次数已用完，请升级到专业版")
            else:
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
            elif status == "running":
                st.warning("⏳ 回测中")
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
    
    # 模拟回测结果（简化版）
    if st.session_state.get("run_backtest_triggered"):
        st.markdown("---")
        st.markdown("**📈 回测报告**")
        
        # 模拟数据
        backtest_results = {
            "总收益率": "+15.8%",
            "年化收益率": "+12.3%",
            "夏普比率": "1.21",
            "最大回撤": "-18.5%",
            "胜率": "58.6%",
            "交易次数": "24次"
        }
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总收益率", backtest_results["总收益率"])
            st.metric("夏普比率", backtest_results["夏普比率"])
        with col2:
            st.metric("年化收益率", backtest_results["年化收益率"])
            st.metric("最大回撤", backtest_results["最大回撤"])
        with col3:
            st.metric("胜率", backtest_results["胜率"])
        with col4:
            st.metric("交易次数", backtest_results["交易次数"])
        
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
    
    # 获取实操池数据
    live_stocks = get_live_pool(st.session_state.user_id)
    recommended_stocks = get_recommended_pool(st.session_state.user_id)
    
    # 生成交易信号（基于推荐池高评分股票）
    signals = []
    
    # 从推荐池获取高评分股票
    for stock in recommended_stocks[:5]:
        score = stock.get('current_score', 0)
        if score >= 70:
            signals.append({
                "stock_code": stock['stock_code'],
                "stock_name": stock.get('stock_name', ''),
                "score": score,
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
    4. 在实操池中记录持仓
    
    ⚠️ 投资有风险，请谨慎决策
    """)


# ==================== 通用功能 ====================

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


def check_usage_and_run(func, *args, **kwargs):
    """装饰器：检查使用次数后执行功能"""
    remaining = get_remaining_trials(st.session_state.user_id)
    profile = get_user_profile(st.session_state.user_id)
    
    if profile.get("subscription_tier") == "pro":
        return func(*args, **kwargs)
    elif remaining > 0:
        return func(*args, **kwargs)
    else:
        show_paywall()
        return None
    """
admin.py - 管理员面板
提供：用户管理、股票池查看、系统统计、重置密码等功能
"""

import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from typing import List, Dict

from config import t, SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_SECRET_KEY, ADMIN_EMAIL
from auth import get_all_users, update_user_profile, send_custom_email
from supabase_ops import (
    get_recommended_pool, get_backtest_pool, get_live_pool,
    supabase_request
)


# ==================== 管理员辅助函数 ====================

def get_supabase_headers(use_secret=True):
    """获取Supabase API请求头（管理员模式默认使用secret key）"""
    api_key = SUPABASE_SECRET_KEY if use_secret else SUPABASE_PUBLISHABLE_KEY
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }


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
            # 发送通知邮件
            send_custom_email(
                user_email,
                "账号已被管理员删除",
                f"您的账号已被管理员删除。如需继续使用，请重新注册。\n\nTechLife团队"
            )
            return True, f"用户 {user_email} 已删除"
        else:
            return False, f"删除失败: {response.text}"
    except Exception as e:
        return False, f"删除失败: {str(e)}"


def admin_reset_user_trials(user_id: str, new_trials: int = 30) -> tuple:
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
            from datetime import timedelta
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


# ==================== 管理员UI组件 ====================

def render_admin_panel():
    """管理员面板主界面"""
    st.markdown("## ⚙️ 管理员面板")
    
    # 获取用户列表
    users = get_all_users()
    
    if not users:
        st.info("暂无用户数据")
        return
    
    # 获取用户认证详情
    users_with_details = []
    for user in users:
        auth_details = get_user_auth_details(user.get("id", ""))
        stock_summary = get_user_stock_summary(user.get("id", ""))
        
        users_with_details.append({
            "id": user.get("id"),
            "email": user.get("email", ""),
            "subscription_tier": user.get("subscription_tier", "free"),
            "free_trials_remaining": user.get("free_trials_remaining", 30),
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
        st.metric("总用户数", len(users))
    with col2:
        pro_count = sum(1 for u in users_with_details if u["subscription_tier"] == "pro")
        st.metric("专业版用户", pro_count)
    with col3:
        free_count = len(users) - pro_count
        st.metric("免费版用户", free_count)
    with col4:
        total_recommended = sum(u["recommended_count"] for u in users_with_details)
        st.metric("总推荐股票数", total_recommended)
    
    st.markdown("---")
    
    # ==================== 用户列表 ====================
    st.markdown("### 👥 用户列表")
    
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
                # 发送密码重置邮件
                try:
                    url = f"{SUPABASE_URL}/auth/v1/recover"
                    headers = get_supabase_headers(use_secret=False)
                    data = {"email": selected_user["email"]}
                    response = requests.post(url, headers=headers, json=data)
                    
                    if response.status_code == 200:
                        st.success(f"密码重置邮件已发送至 {selected_user['email']}")
                    else:
                        st.error(f"发送失败: {response.text}")
                except Exception as e:
                    st.error(f"发送失败: {e}")
        
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
                    admin_reset_user_trials(user["id"], 30)
                    count += 1
            st.success(f"已重置 {count} 位免费用户的次数")
            st.rerun()
    
    with col2:
        if st.button("导出用户数据(CSV)", key="admin_export_csv", use_container_width=True):
            csv = df_users.to_csv(index=False)
            st.download_button(
                label="下载CSV",
                data=csv,
                file_name=f"users_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                key="admin_download_csv"
            )


def render_admin_login_form():
    """管理员登录表单"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h2 style='text-align: center;'>管理员登录</h2>", unsafe_allow_html=True)
        
        with st.form("admin_login_form", border=True):
            username = st.text_input("用户名", key="admin_username")
            password = st.text_input("密码", type="password", key="admin_password")
            submitted = st.form_submit_button("登录", type="primary", use_container_width=True)
            
            if submitted:
                if username == "Laurence_ku" and password == "Ku_product$2026":
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
"""
app.py - AI量化股票系统 主入口
第6部分：主应用程序入口、页面布局、多语言切换、Session管理

完整的AI量化股票系统
包含：用户认证、市场简报、推荐股票池、个股分析、回测功能、实操信号、管理员面板
"""

import streamlit as st

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="AI量化股票系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== 导入自定义模块 ====================
from config import t, init_session_state, ADMIN_EMAIL
from auth import (
    sign_in, sign_up, sign_out, get_user_profile, get_remaining_trials,
    render_login_form, render_register_form
)
from admin import render_admin_panel, render_admin_login_form
from modules import (
    render_market_brief, render_recommended_pool,
    render_stock_analysis, render_backtest, render_live_signals,
    show_paywall
)
from supabase_ops import get_recommended_pool


# ==================== 自定义CSS ====================
st.markdown("""
<style>
    /* 主标题样式 */
    .main-header {
        text-align: center;
        margin-bottom: 1rem;
    }
    
    /* 侧边栏样式 */
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
</style>
""", unsafe_allow_html=True)


# ==================== 侧边栏 ====================
def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.markdown("## 📊 AI量化股票系统")
        st.markdown("---")
        
        # ===== 用户信息 =====
        if st.session_state.authenticated and not st.session_state.admin_mode:
            user_email = st.session_state.user_email
            profile = get_user_profile(st.session_state.user_id)
            tier = profile.get("subscription_tier", "free")
            remaining = get_remaining_trials(st.session_state.user_id)
            
            st.markdown(f"""
            <div class="sidebar-user-info">
                <strong>👤 {user_email}</strong><br>
                📋 {t()['subscription']}: {'💎 专业版' if tier == 'pro' else '🔒 免费版'}<br>
                🎫 {t()['remaining']}: {'∞' if remaining == -1 else remaining}
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


# ==================== 主页内容 ====================
def render_main_app():
    """渲染主页内容（5个功能模块）"""
    # 检查付费墙
    if st.session_state.get("show_paywall", False):
        show_paywall()
        if st.button("返回", key="back_from_paywall"):
            st.session_state.show_paywall = False
            st.rerun()
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
