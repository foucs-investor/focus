# -*- coding: utf-8 -*-
"""
스탠 와인스타인 4단계 주식 분석기 (밝은 리포트 이미지 생성 및 PNG 다운로드 지원)
- MENU_NAME = "와인스타인 4단계 분석"
- app.py의 자동 모듈 로더(MENU_NAME, render)와 호환됩니다.
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

    # 리눅스 나눔폰트 경로 직접 탐색 백업
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


def _apply_bright_theme():
    """화면이 어둡게 보이지 않도록 밝은 라이트 테마 CSS를 적용합니다."""
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
            .bright-info-card {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 10px;
                padding: 14px 18px;
                margin-bottom: 12px;
                box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
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


STAGE_META = {
    "Stage 1": {
        "short": "바닥 형성",
        "re_short": "재바닥 형성",
        "bg": "#EAF2FF",
        "header": "#2563EB",
        "badge": "#2563EB",
        "reason": "50일선·200일선 인근 횡보 및 저점 다지기",
    },
    "Stage 2": {
        "short": "상승 추세",
        "re_short": "상승 추세",
        "bg": "#DCFCE7",
        "header": "#16A34A",
        "badge": "#16A34A",
        "reason": "50일선 상승, 200일선 상향 돌파·추세 유지",
    },
    "Stage 3": {
        "short": "상승 시도",
        "re_short": "상승 시도",
        "bg": "#FEF9C3",
        "header": "#CA8A04",
        "badge": "#CA8A04",
        "reason": "50일선 상향 시도 및 고점권 수급 전환",
    },
    "Stage 4": {
        "short": "하락 추세",
        "re_short": "재하락",
        "bg": "#FEE2E2",
        "header": "#DC2626",
        "badge": "#DC2626",
        "reason": "고점·저점 하락 및 50일선·200일선 약세",
    },
}


def _build_segments(stage_series):
    """연속된 단계 구간 리스트를 생성합니다."""
    if stage_series.empty:
        return []
    segments = []
    start = stage_series.index[0]
    curr = stage_series.iloc[0]
    for i in range(1, len(stage_series)):
        if stage_series.iloc[i] != curr:
            segments.append((start, stage_series.index[i], curr))
            start = stage_series.index[i]
            curr = stage_series.iloc[i]
    segments.append((start, stage_series.index[-1], curr))
    return segments


def _build_strategy_and_segments(data, segments):
    """하단 4단 카드에 들어갈 구간 요약 및 매매/손절/종합 결론을 생성합니다."""
    last = data.iloc[-1]
    close = float(last["Close"])
    ma50 = float(last["MA50"]) if pd.notna(last["MA50"]) else close
    ma200 = float(last["MA200"]) if pd.notna(last["MA200"]) else close
    stage = str(last["Stage"])

    valid_segs = [s for s in segments if s[2] in STAGE_META]
    stage_cards = []
    s1_count = 0
    s4_count = 0
    for dt0, dt1, stg in valid_segs[-6:]:
        meta = STAGE_META[stg]
        if stg == "Stage 1":
            s1_count += 1
            label = "Stage 1" if s1_count == 1 else "Stage 1"
            sub = meta["short"] if s1_count == 1 else meta["re_short"]
        elif stg == "Stage 4":
            s4_count += 1
            label = "Stage 4"
            sub = meta["short"] if s4_count == 1 else meta["re_short"]
        else:
            label = stg
            sub = meta["short"]
        period_str = f"{dt0.strftime('%Y.%m')} ~ {dt1.strftime('%Y.%m')}"
        stage_cards.append((label, sub, meta["badge"], period_str, meta["reason"]))

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
        conclusion_title = "Stage 2 상승·전환 구간"
        conclusion_desc = (
            f"50일선({ma50:,.0f}원)과 200일선({ma200:,.0f}원) 흐름이 우호적입니다. "
            f"{sell1_price:,.0f}원 돌파 및 지지 여부가 핵심입니다."
        )
    elif stage == "Stage 3":
        conclusion_title = "Stage 3 상승 시도·고점 점검 구간"
        conclusion_desc = (
            f"상승 시도가 이어지고 있으나 {sell1_price:,.0f}원 부근 저항과 "
            f"50일선({ma50:,.0f}원) 지지 여부를 함께 확인해야 합니다."
        )
    elif stage == "Stage 4":
        conclusion_title = "Stage 4 하락·재하락 주의 구간"
        conclusion_desc = (
            f"추세 약화 구간으로 {stop_price:,.0f}원 이탈 여부와 "
            f"50일선·200일선 추세 전환 신호를 우선 점검해야 합니다."
        )
    else:
        conclusion_title = "Stage 1 바닥 형성·횡보 구간"
        conclusion_desc = (
            f"바닥 다지기 과정이 진행 중입니다. {buy1_high:,.0f}원 돌파 및 "
            f"200일선({ma200:,.0f}원) 안착 여부를 확인하세요."
        )

    return {
        "stage_cards": stage_cards,
        "buy1": f"{buy1_low:,.0f}~{buy1_high:,.0f}원 구간 진입 및 지지 확인",
        "buy2": f"50일선({buy2_price:,.0f}원) 지지 확인 시 분할 접근",
        "sell1": f"단기 목표: {sell1_price:,.0f}원 부근 저항 확인",
        "sell2": f"추가 목표: {sell2_price:,.0f}원 부근 추세 점검",
        "stop": f"{stop_price:,.0f}원 이탈 시\n(50일선·200일선 하향 이탈 점검)",
        "conclusion_title": conclusion_title,
        "conclusion_desc": conclusion_desc,
    }


def render_report_image(df, benchmark, company_name, code):
    """첨부 이미지 스타일의 밝은 고해상도 분석 리포트 PNG 바이트를 생성합니다."""
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

    segments = _build_segments(data["Stage"])
    info = _build_strategy_and_segments(data, segments)

    fig = plt.figure(figsize=(18, 10.5), dpi=150, facecolor="#FFFFFF")

    # 1. 상단 타이틀 배너
    banner_ax = fig.add_axes([0.01, 0.935, 0.98, 0.055])
    banner_ax.set_facecolor("#1E3A8A")
    banner_ax.set_xticks([])
    banner_ax.set_yticks([])
    for spine in banner_ax.spines.values():
        spine.set_visible(False)

    banner_ax.text(
        0.015,
        0.5,
        f"{company_name} ({code}) - 와인스타인 4단계 분석 (50일선 · 200일선 기준)",
        color="#FFFFFF",
        fontsize=15,
        fontweight="bold",
        va="center",
        ha="left",
    )
    banner_ax.plot([0.74, 0.77], [0.5, 0.5], color="#60A5FA", lw=2.5, transform=banner_ax.transAxes)
    banner_ax.text(
        0.778,
        0.5,
        "50일선",
        color="#FFFFFF",
        fontsize=11,
        fontweight="bold",
        va="center",
        ha="left",
    )
    banner_ax.plot([0.84, 0.87], [0.5, 0.5], color="#EF4444", lw=2.5, transform=banner_ax.transAxes)
    banner_ax.text(
        0.878,
        0.5,
        "200일선",
        color="#FFFFFF",
        fontsize=11,
        fontweight="bold",
        va="center",
        ha="left",
    )

    # 2. 차트 영역 (가격 / 거래량 / Mansfield RS)
    gs = fig.add_gridspec(
        nrows=3,
        ncols=1,
        left=0.015,
        right=0.935,
        top=0.875,
        bottom=0.33,
        height_ratios=[4.2, 1.0, 1.6],
        hspace=0.14,
    )
    ax_price = fig.add_subplot(gs[0])
    ax_vol = fig.add_subplot(gs[1], sharex=ax_price)
    ax_rs = fig.add_subplot(gs[2], sharex=ax_price)

    for ax in (ax_price, ax_vol, ax_rs):
        ax.set_facecolor("#FFFFFF")
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        ax.grid(True, linestyle=":", alpha=0.45, color="#94A3B8")
        ax.tick_params(axis="both", colors="#334155", labelsize=9)
        ax.spines["top"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.spines["right"].set_color("#CBD5E1")
        ax.spines["bottom"].set_color("#CBD5E1")

    # 단계별 배경 음영 및 상단 헤더 뱃지
    valid_segs = [s for s in segments if s[2] in STAGE_META]
    s1_cnt, s4_cnt = 0, 0
    for dt0, dt1, stg in valid_segs:
        meta = STAGE_META[stg]
        ax_price.axvspan(dt0, dt1, color=meta["bg"], alpha=0.55, zorder=0)
        ax_vol.axvspan(dt0, dt1, color=meta["bg"], alpha=0.30, zorder=0)
        ax_rs.axvspan(dt0, dt1, color=meta["bg"], alpha=0.25, zorder=0)

        if stg == "Stage 1":
            s1_cnt += 1
            title_txt = f"Stage 1\n({meta['short'] if s1_cnt == 1 else meta['re_short']})"
        elif stg == "Stage 4":
            s4_cnt += 1
            title_txt = f"Stage 4\n({meta['short'] if s4_cnt == 1 else meta['re_short']})"
        else:
            title_txt = f"{stg}\n({meta['short']})"

        mid_dt = dt0 + (dt1 - dt0) / 2
        ax_price.text(
            mid_dt,
            1.02,
            title_txt,
            transform=ax_price.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=9.5,
            fontweight="bold",
            color="#FFFFFF",
            bbox=dict(
                boxstyle="round,pad=0.35",
                facecolor=meta["header"],
                edgecolor="none",
            ),
        )

    # 캔들스틱 그리기 (성능을 위해 고해상도 라인+고저 바 조합)
    dates = data.index
    opens = data["Open"].values
    highs = data["High"].values
    lows = data["Low"].values
    closes = data["Close"].values
    up_mask = closes >= opens

    ax_price.vlines(dates[up_mask], lows[up_mask], highs[up_mask], color="#16A34A", lw=0.8, zorder=2)
    ax_price.vlines(dates[up_mask], opens[up_mask], closes[up_mask], color="#16A34A", lw=2.0, zorder=3)
    ax_price.vlines(dates[~up_mask], lows[~up_mask], highs[~up_mask], color="#DC2626", lw=0.8, zorder=2)
    ax_price.vlines(dates[~up_mask], closes[~up_mask], opens[~up_mask], color="#DC2626", lw=2.0, zorder=3)

    ax_price.plot(dates, data["MA50"], color="#2563EB", lw=1.8, label="50일선", zorder=4)
    ax_price.plot(dates, data["MA200"], color="#DC2626", lw=2.0, label="200일선", zorder=4)

    # 차트 내 주요 추세 주석 박스
    if len(data) > 60:
        idx_q1 = dates[int(len(data) * 0.12)]
        y_q1 = float(data["Close"].iloc[int(len(data) * 0.12)])
        ax_price.annotate(
            "고점과 저점이\n계속 낮아짐\n(추세 점검 구간)",
            xy=(idx_q1, y_q1),
            xytext=(idx_q1, y_q1 * 1.18),
            ha="center",
            fontsize=8.5,
            fontweight="bold",
            color="#1E293B",
            bbox=dict(boxstyle="round,pad=0.3", fc="#FFFFFF", ec="#94A3B8", alpha=0.92),
            arrowprops=dict(arrowstyle="->", color="#475569", lw=1.2),
        )

        idx_q3 = dates[int(len(data) * 0.45)]
        y_q3 = float(data["MA200"].dropna().iloc[int(len(data["MA200"].dropna()) * 0.45)]) if not data["MA200"].dropna().empty else float(closes.mean())
        ax_price.text(
            idx_q3,
            y_q3 * 1.15,
            "50일선 · 200일선 추세 교차 점검",
            ha="center",
            fontsize=8.5,
            fontweight="bold",
            color="#1E293B",
            bbox=dict(boxstyle="round,pad=0.3", fc="#FFFFFF", ec="#94A3B8", alpha=0.92),
        )

    # 우측 현재가 / 50일선 / 200일선 라벨 뱃지
    last_close = float(closes[-1])
    prev_close = float(closes[-2]) if len(closes) > 1 else last_close
    pct_chg = ((last_close / prev_close) - 1) * 100 if prev_close else 0.0
    last_ma50 = float(data["MA50"].iloc[-1]) if pd.notna(data["MA50"].iloc[-1]) else last_close
    last_ma200 = float(data["MA200"].iloc[-1]) if pd.notna(data["MA200"].iloc[-1]) else last_close

    x_end = dates[-1]
    ax_price.text(
        x_end,
        last_close,
        f" {last_close:,.0f}\n ({pct_chg:+.2f}%)",
        va="center",
        ha="left",
        fontsize=8,
        fontweight="bold",
        color="#FFFFFF",
        bbox=dict(boxstyle="round,pad=0.2", fc="#16A34A" if pct_chg >= 0 else "#DC2626", ec="none"),
        clip_on=False,
    )
    ax_price.text(
        x_end,
        last_ma50,
        f" {last_ma50:,.0f}\n (50일선)",
        va="center",
        ha="left",
        fontsize=7.5,
        fontweight="bold",
        color="#FFFFFF",
        bbox=dict(boxstyle="round,pad=0.18", fc="#2563EB", ec="none"),
        clip_on=False,
    )
    ax_price.text(
        x_end,
        last_ma200,
        f" {last_ma200:,.0f}\n (200일선)",
        va="center",
        ha="left",
        fontsize=7.5,
        fontweight="bold",
        color="#FFFFFF",
        bbox=dict(boxstyle="round,pad=0.18", fc="#DC2626", ec="none"),
        clip_on=False,
    )

    # 거래량 패널
    vol_colors = np.where(up_mask, "#16A34A", "#DC2626")
    ax_vol.bar(dates, data["Volume"].values, color=vol_colors, width=1.0, alpha=0.85)
    ax_vol.text(
        0.01,
        0.82,
        "거래량",
        transform=ax_vol.transAxes,
        fontsize=9,
        fontweight="bold",
        color="#1E293B",
        bbox=dict(boxstyle="round,pad=0.2", fc="#F1F5F9", ec="#CBD5E1"),
    )

    # Mansfield RS 패널
    ax_rs.plot(dates, data["MansfieldRS"], color="#1E293B", lw=1.3)
    ax_rs.axhline(0, color="#2563EB", ls="--", lw=1.0)
    ax_rs.text(
        0.01,
        0.78,
        "Mansfield RS (KOSPI 상대강도 기준)",
        transform=ax_rs.transAxes,
        fontsize=8.5,
        fontweight="bold",
        color="#1E293B",
        bbox=dict(boxstyle="round,pad=0.2", fc="#F1F5F9", ec="#CBD5E1"),
    )

    # 3. 하단 4단 분석 카드 영역
    card_specs = [
        (0.015, 0.245, "단계별 구간 및 근거", "#1E3A8A"),
        (0.262, 0.245, "매수 / 매도 전략", "#1E3A8A"),
        (0.517, 0.185, "손절 기준", "#1E3A8A"),
        (0.712, 0.223, "종합 결론", "#1E3A8A"),
    ]

    for x0, w, card_title, hdr_col in card_specs:
        cax = fig.add_axes([x0, 0.02, w, 0.255])
        cax.set_facecolor("#FFFFFF")
        cax.set_xticks([])
        cax.set_yticks([])
        for sp in cax.spines.values():
            sp.set_color("#CBD5E1")
            sp.set_linewidth(1.0)

        # 카드 헤더 바
        hdr = mpatches.FancyBboxPatch(
            (0.0, 0.80),
            1.0,
            0.20,
            boxstyle="square,pad=0",
            facecolor=hdr_col,
            edgecolor="none",
            transform=cax.transAxes,
        )
        cax.add_patch(hdr)
        cax.text(
            0.04,
            0.90,
            card_title,
            color="#FFFFFF",
            fontsize=10.5,
            fontweight="bold",
            va="center",
            ha="left",
            transform=cax.transAxes,
        )

        if card_title == "단계별 구간 및 근거":
            y_pos = 0.70
            for lbl, sub, bcol, prd, rsn in info["stage_cards"]:
                cax.text(
                    0.04,
                    y_pos,
                    f" {lbl} ",
                    color="#FFFFFF",
                    fontsize=7.5,
                    fontweight="bold",
                    va="center",
                    bbox=dict(boxstyle="round,pad=0.18", fc=bcol, ec="none"),
                )
                cax.text(
                    0.23,
                    y_pos,
                    f"{prd} | {rsn}",
                    color="#1E293B",
                    fontsize=7.5,
                    va="center",
                )
                y_pos -= 0.125

        elif card_title == "매수 / 매도 전략":
            cax.text(
                0.04,
                0.68,
                "매수 지점",
                color="#FFFFFF",
                fontsize=8.5,
                fontweight="bold",
                va="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="#16A34A", ec="none"),
            )
            cax.text(
                0.04,
                0.54,
                f"• 1차: {info['buy1']}",
                color="#1E293B",
                fontsize=8.3,
                va="center",
            )
            cax.text(
                0.04,
                0.42,
                f"• 2차: {info['buy2']}",
                color="#1E293B",
                fontsize=8.3,
                va="center",
            )
            cax.text(
                0.04,
                0.28,
                "매도 지점",
                color="#FFFFFF",
                fontsize=8.5,
                fontweight="bold",
                va="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="#DC2626", ec="none"),
            )
            cax.text(
                0.04,
                0.15,
                f"• {info['sell1']}\n• {info['sell2']}",
                color="#1E293B",
                fontsize=8.2,
                va="center",
            )

        elif card_title == "손절 기준":
            cax.text(
                0.5,
                0.42,
                f"⚠  {info['stop']}",
                color="#1E293B",
                fontsize=9.5,
                fontweight="bold",
                ha="center",
                va="center",
            )

        elif card_title == "종합 결론":
            cax.text(
                0.05,
                0.64,
                f"✔ {info['conclusion_title']}",
                color="#15803D",
                fontsize=11,
                fontweight="bold",
                ha="left",
                va="center",
            )
            cax.text(
                0.05,
                0.34,
                info["conclusion_desc"],
                color="#1E293B",
                fontsize=8.8,
                ha="left",
                va="center",
                wrap=True,
            )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor="#FFFFFF")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue(), data, info


def render():
    _apply_bright_theme()

    st.markdown(
        """
        <div class="bright-info-card">
            <h2 style="margin:0 0 6px 0; color:#1E3A8A;">📈 스탠 와인스타인 4단계 주식 분석기</h2>
            <p style="margin:0; color:#475569; font-size:0.95rem;">
                50일선 · 200일선 · 거래량 · Mansfield 상대강도 기준 | 밝은 리포트 생성 및 PNG 이미지 다운로드 지원
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("분석 설정")
        years = st.selectbox("조회 기간", [3, 5, 7, 10], index=1)
        st.caption("일봉 데이터 기준이며 200일선 계산을 위해 충분한 거래일 데이터가 필요합니다.")
        st.markdown("---")
        st.caption("중복 기업명을 허용하며, 입력한 순서대로 각각 결과를 생성합니다.")

    st.markdown("**기업명을 입력하세요. 한 줄에 하나씩 입력하며, 중복 입력도 가능합니다.**")
    companies_text = st.text_area(
        "기업명 목록",
        value="스튜디오드래곤\n삼성전자",
        height=110,
        help="예: 스튜디오드래곤 / 삼성전자 (중복 입력 가능)",
    )
    run = st.button("분석 및 리포트 이미지 생성", type="primary", use_container_width=True)

    if run:
        names = [x.strip() for x in companies_text.splitlines() if x.strip()]
        if not names:
            st.error("기업명을 한 개 이상 입력해 주세요.")
            st.stop()

        with st.spinner("KRX 종목 목록을 불러오는 중..."):
            listing = load_listing()

        start = (date.today() - timedelta(days=365 * years + 120)).isoformat()

        for idx, name in enumerate(names, start=1):
            st.divider()
            st.subheader(f"{idx}. {name}")
            resolved = resolve_company(name, listing)

            if isinstance(resolved, tuple):
                st.warning(
                    f"'{name}'과 일치하는 종목이 여러 개입니다. 아래에서 종목코드를 확인한 뒤 정확한 종목명을 입력해 주세요."
                )
                st.dataframe(resolved[1], use_container_width=True)
                continue
            if resolved is None:
                st.error(
                    f"'{name}' 종목을 KRX 목록에서 찾지 못했습니다. 정식 기업명 또는 6자리 종목코드를 입력해 주세요."
                )
                continue

            company = resolved["Name"]
            code = resolved["Code"]
            with st.spinner(f"{company} ({code}) 데이터 및 분석 이미지를 생성하는 중..."):
                price = load_price(code, start)
                benchmark = load_benchmark(start)

            if price.empty or not {"Open", "High", "Low", "Close", "Volume"}.issubset(price.columns):
                st.error("가격 데이터를 가져오지 못했습니다.")
                continue

            png_bytes, analyzed, info = render_report_image(price, benchmark, company, code)

            # 화면에 밝은 리포트 이미지 표시
            st.image(
                png_bytes,
                caption=f"{company} ({code}) 와인스타인 4단계 분석 리포트",
                use_container_width=True,
            )

            # 이미지 파일(PNG) 및 CSV 다운로드 버튼
            safe_name = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", company)
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button(
                    label=f"🖼️ {idx}번 {company} 분석 결과 이미지(PNG) 다운로드",
                    data=png_bytes,
                    file_name=f"{idx:02d}_{safe_name}_{code}_weinstein.png",
                    mime="image/png",
                    key=f"png_{idx}_{code}",
                    use_container_width=True,
                )
            with col_dl2:
                st.download_button(
                    label=f"📄 {idx}번 {company} 분석 데이터(CSV) 다운로드",
                    data=analyzed.to_csv(encoding="utf-8-sig").encode("utf-8-sig"),
                    file_name=f"{idx:02d}_{safe_name}_{code}_weinstein.csv",
                    mime="text/csv",
                    key=f"csv_{idx}_{code}",
                    use_container_width=True,
                )

    st.markdown("---")
    st.caption(
        "면책: 본 프로그램은 공개 가격 데이터와 일봉 50/200일선 규칙을 이용한 교육·참고용 도구입니다. "
        "스탠 와인스타인의 원래 주봉 30주선 규칙과는 차이가 있으며 투자 판단 및 수익을 보장하지 않습니다."
    )
