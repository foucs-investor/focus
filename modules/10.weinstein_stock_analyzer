# -*- coding: utf-8 -*-
"""
스탠 와인스타인 4단계 참고용 주식 분석기
- 기업명은 한 줄에 하나씩 입력합니다.
- 중복 기업명 입력을 허용하며, 입력한 순서대로 각각 별도 결과를 생성합니다.
- 50일선 / 200일선, 거래량, Mansfield 상대강도, 단계별 배경 음영을 표시합니다.

주의: 50/200일 이동평균 기반 단계 판정은 와인스타인의 원래 30주선 규칙을
그대로 재현한 것이 아니라, 일봉 데이터용 참고용 휴리스틱입니다.
"""

from datetime import date, timedelta
from pathlib import Path
import re
import unicodedata

import FinanceDataReader as fdr
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

MENU_NAME = "와인스타인 4단계 분석"


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
    # FinanceDataReader의 KOSPI 지수 심볼
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
    # 종목코드를 직접 입력한 경우도 지원
    if q.isdigit():
        found = listing[listing["Code"] == q.zfill(6)]
        if not found.empty:
            return found.iloc[0]
    exact = listing[listing["Name"].map(normalize_name) == q]
    if not exact.empty:
        return exact.iloc[0]
    contains = listing[listing["Name"].map(normalize_name).str.contains(re.escape(q), na=False)]
    if len(contains) == 1:
        return contains.iloc[0]
    if len(contains) > 1:
        return None, contains[["Name", "Code"]].head(15)
    return None


def classify_stages(df):
    """일봉 기반 참고 판정. 50/200선 위치, 200선 기울기, 가격의 200선 이격을 사용."""
    close = df["Close"]
    ma50 = df["MA50"]
    ma200 = df["MA200"]
    slope = ma200.diff(20) / ma200.shift(20)
    distance = (close / ma200) - 1

    # 장기선이 뚜렷하게 상승하고 주가/단기선이 위에 있을 때 Stage 2
    s2 = (close > ma200) & (ma50 > ma200) & (slope > 0.01)
    # 장기선 하락 + 주가/단기선 아래: Stage 4
    s4 = (close < ma200) & (ma50 < ma200) & (slope < -0.01)
    # 상승 추세 이후 장기선 근처로 밀리거나 단기선이 장기선 아래로 내려가는 분배/전환
    s3 = ((ma50 > ma200) & (close < ma50) & (distance > -0.12)) | (
        (close < ma200) & (ma50 >= ma200) & (slope >= -0.01)
    )
    # 나머지 중 장기선 기울기가 완만하고 주가가 장기선 주변이면 Stage 1
    s1 = ~(s2 | s3 | s4)

    stage = pd.Series("Stage 1", index=df.index, dtype="object")
    stage.loc[s2] = "Stage 2"
    stage.loc[s3] = "Stage 3"
    stage.loc[s4] = "Stage 4"
    # NaN 구간은 분석 전 구간으로 표시
    stage.loc[ma200.isna()] = "데이터 축적 중"
    return stage


STAGE_COLORS = {
    "Stage 1": "rgba(55, 125, 235, 0.13)",
    "Stage 2": "rgba(70, 190, 85, 0.15)",
    "Stage 3": "rgba(245, 185, 45, 0.17)",
    "Stage 4": "rgba(225, 65, 65, 0.14)",
}


def add_stage_shading(fig, df):
    stage = df["Stage"]
    if stage.empty:
        return
    start = stage.index[0]
    current = stage.iloc[0]
    for i in range(1, len(stage)):
        if stage.iloc[i] != current:
            end = stage.index[i]
            color = STAGE_COLORS.get(current)
            if color:
                fig.add_vrect(
                    x0=start,
                    x1=end,
                    fillcolor=color,
                    opacity=1,
                    line_width=0,
                    layer="below",
                    row=1,
                    col=1,
                )
            start, current = end, stage.iloc[i]
    color = STAGE_COLORS.get(current)
    if color:
        fig.add_vrect(
            x0=start,
            x1=stage.index[-1],
            fillcolor=color,
            opacity=1,
            line_width=0,
            layer="below",
            row=1,
            col=1,
        )


def build_chart(df, benchmark, company_name, code):
    data = df.copy()
    data["MA50"] = data["Close"].rolling(50).mean()
    data["MA200"] = data["Close"].rolling(200).mean()
    data["Stage"] = classify_stages(data)

    # Mansfield RS: 종목/코스피 상대비율의 52주 평균 대비 편차(%)
    if not benchmark.empty and "Close" in benchmark.columns:
        rel = data["Close"].div(benchmark["Close"].reindex(data.index).ffill())
        rs_base = rel.rolling(252, min_periods=100).mean()
        data["MansfieldRS"] = ((rel / rs_base) - 1) * 100
    else:
        data["MansfieldRS"] = float("nan")

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        row_heights=[0.62, 0.17, 0.21],
        subplot_titles=("주가 · 50일선 · 200일선", "거래량", "Mansfield 상대강도 (KOSPI 대비)"),
    )
    fig.add_trace(
        go.Candlestick(
            x=data.index,
            open=data["Open"],
            high=data["High"],
            low=data["Low"],
            close=data["Close"],
            name="주가",
            increasing_line_color="#16a6a0",
            decreasing_line_color="#e45b63",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["MA50"],
            name="50일선",
            line=dict(color="#2474ff", width=1.8),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["MA200"],
            name="200일선",
            line=dict(color="#ff334d", width=2),
        ),
        row=1,
        col=1,
    )

    vol_colors = [
        "#16a6a0" if c >= o else "#e45b63"
        for c, o in zip(data["Close"], data["Open"])
    ]
    fig.add_trace(
        go.Bar(
            x=data.index,
            y=data["Volume"],
            name="거래량",
            marker_color=vol_colors,
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["MansfieldRS"],
            name="Mansfield RS",
            line=dict(color="#333333", width=1.3),
        ),
        row=3,
        col=1,
    )
    fig.add_hline(y=0, line_dash="dash", line_color="#246bff", row=3, col=1)

    add_stage_shading(fig, data)

    # 최신 종가/단계/이동평균 요약 주석
    last = data.iloc[-1]
    stage_text = last["Stage"]
    ma50_text = f'{last["MA50"]:,.0f}' if pd.notna(last["MA50"]) else "계산 중"
    ma200_text = f'{last["MA200"]:,.0f}' if pd.notna(last["MA200"]) else "계산 중"
    rs_text = f'{last["MansfieldRS"]:.1f}' if pd.notna(last["MansfieldRS"]) else "계산 중"

    fig.update_layout(
        title=f"{company_name} ({code}) | 현재 {stage_text} | 종가 {last['Close']:,.0f}원",
        height=900,
        template="plotly_white",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(l=50, r=30, t=100, b=40),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="가격 (원)", row=1, col=1)
    fig.update_yaxes(title_text="거래량", row=2, col=1)
    fig.update_yaxes(title_text="RS (%)", row=3, col=1)
    return fig, data, {
        "stage": stage_text,
        "close": last["Close"],
        "ma50": ma50_text,
        "ma200": ma200_text,
        "rs": rs_text,
    }


def make_analysis(data, summary):
    last = data.iloc[-1]
    ma50 = last["MA50"]
    ma200 = last["MA200"]
    stage = summary["stage"]

    # 가격대는 실제 돌파 저항선을 자동 탐지한 값이 아니라 차트 참고용 최근 60일 고저 범위
    recent = data.tail(60)
    resistance = float(recent["High"].max())
    support = float(recent["Low"].min())
    rs = last["MansfieldRS"]

    if stage == "Stage 2":
        verdict = "상승 추세(Stage 2) 조건에 부합"
        action = "50일선 또는 돌파 가격대 지지 확인 후 분할 접근 검토"
    elif stage == "Stage 4":
        verdict = "하락 추세(Stage 4) 조건에 부합"
        action = "신규 매수는 보수적으로 접근하고 추세 회복 확인"
    elif stage == "Stage 3":
        verdict = "상승 추세 약화(Stage 3) 가능성"
        action = "보유자는 50일선 이탈과 거래량을 점검"
    else:
        verdict = "바닥 형성/횡보(Stage 1) 가능성"
        action = "저항 돌파 및 50일선·200일선 방향 확인 대기"

    return {
        "verdict": verdict,
        "action": action,
        "support": support,
        "resistance": resistance,
        "ma50": ma50,
        "ma200": ma200,
        "rs": rs,
    }


def render():
    st.title("스탠 와인스타인 4단계 주식 분석기")
    st.caption("50일선·200일선 기준 | 단계별 음영 | 거래량 | Mansfield 상대강도")

    with st.sidebar:
        st.header("분석 설정")
        years = st.selectbox("조회 기간", [3, 5, 7, 10], index=1)
        st.caption("일봉 데이터 기준이며 200일선 계산을 위해 최소 1년 이상의 데이터가 필요합니다.")
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
        output_dir = Path("weinstein_results")
        output_dir.mkdir(exist_ok=True)

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

            fig, analyzed, summary = build_chart(price, benchmark, company, code)
            analysis = make_analysis(analyzed, summary)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("현재 단계", summary["stage"])
            c2.metric("종가", f'{summary["close"]:,.0f}원')
            c3.metric("50일선", f'{summary["ma50"]}원')
            c4.metric("200일선", f'{summary["ma200"]}원')

            st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### 단계 판정 근거")
            st.write(analysis["verdict"])
            st.write(f"- 50일선: {summary['ma50']}원")
            st.write(f"- 200일선: {summary['ma200']}원")
            st.write(f"- Mansfield RS: {summary['rs']}")
            st.write(f"- 최근 60거래일 고점 참고값: {analysis['resistance']:,.0f}원")
            st.write(f"- 최근 60거래일 저점 참고값: {analysis['support']:,.0f}원")

            st.markdown("#### 매매 관찰 기준")
            st.write(f"- 대응 의견: {analysis['action']}")
            st.write(f"- 저항 후보: 최근 60거래일 고점 {analysis['resistance']:,.0f}원 부근")
            st.write(f"- 지지 후보: 최근 60거래일 저점 {analysis['support']:,.0f}원 부근")
            st.caption("자동 산출된 지지·저항은 단순 최근 60거래일 고저값이며, 확정 매수·매도 신호가 아닙니다. 손절·목표가는 사용자가 별도로 검증해야 합니다.")

            safe = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", company)
            # 같은 회사 중복 입력 시에도 결과 파일이 덮어써지지 않도록 입력 순번을 포함
            csv_path = output_dir / f"{idx:02d}_{safe}_{code}.csv"
            analyzed.to_csv(csv_path, encoding="utf-8-sig")
            st.download_button(
                f"{idx}번 {company} 분석 데이터 CSV 다운로드",
                data=analyzed.to_csv(encoding="utf-8-sig").encode("utf-8-sig"),
                file_name=csv_path.name,
                mime="text/csv",
                key=f"csv_{idx}_{code}",
            )

    st.markdown("---")
    st.caption(
        "면책: 본 프로그램은 공개 가격 데이터와 단순 규칙을 이용한 교육·참고용 도구입니다. "
        "50/200일선 방식은 스탠 와인스타인의 원래 주봉 30주 이동평균 규칙과 다릅니다. "
        "단계 분류는 자동화된 근사치이며 투자 판단이나 수익을 보장하지 않습니다."
    )
