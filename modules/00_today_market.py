# modules/00_today_market.py
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
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

# ETF명 Hover 시 주요 구성 종목 말풍선 표시용 매핑
ETF_TOP_HOLDINGS: dict[str, list[str]] = {
    "KODEX 반도체": ["SK하이닉스", "삼성전자", "한미반도체", "주성엔지니어링", "심텍"],
    "KODEX AI반도체TOP2플러스": ["SK하이닉스", "삼성전자", "SK스퀘어", "삼성전기", "한미반도체"],
    "KODEX AI반도체핵심장비": ["한미반도체", "원익IPS", "주성엔지니어링", "이오테크닉스", "HPSP"],
    "SOL AI반도체소부장": ["이수페타시스", "한미반도체", "주성엔지니어링", "대덕전자", "심텍"],
    "TIGER 200 IT": ["SK스퀘어", "SK하이닉스", "삼성전자", "삼성전기", "삼성SDI"],
    "SOL 반도체전공정": ["주성엔지니어링", "HPSP", "원익IPS", "한솔케미칼", "피에스케이"],
    "SOL 반도체후공정": ["이수페타시스", "한미반도체", "이오테크닉스", "리노고업", "대덕전자"],
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
    "TIGER 인터넷TOP10": ["카카오", "서진시스템", "NAVER", "대한광통신", "안랩"],
    "RISE 플랫폼테마": ["NHN", "NICE정보통신", "카카오", "SOOP", "NAVER"],
    "TIGER 미디어컨텐츠": ["스튜디오드래곤", "CJ ENM", "에스엠", "JYP Ent.", "디어유"],
    "RISE 네트워크인프라": ["삼성전자", "sk하이닉스", "삼성전기", "LG이노텍", "이수페타시스"],
    "TIGER 200 헬스케어": ["셀트리온", "삼성바이오로직스", "유한양행", "SK바이오팜", "한미약품"],
    "TIGER 조선TOP10": ["HD한국조선해양", "HD현대중공업", "한화오션", "삼성중공업", "HD현대마린솔루션"],
    "PLUS K방산": ["한화에어로스페이스", "한국항공우주", "한화오션", "LIG디펜스앤에어로스페이스", "현대로템"],
    "KODEX 자동차": ["기아", "현대모비스", "한국타이어앤테크놀로지", "현대차", "HL만도"],
    "TIGER 200 중공업": ["두산에너빌리티", "HD한국조선해양", "삼성중공업", "HD현대일렉트릭", "HD현대중공업"],
    "HANARO CAPEX설비투자iSelect": ["두산밥캣", "HD건설기계", "LS ELECTRIC", "효성중공업", "두산에너빌리티"],
    "KODEX 건설": ["삼성E&A", "현대건설", "대우건설", "GS건설", "DL이앤씨"],
    "KODEX 철강": ["POSCO홀딩스", "현대제철", "고려아연", "풍산", "에이치브이엠"],
    "KODEX 에너지화학": ["LG화학", "SK이노베이션", "HD현대", "S-Oil", "한화솔루션"],
    "TIGER 2차전지테마": ["LG에너지솔루션", "POSCO홀딩스", "삼성SDI", "SK이노베이션", "LG화학"],
    "TIGER 2차전지소재Fn": ["포스코퓨처엠", "에코프로", "	POSCO홀딩스", "에코프로비엠", "LG화학"],
    "TIGER 화장품": ["아모레퍼시픽", "코스맥스", "LG생활건강", "파마리서치", "한국콜마"],
    "HANARO K-뷰티": ["아모레퍼시픽", "에이피알", "코스맥스", "LG생활건강", "한국콜마"],
    "TIGER 중국소비테마": ["코스맥스", "파라다이스", "삼양식품", "덴티움", "아모레퍼시픽"],
    "TIGER 여행레저": ["파라다이스", "아시아나항공", "강원랜드", "대한항공", "호텔신라", "롯데관광개발"],
    "ACE KPOP포커스": ["하이브", "에스엠", "JYP Ent.", "와이지엔터테인먼트", "CJ ENM"],
    "KODEX K-콘텐츠": ["카카오", "NAVER", "크래프톤", "하이브", "NC"],
    "KODEX 게임산업": ["크래프톤", "NC", "펄어비스", "넷마블", "시프트업"],
    "TIGER 게임TOP10": ["크래프톤", "NC", "펄어비스", "넷마블", "NHN"],
    "TIGER 경기방어": ["셀트리온", "KT&G", "KT", "삼성바이오로직스", "SK텔레콤"],
    "TIGER 200 생활소비재": ["KT&G", "한국전력", "에이피알", "삼양식품", "아모레퍼시픽"],
    "KODEX 경기소비재": ["한진칼", "코웨이", "LG전자", "신세계", "강원랜드"],
    "HANARO Fn K-푸드": ["삼양식품", "CJ제일제당", "농심", "오리온", "오뚜기"],
    "MIDAS 중소형액티브": ["삼성전기", "두산", "테스", "효성중공업", "엘앤씨바이오"],
    "ACE K휴머노이드로봇산업TOP2+": ["로보티즈", "현대차", "레인보우로보틱스", "에스피지", "현대모비스"],
    "KoAct 광통신&위성네트워크액티브": ["RF머트리얼즈", "우리로", "대한광통신", "RFHIC", "케이엠더블유"],
    "TIGER 글로벌AI사이버보안": ["Cloudflare", "Okta ", "Zscaler", "Palo Alto Networks", "Fortinet"],
    "KODEX 웹툰&드라마": ["CJ ENM", "스튜디오드래곤", "카카오", "NAVER", "SAMG엔터"],
    "SOL 우주항공밸류체인": ["에이치브이엠", "스피어", "쎄트렉아이", "인텔리안테크", "대주전자재료"],
    "마이티 신약포커스바이오액티브": ["올릭스", "오스코텍", "한올바이오파마", "알지노믹스", "한미약품"],
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
        return "조선/방산/우주"

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
        short_t = t.replace(".KS", "").replace(".KQ", "")
        candidate_name = (
            base_names.get(t)
            or base_names.get(short_t)
            or naver_names.get(t)
            or naver_names.get(short_t)
        )
        resolved_names[t] = _clean_etf_name(candidate_name, t)

        if t not in returns and not etf_data.empty:
            col_target = t if t in etf_data.columns else (short_t if short_t in etf_data.columns else None)
            if col_target is not None:
                series = etf_data[col_target].dropna()
                if len(series) >= 2:
                    prev_c = float(series.iloc[-2])
                    curr_c = float(series.iloc[-1])
                    if prev_c > 0:
                        returns[t] = (curr_c - prev_c) / prev_c * 100.0

    return returns, resolved_names


def _extract_close_df(raw_obj, tickers: list[str]) -> pd.DataFrame:
    """다양한 형태의 종가 DataFrame을 2차원 (날짜 x 종목) 형태로 정규화"""
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


def _load_etf_history_safely(tickers: list[str], period: str = "2y") -> tuple[pd.DataFrame, dict[str, str]]:
    """
    download_etf_data를 호출하되, 빈 결과/짧은 기간/예외 발생 시
    yfinance 2년 일봉 데이터를 직접 다운로드해 충분한 과거 시세를 확보
    """
    df_raw = pd.DataFrame()
    name_map: dict[str, str] = {}

    try:
        res = download_etf_data(tickers, period=period)
        if isinstance(res, tuple) and len(res) >= 2:
            df_raw = _extract_close_df(res[0], tickers)
            if isinstance(res[1], dict):
                name_map = {str(k): str(v) for k, v in res[1].items() if k and v}
        elif isinstance(res, pd.DataFrame):
            df_raw = _extract_close_df(res, tickers)
    except Exception:
        pass

    if df_raw.empty or len(df_raw.dropna(how="all")) < 40:
        try:
            dl = yf.download(tickers, period="2y", auto_adjust=True, progress=False)
            fallback_df = _extract_close_df(dl, tickers)
            if not fallback_df.empty and len(fallback_df.dropna(how="all")) > len(df_raw.dropna(how="all")):
                df_raw = fallback_df
        except Exception:
            pass

    return df_raw, name_map


def _sortino_from_returns(ret: pd.Series, mar: float = 0.0, periods_per_year: int = 252) -> float:
    """일간 수익률 시리즈 기준 연율화 Sortino Ratio 계산"""
    ret = ret.dropna()
    if len(ret) < 5:
        return np.nan
    mar_daily = (1 + mar) ** (1 / periods_per_year) - 1
    excess = ret - mar_daily
    downside = excess[excess < 0]
    if len(downside) < 2:
        return np.nan
    downside_dev = downside.std(ddof=1) * np.sqrt(periods_per_year)
    if downside_dev == 0 or np.isnan(downside_dev):
        return np.nan
    return float(excess.mean() * periods_per_year / downside_dev)


def _get_sortino_ma20_timeline_desc(
    price_df: pd.DataFrame,
    name_map: dict[str, str],
    last_n_days: int = 10,
    ma_filter_days: int = 20,
    top_n: int = 20,
) -> pd.DataFrame:
    """
    Sortino Ratio 기반 필터링 타임라인 → 이동평균선 20일 조건 충족군 계산 후
    날짜 기준 최근순(내림차순)으로 정렬된 DataFrame 반환
    """
    if price_df.empty:
        return pd.DataFrame()

    clean_df = _extract_close_df(price_df, [])
    clean_df = clean_df.drop(columns=["^KS11", "코스피"], errors="ignore").ffill()
    valid_days = clean_df.dropna(how="all").index
    if len(valid_days) < ma_filter_days:
        return pd.DataFrame()

    trading_days = valid_days[-last_n_days:]
    wins = [63, 126, 252]
    daily_top: dict[str, list[str]] = {}

    for day in trading_days:
        end_idx = clean_df.index.get_indexer_for([day])[0]
        scores: dict[str, float] = {}

        for col in clean_df.columns:
            s = clean_df[col].iloc[: end_idx + 1].dropna()
            if len(s) < ma_filter_days:
                continue
            ma_val = s.rolling(ma_filter_days).mean().iloc[-1]
            if pd.isna(ma_val) or s.iloc[-1] < ma_val:
                continue

            vals = []
            for win in wins:
                start_idx = max(0, end_idx - (win - 1))
                w_prices = clean_df[col].iloc[start_idx : end_idx + 1].dropna()
                if len(w_prices) < 15:
                    continue
                v = _sortino_from_returns(w_prices.pct_change().dropna())
                if pd.notna(v):
                    vals.append(v)

            if vals:
                scores[col] = float(np.mean(vals))

        if scores:
            ranked_cols = (
                pd.Series(scores).sort_values(ascending=False).head(top_n).index.tolist()
            )
            ranked_names = [
                _clean_etf_name(
                    name_map.get(str(c))
                    or name_map.get(str(c).replace(".KS", "").replace(".KQ", "")),
                    str(c),
                )
                for c in ranked_cols
            ]
        else:
            ranked_names = []

        while len(ranked_names) < top_n:
            ranked_names.append("")

        daily_top[day.strftime("%Y-%m-%d")] = ranked_names

    if not daily_top:
        return pd.DataFrame()

    df_timeline = pd.DataFrame.from_dict(
        daily_top,
        orient="index",
        columns=[f"Top {i + 1}" for i in range(top_n)],
    )
    df_timeline.index.name = "Date"
    # 날짜 기준 최근순 정렬
    df_timeline = df_timeline.sort_index(ascending=False)
    return df_timeline


def _get_top_holdings_text(etf_name: str) -> str:
    """ETF명에 대응하는 주요 구성 종목 문자열 반환"""
    if not etf_name:
        return ""
    if etf_name in ETF_TOP_HOLDINGS:
        return ", ".join(ETF_TOP_HOLDINGS[etf_name])

    for key, holdings in ETF_TOP_HOLDINGS.items():
        if key in etf_name or etf_name in key:
            return ", ".join(holdings)

    return "구성 종목 정보 준비 중"


def _render_sortino_timeline_with_tooltips(df_timeline: pd.DataFrame) -> None:
    """
    Sortino Ratio 기반 필터링 타임라인(날짜 최근순)을 HTML 테이블로 렌더링하며,
    각 ETF명 위에 마우스를 올리면 주요 구성 종목이 말풍선으로 표시됩니다.
    """
    if df_timeline.empty:
        st.info("Sortino Ratio(20일 이동평균선 충족군) 타임라인을 계산할 과거 시세 데이터가 부족합니다.")
        return

    style_block = """
    <style>
      .sortino-table-wrap {
        width: 100%;
        overflow-x: auto;
        overflow-y: visible;
        border: 1px solid #334155;
        border-radius: 10px;
        background-color: #0f172a;
        padding: 12px 8px 48px 8px;
      }
      .sortino-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        color: #e2e8f0;
        font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
      }
      .sortino-table th, .sortino-table td {
        border: 1px solid #1e293b;
        padding: 7px 9px;
        white-space: nowrap;
        text-align: left;
      }
      .sortino-table th {
        background-color: #1e293b;
        color: #f8fafc;
        position: sticky;
        top: 0;
        z-index: 2;
      }
      .sortino-table th:first-child, .sortino-table td:first-child {
        position: sticky;
        left: 0;
        background-color: #0f172a;
        font-weight: 700;
        color: #38bdf8;
        z-index: 1;
      }
      .sortino-table th:first-child {
        z-index: 3;
        background-color: #1e293b;
      }
      .etf-tooltip-item {
        display: inline-block;
        cursor: help;
        border-bottom: 1px dotted #64748b;
      }
      .etf-tooltip-item:hover {
        color: #fbbf24;
        border-bottom-color: #fbbf24;
      }
      .etf-tooltip-box {
        position: relative;
        display: inline-block;
      }
      .etf-tooltip-box .bubble-popup {
        display: none;
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        background-color: #020617;
        color: #f8fafc;
        border: 1px solid #38bdf8;
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 12px;
        line-height: 1.45;
        min-width: 220px;
        max-width: 320px;
        white-space: normal;
        box-shadow: 0 10px 24px rgba(0, 0, 0, 0.65);
        z-index: 10000;
        pointer-events: none;
      }
      .etf-tooltip-box .bubble-top {
        bottom: 130%;
      }
      .etf-tooltip-box .bubble-top::after {
        content: "";
        position: absolute;
        top: 100%;
        left: 50%;
        margin-left: -6px;
        border-width: 6px;
        border-style: solid;
        border-color: #38bdf8 transparent transparent transparent;
      }
      .etf-tooltip-box .bubble-bottom {
        top: 130%;
      }
      .etf-tooltip-box .bubble-bottom::before {
        content: "";
        position: absolute;
        bottom: 100%;
        left: 50%;
        margin-left: -6px;
        border-width: 6px;
        border-style: solid;
        border-color: transparent transparent #38bdf8 transparent;
      }
      .etf-tooltip-box:hover .bubble-popup {
        display: block;
      }
    </style>
    """

    header_cells = [f"<th>{df_timeline.index.name or 'Date'}</th>"] + [
        f"<th>{col}</th>" for col in df_timeline.columns
    ]
    thead_html = f"<thead><tr>{''.join(header_cells)}</tr></thead>"

    body_rows = []
    for row_idx, (dt_label, row) in enumerate(df_timeline.iterrows()):
        popup_dir_class = "bubble-bottom" if row_idx < 2 else "bubble-top"
        cells = [f"<td>{dt_label}</td>"]
        for col in df_timeline.columns:
            etf_name = str(row[col]) if pd.notna(row[col]) else ""
            if not etf_name:
                cells.append("<td></td>")
                continue

            holdings_str = _get_top_holdings_text(etf_name)
            safe_etf = (
                etf_name.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            safe_holdings = (
                holdings_str.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

            cell_html = (
                f"<td>"
                f"<span class='etf-tooltip-box'>"
                f"<span class='etf-tooltip-item'>{safe_etf}</span>"
                f"<span class='bubble-popup {popup_dir_class}'>"
                f"<b>{safe_etf}</b><br/>"
                f"<span style='color:#94a3b8;'>주요 구성종목:</span> {safe_holdings}"
                f"</span>"
                f"</span>"
                f"</td>"
            )
            cells.append(cell_html)
        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    tbody_html = f"<tbody>{''.join(body_rows)}</tbody>"
    table_html = (
        f"{style_block}"
        f"<div class='sortino-table-wrap'>"
        f"<table class='sortino-table'>{thead_html}{tbody_html}</table>"
        f"</div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


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
        df_raw, mapped_from_dl = _load_etf_history_safely(normalized_tickers, period="2y")
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

    # --------------------------------------------------------------------------
    # 비트맵(트리맵) 아래: Sortino Ratio 기반 필터링 타임라인 → 이동평균선 20일 조건 충족군
    # --------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### Sortino Ratio 기반 필터링 타임라인")
    st.markdown("→ 이동평균선 20일 조건 충족군")

    df_sortino_ma20 = _get_sortino_ma20_timeline_desc(
        price_df=df_raw,
        name_map={**merged_names, **etf_names},
        last_n_days=10,
        ma_filter_days=20,
        top_n=20,
    )

    if df_sortino_ma20.empty:
        st.info("Sortino Ratio(20일 이동평균선 충족군) 타임라인을 계산할 과거 시세 데이터가 부족합니다.")
    else:
        _render_sortino_timeline_with_tooltips(df_sortino_ma20)
