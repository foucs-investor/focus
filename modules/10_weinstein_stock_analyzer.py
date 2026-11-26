# -*- coding: utf-8 -*-
"""
스탠 와인스타인 4단계 주식 분석기
- 기존 Plotly 차트 방식 유지 + Stage별 밝은 색 음영 구분
- 차트 및 다운로드 이미지는 최근 1년치 표시 (이동평균/단계/RS는 전체 기간 기준으로 산출)
- 차트 하단에 4단 요약 패널(단계별 구간 및 근거 / 매수·매도 전략 / 손절 기준 / 종합 결론) 추가
- 전체 결과 PNG 이미지 및 CSV 다운로드 지원
"""

from datetime import timedelta
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


def classify_stages(df):
    """50일선/200일선 및 200일선 기울기 기반 일봉 참고 단계 판정."""
    close = df["Close"]
    ma50 = df["MA50"]
    ma200 = df["MA200"]
    slope = ma200.diff(20) / ma200.shift(20)
    distance = (close / ma200) - 1

    s2 = (close > ma200) & (ma50 > ma200) & (slope > 0.01)
    s4 = (close < ma200) & (ma50 < ma200) & (slope < -0.01)
    s3 = ((ma50 > ma200) & (close < ma50) & (distance > -0.12)) | (
        (close < ma200) & (ma50 >= ma200) & (slope >= -0.01)
    )
    s1 = ~(s2 | s3 | s4)

    stage = pd.Series("Stage 1", index=df.index, dtype="object")
    stage.loc[s2] = "Stage 2"
    stage.loc[s3] = "Stage 3"
    stage.loc[s4] = "Stage 4"
    stage.loc[ma200.isna()] = "데이터 축적 중"
    return stage


# 차트 구간별 밝은 음영 색상 (Plotly & Matplotlib 공용)
STAGE_BRIGHT_COLORS = {
    "Stage 1": "rgba(96, 165, 250, 0.24)",   # 밝은 파랑
    "Stage 2": "rgba(74, 222, 128, 0.26)",   # 밝은 초록
    "Stage 3": "rgba(250, 204, 21, 0.28)",   # 밝은 노랑
    "Stage 4": "rgba(248, 113, 113, 0.25)",  # 밝은 빨강
}

STAGE_STYLE = {
    "Stage 1": {
        "pill_bg": "#2563EB",
        "row_bg": "#EFF6FF",
        "mpl_bg": "#DBEAFE",
        "desc": "50일선 횡보, 바닥 형성",
        "redesc": "저점권 횡보",
    },
    "Stage 2": {
        "pill_bg": "#16A34A",
        "row_bg": "#F0FDF4",
        "mpl_bg": "#DCFCE7",
        "desc": "50일선 상승, 200일선 돌파",
        "redesc": "50일선 상승, 200일선 돌파",
    },
    "Stage 3": {
        "pill_bg": "#CA8A04",
        "row_bg": "#FEFCE8",
        "mpl_bg": "#FEF9C3",
        "desc": "50일선 상승 시도, 200일선 접근",
        "redesc": "50일선 상승 시도, 200일선 접근",
    },
    "Stage 4": {
        "pill_bg": "#DC2626",
        "row_bg": "#FEF2F2",
        "mpl_bg": "#FEE2E2",
        "desc": "고점·저점 하락, 200일선 하락",
        "redesc": "50일선 하락, 재하락",
    },
}


def prepare_analyzed_data(df, benchmark):
    """전체 기간 데이터를 기준으로 지표·단계·Mansfield RS를 계산합니다."""
    data = df.copy()
    data["MA50"] = data["Close"].rolling(50).mean()
    data["MA200"] = data["Close"].rolling(200).mean()
    data["Stage"] = classify_stages(data)

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


def add_stage_shading(fig, df):
    """Plotly 차트의 가격/거래량/RS 패널에 Stage별 밝은 음영을 추가합니다."""
    for dt0, dt1, stg in _get_segments(df["Stage"]):
        color = STAGE_BRIGHT_COLORS.get(stg)
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


def build_chart(data, company_name, code):
    """최근 1년치 기준으로 Plotly 차트를 생성합니다."""
    view_data = slice_recent_1y(data)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        row_heights=[0.62, 0.17, 0.21],
        subplot_titles=(
            "주가 · 50일선 · 200일선 (최근 1년)",
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
            y=view_data["MA50"],
            name="50일선",
            line=dict(color="#2474ff", width=1.8),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=view_data.index,
            y=view_data["MA200"],
            name="200일선",
            line=dict(color="#ff334d", width=2),
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

    add_stage_shading(fig, view_data)

    last = data.iloc[-1]
    stage_text = last["Stage"]
    ma50_text = f'{last["MA50"]:,.0f}' if pd.notna(last["MA50"]) else "계산 중"
    ma200_text = f'{last["MA200"]:,.0f}' if pd.notna(last["MA200"]) else "계산 중"
    rs_text = f'{last["MansfieldRS"]:.1f}' if pd.notna(last["MansfieldRS"]) else "계산 중"

    fig.update_layout(
        title=f"{company_name} ({code}) | 현재 {stage_text} | 종가 {last['Close']:,.0f}원 (최근 1년)",
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

    return fig, {
        "stage": stage_text,
        "close": float(last["Close"]),
        "ma50": ma50_text,
        "ma200": ma200_text,
        "rs": rs_text,
    }


def make_summary_panel_data(data, summary):
    """최근 1년 구간 및 최신 기준가 기반 4단 요약 패널 데이터를 생성합니다."""
    last = data.iloc[-1]
    close = float(last["Close"])
    ma50 = float(last["MA50"]) if pd.notna(last["MA50"]) else close
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
    buy1_low = round(min(close, ma50) * 0.96, -2)
    buy1_high = round(max(close, ma50) * 1.02, -2)
    buy2_price = round(ma50, -2)
    sell1_price = round(max(close * 1.08, res_price), -2)
    sell2_price = round(sell1_price * 1.12, -2)
    stop_price = round(min(sup_price, ma200 * 0.97), -2)

    if stage == "Stage 2":
        c_title = "Stage 2 전환 구간"
        c_body = (
            f"50일선이 200일선을 상향 돌파하며 상승 추세로 전환하는 구간입니다. "
            f"{sell1_price:,.0f}원 돌파 여부가 추가 상승의 핵심입니다."
        )
    elif stage == "Stage 3":
        c_title = "Stage 3 상승 시도 구간"
        c_body = (
            f"50일선 상승 시도 및 고점권 수급 점검 구간입니다. "
            f"{sell1_price:,.0f}원 저항과 50일선({buy2_price:,.0f}원) 지지를 함께 확인하세요."
        )
    elif stage == "Stage 4":
        c_title = "Stage 4 하락 주의 구간"
        c_body = (
            f"추세 약화 및 재하락 점검 구간입니다. "
            f"{stop_price:,.0f}원 이탈 여부와 이동평균선 추세 반전을 확인하세요."
        )
    else:
        c_title = "Stage 1 바닥 형성 구간"
        c_body = (
            f"저점권 횡보 및 바닥 다지기 구간입니다. "
            f"{buy1_high:,.0f}원 돌파와 200일선({ma200:,.0f}원) 안착을 확인하세요."
        )

    return {
        "stage_items": stage_items,
        "buy1": f"1차: {buy1_low:,.0f}~{buy1_high:,.0f}원 돌파 후 안착",
        "buy2": f"2차: 50일선({buy2_price:,.0f}원) 지지 확인 시 추가 매수",
        "sell1": f"단기 매도: {sell1_price:,.0f}원 부근 저항",
        "sell2": f"추가 매도: {sell2_price:,.0f}원 부근",
        "stop_text": f"{stop_price:,.0f}원 이탈 시\n(50일선 하향 이탈 확인)",
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
        f'<div class="summary-card-header">단계별 구간 및 근거</div>'
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
    """최근 1년치 차트(Stage별 밝은 음영) + 4단 요약 패널을 합친 PNG를 생성합니다."""
    view_data = slice_recent_1y(data)
    fig = plt.figure(figsize=(18, 12.2), dpi=150, facecolor="#FFFFFF")

    top_ax = fig.add_axes([0.015, 0.94, 0.97, 0.045])
    top_ax.axis("off")
    last_close = float(data["Close"].iloc[-1])
    last_stage = str(data["Stage"].iloc[-1])
    top_ax.text(
        0.0,
        0.5,
        f"{company_name} ({code}) | 현재 {last_stage} | 종가 {last_close:,.0f}원 (최근 1년)",
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

    for dt0, dt1, stg in _get_segments(view_data["Stage"]):
        if stg in STAGE_STYLE:
            bg = STAGE_STYLE[stg]["mpl_bg"]
            ax1.axvspan(dt0, dt1, color=bg, alpha=0.75, zorder=0)
            ax2.axvspan(dt0, dt1, color=bg, alpha=0.55, zorder=0)
            ax3.axvspan(dt0, dt1, color=bg, alpha=0.50, zorder=0)

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
    ax1.plot(dates, view_data["MA50"], color="#2474FF", lw=1.8, label="50일선", zorder=4)
    ax1.plot(dates, view_data["MA200"], color="#FF334D", lw=2.0, label="200일선", zorder=4)
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


def render():
    _apply_bright_style()
    st.title("스탠 와인스타인 4단계 주식 분석기")
    st.caption("50일선·200일선 기준 | 최근 1년 차트 표시 | Stage별 밝은 음영 | 거래량 | Mansfield 상대강도")

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

    if run:
        names = [x.strip() for x in companies_text.splitlines() if x.strip()]
        if not names:
            st.error("기업명을 한 개 이상 입력해 주세요.")
            st.stop()

        with st.spinner("KRX 종목 목록을 불러오는 중..."):
            listing = load_listing()

        start = (date.today() - timedelta(days=365 * years + 100)).isoformat()

        for idx, name in enumerate(names, start=1):
            st.divider()
            st.subheader(f"{idx}. {name}")
            resolved = resolve_company(name, listing)

            if isinstance(resolved, tuple):
                st.warning(f"'{name}'과 일치하는 종목이 여러 개입니다. 아래에서 종목코드를 확인한 뒤 정확한 종목명으로 다시 입력해 주세요.")
                st.dataframe(resolved[1], use_container_width=True)
                continue
            if resolved is None:
                st.error(f"'{name}' 종목을 KRX 목록에서 찾지 못했습니다. 정식 기업명 또는 6자리 종목코드를 입력해 주세요.")
                continue

            company = resolved["Name"]
            code = resolved["Code"]
            with st.spinner(f"{company} ({code}) 가격 데이터를 불러오는 중..."):
                price = load_price(code, start)
                benchmark = load_benchmark(start)

            if price.empty or not {"Open", "High", "Low", "Close", "Volume"}.issubset(price.columns):
                st.error("가격 데이터를 가져오지 못했습니다.")
                continue

            analyzed = prepare_analyzed_data(price, benchmark)
            last_row = analyzed.iloc[-1]
            summary = {
                "stage": str(last_row["Stage"]),
                "close": float(last_row["Close"]),
                "ma50": f'{last_row["MA50"]:,.0f}' if pd.notna(last_row["MA50"]) else "계산 중",
                "ma200": f'{last_row["MA200"]:,.0f}' if pd.notna(last_row["MA200"]) else "계산 중",
                "rs": f'{last_row["MansfieldRS"]:.1f}' if pd.notna(last_row["MansfieldRS"]) else "계산 중",
            }
            fig, _ = build_chart(analyzed, company, code)
            panel = make_summary_panel_data(analyzed, summary)
            full_png = build_full_download_image(analyzed, company, code, panel)

            # 1) 최근 1년치 Plotly 차트 출력 (Stage별 밝은 음영 포함)
            st.plotly_chart(fig, use_container_width=True)

            # 2) 첨부 이미지의 4단 요약 패널 출력
            st.markdown(render_summary_panel_html(panel), unsafe_allow_html=True)

            # 3) 이미지(PNG) 및 CSV 다운로드 버튼
            safe = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", company)
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    f"🖼️ {idx}번 {company} 전체 결과 이미지(PNG) 다운로드",
                    data=full_png,
                    file_name=f"{idx:02d}_{safe}_{code}_weinstein_1y.png",
                    mime="image/png",
                    key=f"png_{idx}_{code}",
                    use_container_width=True,
                )
            with col2:
                st.download_button(
                    f"📄 {idx}번 {company} 분석 데이터(CSV) 다운로드",
                    data=analyzed.to_csv(encoding="utf-8-sig").encode("utf-8-sig"),
                    file_name=f"{idx:02d}_{safe}_{code}.csv",
                    mime="text/csv",
                    key=f"csv_{idx}_{code}",
                    use_container_width=True,
                )

    st.markdown("---")
    st.caption(
        "면책: 본 프로그램은 공개 가격 데이터와 단순 규칙을 이용한 교육·참고용 도구입니다. "
        "50/200일선 방식은 스탠 와인스타인의 원래 주봉 30주 이동평균 규칙과 다릅니다. "
        "단계 분류는 자동화된 근사치이며 투자 판단이나 수익을 보장하지 않습니다."
    )
