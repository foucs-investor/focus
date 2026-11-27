import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

# Matplotlib 환경 설정
try:
    import matplotlib
    matplotlib.use('Agg')
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# ETF 목록 정의
etf_tickers = {
    # 축 1. AI 패러다임과 공급망
    "091160.KS": "KODEX 반도체",
    "395160.KS": "KODEX AI반도체TOP2플러스",
    "471990.KS": "KODEX AI반도체핵심장비",
    "455850.KS": "SOL AI반도체소부장",
    "139260.KS": "TIGER 200 IT",
    "475300.KS": "SOL 반도체전공정",
    "475310.KS": "SOL 반도체후공정",

    # 축 2. 전력 인프라 및 신재생
    "487240.KS": "KODEX AI전력핵심설비",
    "433500.KS": "ACE 원자력테마딥서치",
    "381570.KS": "HANARO FN친환경에너지",
    "457990.KS": "PLUS 태양광&ESS",

    # 축 3. 금리, 주주환원, 그리고 밸류업
    "091170.KS": "KODEX 은행",
    "140700.KS": "KODEX 보험",
    "102970.KS": "KODEX 증권",
    "307520.KS": "TIGER 지주회사",
    "210780.KS": "TIGER 코스피고배당",
    "261140.KS": "TIGER 우선주",
    "495850.KS": "KODEX 코리아밸류업",

    # 축 4. 금리 인하 수혜 및 미래 성장판
    "244580.KS": "KODEX 바이오",
    "364970.KS": "TIGER 바이오 TOP 10",
    "498050.KS": "HANARO 바이오코리아액티브",
    "0229F0.KS": "마이티 신약포커스바이오액티브",
    "307510.KS": "TIGER 의료기기",
    "483020.KS": "KIWOOM 의료AI",
    "445290.KS": "KODEX 로봇액티브",
    "157490.KS": "TIGER SOFTWARE",
    "365000.KS": "TIGER 인터넷TOP10",
    "427120.KS": "RISE 플랫폼테마",
    "228810.KS": "TIGER 미디어컨텐츠",
    "367760.KS": "RISE 5G테크",
    "227540.KS": "TIGER 200 헬스케어",

    # 축 5. 중공업 르네상스 및 글로벌 공급망 재편
    "494670.KS": "TIGER 조선TOP10",
    "449450.KS": "PLUS K방산",
    "091180.KS": "KODEX 자동차",
    "139230.KS": "TIGER 200 중공업",
    "454320.KS": "HANARO CAPEX설비투자iSelect",
    "117700.KS": "KODEX 건설",
    "117680.KS": "KODEX 철강",
    "117460.KS": "KODEX 에너지화학",
    "305540.KS": "TIGER 2차전지테마",
    "462010.KS": "TIGER 2차전지소재Fn",

    # 축 6. 소비 패러다임과 문화 콘텐츠
    "228790.KS": "TIGER 화장품",
    "479850.KS": "HANARO K-뷰티",
    "150460.KS": "TIGER 중국소비테마",
    "228800.KS": "TIGER 여행레저",
    "475050.KS": "ACE KPOP포커스",
    "266360.KS": "KODEX 미디어&엔터테인먼트",
    "300950.KS": "KODEX 게임산업",
    "364990.KS": "TIGER 게임TOP10",
    "139280.KS": "TIGER 경기방어",
    "227560.KS": "TIGER 200 생활소비재",
    "266390.KS": "KODEX 경기소비재",
    "438900.KS": "HANARO Fn K-푸드",
    "395150.KS": "KODEX 웹툰&드라마",

    # 기타
    "438740.KS": "MIDAS 중소형액티브",
    "418670.KS": "TIGER 글로벌AI사이버보안",

    #로봇
    "0177X0.KS": "ACE K휴머노이드로봇산업TOP2+",
    
    #우주항공
    "0207G0.KS": "SOL 우주항공밸류체인",
}

@st.cache_data(ttl=300)
def download_etf_data(tickers_dict, period="1mo"):
    tickers = list(tickers_dict.keys())
    ticker_to_name = {k.replace('.KS', '').replace('.KQ', ''): v for k, v in tickers_dict.items()}

    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)['Close']
    if isinstance(data, pd.Series):
        data = data.to_frame()
    data.columns = [col.replace('.KS', '').replace('.KQ', '') if isinstance(col, str) else col for col in data.columns]
    data = data.dropna(how='all', axis=1)

    return data, ticker_to_name

def clean_theme_name(full_name):
    brand_keywords = [
        "KODEX", "TIGER", "SOL", "ACE", "HANARO", "PLUS", "RISE", "KIWOOM", "MIDAS", "KoAct",
        "200", "TOP10", "TOP2플러스", "Fn", "iSelect", "액티브", "포커스", "테마"
    ]
    name = full_name
    for kw in brand_keywords:
        name = name.replace(kw, "").strip()

    theme_alias = {
        "AI전력핵심설비": "전력기기",
        "AI반도체핵심장비": "반도체장비",
        "AI반도체": "반도체",
        "반도체소부장": "반도체소부장",
        "바이오코리아": "제약바이오",
        "바이오": "제약바이오",
        "미디어&엔터테인먼트": "엔터",
        "미디어컨텐츠": "엔터",
        "광통신&위성네트워크": "광통신",
        "5G테크": "광통신",
        "태양광&ESS": "친환경에너지",
        "코스피고배당": "고배당",
        "코리아밸류업": "밸류업",
        "글로벌AI사이버보안": "보안",
        "원자력테마딥서치": "원자력",
    }
    clean_n = theme_alias.get(name, name)
    return clean_n if len(clean_n) > 0 else full_name

def pack_circles_non_overlapping(df, iterations=300):
    df = df.sort_values(by="Radius", ascending=False).reset_index(drop=True)
    n = len(df)

    x = np.zeros(n)
    y = np.zeros(n)
    r = df["Radius"].values

    for i in range(1, n):
        angle = i * 137.5 * (np.pi / 180)
        dist = np.sqrt(i) * (r[0] * 0.7)
        x[i] = dist * np.cos(angle)
        y[i] = dist * np.sin(angle)

    for it in range(iterations):
        overlapping = False
        for i in range(n):
            for j in range(i + 1, n):
                dx = x[j] - x[i]
                dy = y[j] - y[i]
                dist = np.hypot(dx, dy)
                min_dist = r[i] + r[j] + 0.4

                if dist < min_dist:
                    overlapping = True
                    overlap = min_dist - dist
                    if dist == 0:
                        dx, dy = 1.0, 0.0
                        dist = 1.0

                    nx = dx / dist
                    ny = dy / dist

                    x[i] -= nx * overlap * 0.5
                    y[i] -= ny * overlap * 0.5
                    x[j] += nx * overlap * 0.5
                    y[j] += ny * overlap * 0.5

        x *= 0.985
        y *= 0.985

        if not overlapping:
            break

    df['X'] = x
    df['Y'] = y
    return df

def assign_color(ret):
    if ret > 1.5:
        return '#C00000'
    elif ret > 0:
        return '#8B2500'
    elif ret < -1.5:
        return '#1F4E78'
    elif ret < 0:
        return '#2C3E50'
    else:
        return '#404040'

@st.cache_data(ttl=1800)
def download_stock_relative_data(ticker, start_date, end_date):
    try:
        stock_data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        if stock_data.empty:
            return None

        close_data = stock_data['Close']
        if isinstance(close_data, pd.DataFrame):
            if not close_data.empty and ticker in close_data.columns:
                close_data = close_data[ticker]
            else:
                return None
        elif not isinstance(close_data, pd.Series):
            return None

        return close_data
    except Exception:
        return None
