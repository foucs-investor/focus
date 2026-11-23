# modules/00_today_market.py
from datetime import datetime
from zoneinfo import ZoneInfo
import re
import requests
import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf
from utils import clean_theme_name, download_etf_data, etf_tickers

# 사이드바 라디오 버튼에 표시될 메뉴명
MENU_NAME = "오늘 시장"
KST = ZoneInfo("Asia/Seoul")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def group_theme_category(ticker: str, full_name: str, theme_name: str) -> str:
    """티커, 전체 종목명, 세부 테마명을 기반으로 상위 대분류 테마로 묶어주는 함수"""
    lower_name = (full_name or "").lower()
    lower_theme = (theme_name or "").lower()

    if ticker in ["^KS11", "^KQ11"]:
        return "시장 지표 (KOSPI/KOSDAQ)"

    if any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["화장품", "k뷰티", "k-뷰티", "뷰티", "푸드"]
    ):
        return "화장품/음식료"

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

    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["반도체", "소부장", "후공정", "장비", "메모리"]
    ):
        return "반도체"

    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["증권", "은행", "금융", "보험", "지주사"]
    ):
        return "금융"

    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["바이오", "헬스케어", "제약", "의료기기", "의료"]
    ):
        return "바이오/헬스케어"

    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["인공지능", "소프트웨어", "클라우드", "software", "보안", "it"]
    ):
        return "IT·소프트웨어"

    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["조선", "방산", "우주", "항공"]
    ):
        return "조선/방산"

    elif any(
        keyword in lower_name or keyword in lower_theme for keyword in ["친환경"]
    ):
        return "친환경에너지"

    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["생활소비", "경기소비"]
    ):
        return "소비재"

    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["건설", "설비", "원자력"]
    ):
        return "AIDC"

    elif any(
        keyword in lower_name or keyword in lower_theme
        for keyword in ["로봇", "자동차", "2차전지", "배터리", "전기차", "lfp", "양극재"]
    ):
        return "로봇/자동차/2차전지"

    return theme_name


def _parse_num(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(text))
    if not cleaned or cleaned in {"-", ".", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _fetch_naver_etf_quote(ticker: str) -> tuple[float, float] | None:
    """
    네이버 금융에서 종목(예: '475310.KS' -> '475310')의 현재가와 등락률(%)을 조회.
    반환: (current_price, return_pct) 또는 실패 시 None
    """
    code = ticker.split(".")[0].strip()
    if not code.isdigit():
        return None

    url = f"https://finance.naver.com/item/main.naver?code={code}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=4)
        resp.raise_for_status()
        html = resp.text

        # <p class="no_today"> 내부 현재가 추출
        no_today_match = re.search(
            r'<p[^>]*class="[^"]*no_today[^"]*"[^>]*>(.*?)</p>',
            html,
            re.S,
        )
        curr_price = None
        if no_today_match:
            blind_match = re.search(
                r'<span[^>]*class="[^"]*blind[^"]*"[^>]*>([^<]+)</span>',
                no_today_match.group(1),
            )
            if blind_match:
                curr_price = _parse_num(blind_match.group(1))

        # <p class="no_exday"> 또는 전일/등락률 영역 추출
        # 네이버 종목 페이지에서 전일가와 등락률을 함께 확인
        prev_close = None
        prev_match = re.search(
            r"전일\s*<span[^>]*class=\"[^\"]*blind[^\"]*\"[^>]*>([^<]+)</span>",
            html,
        )
        if prev_match:
            prev_close = _parse_num(prev_match.group(1))

        # 전일가가 있으면 (현재가 - 전일가) / 전일가로 직접 계산
        if curr_price is not None and prev_close and prev_close > 0:
            ret_pct = (curr_price - prev_close) / prev_close * 100.0
            return curr_price, ret_pct

        # 전일가 파싱 실패 시 no_exday의 등락률 blind 값 시도
        no_exday_match = re.search(
            r'<p[^>]*class="[^"]*no_exday[^"]*"[^>]*>(.*?)</p>',
            html,
            re.S,
        )
        if curr_price is not None and no_exday_match:
            blinds = re.findall(
                r'<span[^>]*class="[^"]*blind[^"]*"[^>]*>([^<]+)</span>',
                no_exday_match.group(1),
            )
            # 보통 [전일대비금액, 부호, 등락률] 순서로 등장
            if len(blinds) >= 3:
                pct_val = _parse_num(blinds[2])
                if pct_val is not None:
                    # 하락(ico down / 감) 여부 반영
                    is_down = bool(
                        re.search(r'class="[^"]*ico\s+down[^"]*"|하락', no_exday_match.group(1))
                    )
                    if is_down and pct_val > 0:
                        pct_val = -pct_val
                    return curr_price, pct_val

    except Exception:
        return None

    return None


def _fetch_naver_index_quote(ticker: str) -> tuple[float, float] | None:
    """네이버 금융에서 KOSPI(^KS11) / KOSDAQ(^KQ11) 지수 현재가 및 등락률(%) 조회"""
    code_map = {"^KS11": "KOSPI", "^KQ11": "KOSDAQ"}
    sise_code = code_map.get(ticker)
    if not sise_code:
        return None

    url = f"https://finance.naver.com/sise/sise_index.naver?code={sise_code}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=4)
        resp.raise_for_status()
        html = resp.text

        val_match = re.search(r'<em[^>]*id="now_value"[^>]*>([^<]+)</em>', html)
        rate_match = re.search(r'<span[^>]*id="rate"[^>]*>([^<]+)</span>', html)
        curr_val = _parse_num(val_match.group(1)) if val_match else None
        rate_val = _parse_num(rate_match.group(1)) if rate_match else None

        if curr_val is not None and rate_val is not None:
            return curr_val, rate_val
    except Exception:
        return None

    return None


def _get_index_quote_with_fallback(ticker: str) -> tuple[float, float]:
    """지수 현재가 및 등락률(%)을 네이버 우선 -> yfinance 폴백으로 조회"""
    naver_res = _fetch_naver_index_quote(ticker)
    if naver_res is not None:
        return naver_res

    t_obj = yf.Ticker(ticker)
    try:
        hist = t_obj.history(period="5d", interval="1d")
        closes = hist["Close"].dropna() if "Close" in hist.columns else pd.Series(dtype=float)
        if len(closes) >= 2:
            prev_c = float(closes.iloc[-2])
            curr_c = float(closes.iloc[-1])
            fi = t_obj.fast_info
            last_p = getattr(fi, "last_price", None)
            if last_p and float(last_p) > 0:
                curr_c = float(last_p)
            ret = ((curr_c - prev_c) / prev_c * 100.0) if prev_c > 0 else 0.0
            return curr_c, ret
    except Exception:
        pass

    return 0.0, 0.0


def _get_etf_return_with_fallback(
    ticker: str, etf_data: pd.DataFrame, now_kst: datetime
) -> float | None:
    """
    ETF 당일 등락률(%) 계산:
    1) 네이버 금융 현재가/전일가 기준 우선 계산
    2) 실패 시 yfinance 일봉/분봉 기반(ffill 없이 종목별 유효 종가만 사용) 계산
    """
    naver_res = _fetch_naver_etf_quote(ticker)
    if naver_res is not None:
        return naver_res[1]

    if ticker not in etf_data.columns:
        return None

    series = etf_data[ticker].dropna()
    if len(series) < 2:
        return None

    today_str = now_kst.strftime("%Y-%m-%d")
    last_ts = pd.Timestamp(series.index[-1])
    if last_ts.tzinfo is None:
        last_ts_kst = last_ts.tz_localize("UTC").tz_convert(KST)
    else:
        last_ts_kst = last_ts.tz_convert(KST)
    last_date_str = last_ts_kst.strftime("%Y-%m-%d")

    # 오늘 날짜 봉이 이미 존재하는 경우 vs 전일 종가만 있는 경우
    if last_date_str == today_str:
        prev_close = float(series.iloc[-2])
        curr_price = float(series.iloc[-1])
    else:
        prev_close = float(series.iloc[-1])
        curr_price = prev_close

    # 장중에는 yfinance fast_info / 1m 최신 체결가가 있으면 반영하되,
    # 직전 종가 대비 과도한 이상치(예: ±30% 초과)는 방어
    try:
        fi = yf.Ticker(ticker).fast_info
        last_p = getattr(fi, "last_price", None)
        if last_p and float(last_p) > 0 and prev_close > 0:
            candidate = float(last_p)
            pct = (candidate - prev_close) / prev_close * 100.0
            if -30.0 <= pct <= 30.0:
                return pct
    except Exception:
        pass

    if prev_close > 0:
        return (curr_price - prev_close) / prev_close * 100.0
    return None


def render():
    now = datetime.now(KST)
    run_date_str = now.strftime("%Y-%m-%d")
    run_timestamp = now.strftime("%Y-%m-%d %H:%M:%S (KST)")

    with st.spinner(f"{run_timestamp} 기준 최신 시장 및 ETF 시세 데이터를 가져오는 중입니다..."):
        # ffll()/bfill()을 제거해 종목별 날짜/가격 왜곡 방지
        df_raw, name_mapping = download_etf_data(etf_tickers, period="10d")
        etf_data = df_raw.copy()
        etf_data.index = pd.to_datetime(etf_data.index)

        index_tickers = {"^KS11": "코스피 (KOSPI)", "^KQ11": "코스닥 (KOSDAQ)"}
        idx_returns: dict[str, float] = {}
        idx_latest_vals: dict[str, float] = {}

        for ticker in index_tickers:
            val, ret = _get_index_quote_with_fallback(ticker)
            idx_latest_vals[ticker] = val
            idx_returns[ticker] = ret

        latest_returns: dict[str, float] = {}
        for ticker in etf_tickers:
            ret = _get_etf_return_with_fallback(ticker, etf_data, now)
            if ret is not None and pd.notna(ret):
                latest_returns[ticker] = float(ret)

    kospi_ret = idx_returns.get("^KS11", 0.0)
    kospi_val = idx_latest_vals.get("^KS11", 0.0)
    kosdaq_ret = idx_returns.get("^KQ11", 0.0)
    kosdaq_val = idx_latest_vals.get("^KQ11", 0.0)

    if abs(kosdaq_ret) >= abs(kospi_ret):
        base_index_ret = kosdaq_ret
        base_index_name = "코스닥"
    else:
        base_index_ret = kospi_ret
        base_index_name = "코스피"

    kospi_color = "#ef4444" if kospi_ret >= 0 else "#10b981"
    kosdaq_color = "#ef4444" if kosdaq_ret >= 0 else "#10b981"

    tree_data = []

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

    for ticker, ret in latest_returns.items():
        if pd.isna(ret):
            continue
        full_name = name_mapping.get(ticker, ticker)
        raw_theme = clean_theme_name(full_name)
        theme_name = group_theme_category(ticker, full_name, raw_theme)

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

    total_count = len(df_tree)
    if total_count > 0:
        rise_count = len(df_tree[df_tree["Status"] == "상승"])
        fall_count = len(df_tree[df_tree["Status"] == "하락"])
        rise_pct = (rise_count / total_count) * 100
        fall_pct = (fall_count / total_count) * 100
    else:
        rise_count, fall_count, rise_pct, fall_pct = 0, 0, 0.0, 0.0

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
                    조회 시각: <b style="color: #f8fafc;">{run_timestamp}</b>
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
            text=f"<b>오늘 시장 분석 - 테마별 당일 등락률 트리맵 ({run_date_str} 기준)</b>",
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
