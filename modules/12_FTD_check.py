# modules/12_FTD_check.py
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
import yfinance as yf

# 사이드바 라디오 버튼에 표시될 메뉴명
MENU_NAME = "FTD 체크"
KST = ZoneInfo("Asia/Seoul")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://m.stock.naver.com/",
}

# KRX 목록 조회 실패 시 활용할 주요 한국 상장기업 폴백 목록
FALLBACK_KR_STOCKS: list[dict[str, str]] = [
    {"Code": "005930", "Name": "삼성전자", "Market": "KOSPI"},
    {"Code": "000660", "Name": "SK하이닉스", "Market": "KOSPI"},
    {"Code": "373220", "Name": "LG에너지솔루션", "Market": "KOSPI"},
    {"Code": "207940", "Name": "삼성바이오로직스", "Market": "KOSPI"},
    {"Code": "005380", "Name": "현대차", "Market": "KOSPI"},
    {"Code": "000270", "Name": "기아", "Market": "KOSPI"},
    {"Code": "068270", "Name": "셀트리온", "Market": "KOSPI"},
    {"Code": "035420", "Name": "NAVER", "Market": "KOSPI"},
    {"Code": "035720", "Name": "카카오", "Market": "KOSPI"},
    {"Code": "012450", "Name": "한화에어로스페이스", "Market": "KOSPI"},
    {"Code": "042660", "Name": "한화오션", "Market": "KOSPI"},
    {"Code": "009540", "Name": "HD한국조선해양", "Market": "KOSPI"},
    {"Code": "267260", "Name": "HD현대일렉트릭", "Market": "KOSPI"},
    {"Code": "042700", "Name": "한미반도체", "Market": "KOSPI"},
    {"Code": "196170", "Name": "알테오젠", "Market": "KOSDAQ"},
    {"Code": "247540", "Name": "에코프로비엠", "Market": "KOSDAQ"},
    {"Code": "086520", "Name": "에코프로", "Market": "KOSDAQ"},
    {"Code": "277810", "Name": "레인보우로보틱스", "Market": "KOSDAQ"},
    {"Code": "058470", "Name": "리노공업", "Market": "KOSDAQ"},
    {"Code": "039030", "Name": "이오테크닉스", "Market": "KOSDAQ"},
]

PLOTLY_INTERACTIVE_CONFIG = {
    "scrollZoom": True,
    "displayModeBar": True,
    "doubleClick": "reset",
}


@st.cache_data(ttl=86400, show_spinner=False)
def _load_krx_listing() -> pd.DataFrame:
    """KRX 전체 상장종목(KOSPI/KOSDAQ/KONEX) 마스터 로드"""
    try:
        import FinanceDataReader as fdr

        df = fdr.StockListing("KRX")
        if isinstance(df, pd.DataFrame) and not df.empty:
            cols = {c.lower(): c for c in df.columns}
            code_col = cols.get("code") or cols.get("symbol")
            name_col = cols.get("name")
            market_col = cols.get("market")
            if code_col and name_col:
                out = pd.DataFrame({
                    "Code": df[code_col].astype(str).str.strip().str.zfill(6),
                    "Name": df[name_col].astype(str).str.strip(),
                    "Market": df[market_col].astype(str).str.strip() if market_col else "KRX",
                })
                out = out[out["Code"].str.len() == 6].drop_duplicates(subset=["Code"])
                return out.reset_index(drop=True)
    except Exception:
        pass

    return pd.DataFrame(FALLBACK_KR_STOCKS)


def _search_naver_stock_code(query: str) -> tuple[str, str, str] | None:
    """네이버 자동완성 API로 상장기업명/종목코드 검색"""
    q = (query or "").strip()
    if not q:
        return None
    url = "https://ac.stock.naver.com/ac"
    params = {"q": q, "target": "stock"}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=4)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items") if isinstance(data, dict) else None
        if isinstance(items, list) and items:
            for it in items:
                code = str(it.get("code", "")).strip().upper()
                name = str(it.get("name", "")).strip()
                mkt = str(it.get("typeCode", "") or it.get("market", "")).strip()
                if len(code) == 6 and code.isalnum() and name:
                    return code, name, mkt
    except Exception:
        pass
    return None


def _resolve_company(query: str, listing_df: pd.DataFrame) -> tuple[str, str, str] | None:
    """입력된 기업명 또는 6자리 종목코드로 (종목코드, 기업명, 시장구분) 반환"""
    q = (query or "").strip()
    if not q:
        return None

    if not listing_df.empty:
        exact_name = listing_df[listing_df["Name"] == q]
        if not exact_name.empty:
            row = exact_name.iloc[0]
            return str(row["Code"]), str(row["Name"]), str(row["Market"])

        exact_code = listing_df[listing_df["Code"] == q.zfill(6)]
        if not exact_code.empty:
            row = exact_code.iloc[0]
            return str(row["Code"]), str(row["Name"]), str(row["Market"])

        partial = listing_df[
            listing_df["Name"].str.contains(q, case=False, na=False, regex=False)
        ]
        if not partial.empty:
            row = partial.iloc[0]
            return str(row["Code"]), str(row["Name"]), str(row["Market"])

    naver_found = _search_naver_stock_code(q)
    if naver_found:
        return naver_found

    cleaned = q.split(".")[0].strip().upper()
    if len(cleaned) == 6 and cleaned.isalnum():
        return cleaned, q, "KRX"

    return None


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_stock_ohlcv(code: str, market: str) -> pd.DataFrame:
    """
    한국 상장종목 일봉 OHLCV 데이터 조회.
    200일 SMA 및 주봉 50주 SMA 계산에 충분한 과거 데이터를 포함해 조회합니다.
    """
    df = pd.DataFrame()
    fetch_period = "5y"

    try:
        import FinanceDataReader as fdr

        fdr_df = fdr.DataReader(code)
        if isinstance(fdr_df, pd.DataFrame) and not fdr_df.empty:
            df = fdr_df.copy()
    except Exception:
        pass

    if df.empty:
        suffixes = [".KS", ".KQ"]
        mkt_upper = (market or "").upper()
        if "KQ" in mkt_upper or "KOSDAQ" in mkt_upper:
            suffixes = [".KQ", ".KS"]

        for sfx in suffixes:
            try:
                yf_df = yf.download(f"{code}{sfx}", period=fetch_period, auto_adjust=False, progress=False)
                if isinstance(yf_df, pd.DataFrame) and not yf_df.empty:
                    if isinstance(yf_df.columns, pd.MultiIndex):
                        yf_df.columns = yf_df.columns.get_level_values(0)
                    df = yf_df.copy()
                    break
            except Exception:
                continue

    if df.empty:
        return pd.DataFrame()

    df.index = pd.to_datetime(df.index)
    df = df.loc[~df.index.duplicated(keep="last")].sort_index()

    needed = ["Open", "High", "Low", "Close", "Volume"]
    if not all(col in df.columns for col in needed):
        return pd.DataFrame()

    df = df[needed].dropna(subset=["Close", "Volume"]).copy()
    for c in needed:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Close"]).copy()
    df["Volume"] = df["Volume"].fillna(0.0)
    return df


def _trim_2y_period(df: pd.DataFrame) -> pd.DataFrame:
    """이동평균선(20 EMA, 50 SMA, 200 SMA) 계산 후 최근 2년 구간으로 슬라이싱"""
    if df.empty:
        return df
    last_dt = df.index.max()
    return df.loc[df.index >= (last_dt - pd.DateOffset(years=2))].copy()


def _detect_ftd_signals(
    df: pd.DataFrame,
    pullback_pct: float = -4.0,
    min_ftd_gain_pct: float = 1.5,
    min_day_num: int = 4,
    max_day_num: int = 25,
    vol_mult_prev: float = 1.0,
    vol_mult_avg20: float = 1.0,
) -> pd.DataFrame:
    """
    일봉 OHLCV 기준 이동평균선(20일 EMA, 50일 SMA, 200일 SMA) 및
    Rally Attempt Day 1 / Follow-Through Day(FTD) / FTD 깨짐(실패) 탐지

    [FTD 깨짐(실패) 기준]
    FTD 발생 이후 활성 FTD 추세가 유지되는 동안 다음 중 하나가 발생하면 FTD 깨짐으로 판정:
    1) 종가가 FTD 당일 저가(FTD_Low) 미만으로 마감
    2) 종가가 해당 랠리 구간의 최저가(Rally_Low) 미만으로 마감
    3) FTD 발생 직후 5거래일 이내에 분배일(전일 대비 거래량 증가 + 등락률 <= -0.2%)이 3회 누적
    """
    out = df.copy()
    out["Prev_Close"] = out["Close"].shift(1)
    out["Pct_Change"] = out["Close"].pct_change() * 100.0
    out["Prev_Volume"] = out["Volume"].shift(1)
    out["Vol_MA20"] = out["Volume"].rolling(20, min_periods=5).mean()

    # 이동평균선: 20일 EMA, 50일 SMA, 200일 SMA
    out["EMA_20"] = out["Close"].ewm(span=20, adjust=False).mean()
    out["SMA_50"] = out["Close"].rolling(50, min_periods=10).mean()
    out["SMA_200"] = out["Close"].rolling(200, min_periods=20).mean()

    out["High_20D"] = out["High"].rolling(20, min_periods=5).max().shift(1)
    out["Drawdown_From_High20"] = np.where(
        out["High_20D"] > 0,
        (out["Close"] - out["High_20D"]) / out["High_20D"] * 100.0,
        0.0,
    )

    out["Is_Rally_Day1"] = False
    out["Rally_Day_Count"] = np.nan
    out["Is_FTD"] = False
    out["FTD_Reason"] = ""
    out["Is_FTD_Failed"] = False
    out["FTD_Fail_Reason"] = ""
    out["FTD_Status"] = ""
    out["FTD_Broken_Date"] = ""

    in_rally = False
    rally_start_idx: int | None = None
    rally_low: float | None = None
    ftd_triggered_in_cycle = False

    # 활성 FTD 추적용 상태 변수
    active_ftd_idx: int | None = None
    active_ftd_low: float | None = None
    active_ftd_rally_low: float | None = None
    dist_days_after_ftd = 0

    n = len(out)
    for i in range(1, n):
        row = out.iloc[i]
        prev_row = out.iloc[i - 1]
        pct = float(row["Pct_Change"]) if pd.notna(row["Pct_Change"]) else 0.0
        close_val = float(row["Close"])
        prev_close = float(prev_row["Close"])
        low_val = float(row["Low"])
        vol_val = float(row["Volume"])
        prev_vol = float(prev_row["Prev_Volume"]) if pd.notna(prev_row["Prev_Volume"]) else 0.0
        vol_ma20 = float(row["Vol_MA20"]) if pd.notna(row["Vol_MA20"]) else 0.0
        dd_high20 = float(row["Drawdown_From_High20"]) if pd.notna(row["Drawdown_From_High20"]) else 0.0

        # 1. 현재 활성화된 FTD가 깨졌는지 먼저 점검
        if active_ftd_idx is not None:
            days_from_ftd = i - active_ftd_idx
            if days_from_ftd <= 5 and pct <= -0.2 and prev_vol > 0 and vol_val > prev_vol:
                dist_days_after_ftd += 1

            fail_reason = ""
            if active_ftd_rally_low is not None and close_val < active_ftd_rally_low:
                fail_reason = f"랠리 저점({active_ftd_rally_low:,.0f}원) 종가 이탈"
            elif active_ftd_low is not None and close_val < active_ftd_low:
                fail_reason = f"FTD 당일 저가({active_ftd_low:,.0f}원) 종가 이탈"
            elif days_from_ftd <= 5 and dist_days_after_ftd >= 3:
                fail_reason = "FTD 직후 5거래일 내 분배일 3회 누적"

            if fail_reason:
                ftd_date_str = out.index[active_ftd_idx].strftime("%Y-%m-%d")
                broken_date_str = out.index[i].strftime("%Y-%m-%d")
                out.iloc[i, out.columns.get_loc("Is_FTD_Failed")] = True
                out.iloc[i, out.columns.get_loc("FTD_Fail_Reason")] = (
                    f"{ftd_date_str} FTD 깨짐 ({fail_reason})"
                )
                out.iloc[active_ftd_idx, out.columns.get_loc("FTD_Status")] = f"❌ 깨짐 ({broken_date_str})"
                out.iloc[active_ftd_idx, out.columns.get_loc("FTD_Broken_Date")] = broken_date_str

                # 활성 FTD 종료 및 새 랠리 탐색 가능 상태로 전환
                active_ftd_idx = None
                active_ftd_low = None
                active_ftd_rally_low = None
                dist_days_after_ftd = 0
                in_rally = False
                rally_start_idx = None
                rally_low = None
                ftd_triggered_in_cycle = False

        # 2. 기존 랠리 사이클 진행 중 무효화 또는 만료 체크
        if in_rally and rally_start_idx is not None:
            elapsed = i - rally_start_idx + 1
            if rally_low is not None and low_val < rally_low * 0.94 and not ftd_triggered_in_cycle:
                in_rally = False
                rally_start_idx = None
                rally_low = None
                ftd_triggered_in_cycle = False
            elif elapsed > max_day_num:
                in_rally = False
                rally_start_idx = None
                rally_low = None
                ftd_triggered_in_cycle = False

        # 3. 새로운 랠리 시도 1일차 탐색
        if not in_rally:
            is_pullback_zone = dd_high20 <= pullback_pct
            is_rebound_day = (close_val > prev_close) or (close_val >= float(row["Open"]) and pct >= 0.0)
            if is_pullback_zone and is_rebound_day:
                in_rally = True
                rally_start_idx = i
                rally_low = low_val
                ftd_triggered_in_cycle = False
                out.iloc[i, out.columns.get_loc("Is_Rally_Day1")] = True
                out.iloc[i, out.columns.get_loc("Rally_Day_Count")] = 1

        # 4. 진행 중인 랠리 일차 카운트 및 FTD 판별
        if in_rally and rally_start_idx is not None:
            day_num = i - rally_start_idx + 1
            if rally_low is not None:
                rally_low = min(rally_low, low_val)
            out.iloc[i, out.columns.get_loc("Rally_Day_Count")] = day_num

            vol_ok_prev = (vol_val >= prev_vol * vol_mult_prev) if prev_vol > 0 else True
            vol_ok_avg20 = (vol_val >= vol_ma20 * vol_mult_avg20) if vol_ma20 > 0 else True

            if (
                not ftd_triggered_in_cycle
                and min_day_num <= day_num <= max_day_num
                and pct >= min_ftd_gain_pct
                and close_val > prev_close
                and vol_ok_prev
                and vol_ok_avg20
            ):
                out.iloc[i, out.columns.get_loc("Is_FTD")] = True
                ftd_triggered_in_cycle = True
                vol_ratio_str = f"{vol_val / prev_vol:.2f}배" if prev_vol > 0 else "-"
                out.iloc[i, out.columns.get_loc("FTD_Reason")] = (
                    f"랠리 {day_num}일차 | 등락률 {pct:+.2f}% | 거래량/전일 {vol_ratio_str}"
                )
                out.iloc[i, out.columns.get_loc("FTD_Status")] = "✅ 유효 유지"

                active_ftd_idx = i
                active_ftd_low = low_val
                active_ftd_rally_low = rally_low
                dist_days_after_ftd = 0

    return out


def _build_ftd_chart(df: pd.DataFrame, company_name: str, code: str) -> go.Figure:
    """일봉(최근 2년) + 이동평균선(20 EMA, 50 SMA, 200 SMA) + Day1/FTD/FTD깨짐(X) + 거래량 차트"""
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.72, 0.28],
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="일봉",
            increasing_line_color="#ef4444",
            decreasing_line_color="#3b82f6",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["EMA_20"],
            mode="lines",
            name="20일 EMA",
            line=dict(color="#22c55e", width=1.6),
            hovertemplate="날짜: %{x|%Y-%m-%d}<br>20일 EMA: %{y:,.0f}원<extra></extra>",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["SMA_50"],
            mode="lines",
            name="50일 SMA",
            line=dict(color="#f59e0b", width=1.8),
            hovertemplate="날짜: %{x|%Y-%m-%d}<br>50일 SMA: %{y:,.0f}원<extra></extra>",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["SMA_200"],
            mode="lines",
            name="200일 SMA",
            line=dict(color="#a855f7", width=2.0),
            hovertemplate="날짜: %{x|%Y-%m-%d}<br>200일 SMA: %{y:,.0f}원<extra></extra>",
        ),
        row=1,
        col=1,
    )

    day1_df = df[df["Is_Rally_Day1"]]
    if not day1_df.empty:
        fig.add_trace(
            go.Scatter(
                x=day1_df.index,
                y=day1_df["Low"] * 0.985,
                mode="markers+text",
                name="랠리 1일차 (Day 1)",
                text=["D1"] * len(day1_df),
                textposition="bottom center",
                textfont=dict(color="#38bdf8", size=11),
                marker=dict(symbol="triangle-up", size=11, color="#38bdf8"),
                hovertemplate="날짜: %{x|%Y-%m-%d}<br>랠리 1일차 (Day 1)<br>저가: %{y:,.0f}원<extra></extra>",
            ),
            row=1,
            col=1,
        )

    ftd_df = df[df["Is_FTD"]]
    if not ftd_df.empty:
        fig.add_trace(
            go.Scatter(
                x=ftd_df.index,
                y=ftd_df["High"] * 1.02,
                mode="markers+text",
                name="Follow-Through Day (FTD)",
                text=["FTD"] * len(ftd_df),
                textposition="top center",
                textfont=dict(color="#22c55e", size=12),
                marker=dict(symbol="star", size=15, color="#22c55e"),
                hovertemplate=(
                    "<b>FTD 발생</b><br>"
                    "날짜: %{x|%Y-%m-%d}<br>"
                    "종가: %{customdata[0]:,.0f}원 (%{customdata[1]:+.2f}%)<br>"
                    "%{customdata[2]}<br>"
                    "상태: %{customdata[3]}<extra></extra>"
                ),
                customdata=np.column_stack([
                    ftd_df["Close"].values,
                    ftd_df["Pct_Change"].fillna(0.0).values,
                    ftd_df["FTD_Reason"].fillna("").values,
                    ftd_df["FTD_Status"].fillna("").values,
                ]),
            ),
            row=1,
            col=1,
        )

    # FTD 깨짐(무효화) X 표기
    failed_df = df[df["Is_FTD_Failed"]]
    if not failed_df.empty:
        fig.add_trace(
            go.Scatter(
                x=failed_df.index,
                y=failed_df["High"] * 1.025,
                mode="markers+text",
                name="FTD 깨짐 (실패)",
                text=["FTD 깨짐"] * len(failed_df),
                textposition="top center",
                textfont=dict(color="#f87171", size=11),
                marker=dict(
                    symbol="x",
                    size=14,
                    color="#ef4444",
                    line=dict(width=2.5, color="#ffffff"),
                ),
                hovertemplate=(
                    "<b>❌ FTD 깨짐 (무효화)</b><br>"
                    "날짜: %{x|%Y-%m-%d}<br>"
                    "종가: %{customdata[0]:,.0f}원 (%{customdata[1]:+.2f}%)<br>"
                    "사유: %{customdata[2]}<extra></extra>"
                ),
                customdata=np.column_stack([
                    failed_df["Close"].values,
                    failed_df["Pct_Change"].fillna(0.0).values,
                    failed_df["FTD_Fail_Reason"].fillna("").values,
                ]),
            ),
            row=1,
            col=1,
        )

    vol_colors = [
        "#ef4444" if c >= o else "#3b82f6"
        for o, c in zip(df["Open"], df["Close"])
    ]
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            name="거래량",
            marker_color=vol_colors,
            opacity=0.75,
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=dict(
            text=f"<b>{company_name} ({code}) - 일봉 FTD 및 이동평균선(최근 2년 · 20 EMA / 50 SMA / 200 SMA)</b>",
            font=dict(size=18, color="#f8fafc"),
            x=0.02,
        ),
        dragmode="pan",
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        height=640,
        xaxis_rangeslider_visible=False,
        margin=dict(l=45, r=20, t=55, b=30),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1.0,
            font=dict(color="#e2e8f0", size=11),
        ),
        xaxis2=dict(tickformat="%Y-%m-%d", gridcolor="#1e293b", tickfont=dict(color="#cbd5e1")),
        xaxis=dict(gridcolor="#1e293b", tickfont=dict(color="#cbd5e1")),
        yaxis=dict(gridcolor="#1e293b", tickformat=",", tickfont=dict(color="#cbd5e1")),
        yaxis2=dict(gridcolor="#1e293b", tickformat=",", tickfont=dict(color="#cbd5e1")),
    )
    return fig


def _build_weekly_chart(df_daily: pd.DataFrame, company_name: str, code: str) -> go.Figure:
    """일봉 데이터를 주봉(W-FRI)으로 변환 후 이평선 계산 뒤 최근 2년만 표기하는 차트"""
    weekly = pd.DataFrame({
        "Open": df_daily["Open"].resample("W-FRI").first(),
        "High": df_daily["High"].resample("W-FRI").max(),
        "Low": df_daily["Low"].resample("W-FRI").min(),
        "Close": df_daily["Close"].resample("W-FRI").last(),
        "Volume": df_daily["Volume"].resample("W-FRI").sum(),
    }).dropna(subset=["Open", "High", "Low", "Close"])

    weekly["EMA_20W"] = weekly["Close"].ewm(span=20, adjust=False).mean()
    weekly["SMA_50W"] = weekly["Close"].rolling(50, min_periods=10).mean()

    if not weekly.empty:
        cutoff_2y = weekly.index.max() - pd.DateOffset(years=2)
        weekly = weekly.loc[weekly.index >= cutoff_2y].copy()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.72, 0.28],
    )

    fig.add_trace(
        go.Candlestick(
            x=weekly.index,
            open=weekly["Open"],
            high=weekly["High"],
            low=weekly["Low"],
            close=weekly["Close"],
            name="주봉",
            increasing_line_color="#ef4444",
            decreasing_line_color="#3b82f6",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=weekly.index,
            y=weekly["EMA_20W"],
            mode="lines",
            name="20주 EMA",
            line=dict(color="#22c55e", width=1.8),
            hovertemplate="주봉 날짜: %{x|%Y-%m-%d}<br>20주 EMA: %{y:,.0f}원<extra></extra>",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=weekly.index,
            y=weekly["SMA_50W"],
            mode="lines",
            name="50주 SMA",
            line=dict(color="#f59e0b", width=2.0),
            hovertemplate="주봉 날짜: %{x|%Y-%m-%d}<br>50주 SMA: %{y:,.0f}원<extra></extra>",
        ),
        row=1,
        col=1,
    )

    vol_colors = [
        "#ef4444" if c >= o else "#3b82f6"
        for o, c in zip(weekly["Open"], weekly["Close"])
    ]
    fig.add_trace(
        go.Bar(
            x=weekly.index,
            y=weekly["Volume"],
            name="주간 거래량",
            marker_color=vol_colors,
            opacity=0.75,
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=dict(
            text=f"<b>{company_name} ({code}) - 주봉 차트 (최근 2년 · 20주 EMA / 50주 SMA)</b>",
            font=dict(size=18, color="#f8fafc"),
            x=0.02,
        ),
        dragmode="pan",
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        height=560,
        xaxis_rangeslider_visible=False,
        margin=dict(l=45, r=20, t=55, b=30),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1.0,
            font=dict(color="#e2e8f0", size=11),
        ),
        xaxis2=dict(tickformat="%Y-%m-%d", gridcolor="#1e293b", tickfont=dict(color="#cbd5e1")),
        xaxis=dict(gridcolor="#1e293b", tickfont=dict(color="#cbd5e1")),
        yaxis=dict(gridcolor="#1e293b", tickformat=",", tickfont=dict(color="#cbd5e1")),
        yaxis2=dict(gridcolor="#1e293b", tickformat=",", tickfont=dict(color="#cbd5e1")),
    )
    return fig


def render():
    now = datetime.now(KST)
    run_timestamp = now.strftime("%Y-%m-%d %H:%M:%S (KST)")

    st.markdown("## 🎯 한국 상장기업 Follow-Through Day (FTD) 체크")
    st.caption(
        f"일봉·주봉 최근 2년 기준 | 20일 EMA · 50일 SMA · 200일 SMA | FTD(★) 및 FTD 깨짐(✕) 표기 | 조회 시각: {run_timestamp}"
    )

    listing_df = _load_krx_listing()

    col_in, col_btn = st.columns([7, 2])
    with col_in:
        company_input = st.text_input(
            "한국 상장기업명 (또는 6자리 종목코드)",
            value="삼성전자",
            placeholder="예: 삼성전자, SK하이닉스, 한미반도체, 알테오젠",
            key="ftd_company_input",
        )
    with col_btn:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 조회", use_container_width=True, key="ftd_refresh_btn"):
            st.cache_data.clear()
            st.rerun()

    with st.expander("⚙️ FTD 판별 기준 파라미터 설정", expanded=False):
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            pullback_pct = st.slider("직전 20일 고점 대비 조정(%)", -25.0, -1.0, -4.0, 0.5, key="ftd_pb")
        with p2:
            min_ftd_gain = st.slider("FTD 당일 최소 상승률(%)", 0.5, 8.0, 1.5, 0.1, key="ftd_gain")
        with p3:
            min_day_num = st.number_input("FTD 최소 랠리 일차", min_value=2, max_value=10, value=4, key="ftd_min_d")
        with p4:
            max_day_num = st.number_input("FTD 최대 랠리 일차", min_value=10, max_value=40, value=25, key="ftd_max_d")

        v1, v2 = st.columns(2)
        with v1:
            vol_mult_prev = st.slider("전일 거래량 대비 배수", 0.5, 3.0, 1.0, 0.1, key="ftd_vol_prev")
        with v2:
            vol_mult_avg20 = st.slider("20일 평균 거래량 대비 배수", 0.5, 3.0, 1.0, 0.1, key="ftd_vol_avg20")

    resolved = _resolve_company(company_input, listing_df)
    if not resolved:
        st.warning(f"'{company_input}'에 해당하는 한국 상장기업을 찾지 못했습니다. 기업명 또는 종목코드를 다시 입력해 주세요.")
        return

    code, company_name, market = resolved

    with st.spinner(f"{company_name} ({code}) 일봉 데이터를 불러와 FTD 신호 및 이동평균선을 계산하는 중입니다..."):
        df_ohlcv_full = _fetch_stock_ohlcv(code, market)

    if df_ohlcv_full.empty:
        st.error(f"{company_name} ({code})의 주가 시세 데이터를 가져오지 못했습니다.")
        return

    df_ftd_full = _detect_ftd_signals(
        df_ohlcv_full,
        pullback_pct=float(pullback_pct),
        min_ftd_gain_pct=float(min_ftd_gain),
        min_day_num=int(min_day_num),
        max_day_num=int(max_day_num),
        vol_mult_prev=float(vol_mult_prev),
        vol_mult_avg20=float(vol_mult_avg20),
    )
    df_ftd = _trim_2y_period(df_ftd_full)

    latest = df_ftd.iloc[-1]
    latest_close = float(latest["Close"])
    latest_pct = float(latest["Pct_Change"]) if pd.notna(latest["Pct_Change"]) else 0.0
    ftd_events = df_ftd[df_ftd["Is_FTD"]].copy()
    failed_events = df_ftd[df_ftd["Is_FTD_Failed"]].copy()
    last_ftd_str = ftd_events.index[-1].strftime("%Y-%m-%d") if not ftd_events.empty else "없음"
    last_ftd_status = str(ftd_events["FTD_Status"].iloc[-1]) if not ftd_events.empty else "신호 미발생"

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("종목", f"{company_name} ({code})", market)
    m2.metric("최근 종가", f"{latest_close:,.0f}원", f"{latest_pct:+.2f}%")
    m3.metric("최근 2년 FTD 발생 / 깨짐", f"{len(ftd_events)}회 / {len(failed_events)}회")
    m4.metric("최근 FTD 발생일", last_ftd_str, last_ftd_status)

    ema20_val = float(latest["EMA_20"]) if pd.notna(latest["EMA_20"]) else np.nan
    sma50_val = float(latest["SMA_50"]) if pd.notna(latest["SMA_50"]) else np.nan
    sma200_val = float(latest["SMA_200"]) if pd.notna(latest["SMA_200"]) else np.nan
    ma_c1, ma_c2, ma_c3 = st.columns(3)
    ma_c1.metric("20일 EMA", f"{ema20_val:,.0f}원" if pd.notna(ema20_val) else "-")
    ma_c2.metric("50일 SMA", f"{sma50_val:,.0f}원" if pd.notna(sma50_val) else "-")
    ma_c3.metric("200일 SMA", f"{sma200_val:,.0f}원" if pd.notna(sma200_val) else "-")

    if bool(latest["Is_FTD_Failed"]):
        st.error(f"❌ **오늘({df_ftd.index[-1].strftime('%Y-%m-%d')}) FTD가 깨졌습니다!** — {latest['FTD_Fail_Reason']}")
    elif bool(latest["Is_FTD"]):
        st.success(f"🚀 **오늘({df_ftd.index[-1].strftime('%Y-%m-%d')}) FTD 신호가 발생했습니다!** — {latest['FTD_Reason']}")
    elif pd.notna(latest["Rally_Day_Count"]):
        st.info(
            f"📈 현재 **랠리 시도 {int(latest['Rally_Day_Count'])}일차** 진행 중입니다 "
            f"(FTD 판별 구간: {int(min_day_num)}~{int(max_day_num)}일차)."
        )

    st.plotly_chart(
        _build_ftd_chart(df_ftd, company_name, code),
        use_container_width=True,
        config=PLOTLY_INTERACTIVE_CONFIG,
    )

    st.markdown("### 📋 FTD 발생 이력 (최근 2년)")
    if ftd_events.empty:
        st.info("최근 2년 및 설정한 FTD 조건에 해당하는 발생일이 없습니다. 파라미터를 조정해 다시 확인해 보세요.")
    else:
        history_rows = []
        for dt_idx, r in ftd_events.iloc[::-1].iterrows():
            vol_ratio_prev = (
                float(r["Volume"]) / float(r["Prev_Volume"])
                if pd.notna(r["Prev_Volume"]) and float(r["Prev_Volume"]) > 0
                else np.nan
            )
            vol_ratio_avg20 = (
                float(r["Volume"]) / float(r["Vol_MA20"])
                if pd.notna(r["Vol_MA20"]) and float(r["Vol_MA20"]) > 0
                else np.nan
            )
            history_rows.append({
                "FTD 날짜": dt_idx.strftime("%Y-%m-%d"),
                "FTD 상태": r["FTD_Status"] if r["FTD_Status"] else "✅ 유효 유지",
                "랠리 일차": f"{int(r['Rally_Day_Count'])}일차" if pd.notna(r["Rally_Day_Count"]) else "-",
                "종가(원)": f"{float(r['Close']):,.0f}",
                "당일 등락률": f"{float(r['Pct_Change']):+.2f}%" if pd.notna(r["Pct_Change"]) else "-",
                "20일 EMA": f"{float(r['EMA_20']):,.0f}" if pd.notna(r["EMA_20"]) else "-",
                "50일 SMA": f"{float(r['SMA_50']):,.0f}" if pd.notna(r["SMA_50"]) else "-",
                "200일 SMA": f"{float(r['SMA_200']):,.0f}" if pd.notna(r["SMA_200"]) else "-",
                "전일 대비 거래량": f"{vol_ratio_prev:.2f}배" if pd.notna(vol_ratio_prev) else "-",
                "20일 평균 대비": f"{vol_ratio_avg20:.2f}배" if pd.notna(vol_ratio_avg20) else "-",
            })
        st.dataframe(pd.DataFrame(history_rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("### 📈 주봉 차트 (최근 2년)")
    st.plotly_chart(
        _build_weekly_chart(df_ftd_full, company_name, code),
        use_container_width=True,
        config=PLOTLY_INTERACTIVE_CONFIG,
    )
