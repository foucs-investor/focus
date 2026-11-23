# modules/00_today_market.py
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.express as px
import requests
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
    ),
    "Referer": "https://m.stock.naver.com/",
    "Accept": "application/json, text/plain, */*",
}


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


def _to_float(val) -> float | None:
    """문자열/숫자 값을 안전하게 float으로 변환"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if pd.notna(val) else None
    cleaned = str(val).replace(",", "").replace("%", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_kr_code(ticker: str) -> str | None:
    """'475310.KS' 또는 '0177X0.KS' 등에서 6자리 영숫자 종목코드 추출"""
    code = str(ticker).split(".")[0].strip().upper()
    if len(code) == 6 and code.isalnum():
        return code
    return None


def _clean_etf_name(raw_name: str | None, ticker: str) -> str:
    """티커 대신 화면에 표시할 깔끔한 ETF명 반환"""
    if raw_name and isinstance(raw_name, str):
        name = raw_name.strip()
        if name and name.upper() != str(ticker).upper():
            return name
    return str(ticker)


def _normalize_tickers_and_names(tickers_obj, name_mapping_obj) -> tuple[list[str], dict[str, str]]:
    """
    utils.py의 etf_tickers(list 또는 dict)와 name_mapping을 정규화해
    (티커 리스트, {티커: ETF명} 딕셔너리) 반환
    """
    normalized_tickers: list[str] = []
    normalized_names: dict[str, str] = {}

    if isinstance(name_mapping_obj, dict):
        for k, v in name_mapping_obj.items():
            if k is not None and v:
                normalized_names[str(k)] = str(v).strip()

    if isinstance(tickers_obj, dict):
        for k, v in tickers_obj.items():
            t_str = str(k).strip()
            if t_str:
                normalized_tickers.append(t_str)
                if v and t_str not in normalized_names:
                    normalized_names[t_str] = str(v).strip()
    elif isinstance(tickers_obj, (list, tuple, set)):
        for item in tickers_obj:
            t_str = str(item).strip()
            if t_str:
                normalized_tickers.append(t_str)

    # 중복 제거하되 순서 유지
    unique_tickers = list(dict.fromkeys(normalized_tickers))
    return unique_tickers, normalized_names


def _fetch_naver_index_api(ticker: str) -> tuple[float, float] | None:
    """네이버 증권 JSON API로 KOSPI / KOSDAQ 현재가 및 등락률(%) 조회"""
    code_map = {"^KS11": "KOSPI", "^KQ11": "KOSDAQ"}
    idx_code = code_map.get(ticker)
    if not idx_code:
        return None

    polling_url = f"https://polling.finance.naver.com/api/realtime/domestic/index/{idx_code}"
    try:
        resp = requests.get(polling_url, headers=HEADERS, timeout=4)
        resp.raise_for_status()
        payload = resp.json()
        datas = payload.get("datas") if isinstance(payload, dict) else None
        if isinstance(datas, list) and datas:
            item = datas[0]
            curr_val = _to_float(item.get("closePrice"))
            rate_val = _to_float(item.get("fluctuationsRatio"))
            if curr_val is not None and rate_val is not None:
                return curr_val, rate_val
    except Exception:
        pass

    basic_url = f"https://m.stock.naver.com/api/index/{idx_code}/basic"
    try:
        resp = requests.get(basic_url, headers=HEADERS, timeout=4)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            curr_val = _to_float(data.get("closePrice"))
            rate_val = _to_float(data.get("fluctuationsRatio"))
            if curr_val is not None and rate_val is not None:
                return curr_val, rate_val
    except Exception:
        pass

    return None


def _fetch_naver_etfs_api(tickers: list[str]) -> tuple[dict[str, float], dict[str, str]]:
    """
    네이버 증권 실시간 JSON API로 ETF 목록의 등락률(%)과 ETF명을 일괄 조회.
    반환: ({원본_티커: 등락률_퍼센트}, {원본_티커: ETF명})
    """
    code_to_tickers: dict[str, list[str]] = {}
    for t in tickers:
        code = _extract_kr_code(t)
        if code:
            code_to_tickers.setdefault(code, []).append(t)

    codes = list(code_to_tickers.keys())
    returns: dict[str, float] = {}
    names: dict[str, str] = {}
    if not codes:
        return returns, names

    chunk_size = 30
    for i in range(0, len(codes), chunk_size):
        chunk = codes[i : i + chunk_size]
        url = (
            "https://polling.finance.naver.com/api/realtime/domestic/stock/"
            + ",".join(chunk)
        )
        try:
            resp = requests.get(url, headers=HEADERS, timeout=5)
            resp.raise_for_status()
            payload = resp.json()
            datas = payload.get("datas") if isinstance(payload, dict) else None
            if isinstance(datas, list):
                for item in datas:
                    item_code = str(item.get("itemCode", "")).strip().upper()
                    rate_val = _to_float(item.get("fluctuationsRatio"))
                    etf_name = (
                        item.get("stockName")
                        or item.get("itemName")
                        or item.get("name")
                    )
                    if item_code in code_to_tickers:
                        for orig_ticker in code_to_tickers[item_code]:
                            if rate_val is not None:
                                returns[orig_ticker] = rate_val
                            if etf_name:
                                names[orig_ticker] = str(etf_name).strip()
        except Exception:
            continue

    # 배치에서 누락된 종목은 개별 /basic API로 보완
    missing_codes = [
        c
        for c, t_list in code_to_tickers.items()
        if not any(t in returns and t in names for t in t_list)
    ]
    for code in missing_codes:
        basic_url = f"https://m.stock.naver.com/api/stock/{code}/basic"
        try:
            resp = requests.get(basic_url, headers=HEADERS, timeout=4)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                rate_val = _to_float(data.get("fluctuationsRatio"))
                etf_name = (
                    data.get("stockName")
                    or data.get("itemName")
                    or data.get("name")
                )
                for orig_ticker in code_to_tickers[code]:
                    if orig_ticker not in returns and rate_val is not None:
                        returns[orig_ticker] = rate_val
                    if orig_ticker not in names and etf_name:
                        names[orig_ticker] = str(etf_name).strip()
        except Exception:
            continue

    return returns, names


def _get_index_quote(ticker: str) -> tuple[float, float]:
    """지수 현재가 및 등락률(%) 조회 (네이버 API 우선 -> yfinance 폴백)"""
    naver_res = _fetch_naver_index_api(ticker)
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


def _get_etf_returns_and_names(
    tickers: list[str], etf_data: pd.DataFrame, base_names: dict[str, str]
) -> tuple[dict[str, float], dict[str, str]]:
    """
    ETF 등락률(%)과 표시용 ETF명 조회:
    - 등락률: 네이버 API 우선 -> yfinance 일봉 폴백
    - ETF명: utils 매핑/딕셔너리 우선 -> 네이버 API 종목명 -> 폴백
    """
    returns, naver_names = _fetch_naver_etfs_api(tickers)
    resolved_names: dict[str, str] = {}

    for t in tickers:
        candidate_name = base_names.get(t) or naver_names.get(t)
        resolved_names[t] = _clean_etf_name(candidate_name, t)

        if t not in returns and not etf_data.empty and t in etf_data.columns:
            series = etf_data[t].dropna()
            if len(series) >= 2:
                prev_c = float(series.iloc[-2])
                curr_c = float(series.iloc[-1])
                if prev_c > 0:
                    returns[t] = (curr_c - prev_c) / prev_c * 100.0

    return returns, resolved_names


def _load_etf_history_safely(tickers: list[str]) -> tuple[pd.DataFrame, dict[str, str]]:
    """download_etf_data를 호출하되, 빈 결과나 예외가 발생해도 안전하게 처리"""
    df_raw = pd.DataFrame()
    name_map: dict[str, str] = {}
    try:
        res = download_etf_data(tickers, period="10d")
        if isinstance(res, tuple) and len(res) >= 2:
            if isinstance(res[0], pd.DataFrame):
                df_raw = res[0].copy()
            if isinstance(res[1], dict):
                name_map = res[1]
        elif isinstance(res, pd.DataFrame):
            df_raw = res.copy()
    except Exception:
        pass

    if not df_raw.empty:
        df_raw.index = pd.to_datetime(df_raw.index)
    return df_raw, name_map


def render():
    now = datetime.now(KST)
    run_date_str = now.strftime("%Y-%m-%d")
    run_timestamp = now.strftime("%Y-%m-%d %H:%M:%S (KST)")

    # 상단 새로고침 버튼으로 캐시 클리어 지원
    col_title, col_btn = st.columns([8, 2])
    with col_btn:
        if st.button("🔄 시세 새로고침", key="refresh_today_market"):
            st.cache_data.clear()
            st.rerun()

    normalized_tickers, pre_names = _normalize_tickers_and_names(etf_tickers, {})

    with st.spinner(f"{run_timestamp} 기준 최신 시장 및 ETF 시세 데이터를 가져오는 중입니다..."):
        df_raw, mapped_from_dl = _load_etf_history_safely(normalized_tickers)
        _, merged_names = _normalize_tickers_and_names(etf_tickers, {**pre_names, **mapped_from_dl})

        index_tickers = {"^KS11": "코스피 (KOSPI)", "^KQ11": "코스닥 (KOSDAQ)"}
        idx_returns: dict[str, float] = {}
        idx_latest_vals: dict[str, float] = {}

        for ticker in index_tickers:
            val, ret = _get_index_quote(ticker)
            idx_latest_vals[ticker] = val
            idx_returns[ticker] = ret

        latest_returns, etf_names = _get_etf_returns_and_names(
            normalized_tickers, df_raw, merged_names
        )

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

    # 1. 시장 지표 데이터
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

    # 2. ETF 테마 데이터 (ETF명 우선 표기)
    for ticker, ret in latest_returns.items():
        if pd.isna(ret):
            continue
        full_name = etf_names.get(ticker) or _clean_etf_name(merged_names.get(ticker), ticker)
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

    # 상단 요약 바
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

    if df_tree.empty:
        st.warning("표시할 시세 데이터가 없습니다. 종목코드 또는 네트워크 상태를 확인해 주세요.")
        return

    # Plotly 트리맵 생성 (ETF명 표기)
    fig = px.treemap(
        df_tree,
        path=["Theme", "FullName"],
        values="Size",
        color="Status",
        color_discrete_map={
            "상승": "#ef4444",
            "하락": "#10b981",
        },
        custom_data=["Ticker", "Return", "SubTheme", "Diff", "DiffHtml", "FullName"],
    )

    fig.update_traces(
        texttemplate="<b>%{customdata[5]}</b><br>%{customdata[1]:+.2f}%<br>%{customdata[4]}",
        textfont=dict(
            size=14,
            family="Malgun Gothic, Apple SD Gothic Neo, sans-serif",
        ),
        hovertemplate=(
            "<b>대분류:</b> %{parent}<br>"
            "<b>세부 테마:</b> %{customdata[2]}<br>"
            "<b>ETF명:</b> %{customdata[5]}<br>"
            "<b>티커:</b> %{customdata[0]}<br>"
            "<b>당일 등락률:</b> %{customdata[1]:+.2f}%<br>"
            "<b>기준지수 대비:</b> %{customdata[3]:+.2f}%<extra></extra>"
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
