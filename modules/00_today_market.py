# modules/00_today_market.py
from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf
from utils import clean_theme_name, download_etf_data, etf_tickers

# 사이드바 라디오 버튼에 표시될 메뉴명
MENU_NAME = "오늘 시장"
KST = ZoneInfo("Asia/Seoul")


def group_theme_category(ticker: str, full_name: str, theme_name: str) -> str:
    """티커, 전체 종목명, 세부 테마명을 기반으로 상위 대분류 테마로 묶어주는 함수"""
    lower_name = (full_name or "").lower()
    lower_theme = (theme_name or "").lower()

    # 시장 지표 자체는 별도의 대분류 명칭 부여
    if ticker in ["^KS11", "^KQ11"]:
        return "시장 지표 (KOSPI/KOSDAQ)"

    # 화장품/음식료 및 K뷰티 통합 그룹화
    if any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["화장품", "k뷰티", "k-뷰티", "뷰티", "푸드"]
    ):
        return "화장품/음식료"

    # 1. 엔터/컨텐츠/인터넷 그룹 (ACE KPOP포커스 포함)
    elif ticker == "475050.KS" or any(
        keyword in lower_name or keyword in lower_theme
        for keyword in [
            "k-pop",
            "kpop",
            "포커스",
            "엔터",
            "미디어",
            "게임",
            "컨텐츠",
            "웹툰",
            "플랫폼",
            "인터넷",
            "포털",
        ]
    ):
        return "엔터/컨텐츠/인터넷"

    # 3. 반도체 그룹
    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["반도체", "소부장", "후공정", "장비", "메모리"]
    ):
        return "반도체"

    # 4. 금융 그룹
    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["증권", "은행", "금융", "보험", "지주사"]
    ):
        return "금융"

    # 5. 바이오/헬스케어 그룹
    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["바이오", "헬스케어", "제약", "의료기기", "의료"]
    ):
        return "바이오/헬스케어"

    # 6. AI/인공지능/소프트웨어 그룹
    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["인공지능", "소프트웨어", "클라우드", "software", "보안", "it"]
    ):
        return "IT·소프트웨어"

    # 7. 조선/방산/우주 그룹
    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["조선", "방산", "우주", "항공"]
    ):
        return "조선/방산"

    # 8. 친환경에너지
    elif any(
        keyword in lower_name or keyword in lower_theme for keyword in ["친환경"]
    ):
        return "친환경에너지"

    # 9. 소비재
    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["생활소비", "경기소비"]
    ):
        return "소비재"

    # 10. AIDC
    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["건설", "설비", "원자력"]
    ):
        return "AIDC"

    # 11. 로봇/자동차/2차전지
    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["로봇", "자동차", "2차전지", "배터리", "전기차", "lfp", "양극재"]
    ):
        return "로봇/자동차/2차전지"

    return theme_name


def _get_latest_index_quote(ticker: str, now_kst: datetime) -> tuple[float, float, str]:
    """실행 시각(KST) 기준으로 지수의 최신가, 등락률(%), 데이터 기준일자를 반환"""
    t_obj = yf.Ticker(ticker)
    hist = t_obj.history(period="5d", interval="1d")
    hist_date_str = ""

    if not hist.empty:
        idx_ts = pd.Timestamp(hist.index[-1])
        if idx_ts.tzinfo is None:
            idx_ts = idx_ts.tz_localize("UTC").tz_convert(KST)
        else:
            idx_ts = idx_ts.tz_convert(KST)
        hist_date_str = idx_ts.strftime("%Y-%m-%d")

    # 장중(09:00~15:35 KST)에는 fast_info의 실시간/최근 체결가를 우선 반영
    is_regular_market_hours = (
        now_kst.weekday() < 5
        and time(9, 0) <= now_kst.time() <= time(15, 45)
    )

    if is_regular_market_hours:
        try:
            fi = t_obj.fast_info
            curr_val = getattr(fi, "last_price", None)
            prev_close = getattr(fi, "previous_close", None)
            if curr_val and prev_close and float(prev_close) != 0:
                curr_f = float(curr_val)
                prev_f = float(prev_close)
                ret = (curr_f - prev_f) / prev_f * 100.0
                return curr_f, ret, now_kst.strftime("%Y-%m-%d")
        except Exception:
            pass

    if len(hist) >= 2:
        curr_f = float(hist["Close"].iloc[-1])
        prev_f = float(hist["Close"].iloc[-2])
        ret = ((curr_f - prev_f) / prev_f * 100.0) if prev_f != 0 else 0.0
        return curr_f, ret, hist_date_str
    elif len(hist) == 1:
        curr_f = float(hist["Close"].iloc[-1])
        return curr_f, 0.0, hist_date_str

    return 0.0, 0.0, now_kst.strftime("%Y-%m-%d")


def _get_etf_latest_returns(
    etf_data: pd.DataFrame, tickers: list[str], now_kst: datetime
) -> tuple[pd.Series, str]:
    """실행 시각(KST) 기준으로 ETF 등락률(%)과 데이터 기준일자를 반환"""
    data_date_str = ""
    if not etf_data.empty:
        last_idx = pd.Timestamp(etf_data.index[-1])
        if last_idx.tzinfo is None:
            last_idx = last_idx.tz_localize("UTC").tz_convert(KST)
        else:
            last_idx = last_idx.tz_convert(KST)
        data_date_str = last_idx.strftime("%Y-%m-%d")

    is_regular_market_hours = (
        now_kst.weekday() < 5
        and time(9, 0) <= now_kst.time() <= time(15, 45)
    )

    # 일봉 데이터에 이미 오늘 날짜 봉이 포함된 경우 vs 장중 실시간가 반영이 필요한 경우
    returns_map: dict[str, float] = {}

    if len(etf_data) >= 2:
        etf_pct = etf_data.pct_change() * 100.0
        latest_row = etf_pct.iloc[-1]
        for col in etf_data.columns:
            if pd.notna(latest_row.get(col)):
                returns_map[col] = float(latest_row[col])

    # 장중에는 ETF 실시간 체결가(fast_info.last_price) 기준으로 당일 등락률 갱신 시도
    if is_regular_market_hours and data_date_str != now_kst.strftime("%Y-%m-%d"):
        updated_any = False
        for ticker in tickers:
            if ticker not in etf_data.columns or len(etf_data[ticker].dropna()) == 0:
                continue
            ref_prev_close = float(etf_data[ticker].dropna().iloc[-1])
            try:
                fi = yf.Ticker(ticker).fast_info
                last_p = getattr(fi, "last_price", None)
                if last_p and float(last_p) > 0 and ref_prev_close > 0:
                    returns_map[ticker] = (float(last_p) - ref_prev_close) / ref_prev_close * 100.0
                    updated_any = True
            except Exception:
                continue
        if updated_any:
            data_date_str = now_kst.strftime("%Y-%m-%d")

    return pd.Series(returns_map, dtype=float), (data_date_str or now_kst.strftime("%Y-%m-%d"))


def render():
    # 실행 시점의 한국 표준시(Asia/Seoul) 기준 날짜/시각
    now = datetime.now(KST)
    run_date_str = now.strftime("%Y-%m-%d")
    run_time_str = now.strftime("%H:%M:%S")
    run_timestamp = f"{run_date_str} {run_time_str} (KST)"

    with st.spinner(f"{run_timestamp} 기준 최신 시장 및 ETF 시세 데이터를 가져오는 중입니다..."):
        # 1. 기존 ETF 데이터 다운로드
        df_raw, name_mapping = download_etf_data(etf_tickers, period="1mo")
        etf_data = df_raw.ffill().bfill()
        etf_data.index = pd.to_datetime(etf_data.index)

        # 2. 코스피(^KS11), 코스닥(^KQ11) 지수 데이터 조회
        index_tickers = {"^KS11": "코스피 (KOSPI)", "^KQ11": "코스닥 (KOSDAQ)"}
        idx_returns: dict[str, float] = {}
        idx_latest_vals: dict[str, float] = {}
        idx_dates: list[str] = []

        for ticker in index_tickers:
            val, ret, d_str = _get_latest_index_quote(ticker, now)
            idx_latest_vals[ticker] = val
            idx_returns[ticker] = ret
            if d_str:
                idx_dates.append(d_str)

        # 3. 실행 시각 기준 ETF 등락률 계산
        latest_returns, etf_data_date = _get_etf_latest_returns(etf_data, etf_tickers, now)

    # 실제 반영된 시세 기준일 (가장 늦은 기준일 또는 ETF 기준일)
    all_dates = [d for d in idx_dates + [etf_data_date] if d]
    effective_data_date = max(all_dates) if all_dates else run_date_str

    kospi_ret = idx_returns.get("^KS11", 0.0)
    kospi_val = idx_latest_vals.get("^KS11", 0.0)
    kosdaq_ret = idx_returns.get("^KQ11", 0.0)
    kosdaq_val = idx_latest_vals.get("^KQ11", 0.0)

    # 코스피와 코스닥 중 변동폭(절대값)이 더 큰 기준 지수 결정
    if abs(kosdaq_ret) >= abs(kospi_ret):
        base_index_ret = kosdaq_ret
        base_index_name = "코스닥"
    else:
        base_index_ret = kospi_ret
        base_index_name = "코스피"

    kospi_color = "#ef4444" if kospi_ret >= 0 else "#10b981"
    kosdaq_color = "#ef4444" if kosdaq_ret >= 0 else "#10b981"

    tree_data = []

    # 1. 시장 지표 데이터 (좌측 상단 고정)
    for idx_t, idx_name in index_tickers.items():
        ret = idx_returns.get(idx_t, 0.0)
        if not pd.isna(ret):
            status = "상승" if ret >= 0 else "하락"
            tree_data.append({
                "Ticker": idx_t,
                "FullName": idx_name,
                "Theme": "시장 지표 (KOSPI/KOSDAQ)",
                "SubTheme": "지표",
                "Return": ret,
                "Diff": 0.0,
                "DiffHtml": "",
                "DisplayStr": f"{ret:+.2f}%",
                "Size": 4.5,
                "Status": status,
            })

    # 2. ETF 테마 데이터 처리 및 지수 대비 상대 강도 계산
    for ticker, ret in latest_returns.items():
        if pd.isna(ret):
            continue
        full_name = name_mapping.get(ticker, ticker)
        raw_theme = clean_theme_name(full_name)
        theme_name = group_theme_category(ticker, full_name, raw_theme)

        # 기준 지수 대비 차이(초과 수익/부진) 계산
        diff = ret - base_index_ret
        if diff >= 0:
            display_str = f"▲ +{diff:.2f}% ({ret:+.2f}%)"
            diff_html = f"<span style='font-size:11px;'>지수대비 {diff:+.2f}%</span>"
        else:
            display_str = f"▼ {diff:.2f}% ({ret:+.2f}%)"
            diff_html = (
                f"<span style='font-size:11px; color:#000000; font-weight:bold;'>"
                f"✔ 지수대비 {diff:+.2f}%</span>"
            )

        status = "상승" if ret >= 0 else "하락"
        abs_ret = abs(ret)
        size_val = max(abs_ret + 3.0, 5.0) if ticker == "475050.KS" else abs_ret + 1.5

        tree_data.append({
            "Ticker": ticker,
            "FullName": full_name,
            "Theme": theme_name,
            "SubTheme": raw_theme,
            "Return": ret,
            "Diff": diff,
            "DiffHtml": diff_html,
            "DisplayStr": display_str,
            "Size": size_val,
            "Status": status,
        })

    df_tree = pd.DataFrame(tree_data)

    # 상승/하락 종목 수 및 비율 계산
    total_count = len(df_tree)
    if total_count > 0:
        rise_count = len(df_tree[df_tree["Status"] == "상승"])
        fall_count = len(df_tree[df_tree["Status"] == "하락"])
        rise_pct = (rise_count / total_count) * 100
        fall_pct = (fall_count / total_count) * 100
    else:
        rise_count, fall_count, rise_pct, fall_pct = 0, 0, 0.0, 0.0

    # 상단 요약 바 (고정형) - 실행 시각 및 시세 기준일 명시
    st.markdown(
        f"""
        <div style="position: sticky; top: 0; z-index: 999; background-color: #0f172a; padding: 16px 24px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #334155; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <div style="display: flex; gap: 30px;">
                    <div><span style="color: #94a3b8; font-size: 17px;">📈 코스피 (KOSPI)</span><br><span style="color: {kospi_color}; font-size: 22px;"><b>{kospi_val:,.2f} ({kospi_ret:+.2f}%)</b></span></div>
                    <div style="border-left: 1px solid #334155; padding-left: 30px;"><span style="color: #94a3b8; font-size: 17px;">📉 코스닥 (KOSDAQ)</span><br><span style="color: {kosdaq_color}; font-size: 22px;"><b>{kosdaq_val:,.2f} ({kosdaq_ret:+.2f}%)</b></span></div>
                </div>
                <div style="text-align: right; color: #94a3b8; font-size: 15px;">
                    기준 비교 지수: <b style="color: #38bdf8;">{base_index_name} ({base_index_ret:+.2f}%)</b><br>
                    시세 기준일: <b style="color: #fbbf24;">{effective_data_date}</b> · 조회 시각: <b style="color: #f8fafc;">{run_timestamp}</b>
                </div>
            </div>
            <div style="border-top: 1px solid #334155; padding-top: 10px; display: flex; gap: 20px; font-size: 16px; color: #e2e8f0;">
                <span>시장 동향 통계:</span>
                <span style="color: #ef4444; font-weight: bold;">상승: {rise_count}개 ({rise_pct:.1f}%)</span>
                <span style="color: #10b981; font-weight: bold;">하락: {fall_count}개 ({fall_pct:.1f}%)</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Plotly 트리맵 생성 (상승/하락 상태별 고정 단색 지정)
    fig = px.treemap(
        df_tree,
        path=["Theme", "FullName"],
        values="Size",
        color="Status",
        color_discrete_map={
            "상승": "#ef4444",
            "하락": "#10b981",
        },
        custom_data=["Ticker", "Return", "SubTheme", "Diff", "DiffHtml"],
    )

    fig.update_traces(
        texttemplate="<b>%{label}</b><br>%{customdata[1]:+.2f}%<br>%{customdata[4]}",
        textfont=dict(
            size=14,
            family="Malgun Gothic, Apple SD Gothic Neo, sans-serif",
        ),
        hovertemplate=(
            "<b>대분류:</b> %{parent}<br><b>세부 테마:</b> %{customdata[2]}<br><b>항목명:</b> %{label}<br><b>티커:</b> %{customdata[0]}<br><b>당일 등락률:</b> %{customdata[1]:+.2f}%<br><b>기준지수 대비:</b> %{customdata[3]:+.2f}%<extra></extra>"
        ),
    )

    fig.update_layout(
        title=dict(
            text=f"<b>오늘 시장 분석 - 테마별 당일 등락률 트리맵 ({effective_data_date} 기준)</b>",
            font=dict(size=24, color="#f8fafc"),
            x=0.03,
            y=0.96,
        ),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        height=850,
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(
            font=dict(color="#f8fafc", size=13),
            orientation="h",
            y=1.02,
            x=0.8,
        ),
    )

    st.plotly_chart(fig, use_container_width=True)
