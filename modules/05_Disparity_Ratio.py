import io
import re
import warnings
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# ==============================================================================
# 1. 메뉴명 정의 (Streamlit 자동 로더 인식용)
# ==============================================================================
MENU_NAME = "기업별 이격도"

warnings.filterwarnings("ignore")

# ====================== 폰트 및 스타일 설정 ======================
plt.rcParams["axes.unicode_minus"] = False


# ====================== 정밀 티커 검색 (완전 일치 우선) ======================
def get_ticker_by_name(company_input: str) -> tuple:
    """기업명(예: 파마리서치, 펌텍코리아)을 입력받아 (6자리 종목코드, 정식 기업명) 튜플을 반환합니다.

    - 완전 일치(Exact Match)를 최우선 검색합니다.
    - 입력어가 포함된 종목들 중 글자 수가 가장 짧은 대표 종목을 선택합니다.
    """
    clean_input = company_input.strip()
    clean_input_no_space = clean_input.replace(" ", "")

    # 1. 사용자가 6자리 숫자 종목코드를 직접 입력한 경우
    if clean_input.isdigit() and len(clean_input) == 6:
        return clean_input, f"기업({clean_input})"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    # 2. KRX 상장법인 전체 목록 검색 (가장 정확한 상장사 DB)
    try:
        krx_url = (
            "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download"
        )
        res = requests.get(krx_url, headers=headers, timeout=5)
        res.encoding = "euc-kr"

        df_krx = pd.read_html(io.StringIO(res.text))[0]
        df_krx["종목코드"] = df_krx["종목코드"].astype(str).str.zfill(6)
        df_krx["회사명_공백제거"] = df_krx["회사명"].str.replace(" ", "")

        # 2-1. 완전 일치 (Exact Match) 확인 (예: '파마리서치' == '파마리서치')
        exact_match = df_krx[
            df_krx["회사명_공백제거"] == clean_input_no_space
        ]
        if not exact_match.empty:
            return (
                exact_match.iloc[0]["종목코드"],
                exact_match.iloc[0]["회사명"],
            )

        # 2-2. 부분 일치 시 글자 수 및 접두사 기준 정렬하여 최적 종목 선택
        contains_match = df_krx[
            df_krx["회사명_공백제거"].str.contains(
                clean_input_no_space, na=False
            )
        ].copy()
        if not contains_match.empty:
            contains_match["name_len"] = contains_match["회사명"].str.len()
            # 이름 길이 순 정렬 (짧은 명칭 우선, 예: '파마리서치'가 '파마리서치바이오'보다 우선)
            contains_match = contains_match.sort_values(by="name_len")
            return (
                contains_match.iloc[0]["종목코드"],
                contains_match.iloc[0]["회사명"],
            )
    except Exception:
        pass

    # 3. 네이버 증권 자동완성 API (보조 검색)
    try:
        naver_api_url = f"https://ac.finance.naver.com/ac?q={clean_input}&target=index%2Cstock"
        res = requests.get(naver_api_url, headers=headers, timeout=5)
        data = res.json()

        items = data.get("items", [])
        if items and len(items) > 0 and len(items[0]) > 0:
            candidates = []
            for item in items[0]:
                name = item[0][0] if isinstance(item[0], list) else item[0]
                code = item[1][0] if isinstance(item[1], list) else item[1]

                # 완전 일치하는 경우 즉시 반환
                if name.replace(" ", "") == clean_input_no_space:
                    return code, name

                if clean_input_no_space in name.replace(" ", ""):
                    candidates.append((code, name, len(name)))

            # 후보 목록 중 이름 길이가 가장 짧은 것 선택
            if candidates:
                candidates.sort(key=lambda x: x[2])
                return candidates[0][0], candidates[0][1]
    except Exception:
        pass

    return None, clean_input


# ====================== Stage 판단 ======================
def get_current_stage(df):
    if len(df) < 200:
        return 0
    try:
        ma = float(df["200MA"].iloc[-1])
        price = float(df["Close"].iloc[-1])
        if pd.isna(ma) or pd.isna(price):
            return 0
        if price > ma * 1.08:
            return 2
        elif price > ma * 0.97:
            return 3
        elif price < ma * 0.92:
            return 4
        else:
            return 1
    except Exception:
        return 0


# ==============================================================================
# 2. Streamlit 렌더링 함수
# ==============================================================================
def render():
    st.title("📈 기업별 이격도 분석")
    st.caption(
        "기업명 또는 종목코드를 입력하여 이동평균선과 30일 이격도를 분석합니다."
    )

    # 입력 폼 생성
    with st.form(key="search_form"):
        user_input = st.text_input(
            label="분석할 기업명 또는 종목코드를 콤마(,)로 구분하여 입력하세요",
            value="에프앤가이드, 티앤엘, 파마리서치",
            placeholder="예: 삼성전자, 카카오, 005930",
        )
        submit_button = st.form_submit_button(
            label="🔍 분석 실행", use_container_width=True
        )

    if submit_button and user_input.strip():
        items = [x.strip() for x in user_input.split(",") if x.strip()]

        if not items:
            st.warning("분석할 기업명을 최소 하나 이상 입력해주세요.")
            return

        with st.spinner("데이터 수집 및 차트 생성 중..."):
            for item_input in items:
                ticker, name = get_ticker_by_name(item_input)

                if not ticker:
                    st.warning(
                        f"⚠️ '{item_input}'의 종목코드를 찾지 못했습니다. 건너뜁니다."
                    )
                    continue

                # 데이터 다운로드
                end_date = datetime.today()
                start_date = end_date - timedelta(days=365 * 3 + 250)
                chart_start = end_date - timedelta(days=365 * 2.5)

                # 코스닥(.KQ) 시도 후 코스피(.KS) 순서로 조회
                df = yf.download(
                    f"{ticker}.KQ",
                    start=start_date,
                    end=end_date,
                    progress=False,
                    auto_adjust=True,
                )
                if df.empty or len(df) < 100:
                    df = yf.download(
                        f"{ticker}.KS",
                        start=start_date,
                        end=end_date,
                        progress=False,
                        auto_adjust=True,
                    )

                if df.empty or len(df) < 100:
                    st.error(
                        f"❌ {name} ({ticker}) 데이터를 가져오지 못했습니다. (종목코드 또는 데이터 공급 상태 확인 필요)"
                    )
                    continue

                # MultiIndex 컬럼 정제
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

                # 기술지표 계산
                df["200MA"] = df["Close"].rolling(200).mean()
                df["MA30"] = df["Close"].rolling(30).mean()
                df["Disparity"] = (df["Close"] / df["MA30"]) * 100

                df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
                df["Vol_1M_Avg"] = (
                    df["Volume"].shift(1).rolling(window=20, min_periods=10).mean()
                )

                # 데이터 슬라이싱
                df_chart = df.loc[chart_start:].copy()
                df_chart = df_chart.dropna(subset=["Close", "200MA", "MA30"])

                if len(df_chart) < 30:
                    st.error(f"❌ {name} 차트 표시 구간 데이터가 부족합니다.")
                    continue

                # Stage 판단
                stage_num = get_current_stage(df_chart)
                stage_text = {
                    1: "Stage 1 (축적)",
                    2: "Stage 2 (상승)",
                    3: "Stage 3 (분산)",
                    4: "Stage 4 (하락)",
                }
                current_stage = stage_text.get(stage_num, "판단불가")

                # ================= 차트 그리기 =================
                fig = plt.figure(figsize=(16, 6))
                gs = fig.add_gridspec(1, 2, width_ratios=[1.15, 1], wspace=0.12)

                left_gs = gs[0].subgridspec(
                    2, 1, height_ratios=[3.2, 1], hspace=0.15
                )

                # 왼쪽 상단: 가격 차트
                ax_price = fig.add_subplot(left_gs[0])
                ax_price.plot(
                    df_chart.index,
                    df_chart["Close"],
                    label="종가",
                    color="#1f4e9c",
                    linewidth=2.0,
                )
                ax_price.plot(
                    df_chart.index,
                    df_chart["200MA"],
                    label="200일선",
                    color="#f97316",
                    linestyle="--",
                    linewidth=1.8,
                )
                ax_price.set_title(
                    f"{name} ({ticker}) | {current_stage}",
                    fontsize=13,
                    fontweight="bold",
                    pad=10,
                )
                ax_price.set_ylabel("주가 (원)", fontsize=10)
                ax_price.grid(True, linestyle=":", alpha=0.5)
                ax_price.legend(loc="upper left", fontsize=9)

                # 왼쪽 하단: 거래량 차트
                ax_vol = fig.add_subplot(left_gs[1], sharex=ax_price)
                vol_colors = [
                    (
                        "#ef4444"
                        if (
                            pd.notna(v)
                            and pd.notna(a)
                            and v >= a * 2.0
                        )
                        else "#64748b"
                    )
                    for v, a in zip(df_chart["Volume"], df_chart["Vol_1M_Avg"])
                ]
                ax_vol.bar(
                    df_chart.index,
                    df_chart["Volume"],
                    color=vol_colors,
                    alpha=0.85,
                    width=1.0,
                )
                ax_vol.set_ylabel("거래량", fontsize=10)
                ax_vol.grid(True, linestyle=":", alpha=0.4)

                # 오른쪽: 이격도 차트
                ax2 = fig.add_subplot(gs[1])

                last_idx = -1
                last_close = float(df_chart["Close"].iloc[last_idx])
                last_ma30 = float(df_chart["MA30"].iloc[last_idx])
                last_disparity = float(df_chart["Disparity"].iloc[last_idx])
                last_date_str = df_chart.index[last_idx].strftime("%Y-%m-%d")

                ax2.plot(
                    df_chart.index,
                    df_chart["Close"],
                    color="black",
                    linewidth=1.8,
                    label=f"주가 ({last_close:,.0f})",
                )
                ax2.plot(
                    df_chart.index,
                    df_chart["MA30"],
                    color="tab:orange",
                    linestyle="--",
                    linewidth=1.5,
                    label=f"30일선 ({last_ma30:,.0f})",
                )

                ax3 = ax2.twinx()
                dis_offset = df_chart["Disparity"] - 100
                colors = [
                    "#ff7f0e" if v >= 0 else "#1f77b4" for v in dis_offset
                ]

                ax3.bar(
                    df_chart.index,
                    dis_offset,
                    bottom=100,
                    color=colors,
                    alpha=0.35,
                    width=0.9,
                )
                ax3.plot(
                    df_chart.index,
                    df_chart["Disparity"],
                    color="darkgoldenrod",
                    linewidth=1.8,
                    label=f"이격도 ({last_disparity:.1f}%)",
                )
                ax3.axhline(
                    100, color="crimson", linestyle="-", alpha=0.7, linewidth=1.2
                )

                ax2.set_ylabel("주가 (원)", fontsize=10)
                ax3.set_ylabel(
                    "이격도 (%)", color="darkgoldenrod", fontsize=10
                )
                ax2.grid(True, linestyle=":", alpha=0.5)

                ax2.legend(loc="upper left", fontsize=9)
                ax3.legend(loc="upper right", fontsize=9)
                ax2.set_title(
                    f"이격도 분석 ({last_date_str})",
                    fontsize=12,
                    fontweight="bold",
                    pad=10,
                )

                plt.tight_layout()

                # Streamlit 화면 출력
                st.subheader(f"📊 {name} ({ticker})")
                st.pyplot(fig)
                plt.close(fig)