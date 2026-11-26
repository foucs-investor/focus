# -*- coding: utf-8 -*-
"""
스탠 와인스타인 4단계 주식 분석기 (200일선 기준)
- 200일선 위치 및 기울기 기준 Stage 1~4 판정 (1단계 베이스 / 2단계 업트렌드 / 3단계 탑 / 4단계 다운트렌드)
- 최근 1년 차트 표시 + Stage별 밝은 음영 및 Stage 표기
- 차트 하단 4단 요약 패널 + PNG / CSV 다운로드
- st.session_state 활용으로 다운로드 클릭 시에도 화면 결과 유지
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
    margin-bottom: 14px;
    font-size: 0.88rem;
    line-height: 1.5;
}
.summary-grid {
    display: grid;
    grid-template-columns: 1.35fr 1.25fr 0.85fr 1.15fr;
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
.stop-center {
    height: 100%;
    min-height: 140px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    font-weight: 700;
    color: #1E293B !important;
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


def classify_stages_200ma(df):
    """
    200일 이동평균선(200일선) 기준 주가 사이클 4단계 판정:
    - Stage 2 (상승 국면 / 업트렌드): 200일선이 우상향하고 주가가 200일선 위에서 추세 유지/돌파
    - Stage 4 (쇠퇴 국면 / 다운트렌드): 200일선이 하락세이고 주가가 200일선 아래에서 하락
    - Stage 3 (최정상 지역 / 탑): 상승 이후 200일선 기울기가 둔화·평평해지고 고점권 박스/조정 진입
    - Stage 1 (기초 지역 / 베이스): 하락 이후 200일선 하락이 멈추고 평평해지며 바닥을 다지는 횡보 구간
    """
    close = df["Close"]
    ma200 = df["MA200"]
    # 약 1개월(20거래일) 기준 200일선 기울기 변화율
    slope200 = ma200.diff(20) / ma200.shift(20)
    # 최근 60거래일 고점 대비 현재가 위치
    high60 = close.rolling(60, min_periods=20).max()
    near_top = close >= high60 * 0.93

    # 2단계: 200일선 상승(기울기 > +0.8%) & 주가가 200일선 위
    s2 = (close > ma200) & (slope200 > 0.008)

    # 4단계: 200일선 하락(기울기 < -0.8%) & 주가가 200일선 아래
    s4 = (close < ma200) & (slope200 < -0.008)

    # 3단계: 주가가 200일선 위이거나 근접한 상태에서 200일선 기울기가 둔화/평평해지며 고점권 형성
    s3 = (
        (~s2)
        & (close >= ma200 * 0.97)
        & (slope200.abs() <= 0.008)
        & near_top
    )

    # 1단계: 나머지 중 200일선 하락이 멈추고 평평해지거나 바닥권 횡보/재진입 구간
    s1 = ~(s2 | s3 | s4)

    stage = pd.Series("Stage 1", index=df.index, dtype="object")
    stage.loc[s2] = "Stage 2"
    stage.loc[s3] = "Stage 3"
    stage.loc[s4] = "Stage 4"
    stage.loc[ma200.isna()] = "데이터 축적 중"
    return stage


STAGE_BRIGHT_COLORS = {
    "Stage 1": "rgba(96, 165, 250, 0.24)",
    "Stage 2": "rgba(74, 222, 128, 0.26)",
    "Stage 3": "rgba(250, 204, 21, 0.28)",
    "Stage 4": "rgba(248, 113, 113, 0.25)",
}

STAGE_STYLE = {
    "Stage 1": {
        "pill_bg": "#2563EB",
        "row_bg": "#EFF6FF",
        "mpl_bg": "#DBEAFE",
        "short": "1단계·베이스",
        "desc": "200일선 평평화, 바닥 횡보·물량 매집",
        "redesc": "200일선 평평화, 재바닥 횡보",
    },
    "Stage 2": {
        "pill_bg": "#16A34A",
        "row_bg": "#F0FDF4",
        "mpl_bg": "#DCFCE7",
        "short": "2단계·업트렌드",
        "desc": "200일선 우상향·돌파, 본격 상승 추세",
        "redesc": "200일선 우상향, 상승 추세 지속",
    },
    "Stage 3": {
        "pill_bg": "#CA8A04",
        "row_bg": "#FEFCE8",
        "mpl_bg": "#FEF9C3",
        "short": "3단계·탑",
        "desc": "200일선 기울기 둔화, 고점권 횡보·모멘텀 약화",
        "redesc": "200일선 평평화, 고점권 박스·분배 점검",
    },
    "Stage 4": {
        "pill_bg": "#DC2626",
        "row_bg": "#FEF2F2",
        "mpl_bg": "#FEE2E2",
        "short": "4단계·다운트렌드",
        "desc": "200일선 하락 전환·이탈, 본격 하락 추세",
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


def add_stage_shading_and_labels(fig, df):
    """Plotly 차트에 Stage별 밝은 음영과 구간별 Stage 라벨을 표기합니다."""
    y_max = float(df["High"].max()) if not df.empty else 0.0
    y_min = float(df["Low"].min()) if not df.empty else 0.0
    label_y = y_max - (y_max - y_min) * 0.04 if y_max > y_min else y_max

    for dt0, dt1, stg in _get_segments(df["Stage"]):
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

        if style and (dt1 - dt0).days >= 7:
            mid_dt = dt0 + (dt1 - dt0) / 2
            fig.add_annotation(
                x=mid_dt,
                y=label_y,
                text=f"<b>{stg}</b><br><span style='font-size:10px;'>({style['short']})</span>",
                showarrow=False,
                bgcolor=style["pill_bg"],
                bordercolor=style["pill_bg"],
                borderwidth=1,
                borderpad=3,
                font=dict(color="#FFFFFF", size=11),
                row=1,
                col=1,
            )


def build_chart(data, company_name, code):
    """최근 1년치 기준으로 Stage 음영 및 Stage 표기가 포함된 Plotly 차트를 생성합니다."""
    view_data = slice_recent_1y(data)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        row_heights=[0.62, 0.17, 0.21],
        subplot_titles=(
            "주가 · 200일선(핵심) · 50일선 (최근 1년 / 200일선 기준 Stage 표기)",
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


def make_summary_panel_data(data, summary):
    """200일선 기준 최근 1년 구간 및 최신 기준가 기반 4단 요약 패널 데이터를 생성합니다."""
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
    sup_price = round(float(recent60["Low"].min()), -2)
    buy1_low = round(min(close, ma200) * 0.98, -2)
    buy1_high = round(max(close, ma200) * 1.02, -2)
    buy2_price = round(ma200, -2)
    sell1_price = round(max(close * 1.08, res_price), -2)
    sell2_price = round(sell1_price * 1.12, -2)
    stop_price = round(min(sup_price, ma200 * 0.96), -2)

    if stage == "Stage 2":
        c_title = "2단계 상승 국면 (200일선 기준)"
        c_body = (
            f"주가가 200일선({ma200:,.0f}원) 위에서 우상향 추세를 보이는 상승 국면입니다. "
            f"{sell1_price:,.0f}원 부근 저항과 200일선 지지 여부를 점검하세요."
        )
    elif stage == "Stage 3":
        c_title = "3단계 최정상·고점 점검 구간"
        c_body = (
            f"200일선({ma200:,.0f}원) 기울기가 둔화되며 고점권 횡보 흐름을 보이는 구간입니다. "
            f"{sell1_price:,.0f}원 부근 저항과 추세 둔화 신호를 확인하세요."
        )
    elif stage == "Stage 4":
        c_title = "4단계 쇠퇴·하락 국면"
        c_body = (
            f"주가가 200일선({ma200:,.0f}원) 아래에서 하락세로 돌아선 구간입니다. "
            f"{stop_price:,.0f}원 이탈 여부 및 200일선 재돌파·평평화 여부를 확인하세요."
        )
    else:
        c_title = "1단계 기초·베이스 구간"
        c_body = (
            f"하락 이후 200일선({ma200:,.0f}원)이 평평해지며 바닥을 다지는 구간입니다. "
            f"{buy1_high:,.0f}원 돌파 및 200일선 추세 전환을 확인하세요."
        )

    return {
        "stage_items": stage_items,
        "buy1": f"1차: {buy1_low:,.0f}~{buy1_high:,.0f}원 구간 돌파·지지 확인",
        "buy2": f"2차: 200일선({buy2_price:,.0f}원) 지지 및 추세 확인 시 분할 접근",
        "sell1": f"단기 매도: {sell1_price:,.0f}원 부근 저항 점검",
        "sell2": f"추가 매도: {sell2_price:,.0f}원 부근 목표 점검",
        "stop_text": f"{stop_price:,.0f}원 이탈 시\n(200일선 하향 이탈·추세 약화 확인)",
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
    stop_html = panel["stop_text"].replace("\n", "<br>")

    return (
        f'<div class="summary-grid">'
        f'<div class="summary-card">'
        f'<div class="summary-card-header">단계별 구간 및 근거 (200일선 기준)</div>'
        f'<div class="summary-card-body">{rows_html}</div>'
        f"</div>"
        f'<div class="summary-card">'
        f'<div class="summary-card-header">매수 / 매도 전략</div>'
        f'<div class="summary-card-body">'
        f'<div class="strat-box-buy">'
        f'<span class="strat-badge" style="background-color:#16A34A;">매수 지점</span><br>'
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
        f'<div class="summary-card-header">손절 기준</div>'
        f'<div class="summary-card-body">'
        f'<div class="stop-center">'
        f'<div style="font-size:1.5rem; margin-bottom:4px;">⚠️</div>'
        f"<div>{stop_html}</div>"
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


def build_full_download_image(data, company_name, code, panel):
    """최근 1년치 차트(200일선 기준 Stage 음영 및 표기) + 4단 요약 패널을 합친 PNG를 생성합니다."""
    view_data = slice_recent_1y(data)
    fig = plt.figure(figsize=(18, 12.2), dpi=150, facecolor="#FFFFFF")

    top_ax = fig.add_axes([0.015, 0.94, 0.97, 0.045])
    top_ax.axis("off")
    last_close = float(data["Close"].iloc[-1])
    last_stage = str(data["Stage"].iloc[-1])
    top_ax.text(
        0.0,
        0.5,
        f"{company_name} ({code}) | 현재 {last_stage} (200일선 기준) | 종가 {last_close:,.0f}원 (최근 1년)",
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

    for dt0, dt1, stg in _get_segments(view_data["Stage"]):
        if stg in STAGE_STYLE:
            st_info = STAGE_STYLE[stg]
            bg = st_info["mpl_bg"]
            ax1.axvspan(dt0, dt1, color=bg, alpha=0.75, zorder=0)
            ax2.axvspan(dt0, dt1, color=bg, alpha=0.55, zorder=0)
            ax3.axvspan(dt0, dt1, color=bg, alpha=0.50, zorder=0)

            if (dt1 - dt0).days >= 7:
                mid_dt = dt0 + (dt1 - dt0) / 2
                ax1.text(
                    mid_dt,
                    txt_y,
                    f"{stg}\n({st_info['short']})",
                    ha="center",
                    va="top",
                    fontsize=8.5,
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
        (0.298, 0.255, "매수 / 매도 전략"),
        (0.561, 0.175, "손절 기준"),
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

        elif title == "매수 / 매도 전략":
            cax.text(
                0.04,
                0.69,
                " 매수 지점 ",
                color="#FFFFFF",
                fontsize=8,
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
                fontsize=8,
                va="center",
                transform=cax.transAxes,
            )
            cax.text(
                0.04,
                0.44,
                f"✔ {panel['buy2']}",
                color="#1E293B",
                fontsize=8,
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

        elif title == "손절 기준":
            cax.text(
                0.5,
                0.42,
                f"⚠️\n{panel['stop_text']}",
                color="#1E293B",
                fontsize=9.5,
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
        last_row = analyzed.iloc[-1]
        summary = {
            "stage": str(last_row["Stage"]),
            "close": float(last_row["Close"]),
            "ma200": f'{last_row["MA200"]:,.0f}' if pd.notna(last_row["MA200"]) else "계산 중",
            "ma50": f'{last_row["MA50"]:,.0f}' if pd.notna(last_row["MA50"]) else "계산 중",
            "rs": f'{last_row["MansfieldRS"]:.1f}' if pd.notna(last_row["MansfieldRS"]) else "계산 중",
        }
        fig = build_chart(analyzed, company, code)
        panel = make_summary_panel_data(analyzed, summary)
        full_png = build_full_download_image(analyzed, company, code, panel)
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
    st.title("스탠 와인스타인 4단계 주식 분석기 (200일선 기준)")
    st.caption("200일선 위치·기울기 기준 4단계 판정 | 최근 1년 차트 표시 | Stage별 밝은 음영 및 표기 | 다운로드 시 화면 유지")

    st.markdown(
        """
<div class="cycle-guide-box">
<b>📌 200일선 기준 주가 사이클 4단계 요약</b><br>
• <b>1단계 (기초 지역 / 베이스):</b> 긴 하락 뒤 주가가 횡보하며 바닥을 다지는 구간으로, 200일선이 하락을 멈추고 평평해지며 물량을 모으는 시기입니다.<br>
• <b>2단계 (상승 국면 / 업트렌드):</b> 주가가 200일선을 상향 돌파하며 본격 상승하는 구간으로, 200일선이 우상향으로 전환됩니다.<br>
• <b>3단계 (최정상 지역 / 탑):</b> 상승세가 둔화되며 고점권 박스/조정을 보이는 구간으로, 200일선 기울기가 평평해지고 매수 모멘텀이 약화됩니다.<br>
• <b>4단계 (쇠퇴 국면 / 다운트렌드):</b> 주가가 200일선을 하향 이탈하며 본격 하락하는 구간으로, 200일선이 하락세로 돌아섭니다.
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
        "면책: 본 프로그램은 공개 가격 데이터와 일봉 200일선 규칙을 이용한 교육·참고용 도구입니다. "
        "단계 분류는 자동화된 규칙 기반 근사치이며 투자 판단이나 수익을 보장하지 않습니다."
    )
