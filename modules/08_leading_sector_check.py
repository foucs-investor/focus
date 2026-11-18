import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

MENU_NAME = "주도업종 체크"

def render():
    st.title("📊 AI Tech Breadth & Peak-out Dashboard")
    st.markdown("AI 관련 주요 테크 종목들의 시장 넓이(Breadth)와 피크아웃 위험도를 분석하는 대시보드입니다.")

    # ============================================================
    # 1. Universe
    # ============================================================
    stocks = {
        # US
        "NVDA": "NVDA", "AVGO": "AVGO", "AMD": "AMD", "TSM": "TSM", "ASML": "ASML",
        "MU": "MU", "ARM": "ARM", "QCOM": "QCOM", "MRVL": "MRVL", "LRCX": "LRCX",
        "AMAT": "AMAT", "KLAC": "KLAC", "CDNS": "CDNS", "SNPS": "SNPS", "ANET": "ANET",
        "TXN": "TXN", "ON": "ON", "DELL": "DELL",

        # Added US
        "Sandisk": "SNDK", "Intel": "INTC", "Amkor": "AMKR", "WesternDigital": "WDC",
        "Seagate": "STX", "Lumentum": "LITE", "Corning": "GLW", "AsteraLabs": "ALAB",

        # Korea
        "Samsung": "005930.KS", "SKHynix": "000660.KS", "SamsungElectroMechanics": "009150.KS",

        # Japan
        "TokyoElectron": "8035.T", "Advantest": "6857.T", "Disco": "6146.T",
        "Lasertec": "6920.T", "SCREEN": "7735.T", "Socionext": "6526.T",
        "Murata": "6981.T", "Kioxia": "285A.T",

        # Taiwan / ADR
        "UMC": "UMC", "ASE": "ASX", "Himax": "HIMX", "SiliconMotion": "SIMO"
    }

    # ============================================================
    # 2. Download (캐싱 적용)
    # ============================================================
    @st.cache_data(ttl=3600)
    def load_data():
        raw = yf.download(
            list(stocks.values()),
            period="3y",
            auto_adjust=True,
            progress=False,
            group_by="column"
        )
        prices = raw["Close"].copy()
        reverse = {ticker: name for name, ticker in stocks.items()}
        prices = prices.rename(columns=reverse)
        prices = prices.sort_index()
        prices = prices.ffill(limit=5)
        return prices

    with st.spinner("주가 데이터 다운로드 및 계산 중..."):
        prices = load_data()

    minimum_data = 220
    valid_columns = prices.columns[prices.notna().sum() >= minimum_data]
    excluded_columns = [col for col in prices.columns if col not in valid_columns]
    prices = prices[valid_columns]

    st.info(f"분석 종목 수: {len(prices.columns)}개 | 분석 기간: {prices.index.min().date()} ~ {prices.index.max().date()}")
    if excluded_columns:
        st.warning(f"데이터 부족으로 제외된 종목: {', '.join(excluded_columns)}")

    # ============================================================
    # 3. Positive / Negative Counts
    # ============================================================
    periods = {"1M": 21, "2M": 42, "3M": 63, "6M": 126}
    count_rows = []

    for period_name, days in periods.items():
        period_return = prices.pct_change(days, fill_method=None).iloc[-1].dropna()
        positive_count = int((period_return > 0).sum())
        negative_count = int((period_return < 0).sum())
        zero_count = int((period_return == 0).sum())
        total_count = len(period_return)

        count_rows.append({
            "Period": period_name,
            "Positive": positive_count,
            "Negative": negative_count,
            "Zero": zero_count,
            "Total": total_count,
            "Positive_Ratio": positive_count / total_count * 100 if total_count > 0 else np.nan,
            "Negative_Ratio": negative_count / total_count * 100 if total_count > 0 else np.nan
        })

    count_table = pd.DataFrame(count_rows).set_index("Period")

    st.subheader("📈 기간별 상승·하락 종목 수")
    st.dataframe(count_table.style.format({
        "Positive": "{:.0f}", "Negative": "{:.0f}", "Zero": "{:.0f}", "Total": "{:.0f}",
        "Positive_Ratio": "{:.1f}%", "Negative_Ratio": "{:.1f}%"
    }), use_container_width=True)

    # ============================================================
    # 4. Breadth Indicators
    # ============================================================
    ma20 = prices.rolling(20, min_periods=15).mean()
    ma60 = prices.rolling(60, min_periods=45).mean()
    ma200 = prices.rolling(200, min_periods=160).mean()
    ret60 = prices.pct_change(60, fill_method=None)

    above_ma20_count = ((prices > ma20) & prices.notna() & ma20.notna()).sum(axis=1)
    above_ma60_count = ((prices > ma60) & prices.notna() & ma60.notna()).sum(axis=1)
    above_ma200_count = ((prices > ma200) & prices.notna() & ma200.notna()).sum(axis=1)
    positive_60d_count = ((ret60 > 0) & ret60.notna()).sum(axis=1)

    ma20_available = (prices.notna() & ma20.notna()).sum(axis=1)
    ma60_available = (prices.notna() & ma60.notna()).sum(axis=1)
    ma200_available = (prices.notna() & ma200.notna()).sum(axis=1)
    ret60_available = ret60.notna().sum(axis=1)

    above_ma20 = above_ma20_count / ma20_available.replace(0, np.nan) * 100
    above_ma60 = above_ma60_count / ma60_available.replace(0, np.nan) * 100
    above_ma200 = above_ma200_count / ma200_available.replace(0, np.nan) * 100
    positive_60d = positive_60d_count / ret60_available.replace(0, np.nan) * 100

    breadth = pd.DataFrame({
        "Above_MA20": above_ma20,
        "Above_MA60": above_ma60,
        "Above_MA200": above_ma200,
        "Positive_60D": positive_60d
    })

    # ============================================================
    # 5. Breadth Score
    # ============================================================
    breadth["Breadth_Score"] = (
        breadth["Above_MA20"] * 0.20 +
        breadth["Above_MA60"] * 0.35 +
        breadth["Above_MA200"] * 0.25 +
        breadth["Positive_60D"] * 0.20
    )

    breadth["Breadth_Score_MA5"] = breadth["Breadth_Score"].rolling(5, min_periods=3).mean()
    breadth["Breadth_Score_MA10"] = breadth["Breadth_Score"].rolling(10, min_periods=5).mean()
    breadth["Breadth_Diff"] = breadth["Breadth_Score"] - breadth["Breadth_Score_MA5"]
    breadth["Slope_3D"] = breadth["Breadth_Score_MA5"] - breadth["Breadth_Score_MA5"].shift(3)
    breadth["Slope_5D"] = breadth["Breadth_Score_MA5"] - breadth["Breadth_Score_MA5"].shift(5)
    breadth["Slope_10D"] = breadth["Breadth_Score_MA5"] - breadth["Breadth_Score_MA5"].shift(10)
    breadth["Falling_Days_10D"] = breadth["Breadth_Score_MA5"].diff().lt(0).rolling(10).sum()

    # ============================================================
    # 6. Equal-weight AI Tech Index
    # ============================================================
    normalized_prices = (prices / prices.apply(lambda col: col.dropna().iloc[0] if not col.dropna().empty else np.nan)) * 100
    breadth["AI_Tech_Index"] = normalized_prices.mean(axis=1)
    breadth["AI_Index_MA20"] = breadth["AI_Tech_Index"].rolling(20).mean()
    breadth["AI_Index_20D_Return"] = breadth["AI_Tech_Index"].pct_change(20) * 100
    breadth["AI_Index_60D_Return"] = breadth["AI_Tech_Index"].pct_change(60) * 100

    # ============================================================
    # 7. Divergence Detection
    # ============================================================
    index_high_20 = breadth["AI_Tech_Index"].rolling(20).max()
    breadth_high_20 = breadth["Breadth_Score_MA5"].rolling(20).max()

    breadth["Index_Near_20D_High"] = breadth["AI_Tech_Index"] >= index_high_20 * 0.99
    breadth["Breadth_From_20D_High"] = breadth["Breadth_Score_MA5"] - breadth_high_20

    breadth["Bearish_Divergence"] = (
        breadth["Index_Near_20D_High"] &
        (breadth["Breadth_From_20D_High"] <= -10) &
        (breadth["Slope_5D"] < 0)
    )

    breadth["Strong_Bearish_Divergence"] = (
        breadth["Index_Near_20D_High"] &
        (breadth["Breadth_From_20D_High"] <= -20) &
        (breadth["Slope_10D"] < 0)
    )

    # ============================================================
    # 8. Risk Level
    # ============================================================
    def classify_risk(row):
        score = row["Breadth_Score_MA5"]
        slope_5d = row["Slope_5D"]
        slope_10d = row["Slope_10D"]
        divergence = row["Bearish_Divergence"]
        strong_divergence = row["Strong_Bearish_Divergence"]

        if pd.isna(score): return "데이터 부족"
        if strong_divergence: return "피크아웃 강경고"
        if divergence: return "피크아웃 경고"
        if score >= 70 and slope_5d >= 0: return "강세"
        if score >= 70 and slope_5d < 0: return "고점 경계"
        if score >= 60: return "정상"
        if score >= 50:
            if slope_5d < 0: return "주의"
            return "중립"
        if score >= 35:
            if slope_10d < 0: return "위험"
            return "약세 반등"
        if score < 35 and slope_5d < 0: return "투매 진행"
        if score < 35 and slope_5d >= 0: return "투매 후 반등"
        return "중립"

    breadth["Risk_Level"] = breadth.apply(classify_risk, axis=1)

    # ============================================================
    # 9. Current Summary
    # ============================================================
    latest = breadth.dropna(subset=["Breadth_Score_MA5"]).iloc[-1]
    latest_date = breadth.dropna(subset=["Breadth_Score_MA5"]).index[-1]

    st.markdown("---")
    st.subheader(f"📌 현재 시장 요약 (기준일: {latest_date.date()})")

    col1, col2, col3 = st.columns(3)
    col1.metric("현재 위험 단계", f"{latest['Risk_Level']}")
    col2.metric("Breadth Score (MA5)", f"{latest['Breadth_Score_MA5']:.1f}")
    col3.metric("20일선 위 종목 비율", f"{latest['Above_MA20']:.1f}%")

    # ============================================================
    # 10 ~ 14. Charts (Matplotlib -> st.pyplot)
    # ============================================================
    st.markdown("### 📊 주요 기술적 지표 차트")

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(breadth.index, breadth["Above_MA20"], label="Above MA20")
    ax.plot(breadth.index, breadth["Above_MA60"], label="Above MA60")
    ax.plot(breadth.index, breadth["Above_MA200"], label="Above MA200")
    ax.axhline(70, linestyle="--", alpha=0.5, color="gray")
    ax.axhline(50, linestyle="--", alpha=0.5, color="gray")
    ax.axhline(30, linestyle="--", alpha=0.5, color="gray")
    ax.set_title("AI Tech Moving Average Breadth")
    ax.set_ylabel("Stocks (%)")
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(alpha=0.3)
    st.pyplot(fig)

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(breadth.index, breadth["Breadth_Score"], alpha=0.30, label="Daily Breadth Score")
    ax.plot(breadth.index, breadth["Breadth_Score_MA5"], linewidth=2, label="Breadth Score MA5", color="orange")
    ax.axhline(70, linestyle="--", alpha=0.5, color="gray")
    ax.axhline(60, linestyle="--", alpha=0.5, color="gray")
    ax.set_title("AI Tech Breadth Score")
    ax.set_ylabel("Score")
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(alpha=0.3)
    st.pyplot(fig)

    fig, ax1 = plt.subplots(figsize=(12, 4))
    line1 = ax1.plot(breadth.index, breadth["AI_Tech_Index"], color="black", linewidth=1.8, label="AI Tech Equal-weight Index")
    ax1.set_ylabel("AI Tech Index", color="black")
    ax2 = ax1.twinx()
    line2 = ax2.plot(breadth.index, breadth["Breadth_Score_MA5"], color="orange", linewidth=2.0, label="Breadth Score MA5")
    ax2.set_ylabel("Breadth Score", color="orange")
    ax2.set_ylim(0, 100)
    
    strong_divergence_dates = breadth.index[breadth["Strong_Bearish_Divergence"].fillna(False)]
    for date in strong_divergence_dates:
        ax1.axvline(date, color="red", alpha=0.10)

    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper left")
    ax1.set_title("AI Tech Equal-weight Index vs Breadth")
    st.pyplot(fig)

    # ============================================================
    # 15. Recent 30 Trading Days (최신순 내림차순 정렬)
    # ============================================================
    st.markdown("### 📋 최근 30 거래일 상세 데이터")
    recent_columns = [
        "Above_MA20", "Above_MA60", "Above_MA200", "Positive_60D",
        "Breadth_Score_MA5", "Breadth_Diff", "Slope_5D", "Slope_10D",
        "Breadth_From_20D_High", "Bearish_Divergence", "Strong_Bearish_Divergence", "Risk_Level"
    ]
    
    # tail(30)을 가져온 뒤 sort_index(ascending=False)를 적용하여 최신 날짜가 맨 위에 오도록 정렬
    recent_table = breadth[recent_columns].tail(30).sort_index(ascending=False)

    st.dataframe(recent_table.style.format({
        "Above_MA20": "{:.1f}", "Above_MA60": "{:.1f}", "Above_MA200": "{:.1f}",
        "Positive_60D": "{:.1f}", "Breadth_Score_MA5": "{:.1f}", "Breadth_Diff": "{:+.1f}",
        "Slope_5D": "{:+.1f}", "Slope_10D": "{:+.1f}", "Breadth_From_20D_High": "{:+.1f}"
    }), use_container_width=True)
