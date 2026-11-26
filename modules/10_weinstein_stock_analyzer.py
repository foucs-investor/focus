# -*- coding: utf-8 -*-
"""
스탠 와인스타인 4단계 주식 분석기 (200일선 기준 + Investor A/B + 트레일링 스탑)
- Stage 1(Base), Stage 2(Advancing), Stage 3(Distribution), Stage 4(Declining) 특성 반영
- 200일선 위치·기울기 및 50일선·거래량·Mansfield RS 연계 판정
- 투자자(6~12개월) Stage 2 초기 진입시점: 돌파(Breakout) A 및 눌림목(Pullback) B
- 이익 보호형 트레일링 스탑(Trailing Stop): 초기 손절선, 반등 확인 후 상향, Stage 3 타이트 상향, Stage 4 이탈 신호
- Stage 1 -> Stage 3 직행 차단 및 인접 사이클 흐름 유지
- 차트에는 Stage 2와 Stage 4만 표기 (구간 폭이 좁을 경우 숫자 2, 4만 표기)
- 최근 1년 차트 표시 + Stage 2/4 밝은 음영 + 다운로드 시 화면 유지
"""

from datetime import date, timedelta
import io
import os
import re
import unicodedata

import FinanceDataReader as fdr
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

MENU_NAME = "와인스타인 4단계 분석"
CHART_DISPLAY_STAGES = {"Stage 2", "Stage 4"}


def _configure_korean_font():
    """Windows, macOS, Linux(Streamlit Cloud) 환경에서 한글 폰트를 설정합니다."""
    candidates = [
        "Malgun Gothic",
        "NanumGothic",
        "NanumBarunGothic",
        "AppleGothic",
        "DejaVu Sans",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = name
            break

    linux_paths = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    if plt.rcParams.get("font.family") == "DejaVu Sans":
        for path in linux_paths:
            if os.path.exists(path):
                fm.fontManager.addfont(path)
                prop = fm.FontProperties(fname=path)
                plt.rcParams["font.family"] = prop.get_name()
                break

    plt.rcParams["axes.unicode_minus"] = False


_configure_korean_font()


def _apply_bright_style():
    """전체 화면과 4단 요약 패널을 밝은 톤으로 표시합니다."""
    st.markdown(
        """
<style>
.stApp {
    background-color: #F8FAFC !important;
    color: #1E293B !important;
}
[data-testid="stSidebar"] {
    background-color: #FFFFFF !important;
    border-right: 1px solid #E2E8F0 !important;
}
[data-testid="stSidebar"] * {
    color: #1E293B !important;
}
.stMarkdown, .stText, p, span, label, h1, h2, h3, h4 {
    color: #1E293B !important;
}
.stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
    background-color: #FFFFFF !important;
    color: #1E293B !important;
    border-color: #CBD5E1 !important;
}
.cycle-guide-box {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 12px;
    font-size: 0.88rem;
    line-height: 1.52;
}
.investor-guide-box {
    background-color: #F0FDF4;
    border: 1px solid #86EFAC;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 12px;
    font-size: 0.88rem;
    line-height: 1.52;
}
.trailing-guide-box {
    background-color: #FFFBEB;
    border: 1px solid #FCD34D;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 14px;
    font-size: 0.88rem;
    line-height: 1.52;
}
.summary-grid {
    display: grid;
    grid-template-columns: 1.35fr 1.25fr 0.9fr 1.15fr;
    gap: 10px;
    margin-top: 8px;
    margin-bottom: 16px;
}
@media (max-width: 1100px) {
    .summary-grid {
        grid-template-columns: 1fr 1fr;
    }
}
@media (max-width: 650px) {
    .summary-grid {
        grid-template-columns: 1fr;
    }
}
.summary-card {
    background-color: #FFFFFF;
    border: 1.5px solid #1E3A8A;
    border-radius: 6px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}
.summary-card-header {
    background-color: #1E3A8A;
    color: #FFFFFF !important;
    font-weight: 700;
    font-size: 0.98rem;
    padding: 7px 12px;
}
.summary-card-body {
    padding: 10px 12px;
    font-size: 0.85rem;
    line-height: 1.45;
    color: #1E293B !important;
}
.stage-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 6px;
    border-radius: 4px;
    margin-bottom: 4px;
}
.stage-pill {
    display: inline-block;
    min-width: 56px;
    text-align: center;
    color: #FFFFFF !important;
    font-weight: 700;
    font-size: 0.76rem;
    padding: 2px 6px;
    border-radius: 3px;
}
.strat-badge {
    display: inline-block;
    color: #FFFFFF !important;
    font-weight: 700;
    font-size: 0.8rem;
    padding: 2px 8px;
    border-radius: 3px;
    margin-bottom: 4px;
}
.strat-box-buy {
    background-color: #F0FDF4;
    border-radius: 4px;
    padding: 6px 8px;
    margin-bottom: 8px;
}
.strat-box-sell {
    background-color: #FEF2F2;
    border-radius: 4px;
    padding: 6px 8px;
}
.stop-box {
    height: 100%;
    min-height: 140px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    font-weight: 700;
    color: #1E293B !important;
    gap: 6px;
}
.conclusion-title {
    color: #15803D !important;
    font-weight: 800;
    font-size: 1.02rem;
    margin-bottom: 6px;
}
</style>
""",
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=3600, show_spinner=False)
def load_listing():
    listing = fdr.StockListing("KRX")
    listing = listing.copy()
    listing["Name"] = listing["Name"].astype(str).str.strip()
    listing["Code"] = listing["Code"].astype(str).str.zfill(6)
    return listing


@st.cache_data(ttl=1800, show_spinner=False)
def load_price(code: str, start: str):
    df = fdr.DataReader(code, start)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


@st.cache_data(ttl=1800, show_spinner=False)
def load_benchmark(start: str):
    df = fdr.DataReader("KS11", start)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def normalize_name(s):
    return unicodedata.normalize("NFKC", str(s)).strip().casefold()


def resolve_company(name, listing):
    q = normalize_name(name)
    if q.isdigit():
        found = listing[listing["Code"] == q.zfill(6)]
        if not found.empty:
            return found.iloc[0]
    exact = listing[listing["Name"].map(normalize_name) == q]
    if not exact.empty:
        return exact.iloc[0]
    contains = listing[
        listing["Name"].map(normalize_name).str.contains(re.escape(q), na=False)
    ]
    if len(contains) == 1:
        return contains.iloc[0]
    if len(contains) > 1:
        return None, contains[["Name", "Code"]].head(15)
    return None


def _allowed_next_stages(curr_stage: str):
    """스탠 와인스타인 스테이지 전이 규칙 (Stage 1 -> Stage 3 직행 차단)."""
    if curr_stage == "Stage 1":
        return {"Stage 1", "Stage 2", "Stage 4"}
    if curr_stage == "Stage 2":
        return {"Stage 2", "Stage 3", "Stage 4", "Stage 1"}
    if curr_stage == "Stage 3":
        return {"Stage 3", "Stage 4", "Stage 2"}
    if curr_stage == "Stage 4":
        return {"Stage 4", "Stage 1"}
    return {"Stage 1", "Stage 2", "Stage 3", "Stage 4"}


def _raw_candidate_stage_traderlion_200ma(
    close_val,
    ma200_val,
    ma50_val,
    slope20_val,
    ret10_val,
    vol_ratio_val,
    near_high60_val,
    low60_val,
    prev_stage,
):
    """
    TraderLion Stage Analysis 원칙을 200일선 중심으로 적용한 일차 후보 단계 판정.
    """
    if pd.isna(ma200_val):
        return "데이터 축적 중"

    slope = 0.0 if pd.isna(slope20_val) else float(slope20_val)
    ret10 = 0.0 if pd.isna(ret10_val) else float(ret10_val)
    vol_ratio = 1.0 if pd.isna(vol_ratio_val) else float(vol_ratio_val)
    below_ma50 = pd.notna(ma50_val) and (close_val < float(ma50_val))

    dist_signal = (
        bool(near_high60_val)
        and (slope <= 0.014 or ret10 < -0.015 or (below_ma50 and vol_ratio >= 1.0))
        and close_val >= ma200_val * 0.94
    )
    if prev_stage in {"Stage 2", "Stage 3"} and dist_signal:
        return "Stage 3"

    if close_val > ma200_val and slope >= -0.002:
        return "Stage 2"

    if close_val < ma200_val and slope < -0.003:
        return "Stage 4"

    if prev_stage in {"Stage 2", "Stage 3"} and close_val < ma200_val * 0.985 and ret10 < -0.025:
        return "Stage 4"

    if prev_stage == "Stage 4":
        near_low60 = pd.notna(low60_val) and (close_val <= float(low60_val) * 1.13)
        if slope >= -0.003 and (near_low60 or close_val >= ma200_val * 0.95):
            return "Stage 1"
        return "Stage 4"

    return "Stage 1"


def classify_stages_200ma(df):
    """
    TraderLion 기준 + 200일선 중심 4단계 판정
    - Stage 1 -> Stage 3 직행을 방지하고 인접 사이클 전이를 반영합니다.
    """
    close = df["Close"]
    ma200 = df["MA200"]
    ma50 = df["MA50"]
    slope200 = ma200.diff(20) / ma200.shift(20)
    ret10 = close.pct_change(10)
    vol_avg30 = df["Volume"].rolling(30, min_periods=10).mean()
    vol_ratio = df["Volume"] / vol_avg30.replace(0, np.nan)
    high60 = close.rolling(60, min_periods=20).max()
    low60 = close.rolling(60, min_periods=20).min()
    near_high60 = close >= high60 * 0.84

    raw_stages = []
    prev_stage = None

    for idx in range(len(df)):
        cand = _raw_candidate_stage_traderlion_200ma(
            float(close.iloc[idx]),
            ma200.iloc[idx],
            ma50.iloc[idx],
            slope200.iloc[idx],
            ret10.iloc[idx],
            vol_ratio.iloc[idx],
            near_high60.iloc[idx],
            low60.iloc[idx],
            prev_stage,
        )
        if cand == "데이터 축적 중":
            raw_stages.append(cand)
            continue

        if prev_stage is None or prev_stage == "데이터 축적 중":
            chosen = cand
        else:
            allowed = _allowed_next_stages(prev_stage)
            if cand in allowed:
                chosen = cand
            else:
                if prev_stage == "Stage 1" and cand == "Stage 3":
                    chosen = "Stage 2" if float(close.iloc[idx]) >= float(ma200.iloc[idx]) else "Stage 1"
                else:
                    chosen = prev_stage

        raw_stages.append(chosen)
        prev_stage = chosen

    stage_series = pd.Series(raw_stages, index=df.index, dtype="object")
    segs = _get_segments(stage_series)
    for dt0, dt1, stg in segs:
        if stg == "데이터 축적 중":
            continue
        seg_len = len(stage_series.loc[(stage_series.index >= dt0) & (stage_series.index < dt1)])
        if 0 < seg_len < 5 and dt1 != stage_series.index[-1]:
            next_val = stage_series.loc[stage_series.index >= dt1]
            prev_val = stage_series.loc[stage_series.index < dt0]
            if not next_val.empty:
                target_stg = next_val.iloc[0]
                prev_stg = prev_val.iloc[-1] if not prev_val.empty else target_stg
                if target_stg in _allowed_next_stages(prev_stg):
                    mask = (stage_series.index >= dt0) & (stage_series.index < dt1)
                    stage_series.loc[mask] = target_stg

    return stage_series


STAGE_BRIGHT_COLORS = {
    "Stage 1": "rgba(96, 165, 250, 0.24)",
    "Stage 2": "rgba(74, 222, 128, 0.26)",
    "Stage 3": "rgba(250, 204, 21, 0.28)",
    "Stage 4": "rgba(248, 113, 113, 0.25)",
}

STAGE_STYLE = {
    "Stage 1": {
        "num": "1",
        "pill_bg": "#2563EB",
        "row_bg": "#EFF6FF",
        "mpl_bg": "#DBEAFE",
        "short": "1단계·Base",
        "desc": "200일선 평평화, 저점권 횡보·베이스 형성",
        "redesc": "저점권 횡보, 1단계 베이스 유지",
    },
    "Stage 2": {
        "num": "2",
        "pill_bg": "#16A34A",
        "row_bg": "#F0FDF4",
        "mpl_bg": "#DCFCE7",
        "short": "2단계·Advancing",
        "desc": "200일선 위 상승 추세·돌파 흐름",
        "redesc": "200일선 위 상승 추세 재개",
    },
    "Stage 3": {
        "num": "3",
        "pill_bg": "#CA8A04",
        "row_bg": "#FEFCE8",
        "mpl_bg": "#FEF9C3",
        "short": "3단계·Distribution",
        "desc": "고점권 상승 둔화·횡보/변동성 분배 구간",
        "redesc": "고점권 추세 둔화·분배 점검",
    },
    "Stage 4": {
        "num": "4",
        "pill_bg": "#DC2626",
        "row_bg": "#FEF2F2",
        "mpl_bg": "#FEE2E2",
        "short": "4단계·Declining",
        "desc": "200일선 하향 이탈·고점/저점 하락 추세",
        "redesc": "200일선 하락세 지속, 하락 추세 주의",
    },
}


def prepare_analyzed_data(df, benchmark):
    """전체 기간 데이터를 기준으로 200일선·50일선·Stage(200일선 기준)·Mansfield RS를 계산합니다."""
    data = df.copy()
    data["MA50"] = data["Close"].rolling(50).mean()
    data["MA200"] = data["Close"].rolling(200).mean()
    data["Stage"] = classify_stages_200ma(data)

    if not benchmark.empty and "Close" in benchmark.columns:
        bench_close = benchmark["Close"].reindex(data.index).ffill()
        rel = data["Close"].div(bench_close)
        rs_base = rel.rolling(252, min_periods=60).mean()
        data["MansfieldRS"] = ((rel / rs_base) - 1) * 100
    else:
        data["MansfieldRS"] = np.nan

    return data


def slice_recent_1y(data):
    """최근 1년치 데이터만 추출합니다."""
    if data.empty:
        return data
    cutoff = data.index[-1] - pd.Timedelta(days=365)
    sliced = data.loc[data.index >= cutoff]
    return sliced if not sliced.empty else data


def detect_investor_ab_points(data):
    """
    투자자(Investor, 6~12개월 투자)의 Stage 2 초기 진입시점(200일선 기준):
    - A (Breakout / 돌파): 직전 20일 고점(저항선) 상향 돌파 + 200일선 부근/상방 안착 + 거래량 확인 시점
    - B (Pullback / 눌림목): A 돌파 이후 3~25거래일 내 돌파선/200일선 지지 테스트 및 재반등 확인 시점
    """
    view = slice_recent_1y(data)
    if len(view) < 25:
        return {"a_point": None, "b_point": None, "resistance_level": None}

    close = view["Close"]
    low = view["Low"]
    ma200 = view["MA200"]
    vol = view["Volume"]
    vol_avg20 = vol.rolling(20, min_periods=5).mean()
    prev_high20 = view["High"].shift(1).rolling(20, min_periods=10).max()

    a_idx = None
    breakout_level = None

    for i in range(20, len(view)):
        c_val = float(close.iloc[i])
        res_val = prev_high20.iloc[i]
        m200_val = ma200.iloc[i]
        v_val = float(vol.iloc[i])
        v_avg = float(vol_avg20.iloc[i]) if pd.notna(vol_avg20.iloc[i]) and vol_avg20.iloc[i] > 0 else 0.0

        if pd.isna(res_val) or pd.isna(m200_val):
            continue

        above_200 = c_val >= float(m200_val) * 0.98
        broke_res = c_val > float(res_val) and float(close.iloc[i - 1]) <= float(res_val) * 1.01
        vol_ok = v_avg == 0.0 or v_val >= v_avg * 1.05

        if broke_res and above_200 and vol_ok:
            a_idx = i
            breakout_level = float(res_val)

    if a_idx is None:
        valid_mask = (close > prev_high20) & (close >= ma200 * 0.97)
        valid_positions = np.where(valid_mask.fillna(False).values)[0]
        valid_positions = [p for p in valid_positions if p >= 20]
        if valid_positions:
            a_idx = int(valid_positions[-1])
            breakout_level = float(prev_high20.iloc[a_idx])

    a_point = None
    if a_idx is not None:
        a_point = {
            "date": view.index[a_idx],
            "price": float(close.iloc[a_idx]),
            "low": float(low.iloc[a_idx]),
            "level": float(breakout_level) if breakout_level is not None else float(close.iloc[a_idx]),
        }

    b_point = None
    if a_idx is not None and a_idx + 3 < len(view):
        search_end = min(len(view), a_idx + 30)
        support_ref = max(
            float(breakout_level) * 0.95 if breakout_level is not None else float(close.iloc[a_idx]) * 0.95,
            float(ma200.iloc[a_idx]) * 0.97 if pd.notna(ma200.iloc[a_idx]) else 0.0,
        )
        best_b = None
        for j in range(a_idx + 2, search_end):
            l_val = float(low.iloc[j])
            c_val = float(close.iloc[j])
            m200_j = float(ma200.iloc[j]) if pd.notna(ma200.iloc[j]) else l_val
            near_support = abs(l_val - support_ref) / max(support_ref, 1.0) <= 0.06 or (
                l_val <= m200_j * 1.04 and c_val >= m200_j * 0.97
            )
            rebound_ok = c_val >= float(close.iloc[j - 1]) * 0.99
            if near_support and rebound_ok:
                best_b = j
                break

        if best_b is not None:
            b_point = {
                "date": view.index[best_b],
                "price": float(close.iloc[best_b]),
                "low": float(low.iloc[best_b]),
                "support_ref": support_ref,
            }

    return {
        "a_point": a_point,
        "b_point": b_point,
        "resistance_level": breakout_level,
    }


def compute_trailing_stop_200ma(data, ab_info=None):
    """
    200일선 기준 트레일링 스탑(이익 보호형 매도 전략) 시계열 및 현재 손절선 산출:
    1) 초기 손절선: 돌파(A) 직전 저점/베이스 하단 아래 또는 200일선 하단 기준
    2) 조정 후 반등(이전 하락분 회복) 확인 시 손절선을 200일선 아래(또는 직전 스윙 저점)로 단계적 상향
    3) Stage 3 진입 시 최근 조정 저점(200일선 상단 스윙 저점) 쪽으로 공격적 상향
    4) 손절선 하향 이탈 또는 Stage 4 진입 시 스탑아웃(Stopped out) 표시
    """
    if ab_info is None:
        ab_info = detect_investor_ab_points(data)

    view = slice_recent_1y(data)
    if view.empty:
        return {
            "stop_series": pd.Series(dtype="float64"),
            "current_stop": 0.0,
            "mode_label": "손절선 산출 대기",
            "stopped_out": False,
            "stop_event": None,
        }

    close = view["Close"]
    low = view["Low"]
    high = view["High"]
    ma200 = view["MA200"]
    stages = view["Stage"]

    a_pt = ab_info.get("a_point")
    base_low = float(low.iloc[: min(20, len(low))].min())
    init_stop = round(min(base_low * 0.96, float(ma200.iloc[0]) * 0.95 if pd.notna(ma200.iloc[0]) else base_low * 0.96), -2)
    if a_pt is not None:
        init_stop = round(min(init_stop, a_pt["low"] * 0.96), -2)

    trailing_stop = float(init_stop)
    stop_values = []
    swing_high_since_pullback = float(high.iloc[0])
    pullback_low = None
    in_pullback = False
    mode_label = "초기 손절선 설정"
    stopped_out = False
    stop_event = None

    for i in range(len(view)):
        c_val = float(close.iloc[i])
        l_val = float(low.iloc[i])
        h_val = float(high.iloc[i])
        m200_val = float(ma200.iloc[i]) if pd.notna(ma200.iloc[i]) else c_val
        stg = str(stages.iloc[i])

        # 조정 시작 감지(전고점 대비 6% 이상 조정)
        if h_val > swing_high_since_pullback:
            swing_high_since_pullback = h_val

        if not in_pullback and c_val < swing_high_since_pullback * 0.94:
            in_pullback = True
            pullback_low = l_val
        elif in_pullback and pullback_low is not None and l_val < pullback_low:
            pullback_low = l_val

        # 조정 후 반등해 이전 고점(하락분)을 회복한 것이 확인되면 200일선 아래/최근 저점 기준으로 손절선 상향
        if in_pullback and c_val >= swing_high_since_pullback * 0.99:
            candidate_stop = max(
                trailing_stop,
                round(min(m200_val * 0.98, pullback_low * 0.99 if pullback_low else m200_val * 0.98), -2),
            )
            if candidate_stop > trailing_stop:
                trailing_stop = candidate_stop
                mode_label = "반등 확인 후 손절선 상향(200일선 기준)"
            in_pullback = False
            pullback_low = None
            swing_high_since_pullback = h_val

        # Stage 3 진입 시 최근 조정 저점 / 200일선 위 저점 쪽으로 공격적 상향
        if stg == "Stage 3":
            recent_low_15 = float(low.iloc[max(0, i - 15) : i + 1].min())
            tight_stop = round(max(trailing_stop, min(recent_low_15 * 0.985, m200_val * 1.01)), -2)
            if tight_stop > trailing_stop:
                trailing_stop = tight_stop
                mode_label = "Stage 3 진입 · 타이트 트레일링 상향"

        # Stage 2 진행 중 200일선 상방 안착이 이어지면 200일선 하단 기준 완만 상향
        if stg == "Stage 2" and c_val > m200_val * 1.03:
            gradual_stop = round(max(trailing_stop, m200_val * 0.97), -2)
            if gradual_stop > trailing_stop:
                trailing_stop = gradual_stop
                mode_label = "200일선 상승 추종 트레일링"

        stop_values.append(trailing_stop)

        # 트레일링 스탑 하향 이탈 또는 Stage 4 진입 시 스탑아웃 체크
        if not stopped_out and (c_val < trailing_stop or (stg == "Stage 4" and i > 0 and str(stages.iloc[i - 1]) != "Stage 4")):
            stopped_out = True
            mode_label = "손절 실행 / Stage 4 하락 주의"
            stop_event = {
                "date": view.index[i],
                "price": c_val,
                "stop_price": trailing_stop,
            }

    stop_series = pd.Series(stop_values, index=view.index, dtype="float64")
    return {
        "stop_series": stop_series,
        "current_stop": float(stop_series.iloc[-1]),
        "mode_label": mode_label,
        "stopped_out": stopped_out,
        "stop_event": stop_event,
    }


def _get_segments(stage_series):
    if stage_series.empty:
        return []
    segs = []
    start = stage_series.index[0]
    curr = stage_series.iloc[0]
    for i in range(1, len(stage_series)):
        if stage_series.iloc[i] != curr:
            segs.append((start, stage_series.index[i], curr))
            start = stage_series.index[i]
            curr = stage_series.iloc[i]
    segs.append((start, stage_series.index[-1], curr))
    return segs


def _format_stage_label(stg, style, seg_days, total_days):
    """
    구간 폭이 좁아 라벨이 겹칠 경우 단계 숫자('2', '4')만 표기하고,
    충분히 넓은 구간에서는 'Stage X (설명)' 형태로 표기합니다.
    """
    ratio = seg_days / max(total_days, 1)
    if seg_days < 30 or ratio < 0.09:
        return f"<b>{style['num']}</b>", True
    return f"<b>{stg}</b><br><span style='font-size:10px;'>({style['short']})</span>", False


def add_stage_shading_and_labels(fig, df):
    """Plotly 차트에 Stage 2와 Stage 4의 음영 및 구간 표기(겹침 시 숫자 2, 4만)만 추가합니다."""
    y_max = float(df["High"].max()) if not df.empty else 0.0
    y_min = float(df["Low"].min()) if not df.empty else 0.0
    label_y = y_max - (y_max - y_min) * 0.04 if y_max > y_min else y_max
    total_days = max((df.index[-1] - df.index[0]).days, 1) if len(df) >= 2 else 1

    for dt0, dt1, stg in _get_segments(df["Stage"]):
        if stg not in CHART_DISPLAY_STAGES:
            continue

        color = STAGE_BRIGHT_COLORS.get(stg)
        style = STAGE_STYLE.get(stg)
        if color:
            fig.add_vrect(
                x0=dt0,
                x1=dt1,
                fillcolor=color,
                opacity=1,
                line_width=0,
                layer="below",
                row=1,
                col=1,
            )
            fig.add_vrect(
                x0=dt0,
                x1=dt1,
                fillcolor=color,
                opacity=0.75,
                line_width=0,
                layer="below",
                row=2,
                col=1,
            )
            fig.add_vrect(
                x0=dt0,
                x1=dt1,
                fillcolor=color,
                opacity=0.65,
                line_width=0,
                layer="below",
                row=3,
                col=1,
            )

        seg_days = (dt1 - dt0).days
        if style and seg_days >= 3:
            mid_dt = dt0 + (dt1 - dt0) / 2
            lbl_text, is_num_only = _format_stage_label(stg, style, seg_days, total_days)
            fig.add_annotation(
                x=mid_dt,
                y=label_y,
                text=lbl_text,
                showarrow=False,
                bgcolor=style["pill_bg"],
                bordercolor=style["pill_bg"],
                borderwidth=1,
                borderpad=3 if is_num_only else 4,
                font=dict(color="#FFFFFF", size=12 if is_num_only else 10.5),
                row=1,
                col=1,
            )


def add_investor_ab_and_stop_plotly(fig, ab_info, stop_info):
    """Plotly 차트에 진입시점 A(돌파)/B(눌림목) 및 트레일링 스탑 라인/이탈 신호를 추가합니다."""
    a_pt = ab_info.get("a_point")
    b_pt = ab_info.get("b_point")
    stop_series = stop_info.get("stop_series")
    stop_event = stop_info.get("stop_event")

    if stop_series is not None and not stop_series.empty:
        fig.add_trace(
            go.Scatter(
                x=stop_series.index,
                y=stop_series.values,
                name="트레일링 스탑(손절선)",
                line=dict(color="#D97706", width=1.8, dash="dot"),
            ),
            row=1,
            col=1,
        )

    if a_pt is not None:
        fig.add_trace(
            go.Scatter(
                x=[a_pt["date"]],
                y=[a_pt["low"] * 0.985],
                mode="markers+text",
                name="진입 A (Breakout 돌파)",
                text=["A(돌파)"],
                textposition="bottom center",
                marker=dict(symbol="triangle-up", size=13, color="#059669", line=dict(color="#FFFFFF", width=1)),
                textfont=dict(color="#065F46", size=11, family="Arial Black"),
            ),
            row=1,
            col=1,
        )

    if b_pt is not None:
        fig.add_trace(
            go.Scatter(
                x=[b_pt["date"]],
                y=[b_pt["low"] * 0.985],
                mode="markers+text",
                name="진입 B (Pullback 눌림목)",
                text=["B(눌림목)"],
                textposition="bottom center",
                marker=dict(symbol="diamond", size=11, color="#0284C7", line=dict(color="#FFFFFF", width=1)),
                textfont=dict(color="#075985", size=11, family="Arial Black"),
            ),
            row=1,
            col=1,
        )

    if stop_event is not None:
        fig.add_trace(
            go.Scatter(
                x=[stop_event["date"]],
                y=[stop_event["price"] * 1.02],
                mode="markers+text",
                name="손절 이탈(Stopped Out)",
                text=["STOP"],
                textposition="top center",
                marker=dict(symbol="x", size=12, color="#DC2626", line=dict(color="#FFFFFF", width=1)),
                textfont=dict(color="#B91C1C", size=11, family="Arial Black"),
            ),
            row=1,
            col=1,
        )


def build_chart(data, company_name, code, ab_info=None, stop_info=None):
    """최근 1년치 기준으로 Stage 2·4 음영·표기, A/B 진입시점, 트레일링 스탑을 포함한 Plotly 차트를 생성합니다."""
    view_data = slice_recent_1y(data)
    if ab_info is None:
        ab_info = detect_investor_ab_points(data)
    if stop_info is None:
        stop_info = compute_trailing_stop_200ma(data, ab_info)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        row_heights=[0.62, 0.17, 0.21],
        subplot_titles=(
            "주가 · 200일선(기준) · 50일선 + A(돌파)/B(눌림목) + 트레일링 스탑 (차트 표기: Stage 2 · 4)",
            "거래량",
            "Mansfield 상대강도 (KOSPI 대비)",
        ),
    )
    fig.add_trace(
        go.Candlestick(
            x=view_data.index,
            open=view_data["Open"],
            high=view_data["High"],
            low=view_data["Low"],
            close=view_data["Close"],
            name="주가",
            increasing_line_color="#16a6a0",
            decreasing_line_color="#e45b63",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=view_data.index,
            y=view_data["MA200"],
            name="200일선 (Stage 기준)",
            line=dict(color="#ff334d", width=2.2),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=view_data.index,
            y=view_data["MA50"],
            name="50일선 (참고)",
            line=dict(color="#2474ff", width=1.6),
        ),
        row=1,
        col=1,
    )

    vol_colors = [
        "#16a6a0" if c >= o else "#e45b63"
        for c, o in zip(view_data["Close"], view_data["Open"])
    ]
    fig.add_trace(
        go.Bar(
            x=view_data.index,
            y=view_data["Volume"],
            name="거래량",
            marker_color=vol_colors,
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=view_data.index,
            y=view_data["MansfieldRS"],
            name="Mansfield RS",
            line=dict(color="#333333", width=1.3),
        ),
        row=3,
        col=1,
    )
    fig.add_hline(y=0, line_dash="dash", line_color="#246bff", row=3, col=1)

    add_stage_shading_and_labels(fig, view_data)
    add_investor_ab_and_stop_plotly(fig, ab_info, stop_info)

    last = data.iloc[-1]
    stage_text = str(last["Stage"])

    fig.update_layout(
        title=f"{company_name} ({code}) | 현재 {stage_text} (200일선 기준) | 종가 {last['Close']:,.0f}원",
        height=820,
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        font=dict(color="#1E293B"),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(l=50, r=30, t=95, b=35),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#E2E8F0")
    fig.update_yaxes(showgrid=True, gridcolor="#E2E8F0")
    fig.update_yaxes(title_text="가격 (원)", row=1, col=1)
    fig.update_yaxes(title_text="거래량", row=2, col=1)
    fig.update_yaxes(title_text="RS (%)", row=3, col=1)

    return fig


def make_summary_panel_data(data, summary, ab_info=None, stop_info=None):
    """200일선 기준 최근 1년 구간, A/B 진입시점, 트레일링 스탑 및 최신 기준가 기반 4단 요약 패널 데이터를 생성합니다."""
    if ab_info is None:
        ab_info = detect_investor_ab_points(data)
    if stop_info is None:
        stop_info = compute_trailing_stop_200ma(data, ab_info)

    last = data.iloc[-1]
    close = float(last["Close"])
    ma200 = float(last["MA200"]) if pd.notna(last["MA200"]) else close
    stage = summary["stage"]

    view_data = slice_recent_1y(data)
    segs = [s for s in _get_segments(view_data["Stage"]) if s[2] in STAGE_STYLE]
    stage_items = []
    seen = {}
    for idx_s, (dt0, dt1, stg) in enumerate(segs[-6:], start=1):
        meta = STAGE_STYLE[stg]
        seen[stg] = seen.get(stg, 0) + 1
        desc = meta["desc"] if seen[stg] == 1 else meta["redesc"]
        if idx_s == len(segs[-6:]):
            period_str = f"{dt0.strftime('%Y.%m')} ~ 현재"
        else:
            period_str = f"{dt0.strftime('%Y.%m')} ~ {dt1.strftime('%Y.%m')}"
        stage_items.append(
            {
                "stage": stg,
                "pill_bg": meta["pill_bg"],
                "row_bg": meta["row_bg"],
                "period": period_str,
                "desc": desc,
            }
        )

    recent60 = data.tail(60)
    res_price = round(float(recent60["High"].max()), -2)

    a_pt = ab_info.get("a_point")
    b_pt = ab_info.get("b_point")

    a_price_ref = round(a_pt["price"], -2) if a_pt is not None else round(max(close, ma200 * 1.02), -2)
    b_price_ref = round(b_pt["price"], -2) if b_pt is not None else round(max(ma200, a_price_ref * 0.95), -2)

    sell1_price = round(max(close * 1.08, res_price), -2)
    sell2_price = round(sell1_price * 1.12, -2)
    cur_stop = float(stop_info.get("current_stop", ma200 * 0.96))
    mode_lbl = str(stop_info.get("mode_label", "트레일링 스탑"))
    stopped_out = bool(stop_info.get("stopped_out", False))

    a_label_txt = (
        f"A(돌파 {a_pt['date'].strftime('%m.%d')}): {a_price_ref:,.0f}원 돌파·거래량 확인"
        if a_pt is not None
        else f"A(돌파 목표): {a_price_ref:,.0f}원 돌파·200일선 안착 확인"
    )
    b_label_txt = (
        f"B(눌림목 {b_pt['date'].strftime('%m.%d')}): {b_price_ref:,.0f}원 지지 테스트 확인"
        if b_pt is not None
        else f"B(눌림목 대기): {b_price_ref:,.0f}원 부근 지지/거래량 확인"
    )

    if stage == "Stage 2":
        c_title = "Stage 2 초기·상승 국면 (트레일링 보호 중)"
        c_body = (
            f"200일선({ma200:,.0f}원) 기준 상승 추세 구간입니다. "
            f"A/B 진입 이후 반등 회복 확인에 맞춰 트레일링 손절선({cur_stop:,.0f}원)을 추적 상향하며 대응하세요."
        )
    elif stage == "Stage 3":
        c_title = "Stage 3 고점 분배 구간 (손절선 타이트 상향)"
        c_body = (
            f"고점권 둔화 및 200일선 기울기 평평화 구간입니다. "
            f"최근 조정 저점/200일선 기준 손절선({cur_stop:,.0f}원)을 올려 이익을 보호하세요."
        )
    elif stage == "Stage 4":
        c_title = "Stage 4 하락 추세 구간 (손절·비중 축소 우선)"
        c_body = (
            f"손절선({cur_stop:,.0f}원) 및 200일선({ma200:,.0f}원) 하향 이탈 흐름이 나타난 구간입니다. "
            f"추가 하락 위험이 있으므로 1단계 베이스 전환 전까지 보수적으로 대응하세요."
        )
    else:
        c_title = "Stage 1 바닥 다지기 구간 (Base)"
        c_body = (
            f"200일선({ma200:,.0f}원) 부근 베이스 형성 구간입니다. "
            f"돌파(A: {a_price_ref:,.0f}원)와 눌림목(B: {b_price_ref:,.0f}원) 확인 뒤 초기 손절선({cur_stop:,.0f}원)을 관리하세요."
        )

    stop_status_line = "손절 실행 / Stage 4 진입 주의" if stopped_out else "손절선 유지 중 (이익 보호)"

    return {
        "stage_items": stage_items,
        "buy1": a_label_txt,
        "buy2": b_label_txt,
        "sell1": f"단기 매도: {sell1_price:,.0f}원 부근 저항 점검",
        "sell2": f"추가 매도: {sell2_price:,.0f}원 부근 목표 점검",
        "stop_price_str": f"{cur_stop:,.0f}원 이탈 시",
        "stop_mode_str": mode_lbl,
        "stop_status_str": stop_status_line,
        "stop_text": f"{cur_stop:,.0f}원 이탈 시\n[{mode_lbl}]\n{stop_status_line}",
        "conclusion_title": c_title,
        "conclusion_body": c_body,
    }


def render_summary_panel_html(panel):
    """들여쓰기 공백 없이 HTML 4단 요약 패널을 생성합니다."""
    rows_html = "".join(
        f'<div class="stage-row" style="background-color:{item["row_bg"]};">'
        f'<span class="stage-pill" style="background-color:{item["pill_bg"]};">{item["stage"]}</span>'
        f'<span>{item["period"]} | {item["desc"]}</span>'
        f"</div>"
        for item in panel["stage_items"]
    )

    return (
        f'<div class="summary-grid">'
        f'<div class="summary-card">'
        f'<div class="summary-card-header">단계별 구간 및 근거 (200일선 기준)</div>'
        f'<div class="summary-card-body">{rows_html}</div>'
        f"</div>"
        f'<div class="summary-card">'
        f'<div class="summary-card-header">투자자 진입(A/B) 및 매도 전략</div>'
        f'<div class="summary-card-body">'
        f'<div class="strat-box-buy">'
        f'<span class="strat-badge" style="background-color:#16A34A;">진입시점 (A 돌파 / B 눌림목)</span><br>'
        f'<span style="color:#15803D; font-weight:700;">✔</span> {panel["buy1"]}<br>'
        f'<span style="color:#15803D; font-weight:700;">✔</span> {panel["buy2"]}'
        f"</div>"
        f'<div class="strat-box-sell">'
        f'<span class="strat-badge" style="background-color:#DC2626;">매도 지점</span><br>'
        f'<span style="color:#DC2626; font-weight:700;">✔</span> {panel["sell1"]}<br>'
        f'<span style="color:#DC2626; font-weight:700;">✔</span> {panel["sell2"]}'
        f"</div>"
        f"</div>"
        f"</div>"
        f'<div class="summary-card">'
        f'<div class="summary-card-header">트레일링 스탑 기준</div>'
        f'<div class="summary-card-body">'
        f'<div class="stop-box">'
        f'<div style="font-size:1.45rem;">⚠️</div>'
        f'<div style="color:#B91C1C; font-size:0.96rem;">{panel["stop_price_str"]}</div>'
        f'<div style="font-size:0.78rem; color:#334155;">{panel["stop_mode_str"]}</div>'
        f'<div style="font-size:0.78rem; color:#1E3A8A;">{panel["stop_status_str"]}</div>'
        f"</div>"
        f"</div>"
        f"</div>"
        f'<div class="summary-card">'
        f'<div class="summary-card-header">종합 결론</div>'
        f'<div class="summary-card-body">'
        f'<div class="conclusion-title">✔ {panel["conclusion_title"]}</div>'
        f'<div>{panel["conclusion_body"]}</div>'
        f"</div>"
        f"</div>"
        f"</div>"
    )


def build_full_download_image(data, company_name, code, panel, ab_info=None, stop_info=None):
    """최근 1년치 차트(Stage 2·4 음영·표기·A/B 진입시점·트레일링 스탑) + 4단 요약 패널을 합친 PNG를 생성합니다."""
    view_data = slice_recent_1y(data)
    if ab_info is None:
        ab_info = detect_investor_ab_points(data)
    if stop_info is None:
        stop_info = compute_trailing_stop_200ma(data, ab_info)

    fig = plt.figure(figsize=(18, 12.2), dpi=150, facecolor="#FFFFFF")

    top_ax = fig.add_axes([0.015, 0.94, 0.97, 0.045])
    top_ax.axis("off")
    last_close = float(data["Close"].iloc[-1])
    last_stage = str(data["Stage"].iloc[-1])
    top_ax.text(
        0.0,
        0.5,
        f"{company_name} ({code}) | 현재 {last_stage} | 종가 {last_close:,.0f}원 | 진입 A/B & 트레일링 스탑",
        fontsize=14,
        fontweight="bold",
        color="#1E3A8A",
        va="center",
    )

    gs = fig.add_gridspec(
        nrows=3,
        ncols=1,
        left=0.05,
        right=0.97,
        top=0.91,
        bottom=0.33,
        height_ratios=[4.0, 1.0, 1.4],
        hspace=0.14,
    )
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

    for ax in (ax1, ax2, ax3):
        ax.set_facecolor("#FFFFFF")
        ax.grid(True, linestyle=":", alpha=0.5, color="#CBD5E1")
        ax.tick_params(colors="#334155", labelsize=9)

    y_top = float(view_data["High"].max()) if not view_data.empty else 0.0
    y_bot = float(view_data["Low"].min()) if not view_data.empty else 0.0
    txt_y = y_top - (y_top - y_bot) * 0.05 if y_top > y_bot else y_top
    total_days = max((view_data.index[-1] - view_data.index[0]).days, 1) if len(view_data) >= 2 else 1

    for dt0, dt1, stg in _get_segments(view_data["Stage"]):
        if stg in CHART_DISPLAY_STAGES and stg in STAGE_STYLE:
            st_info = STAGE_STYLE[stg]
            bg = st_info["mpl_bg"]
            ax1.axvspan(dt0, dt1, color=bg, alpha=0.75, zorder=0)
            ax2.axvspan(dt0, dt1, color=bg, alpha=0.55, zorder=0)
            ax3.axvspan(dt0, dt1, color=bg, alpha=0.50, zorder=0)

            seg_days = (dt1 - dt0).days
            if seg_days >= 3:
                mid_dt = dt0 + (dt1 - dt0) / 2
                ratio = seg_days / total_days
                is_num_only = seg_days < 30 or ratio < 0.09
                mpl_lbl = st_info["num"] if is_num_only else f"{stg}\n({st_info['short']})"
                ax1.text(
                    mid_dt,
                    txt_y,
                    mpl_lbl,
                    ha="center",
                    va="top",
                    fontsize=9.5 if is_num_only else 8.0,
                    fontweight="bold",
                    color="#FFFFFF",
                    bbox=dict(
                        boxstyle="round,pad=0.25",
                        facecolor=st_info["pill_bg"],
                        edgecolor="none",
                        alpha=0.92,
                    ),
                    zorder=5,
                )

    dates = view_data.index
    opens = view_data["Open"].values
    highs = view_data["High"].values
    lows = view_data["Low"].values
    closes = view_data["Close"].values
    up = closes >= opens

    ax1.vlines(dates[up], lows[up], highs[up], color="#16A6A0", lw=0.8, zorder=2)
    ax1.vlines(dates[up], opens[up], closes[up], color="#16A6A0", lw=2.0, zorder=3)
    ax1.vlines(dates[~up], lows[~up], highs[~up], color="#E45B63", lw=0.8, zorder=2)
    ax1.vlines(dates[~up], closes[~up], opens[~up], color="#E45B63", lw=2.0, zorder=3)
    ax1.plot(dates, view_data["MA200"], color="#FF334D", lw=2.2, label="200일선 (기준)", zorder=4)
    ax1.plot(dates, view_data["MA50"], color="#2474FF", lw=1.6, label="50일선 (참고)", zorder=4)

    stop_series = stop_info.get("stop_series")
    if stop_series is not None and not stop_series.empty:
        ax1.plot(
            stop_series.index,
            stop_series.values,
            color="#D97706",
            lw=1.7,
            ls="--",
            label="트레일링 스탑",
            zorder=4,
        )

    a_pt = ab_info.get("a_point")
    b_pt = ab_info.get("b_point")
    stop_event = stop_info.get("stop_event")
    y_span = max(y_top - y_bot, 1.0)

    if a_pt is not None:
        ay = a_pt["low"] - y_span * 0.02
        ax1.scatter([a_pt["date"]], [ay], marker="^", s=95, color="#059669", edgecolors="#FFFFFF", linewidths=0.8, zorder=6)
        ax1.text(
            a_pt["date"],
            ay - y_span * 0.015,
            "A(돌파)",
            ha="center",
            va="top",
            fontsize=8.5,
            fontweight="bold",
            color="#065F46",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="#DCFCE7", edgecolor="#059669", lw=0.8),
            zorder=6,
        )

    if b_pt is not None:
        by = b_pt["low"] - y_span * 0.02
        ax1.scatter([b_pt["date"]], [by], marker="D", s=70, color="#0284C7", edgecolors="#FFFFFF", linewidths=0.8, zorder=6)
        ax1.text(
            b_pt["date"],
            by - y_span * 0.015,
            "B(눌림목)",
            ha="center",
            va="top",
            fontsize=8.5,
            fontweight="bold",
            color="#075985",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="#E0F2FE", edgecolor="#0284C7", lw=0.8),
            zorder=6,
        )

    if stop_event is not None:
        sy = stop_event["price"] + y_span * 0.025
        ax1.scatter([stop_event["date"]], [sy], marker="X", s=85, color="#DC2626", edgecolors="#FFFFFF", linewidths=0.8, zorder=6)
        ax1.text(
            stop_event["date"],
            sy + y_span * 0.015,
            "STOP",
            ha="center",
            va="bottom",
            fontsize=8.5,
            fontweight="bold",
            color="#991B1B",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="#FEE2E2", edgecolor="#DC2626", lw=0.8),
            zorder=6,
        )

    ax1.set_ylabel("가격 (원)", fontsize=9.5, color="#1E293B")
    ax1.legend(loc="upper left", frameon=True, facecolor="#FFFFFF", edgecolor="#CBD5E1")

    vol_colors = np.where(up, "#16A6A0", "#E45B63")
    ax2.bar(dates, view_data["Volume"].values, color=vol_colors, width=1.0, alpha=0.85)
    ax2.set_ylabel("거래량", fontsize=9.5, color="#1E293B")

    ax3.plot(dates, view_data["MansfieldRS"], color="#333333", lw=1.3, label="Mansfield RS")
    ax3.axhline(0, color="#246BFF", ls="--", lw=1.0)
    ax3.set_ylabel("RS (%)", fontsize=9.5, color="#1E293B")

    cards = [
        (0.015, 0.275, "단계별 구간 및 근거"),
        (0.298, 0.255, "투자자 진입(A/B) 및 매도 전략"),
        (0.561, 0.175, "트레일링 스탑 기준"),
        (0.744, 0.241, "종합 결론"),
    ]
    for x0, w, title in cards:
        cax = fig.add_axes([x0, 0.025, w, 0.255])
        cax.set_facecolor("#FFFFFF")
        cax.set_xticks([])
        cax.set_yticks([])
        for sp in cax.spines.values():
            sp.set_color("#1E3A8A")
            sp.set_linewidth(1.3)

        cax.add_patch(
            mpatches.Rectangle(
                (0, 0.81), 1, 0.19, facecolor="#1E3A8A", edgecolor="none", transform=cax.transAxes
            )
        )
        cax.text(
            0.03,
            0.905,
            title,
            color="#FFFFFF",
            fontsize=10,
            fontweight="bold",
            va="center",
            transform=cax.transAxes,
        )

        if title == "단계별 구간 및 근거":
            y = 0.71
            for it in panel["stage_items"]:
                cax.add_patch(
                    mpatches.FancyBboxPatch(
                        (0.03, y - 0.045),
                        0.17,
                        0.085,
                        boxstyle="round,pad=0.01",
                        facecolor=it["pill_bg"],
                        edgecolor="none",
                        transform=cax.transAxes,
                    )
                )
                cax.text(
                    0.115,
                    y,
                    it["stage"],
                    color="#FFFFFF",
                    fontsize=7.5,
                    fontweight="bold",
                    ha="center",
                    va="center",
                    transform=cax.transAxes,
                )
                cax.text(
                    0.22,
                    y,
                    f"{it['period']} | {it['desc']}",
                    color="#1E293B",
                    fontsize=7.5,
                    va="center",
                    transform=cax.transAxes,
                )
                y -= 0.125

        elif title == "투자자 진입(A/B) 및 매도 전략":
            cax.text(
                0.04,
                0.69,
                " 진입시점 (A 돌파 / B 눌림목) ",
                color="#FFFFFF",
                fontsize=7.8,
                fontweight="bold",
                va="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="#16A34A", ec="none"),
                transform=cax.transAxes,
            )
            cax.text(
                0.04,
                0.56,
                f"✔ {panel['buy1']}",
                color="#1E293B",
                fontsize=7.8,
                va="center",
                transform=cax.transAxes,
            )
            cax.text(
                0.04,
                0.44,
                f"✔ {panel['buy2']}",
                color="#1E293B",
                fontsize=7.8,
                va="center",
                transform=cax.transAxes,
            )

            cax.text(
                0.04,
                0.29,
                " 매도 지점 ",
                color="#FFFFFF",
                fontsize=8,
                fontweight="bold",
                va="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="#DC2626", ec="none"),
                transform=cax.transAxes,
            )
            cax.text(
                0.04,
                0.16,
                f"✔ {panel['sell1']}",
                color="#1E293B",
                fontsize=8,
                va="center",
                transform=cax.transAxes,
            )
            cax.text(
                0.04,
                0.05,
                f"✔ {panel['sell2']}",
                color="#1E293B",
                fontsize=8,
                va="center",
                transform=cax.transAxes,
            )

        elif title == "트레일링 스탑 기준":
            cax.text(
                0.5,
                0.44,
                f"⚠️\n{panel['stop_text']}",
                color="#1E293B",
                fontsize=8.5,
                fontweight="bold",
                ha="center",
                va="center",
                transform=cax.transAxes,
            )

        elif title == "종합 결론":
            cax.text(
                0.04,
                0.65,
                f"✔ {panel['conclusion_title']}",
                color="#15803D",
                fontsize=10.5,
                fontweight="bold",
                ha="left",
                va="center",
                transform=cax.transAxes,
            )
            cax.text(
                0.04,
                0.34,
                panel["conclusion_body"],
                color="#1E293B",
                fontsize=8.5,
                ha="left",
                va="center",
                wrap=True,
                transform=cax.transAxes,
            )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor="#FFFFFF")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _generate_results(names, years):
    """입력된 종목 리스트에 대한 분석 결과를 생성합니다."""
    with st.spinner("KRX 종목 목록을 불러오는 중..."):
        listing = load_listing()

    start = (date.today() - timedelta(days=365 * years + 120)).isoformat()
    results = []

    for idx, name in enumerate(names, start=1):
        resolved = resolve_company(name, listing)

        if isinstance(resolved, tuple):
            results.append(
                {
                    "idx": idx,
                    "query_name": name,
                    "status": "multiple",
                    "candidates": resolved[1],
                }
            )
            continue
        if resolved is None:
            results.append(
                {
                    "idx": idx,
                    "query_name": name,
                    "status": "not_found",
                }
            )
            continue

        company = resolved["Name"]
        code = resolved["Code"]
        with st.spinner(f"{company} ({code}) 가격 데이터를 불러오는 중..."):
            price = load_price(code, start)
            benchmark = load_benchmark(start)

        if price.empty or not {"Open", "High", "Low", "Close", "Volume"}.issubset(price.columns):
            results.append(
                {
                    "idx": idx,
                    "query_name": name,
                    "company": company,
                    "code": code,
                    "status": "no_price",
                }
            )
            continue

        analyzed = prepare_analyzed_data(price, benchmark)
        ab_info = detect_investor_ab_points(analyzed)
        stop_info = compute_trailing_stop_200ma(analyzed, ab_info)
        last_row = analyzed.iloc[-1]
        summary = {
            "stage": str(last_row["Stage"]),
            "close": float(last_row["Close"]),
            "ma200": f'{last_row["MA200"]:,.0f}' if pd.notna(last_row["MA200"]) else "계산 중",
            "ma50": f'{last_row["MA50"]:,.0f}' if pd.notna(last_row["MA50"]) else "계산 중",
            "rs": f'{last_row["MansfieldRS"]:.1f}' if pd.notna(last_row["MansfieldRS"]) else "계산 중",
        }
        fig = build_chart(analyzed, company, code, ab_info=ab_info, stop_info=stop_info)
        panel = make_summary_panel_data(analyzed, summary, ab_info=ab_info, stop_info=stop_info)
        full_png = build_full_download_image(analyzed, company, code, panel, ab_info=ab_info, stop_info=stop_info)
        csv_bytes = analyzed.to_csv(encoding="utf-8-sig").encode("utf-8-sig")

        results.append(
            {
                "idx": idx,
                "query_name": name,
                "company": company,
                "code": code,
                "status": "ok",
                "summary": summary,
                "fig": fig,
                "panel_html": render_summary_panel_html(panel),
                "full_png": full_png,
                "csv_bytes": csv_bytes,
            }
        )

    return results


def render():
    _apply_bright_style()
    st.title("스탠 와인스타인 4단계 주식 분석기 (200일선 + 진입 A/B + 트레일링 스탑)")
    st.caption("TraderLion + 200일선 기준 4단계 | 차트 표기: Stage 2 · Stage 4 | 투자자 A(돌파)/B(눌림목) | 이익 보호형 트레일링 스탑")

    st.markdown(
        """
<div class="cycle-guide-box">
<b>📌 TraderLion 기준 + 200일선 주가 사이클 4단계 요약</b><br>
• <b>Stage 1 (Base / 기초 다지기):</b> 하락세 진정 후 횡보하며 바닥을 다지는 구간으로, 200일선이 평평해지고 물량 매집이 이루어집니다.<br>
• <b>Stage 2 (Advancing / 상승 추세):</b> 저항 돌파 및 200일선 우상향·상방 안착과 함께 본격 상승 추세가 이어지는 구간입니다. <i>(차트 표기)</i><br>
• <b>Stage 3 (Distribution / 고점 분배):</b> 고점권에서 상승 모멘텀이 둔화되고 변동성·횡보(churning) 및 200일선 기울기 둔화가 나타나는 구간입니다.<br>
• <b>Stage 4 (Declining / 하락 추세):</b> 지지선과 200일선을 하향 이탈하며 저점·고점이 낮아지는 하락 추세 구간입니다. <i>(차트 표기)</i>
</div>
<div class="investor-guide-box">
<b>🎯 투자자(Investor, 6~12개월 투자) 진입시점 — Stage 2 초기 (200일선 기준)</b><br>
• <b>돌파(Breakout) A에 진입:</b> 베이스 상단 저항을 돌파하며 200일선 부근/상방 안착 및 거래량 동반이 확인되는 지점(<b>A</b>)에서 진입합니다.<br>
• <b>눌림목(Pullback) B에 추가 진입:</b> 돌파 이후 200일선·돌파선 지지 테스트 및 재반등 확인 시점(<b>B</b>)에서 추가 매수를 고려합니다.
</div>
<div class="trailing-guide-box">
<b>🛡️ 트레일링 스탑 (이익 보호형 매도 전략 — 200일선 적용)</b><br>
• <b>초기 손절선 설정:</b> 베이스 하단/돌파 직전 저점 아래에 초기 손절선을 둡니다.<br>
• <b>조정 후 반등 회복 시 손절선 상향:</b> 조정이 멈추고 반등이 이전 하락분을 회복해 추세가 살아난 것을 확인한 뒤, 손절선을 <b>200일선 아래</b>로 올려 잡습니다.<br>
• <b>Stage 3 진입 시 공격적 대응:</b> 200일선이 평평해지며 Stage 3 신호가 나타나면 최근 조정 저점 쪽으로 손절선을 바짝 올려 이익을 지키고, 이탈 시(<b>STOP</b> / <b>Stage 4</b>) 매도로 대응합니다.
</div>
""",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("분석 설정")
        years = st.selectbox("지표 산출용 조회 기간", [3, 5, 7, 10], index=1)
        st.caption("200일선과 Mansfield RS를 안정적으로 계산하기 위해 과거 데이터를 함께 불러오며, 차트는 최근 1년치만 표시합니다.")
        st.markdown("---")
        st.caption("중복 기업명은 제거하지 않습니다. 같은 이름을 여러 줄에 입력하면 각각 분석합니다.")

    st.markdown("**기업명을 입력하세요. 한 줄에 하나씩 입력하며, 중복 입력도 가능합니다.**")
    companies_text = st.text_area(
        "기업명 목록",
        value="스튜디오드래곤\n삼성전자\n스튜디오드래곤",
        height=130,
        help="예: 삼성전자 / SK하이닉스 / 삼성전자 (중복 허용)",
    )
    run = st.button("분석 및 차트 생성", type="primary", use_container_width=True)

    if "weinstein_200ma_results" not in st.session_state:
        st.session_state["weinstein_200ma_results"] = None

    if run:
        names = [x.strip() for x in companies_text.splitlines() if x.strip()]
        if not names:
            st.error("기업명을 한 개 이상 입력해 주세요.")
            st.stop()
        st.session_state["weinstein_200ma_results"] = _generate_results(names, years)

    results = st.session_state.get("weinstein_200ma_results")
    if results:
        for item in results:
            idx = item["idx"]
            name = item["query_name"]
            st.divider()
            st.subheader(f"{idx}. {name}")

            status = item["status"]
            if status == "multiple":
                st.warning(
                    f"'{name}'과 일치하는 종목이 여러 개입니다. 아래에서 종목코드를 확인한 뒤 정확한 종목명으로 다시 입력해 주세요."
                )
                st.dataframe(item["candidates"], use_container_width=True)
                continue
            if status == "not_found":
                st.error(
                    f"'{name}' 종목을 KRX 목록에서 찾지 못했습니다. 정식 기업명 또는 6자리 종목코드를 입력해 주세요."
                )
                continue
            if status == "no_price":
                st.error("가격 데이터를 가져오지 못했습니다.")
                continue

            company = item["company"]
            code = item["code"]
            summary = item["summary"]

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("현재 단계 (200일선)", summary["stage"])
            m2.metric("종가", f"{summary['close']:,.0f}원")
            m3.metric("200일선 (기준)", f"{summary['ma200']}원")
            m4.metric("50일선 (참고)", f"{summary['ma50']}원")

            st.plotly_chart(item["fig"], use_container_width=True, key=f"chart_{idx}_{code}")
            st.markdown(item["panel_html"], unsafe_allow_html=True)

            safe = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", company)
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    f"🖼️ {idx}번 {company} 전체 결과 이미지(PNG) 다운로드",
                    data=item["full_png"],
                    file_name=f"{idx:02d}_{safe}_{code}_weinstein_200ma_1y.png",
                    mime="image/png",
                    key=f"png_{idx}_{code}",
                    use_container_width=True,
                )
            with col2:
                st.download_button(
                    f"📄 {idx}번 {company} 분석 데이터(CSV) 다운로드",
                    data=item["csv_bytes"],
                    file_name=f"{idx:02d}_{safe}_{code}_200ma.csv",
                    mime="text/csv",
                    key=f"csv_{idx}_{code}",
                    use_container_width=True,
                )

    st.markdown("---")
    st.caption(
        "면책: 본 프로그램은 공개 가격 데이터와 200일선 기반 규칙을 이용한 교육·참고용 도구입니다. "
        "단계 분류, A/B 진입시점 및 트레일링 스탑 신호는 자동화된 규칙 기반 근사치이며 투자 판단이나 수익을 보장하지 않습니다."
    )
