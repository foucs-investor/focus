# modules/11_sector_price_stage.py
from datetime import datetime
from io import BytesIO
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

import matplotlib.dates as mdates
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from utils import clean_theme_name, download_etf_data, etf_tickers

# 사이드바 라디오 버튼에 표시될 메뉴명
MENU_NAME = "섹터별 주식단계"
KST = ZoneInfo("Asia/Seoul")

# 주식 단계 오름차순 정렬 우선순위
STAGE_SORT_ORDER: dict[str, int] = {
    "1단계 (바닥/기초)": 1,
    "2단계 (상승 국면)": 2,
    "3단계 (천장/횡보)": 3,
    "4단계 (하락 국면)": 4,
    "데이터 부족": 99,
}

# ETF명 Hover 시 주요 구성 종목 말풍선 표시용 매핑
ETF_TOP_HOLDINGS: dict[str, list[str]] = {
    "KODEX 반도체": ["SK하이닉스", "삼성전자", "한미반도체", "주성엔지니어링", "심텍"],
    "KODEX AI반도체TOP2플러스": ["SK하이닉스", "삼성전자", "SK스퀘어", "삼성전기", "한미반도체"],
    "KODEX AI반도체핵심장비": ["한미반도체", "원익IPS", "주성엔지니어링", "이오테크닉스", "HPSP"],
    "SOL AI반도체소부장": ["이수페타시스", "한미반도체", "주성엔지니어링", "대덕전자", "심텍"],
    "TIGER 200 IT": ["SK스퀘어", "SK하이닉스", "삼성전자", "삼성전기", "삼성SDI"],
    "SOL 반도체전공정": ["주성엔지니어링", "HPSP", "원익IPS", "한솔케미칼", "피에스케이"],
    "SOL 반도체후공정": ["이수페타시스", "한미반도체", "이오테크닉스", "리노공업", "대덕전자"],
    "KODEX AI전력핵심설비": ["LS ELECTRIC", "효성중공업", "HD현대일렉트릭", "LS", "대한전선"],
    "ACE 원자력테마딥서치": ["현대건설", "두산에너빌리티", "비에이치아이", "우리기술", "대우건설"],
    "HANARO FN친환경에너지": ["삼성SDI", "LG에너지솔루션", "POSCO홀딩스", "포스코인터내셔널", "OCI홀딩스"],
    "PLUS 태양광&ESS": ["한화솔루션", "OCI홀딩스", "삼성SDI", "LG에너지솔루션", "HD현대에너지솔루션"],
    "KODEX 은행": ["하나금융지주", "우리금융지주", "KB금융", "신한지주", "카카오뱅크"],
    "KODEX 보험": ["DB손해보험", "삼성화재", "삼성생명", "현대해상", "코리안리"],
    "KODEX 증권": ["삼성증권", "한국금융지주", "NH투자증권", "키움증권", "미래에셋증권"],
    "TIGER 지주회사": ["한진칼", "LG", "SK", "POSCO홀딩스", "삼성물산"],
    "TIGER 코스피고배당": ["한일시멘트", "아이마켓코리아", "제일기획", "에스원", "DB손해보험"],
    "TIGER 우선주": ["삼성전자우", "현대차2우B", "삼성화재우", "LG전자우", "미래에셋증권2우B"],
    "KODEX 코리아밸류업": ["SK하이닉스", "삼성전자", "SK스퀘어", "KB금융", "현대차"],
    "KODEX 바이오": ["프로티나", "루닛", "동국제약", "리브스메드", "셀트리온"],
    "TIGER 바이오 TOP 10": ["셀트리온", "삼성바이오로직스", "알테오젠", "유한양행", "SK바이오팜"],
    "HANARO 바이오코리아액티브": ["한올바이오파마", "셀트리온", "한미약품", "에이비엘바이오", "유한양행"],
    "TIGER 의료기기": ["파마리서치", "루닛", "엘앤씨바이오", "씨젠", "리브스메드"],
    "KIWOOM 의료AI": ["셀트리온", "SK바이오팜", "루닛", "프로티나", "차바이오텍"],
    "KODEX 로봇액티브": ["로보티즈", "레인보우로보틱스", "삼성전자", "현대모비스", "LG전자"],
    "TIGER 소프트웨어": ["NAVER", "카카오", "삼성SDS", "크래프톤", "LG씨엔에스"],
    "TIGER SOFTWARE": ["NAVER", "카카오", "삼성SDS", "크래프톤", "LG씨엔에스"],
    "TIGER 인터넷TOP10": ["카카오", "서진시스템", "NAVER", "대한광통신", "안랩"],
    "RISE 플랫폼테마": ["NHN", "NICE정보통신", "카카오", "SOOP", "NAVER"],
    "TIGER 미디어컨텐츠": ["스튜디오드래곤", "CJ ENM", "에스엠", "JYP Ent.", "디어유"],
    "RISE 네트워크인프라": ["삼성전자", "SK하이닉스", "삼성전기", "LG이노텍", "이수페타시스"],
    "RISE 5G테크": ["에이스테크", "오이솔루션", "서진시스템", "이노와이어리스", "RFHIC"],
    "TIGER 200 헬스케어": ["셀트리온", "삼성바이오로직스", "유한양행", "SK바이오팜", "한미약품"],
    "TIGER 조선TOP10": ["HD한국조선해양", "HD현대중공업", "한화오션", "삼성중공업", "HD현대마린솔루션"],
    "PLUS K방산": ["한화에어로스페이스", "한국항공우주", "한화오션", "LIG넥스원", "현대로템"],
    "KODEX 자동차": ["기아", "현대모비스", "한국타이어앤테크놀로지", "현대차", "HL만도"],
    "TIGER 200 중공업": ["두산에너빌리티", "HD한국조선해양", "삼성중공업", "HD현대일렉트릭", "HD현대중공업"],
    "HANARO CAPEX설비투자iSelect": ["두산밥캣", "HD건설기계", "LS ELECTRIC", "효성중공업", "두산에너빌리티"],
    "KODEX 건설": ["삼성E&A", "현대건설", "대우건설", "GS건설", "DL이앤씨"],
    "KODEX 철강": ["POSCO홀딩스", "현대제철", "고려아연", "풍산", "에이치브이엠"],
    "KODEX 에너지화학": ["LG화학", "SK이노베이션", "HD현대", "S-Oil", "한화솔루션"],
    "TIGER 2차전지테마": ["LG에너지솔루션", "POSCO홀딩스", "삼성SDI", "SK이노베이션", "LG화학"],
    "TIGER 2차전지소재Fn": ["포스코퓨처엠", "에코프로", "POSCO홀딩스", "에코프로비엠", "LG화학"],
    "TIGER 화장품": ["아모레퍼시픽", "코스맥스", "LG생활건강", "파마리서치", "한국콜마"],
    "HANARO K-뷰티": ["아모레퍼시픽", "에이피알", "코스맥스", "LG생활건강", "한국콜마"],
    "TIGER 중국소비테마": ["코스맥스", "파라다이스", "삼양식품", "덴티움", "아모레퍼시픽"],
    "TIGER 여행레저": ["파라다이스", "아시아나항공", "강원랜드", "대한항공", "호텔신라", "롯데관광개발"],
    "ACE KPOP포커스": ["하이브", "에스엠", "JYP Ent.", "와이지엔터테인먼트", "CJ ENM"],
    "KODEX K-콘텐츠": ["카카오", "NAVER", "크래프톤", "하이브", "엔씨소프트"],
    "KODEX 미디어&엔터테인먼트": ["하이브", "CJ ENM", "에스엠", "JYP Ent.", "스튜디오드래곤"],
    "KODEX 게임산업": ["크래프톤", "엔씨소프트", "펄어비스", "넷마블", "시프트업"],
    "TIGER 게임TOP10": ["크래프톤", "엔씨소프트", "펄어비스", "넷마블", "NHN"],
    "TIGER 경기방어": ["셀트리온", "KT&G", "KT", "삼성바이오로직스", "SK텔레콤"],
    "TIGER 200 생활소비재": ["KT&G", "한국전력", "에이피알", "삼양식품", "아모레퍼시픽"],
    "KODEX 경기소비재": ["한진칼", "코웨이", "LG전자", "신세계", "강원랜드"],
    "HANARO Fn K-푸드": ["삼양식품", "CJ제일제당", "농심", "오리온", "오뚜기"],
    "MIDAS 중소형액티브": ["삼성전기", "두산", "테스", "효성중공업", "엘앤씨바이오"],
    "ACE K휴머노이드로봇산업TOP2+": ["로보티즈", "현대차", "레인보우로보틱스", "에스피지", "현대모비스"],
    "KoAct 광통신&위성네트워크액티브": ["RF머트리얼즈", "우리로", "대한광통신", "RFHIC", "케이엠더블유"],
    "TIGER 글로벌AI사이버보안": ["Cloudflare", "Okta", "Zscaler", "Palo Alto Networks", "Fortinet"],
}


def _get_top_holdings_text(etf_name: str) -> str:
    """ETF명에 대응하는 주요 구성 종목 문자열 반환"""
    if not etf_name:
        return "구성 종목 정보 없음"
    if etf_name in ETF_TOP_HOLDINGS:
        return ", ".join(ETF_TOP_HOLDINGS[etf_name])
    for key, holdings in ETF_TOP_HOLDINGS.items():
        if key in etf_name or etf_name in key:
            return ", ".join(holdings)
    return "구성 종목 정보 준비 중"


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


def _clean_etf_name(raw_name: str | None, ticker: str) -> str:
    """티커 대신 화면에 표시할 깔끔한 ETF명 반환"""
    if raw_name and isinstance(raw_name, str):
        name = raw_name.strip()
        if name and name.upper() != str(ticker).upper():
            return name
    return str(ticker)


def _normalize_tickers_and_names(tickers_obj, name_mapping_obj) -> tuple[list[str], dict[str, str]]:
    """etf_tickers와 name_mapping을 정규화해 (티커 리스트, {티커/코드: ETF명}) 반환"""
    normalized_tickers: list[str] = []
    normalized_names: dict[str, str] = {}

    if isinstance(name_mapping_obj, dict):
        for k, v in name_mapping_obj.items():
            if k is not None and v:
                k_str = str(k).strip()
                v_str = str(v).strip()
                normalized_names[k_str] = v_str
                normalized_names[k_str.replace(".KS", "").replace(".KQ", "")] = v_str

    if isinstance(tickers_obj, dict):
        for k, v in tickers_obj.items():
            t_str = str(k).strip()
            if t_str:
                normalized_tickers.append(t_str)
                if v:
                    v_str = str(v).strip()
                    if t_str not in normalized_names:
                        normalized_names[t_str] = v_str
                    short_k = t_str.replace(".KS", "").replace(".KQ", "")
                    if short_k not in normalized_names:
                        normalized_names[short_k] = v_str
    elif isinstance(tickers_obj, (list, tuple, set)):
        for item in tickers_obj:
            t_str = str(item).strip()
            if t_str:
                normalized_tickers.append(t_str)

    unique_tickers = list(dict.fromkeys(normalized_tickers))
    return unique_tickers, normalized_names


def _extract_close_df(raw_obj) -> pd.DataFrame:
    """종가 DataFrame을 2차원 (날짜 x 종목) 형태로 정규화"""
    if not isinstance(raw_obj, pd.DataFrame) or raw_obj.empty:
        return pd.DataFrame()

    df_out = raw_obj.copy()
    if isinstance(df_out.columns, pd.MultiIndex):
        level_0 = set(df_out.columns.get_level_values(0))
        if "Close" in level_0:
            df_out = df_out["Close"].copy()
        elif "Adj Close" in level_0:
            df_out = df_out["Adj Close"].copy()
        else:
            df_out.columns = df_out.columns.get_level_values(-1)

    df_out.index = pd.to_datetime(df_out.index)
    df_out = df_out.loc[~df_out.index.duplicated(keep="last")].sort_index()
    return df_out


@st.cache_data(ttl=1800, show_spinner=False)
def _load_2y_etf_prices(tickers: list[str]) -> tuple[pd.DataFrame, dict[str, str]]:
    """최근 2년치 ETF 일봉 종가 데이터 다운로드 (utils.download_etf_data 우선 -> yfinance 폴백)"""
    df_raw = pd.DataFrame()
    name_map: dict[str, str] = {}

    try:
        res = download_etf_data(tickers, period="2y")
        if isinstance(res, tuple) and len(res) >= 2:
            df_raw = _extract_close_df(res[0])
            if isinstance(res[1], dict):
                name_map = {str(k): str(v) for k, v in res[1].items() if k and v}
        elif isinstance(res, pd.DataFrame):
            df_raw = _extract_close_df(res)
    except Exception:
        pass

    if df_raw.empty or len(df_raw.dropna(how="all")) < 120:
        try:
            dl = yf.download(tickers, period="2y", auto_adjust=True, progress=False)
            fallback_df = _extract_close_df(dl)
            if not fallback_df.empty and len(fallback_df.dropna(how="all")) > len(df_raw.dropna(how="all")):
                df_raw = fallback_df
        except Exception:
            pass

    if not df_raw.empty:
        df_raw = df_raw.drop(columns=["^KS11", "^KQ11", "코스피", "코스닥"], errors="ignore")

    return df_raw, name_map


def _classify_weinstein_stage(weekly_close: pd.Series, ma30: pd.Series) -> tuple[str, int, str, float]:
    """
    주봉 종가와 30주 이동평균선 기반 스탠 와인스타인 4단계 판별
    반환: (단계 라벨, 정렬 순서, 배지 색상 hex, 30주선 대비 이격률 %)
    """
    valid = pd.DataFrame({"close": weekly_close, "ma30": ma30}).dropna()
    if len(valid) < 5:
        return "데이터 부족", STAGE_SORT_ORDER["데이터 부족"], "#64748b", 0.0

    curr_price = float(valid["close"].iloc[-1])
    curr_ma = float(valid["ma30"].iloc[-1])
    prev_ma_4w = float(valid["ma30"].iloc[-5])

    ma_slope_pct = ((curr_ma - prev_ma_4w) / prev_ma_4w * 100.0) if prev_ma_4w > 0 else 0.0
    dist_pct = ((curr_price - curr_ma) / curr_ma * 100.0) if curr_ma > 0 else 0.0

    if curr_price >= curr_ma and ma_slope_pct > 0.15:
        label = "2단계 (상승 국면)"
        return label, STAGE_SORT_ORDER[label], "#ef4444", dist_pct
    elif curr_price < curr_ma and ma_slope_pct < -0.15:
        label = "4단계 (하락 국면)"
        return label, STAGE_SORT_ORDER[label], "#3b82f6", dist_pct
    elif curr_price >= curr_ma and ma_slope_pct <= 0.15:
        label = "3단계 (천장/횡보)"
        return label, STAGE_SORT_ORDER[label], "#f59e0b", dist_pct
    else:
        label = "1단계 (바닥/기초)"
        return label, STAGE_SORT_ORDER[label], "#10b981", dist_pct


def _prepare_weekly_stage_items(
    df_daily: pd.DataFrame,
    tickers: list[str],
    name_map: dict[str, str],
) -> list[dict]:
    """각 ETF별 최근 2년 주봉 종가 및 30주 이동평균선, 섹터, 주식단계 데이터를 계산 후 단계 오름차순 정렬"""
    items: list[dict] = []
    if df_daily.empty:
        return items

    cutoff_date = df_daily.index.max() - pd.DateOffset(years=2)
    df_2y = df_daily.loc[df_daily.index >= cutoff_date].copy()

    for ticker in tickers:
        short_t = ticker.replace(".KS", "").replace(".KQ", "")
        col = ticker if ticker in df_2y.columns else (short_t if short_t in df_2y.columns else None)
        if col is None:
            continue

        s_daily = df_2y[col].dropna()
        if len(s_daily) < 30:
            continue

        s_weekly = s_daily.resample("W-FRI").last().dropna()
        if len(s_weekly) < 10:
            continue

        ma30 = s_weekly.rolling(window=30, min_periods=10).mean()

        full_name = _clean_etf_name(
            name_map.get(ticker) or name_map.get(short_t),
            ticker,
        )
        raw_theme = clean_theme_name(full_name)
        sector = group_theme_category(ticker, full_name, raw_theme)
        stage_label, stage_order, stage_color, dist_pct = _classify_weinstein_stage(s_weekly, ma30)

        curr_price = float(s_weekly.iloc[-1])
        curr_ma30 = float(ma30.dropna().iloc[-1]) if not ma30.dropna().empty else np.nan

        items.append({
            "ticker": ticker,
            "code": short_t,
            "name": full_name,
            "sector": sector,
            "sub_theme": raw_theme,
            "stage": stage_label,
            "stage_order": stage_order,
            "stage_color": stage_color,
            "curr_price": curr_price,
            "curr_ma30": curr_ma30,
            "dist_pct": dist_pct,
            "weekly_close": s_weekly,
            "ma30": ma30,
            "holdings": _get_top_holdings_text(full_name),
        })

    items.sort(key=lambda x: (x["stage_order"], -x["dist_pct"], x["name"]))
    return items


def _build_plotly_weekly_chart(item: dict) -> go.Figure:
    """개별 ETF의 2년 주봉 종가 + 30주 이동평균선 Plotly 차트 생성 (X축 날짜 숫자만 표기)"""
    s_weekly: pd.Series = item["weekly_close"]
    ma30: pd.Series = item["ma30"]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=s_weekly.index,
            y=s_weekly.values,
            mode="lines",
            name="주봉 종가",
            line=dict(color="#38bdf8", width=2.2),
            hovertemplate="날짜: %{x|%Y-%m-%d}<br>주봉 종가: %{y:,.0f}원<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=ma30.index,
            y=ma30.values,
            mode="lines",
            name="30주 이동평균선",
            line=dict(color="#f97316", width=2.4),
            hovertemplate="날짜: %{x|%Y-%m-%d}<br>30주선: %{y:,.0f}원<extra></extra>",
        )
    )

    ma30_str = f"{item['curr_ma30']:,.0f}" if pd.notna(item["curr_ma30"]) else "-"
    fig.update_layout(
        title=dict(
            text=(
                f"<b>{item['name']}</b> ({item['code']})<br>"
                f"<span style='font-size:12px; color:#94a3b8;'>"
                f"섹터: {item['sector']} | 현재가: {item['curr_price']:,.0f}원 | "
                f"30주선: {ma30_str}원 ({item['dist_pct']:+.2f}%)"
                f"</span>"
            ),
            font=dict(size=15, color="#f8fafc"),
            x=0.02,
            y=0.94,
        ),
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        height=370,
        margin=dict(l=45, r=20, t=68, b=42),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1.0,
            font=dict(size=11, color="#e2e8f0"),
        ),
        xaxis=dict(
            tickformat="%Y-%m-%d",
            tickangle=-30,
            showgrid=True,
            gridcolor="#1e293b",
            tickfont=dict(color="#cbd5e1", size=11),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#1e293b",
            tickformat=",",
            tickfont=dict(color="#cbd5e1", size=11),
        ),
    )
    return fig


def _render_etf_title_with_bubble(item: dict) -> None:
    """ETF 제목에 마우스를 올리면 소속 주요 기업들이 말풍선으로 표시되는 헤더 렌더링"""
    safe_name = (
        item["name"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    safe_sector = (
        item["sector"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    safe_stage = (
        item["stage"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    safe_holdings = (
        item["holdings"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    stage_color = item["stage_color"]

    html = f"""
    <style>
      .etf-stage-header-wrap {{
        position: relative;
        display: flex;
        justify-content: space-between;
        align-items: center;
        background-color: #1e293b;
        border-left: 5px solid {stage_color};
        padding: 9px 14px;
        border-radius: 8px;
        margin-bottom: 6px;
        cursor: help;
      }}
      .etf-stage-title-text {{
        color: #f8fafc;
        font-weight: 700;
        font-size: 14px;
        border-bottom: 1px dotted #94a3b8;
        padding-bottom: 1px;
      }}
      .etf-stage-header-wrap:hover .etf-stage-title-text {{
        color: #fbbf24;
        border-bottom-color: #fbbf24;
      }}
      .etf-stage-bubble {{
        display: none;
        position: fixed;
        top: auto;
        left: auto;
        background-color: #020617;
        color: #f8fafc;
        border: 1px solid #38bdf8;
        border-radius: 10px;
        padding: 10px 14px;
        font-size: 12.5px;
        line-height: 1.5;
        max-width: 360px;
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.7);
        z-index: 99999;
        pointer-events: none;
      }}
      .etf-stage-popup-card {{
        display: none;
        position: absolute;
        top: 108%;
        left: 12px;
        background-color: #020617;
        color: #f8fafc;
        border: 1px solid #38bdf8;
        border-radius: 10px;
        padding: 10px 14px;
        font-size: 12.5px;
        line-height: 1.5;
        width: max-content;
        max-width: 360px;
        white-space: normal;
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.75);
        z-index: 9999;
        pointer-events: none;
      }}
      .etf-stage-popup-card::before {{
        content: "";
        position: absolute;
        bottom: 100%;
        left: 24px;
        border-width: 6px;
        border-style: solid;
        border-color: transparent transparent #38bdf8 transparent;
      }}
      .etf-stage-header-wrap:hover .etf-stage-popup-card {{
        display: block;
      }}
      .etf-stage-badge {{
        background-color: {stage_color};
        color: #ffffff;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 700;
        flex-shrink: 0;
        margin-left: 8px;
      }}
    </style>
    <div class="etf-stage-header-wrap">
      <span class="etf-stage-title-text">[{safe_sector}] {safe_name}</span>
      <span class="etf-stage-badge">{safe_stage}</span>
      <div class="etf-stage-popup-card">
        <div style="font-weight:700; color:#38bdf8; margin-bottom:4px;">{safe_name} 주요 구성 기업</div>
        <div style="color:#f8fafc;">{safe_holdings}</div>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def _find_or_install_korean_font_path() -> str | None:
    """PDF 생성 시 한글이 깨지지 않도록 TTF/OTF 한글 폰트 경로를 탐색하거나 설치"""
    here = Path(__file__).resolve()
    candidate_paths = [
        here.parent / "fonts" / "NanumGothic.ttf",
        here.parent.parent / "fonts" / "NanumGothic.ttf",
        here.parent / "NanumGothic.ttf",
        here.parent.parent / "NanumGothic.ttf",
        here.parent / "fonts" / "NotoSansKR-Regular.ttf",
        here.parent.parent / "fonts" / "NotoSansKR-Regular.ttf",
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/NanumGothic.ttf"),
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]

    for p in candidate_paths:
        if p.exists():
            return str(p)

    kr_keywords = (
        "nanum",
        "malgun",
        "noto sans cjk",
        "applegothic",
        "applesdgothic",
        "unbatang",
        "baekmuk",
    )
    for f in fm.fontManager.ttflist:
        low_name = (f.name or "").lower()
        if any(k in low_name for k in kr_keywords) and Path(f.fname).exists():
            return f.fname

    if sys.platform.startswith("linux"):
        try:
            subprocess.run(
                ["apt-get", "update", "-qq"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
            subprocess.run(
                ["apt-get", "install", "-y", "-qq", "fonts-nanum"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=40,
            )
            for p in fm.findSystemFonts(fontpaths=["/usr/share/fonts"], fontext="ttf"):
                if "nanum" in Path(p).name.lower():
                    return p
        except Exception:
            pass

    return None


@st.cache_data(ttl=1800, show_spinner=False)
def _generate_pdf_bytes(items_serializable: list[dict], run_date_str: str) -> bytes:
    """
    주식 단계 오름차순으로 정렬된 ETF들의 30주 이동평균선 차트를
    한 페이지당 2개(좌·우 1행 2열)씩 배치한 PDF 생성 (한글 폰트 내장)
    """
    font_path = _find_or_install_korean_font_path()
    kr_prop = fm.FontProperties(fname=font_path) if font_path else None

    if font_path:
        try:
            fm.fontManager.addfont(font_path)
            registered_name = fm.FontProperties(fname=font_path).get_name()
            plt.rcParams["font.family"] = registered_name
        except Exception:
            pass

    plt.rcParams["axes.unicode_minus"] = False
    buf = BytesIO()

    with PdfPages(buf) as pdf:
        per_page = 2
        total_pages = max(1, (len(items_serializable) + per_page - 1) // per_page)

        for page_idx in range(total_pages):
            batch = items_serializable[page_idx * per_page : (page_idx + 1) * per_page]
            fig, axes = plt.subplots(1, 2, figsize=(11.69, 6.2))
            fig.patch.set_facecolor("#ffffff")

            title_text = (
                f"섹터별 주식단계 리포트 (단계 오름차순 · 최근 2년 주봉 & 30주 이평선)  |  "
                f"기준일: {run_date_str}  ({page_idx + 1}/{total_pages})"
            )
            if kr_prop:
                fig.suptitle(title_text, fontsize=12, fontweight="bold", y=0.97, fontproperties=kr_prop)
            else:
                fig.suptitle(title_text, fontsize=12, fontweight="bold", y=0.97)

            for idx, ax in enumerate(axes):
                if idx >= len(batch):
                    ax.axis("off")
                    continue

                item = batch[idx]
                dates = pd.to_datetime(item["dates"])
                closes = np.array(item["closes"], dtype=float)
                ma30 = np.array(item["ma30"], dtype=float)

                ax.plot(dates, closes, color="#0284c7", linewidth=1.6, label="주봉 종가")
                ax.plot(dates, ma30, color="#ea580c", linewidth=1.8, label="30주 이동평균선")

                ma30_str = f"{item['curr_ma30']:,.0f}" if pd.notna(item["curr_ma30"]) else "-"
                sub_title = (
                    f"[{item['stage']}] {item['name']} ({item['code']})\n"
                    f"섹터: {item['sector']} | 현재가: {item['curr_price']:,.0f}원 | "
                    f"30주선: {ma30_str}원 ({item['dist_pct']:+.2f}%)"
                )
                if kr_prop:
                    ax.set_title(sub_title, fontsize=9.5, fontweight="bold", pad=8, fontproperties=kr_prop)
                else:
                    ax.set_title(sub_title, fontsize=9.5, fontweight="bold", pad=8)

                ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
                ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
                ax.tick_params(axis="x", labelsize=8, rotation=25)
                ax.tick_params(axis="y", labelsize=8)
                ax.grid(True, linestyle="--", alpha=0.35)

                leg = ax.legend(loc="upper left", fontsize=8, frameon=True)
                if kr_prop and leg:
                    for txt in leg.get_texts():
                        txt.set_fontproperties(kr_prop)

            plt.tight_layout(rect=[0.01, 0.02, 0.99, 0.90])
            pdf.savefig(fig, dpi=150)
            plt.close(fig)

    buf.seek(0)
    return buf.getvalue()


def render():
    now = datetime.now(KST)
    run_date_str = now.strftime("%Y-%m-%d")
    file_date_str = now.strftime("%Y%m%d")
    run_timestamp = now.strftime("%Y-%m-%d %H:%M:%S (KST)")

    col_head, col_refresh = st.columns([8, 2])
    with col_head:
        st.markdown("## 📊 섹터별 주식단계 분석 (30주 이동평균선 기준)")
        st.caption(
            f"주식 단계 오름차순(1단계 → 4단계) 정렬 | ETF 제목에 마우스를 올리면 주요 구성 기업 표시 | 조회 시각: {run_timestamp}"
        )
    with col_refresh:
        if st.button("🔄 데이터 새로고침", key="refresh_sector_price_stage"):
            st.cache_data.clear()
            st.rerun()

    normalized_tickers, pre_names = _normalize_tickers_and_names(etf_tickers, {})

    with st.spinner("최근 2년치 ETF 주가 데이터를 불러와 30주 이동평균선을 계산하는 중입니다..."):
        df_daily, mapped_names = _load_2y_etf_prices(normalized_tickers)
        _, merged_names = _normalize_tickers_and_names(etf_tickers, {**pre_names, **mapped_names})
        all_items = _prepare_weekly_stage_items(df_daily, normalized_tickers, merged_names)

    if not all_items:
        st.warning("표시할 ETF 주가 데이터가 없습니다. 네트워크 상태 또는 종목 구성을 확인해 주세요.")
        return

    sectors = ["전체"] + sorted(list({item["sector"] for item in all_items}))
    stages = [
        "전체",
        "1단계 (바닥/기초)",
        "2단계 (상승 국면)",
        "3단계 (천장/횡보)",
        "4단계 (하락 국면)",
    ]

    col_f1, col_f2, col_pdf = st.columns([3, 3, 4])
    with col_f1:
        selected_sector = st.selectbox("대분류 섹터 필터", sectors, index=0, key="stage_sector_filter")
    with col_f2:
        selected_stage = st.selectbox("주식 단계 필터", stages, index=0, key="stage_phase_filter")

    filtered_items = [
        item
        for item in all_items
        if (selected_sector == "전체" or item["sector"] == selected_sector)
        and (selected_stage == "전체" or item["stage"] == selected_stage)
    ]
    filtered_items.sort(key=lambda x: (x["stage_order"], -x["dist_pct"], x["name"]))

    serializable_for_pdf = [
        {
            "ticker": it["ticker"],
            "code": it["code"],
            "name": it["name"],
            "sector": it["sector"],
            "stage": it["stage"],
            "stage_order": it["stage_order"],
            "curr_price": it["curr_price"],
            "curr_ma30": it["curr_ma30"],
            "dist_pct": it["dist_pct"],
            "dates": [d.strftime("%Y-%m-%d") for d in it["weekly_close"].index],
            "closes": it["weekly_close"].tolist(),
            "ma30": it["ma30"].tolist(),
        }
        for it in filtered_items
    ]

    pdf_filename = f"섹터별_주식단계_{file_date_str}.pdf"
    with col_pdf:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if serializable_for_pdf:
            pdf_bytes = _generate_pdf_bytes(serializable_for_pdf, run_date_str)
            st.download_button(
                label=f"📥 PDF 다운로드 ({pdf_filename})",
                data=pdf_bytes,
                file_name=pdf_filename,
                mime="application/pdf",
                use_container_width=True,
                key="download_sector_stage_pdf",
            )

    if not filtered_items:
        st.info("선택한 필터 조건에 해당하는 ETF가 없습니다.")
        return

    with st.expander(f"📋 섹터별 주식단계 요약표 보기 (총 {len(filtered_items)}개 ETF · 단계 오름차순)", expanded=False):
        summary_df = pd.DataFrame([
            {
                "주식 단계": it["stage"],
                "대분류 섹터": it["sector"],
                "ETF명": it["name"],
                "주요 구성 기업": it["holdings"],
                "종목코드": it["code"],
                "현재가(원)": f"{it['curr_price']:,.0f}",
                "30주 이동평균(원)": f"{it['curr_ma30']:,.0f}" if pd.notna(it["curr_ma30"]) else "-",
                "30주선 대비(%)": f"{it['dist_pct']:+.2f}%",
            }
            for it in filtered_items
        ])
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # 한 화면(한 행)에 ETF 2개씩 나란히 배치 (주식 단계 오름차순)
    for i in range(0, len(filtered_items), 2):
        cols = st.columns(2)
        for col_idx in range(2):
            item_idx = i + col_idx
            if item_idx >= len(filtered_items):
                break

            item = filtered_items[item_idx]
            with cols[col_idx]:
                _render_etf_title_with_bubble(item)
                fig = _build_plotly_weekly_chart(item)
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{item['code']}_{item_idx}")
