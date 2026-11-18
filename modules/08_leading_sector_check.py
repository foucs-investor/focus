# ============================================================
# AI Tech Breadth & Peak-out Dashboard
# ============================================================

!pip install yfinance -q

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from IPython.display import display

MENU_NAME = "주도업종 체크"

# ============================================================
# 1. Universe
# ============================================================

stocks = {
    # US
    "NVDA": "NVDA",
    "AVGO": "AVGO",
    "AMD": "AMD",
    "TSM": "TSM",
    "ASML": "ASML",
    "MU": "MU",
    "ARM": "ARM",
    "QCOM": "QCOM",
    "MRVL": "MRVL",
    "LRCX": "LRCX",
    "AMAT": "AMAT",
    "KLAC": "KLAC",
    "CDNS": "CDNS",
    "SNPS": "SNPS",
    "ANET": "ANET",
    "TXN": "TXN",
    "ON": "ON",
    "DELL": "DELL",

    # Added US
    "Sandisk": "SNDK",
    "Intel": "INTC",
    "Amkor": "AMKR",
    "WesternDigital": "WDC",
    "Seagate": "STX",
    "Lumentum": "LITE",
    "Corning": "GLW",
    "AsteraLabs": "ALAB",

    # Korea
    "Samsung": "005930.KS",
    "SKHynix": "000660.KS",
    "SamsungElectroMechanics": "009150.KS",

    # Japan
    "TokyoElectron": "8035.T",
    "Advantest": "6857.T",
    "Disco": "6146.T",
    "Lasertec": "6920.T",
    "SCREEN": "7735.T",
    "Socionext": "6526.T",
    "Murata": "6981.T",
    "Kioxia": "285A.T",

    # Taiwan / ADR
    "UMC": "UMC",
    "ASE": "ASX",
    "Himax": "HIMX",
    "SiliconMotion": "SIMO"
}

# ============================================================
# 2. Download
# ============================================================

raw = yf.download(
    list(stocks.values()),
    period="3y",
    auto_adjust=True,
    progress=False,
    group_by="column"
)

prices = raw["Close"].copy()

reverse = {
    ticker: name
    for name, ticker in stocks.items()
}

prices = prices.rename(columns=reverse)
prices = prices.sort_index()

# 국가별 휴장일 차이를 고려
prices = prices.ffill(limit=5)

# 200일선 계산이 가능한 종목만 사용
minimum_data = 220

valid_columns = prices.columns[
    prices.notna().sum() >= minimum_data
]

excluded_columns = [
    col for col in prices.columns
    if col not in valid_columns
]

prices = prices[valid_columns]

print(f"분석 종목 수: {len(prices.columns)}개")

if excluded_columns:
    print("데이터 부족으로 제외:", excluded_columns)

print(
    f"분석 기간: "
    f"{prices.index.min().date()} ~ "
    f"{prices.index.max().date()}"
)

# ============================================================
# 3. Positive / Negative Counts
# ============================================================

periods = {
    "1M": 21,
    "2M": 42,
    "3M": 63,
    "6M": 126
}

count_rows = []

for period_name, days in periods.items():

    period_return = (
        prices
        .pct_change(days, fill_method=None)
        .iloc[-1]
        .dropna()
    )

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
        "Positive_Ratio": (
            positive_count / total_count * 100
            if total_count > 0 else np.nan
        ),
        "Negative_Ratio": (
            negative_count / total_count * 100
            if total_count > 0 else np.nan
        )
    })

count_table = pd.DataFrame(
    count_rows
).set_index("Period")

print("\n기간별 상승·하락 종목 수")

display(
    count_table.style.format({
        "Positive": "{:.0f}",
        "Negative": "{:.0f}",
        "Zero": "{:.0f}",
        "Total": "{:.0f}",
        "Positive_Ratio": "{:.1f}%",
        "Negative_Ratio": "{:.1f}%"
    })
)

# ============================================================
# 4. Breadth Indicators
# ============================================================

ma20 = prices.rolling(
    20,
    min_periods=15
).mean()

ma60 = prices.rolling(
    60,
    min_periods=45
).mean()

ma200 = prices.rolling(
    200,
    min_periods=160
).mean()

ret60 = prices.pct_change(
    60,
    fill_method=None
)

# 각 날짜마다 실제 데이터가 있는 종목만 계산
valid_count = prices.notna().sum(axis=1)

above_ma20_count = (
    (prices > ma20) &
    prices.notna() &
    ma20.notna()
).sum(axis=1)

above_ma60_count = (
    (prices > ma60) &
    prices.notna() &
    ma60.notna()
).sum(axis=1)

above_ma200_count = (
    (prices > ma200) &
    prices.notna() &
    ma200.notna()
).sum(axis=1)

positive_60d_count = (
    (ret60 > 0) &
    ret60.notna()
).sum(axis=1)

ma20_available = (
    prices.notna() &
    ma20.notna()
).sum(axis=1)

ma60_available = (
    prices.notna() &
    ma60.notna()
).sum(axis=1)

ma200_available = (
    prices.notna() &
    ma200.notna()
).sum(axis=1)

ret60_available = ret60.notna().sum(axis=1)

above_ma20 = (
    above_ma20_count /
    ma20_available.replace(0, np.nan) *
    100
)

above_ma60 = (
    above_ma60_count /
    ma60_available.replace(0, np.nan) *
    100
)

above_ma200 = (
    above_ma200_count /
    ma200_available.replace(0, np.nan) *
    100
)

positive_60d = (
    positive_60d_count /
    ret60_available.replace(0, np.nan) *
    100
)

breadth = pd.DataFrame({
    "Above_MA20": above_ma20,
    "Above_MA60": above_ma60,
    "Above_MA200": above_ma200,
    "Positive_60D": positive_60d
})

# ============================================================
# 5. Breadth Score
# ============================================================

# 단기 20%, 중기 35%, 장기 25%, 수익률 확산 20%
breadth["Breadth_Score"] = (
    breadth["Above_MA20"] * 0.20 +
    breadth["Above_MA60"] * 0.35 +
    breadth["Above_MA200"] * 0.25 +
    breadth["Positive_60D"] * 0.20
)

# 노이즈 축소
breadth["Breadth_Score_MA5"] = (
    breadth["Breadth_Score"]
    .rolling(5, min_periods=3)
    .mean()
)

breadth["Breadth_Score_MA10"] = (
    breadth["Breadth_Score"]
    .rolling(10, min_periods=5)
    .mean()
)

# 당일 점수와 5일 평균의 차이
breadth["Breadth_Diff"] = (
    breadth["Breadth_Score"] -
    breadth["Breadth_Score_MA5"]
)

# 기울기
breadth["Slope_3D"] = (
    breadth["Breadth_Score_MA5"] -
    breadth["Breadth_Score_MA5"].shift(3)
)

breadth["Slope_5D"] = (
    breadth["Breadth_Score_MA5"] -
    breadth["Breadth_Score_MA5"].shift(5)
)

breadth["Slope_10D"] = (
    breadth["Breadth_Score_MA5"] -
    breadth["Breadth_Score_MA5"].shift(10)
)

# 최근 10일 중 점수가 하락한 날짜 수
breadth["Falling_Days_10D"] = (
    breadth["Breadth_Score_MA5"]
    .diff()
    .lt(0)
    .rolling(10)
    .sum()
)

# ============================================================
# 6. Equal-weight AI Tech Index
# ============================================================

# 개별 종목을 시작점 100으로 정규화
normalized_prices = (
    prices /
    prices.apply(
        lambda col: col.dropna().iloc[0]
        if not col.dropna().empty
        else np.nan
    )
) * 100

# 동일가중 지수
breadth["AI_Tech_Index"] = (
    normalized_prices.mean(axis=1)
)

breadth["AI_Index_MA20"] = (
    breadth["AI_Tech_Index"]
    .rolling(20)
    .mean()
)

breadth["AI_Index_20D_Return"] = (
    breadth["AI_Tech_Index"]
    .pct_change(20) *
    100
)

breadth["AI_Index_60D_Return"] = (
    breadth["AI_Tech_Index"]
    .pct_change(60) *
    100
)

# ============================================================
# 7. Divergence Detection
# ============================================================

# 지수는 20일 신고가 부근인데
# Breadth Score는 최근 20일 고점 대비 약해지는 경우
index_high_20 = (
    breadth["AI_Tech_Index"]
    .rolling(20)
    .max()
)

breadth_high_20 = (
    breadth["Breadth_Score_MA5"]
    .rolling(20)
    .max()
)

breadth["Index_Near_20D_High"] = (
    breadth["AI_Tech_Index"] >=
    index_high_20 * 0.99
)

breadth["Breadth_From_20D_High"] = (
    breadth["Breadth_Score_MA5"] -
    breadth_high_20
)

breadth["Bearish_Divergence"] = (
    breadth["Index_Near_20D_High"] &
    (breadth["Breadth_From_20D_High"] <= -10) &
    (breadth["Slope_5D"] < 0)
)

# 강한 다이버전스:
# 지수는 고점권인데 Breadth가 고점보다 20점 이상 낮음
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

    if pd.isna(score):
        return "데이터 부족"

    if strong_divergence:
        return "피크아웃 강경고"

    if divergence:
        return "피크아웃 경고"

    if score >= 70 and slope_5d >= 0:
        return "강세"

    if score >= 70 and slope_5d < 0:
        return "고점 경계"

    if score >= 60:
        return "정상"

    if score >= 50:
        if slope_5d < 0:
            return "주의"
        return "중립"

    if score >= 35:
        if slope_10d < 0:
            return "위험"
        return "약세 반등"

    if score < 35 and slope_5d < 0:
        return "투매 진행"

    if score < 35 and slope_5d >= 0:
        return "투매 후 반등"

    return "중립"

breadth["Risk_Level"] = breadth.apply(
    classify_risk,
    axis=1
)

# ============================================================
# 9. Current Summary
# ============================================================

latest = breadth.dropna(
    subset=["Breadth_Score_MA5"]
).iloc[-1]

latest_date = breadth.dropna(
    subset=["Breadth_Score_MA5"]
).index[-1]

latest_summary = pd.DataFrame({
    "현재값": {
        "20일선 위 종목 비율": latest["Above_MA20"],
        "60일선 위 종목 비율": latest["Above_MA60"],
        "200일선 위 종목 비율": latest["Above_MA200"],
        "60일 수익률 플러스 비율": latest["Positive_60D"],
        "Breadth Score": latest["Breadth_Score"],
        "Breadth Score MA5": latest["Breadth_Score_MA5"],
        "Breadth Diff": latest["Breadth_Diff"],
        "3일 기울기": latest["Slope_3D"],
        "5일 기울기": latest["Slope_5D"],
        "10일 기울기": latest["Slope_10D"],
        "최근 10일 하락 일수": latest["Falling_Days_10D"],
        "20일 고점 대비 Breadth": latest["Breadth_From_20D_High"]
    }
})

print(f"\n기준일: {latest_date.date()}")

display(
    latest_summary.style.format("{:.1f}")
)

print(f"현재 위험 단계: {latest['Risk_Level']}")
print(
    "Bearish Divergence:",
    bool(latest["Bearish_Divergence"])
)
print(
    "Strong Bearish Divergence:",
    bool(latest["Strong_Bearish_Divergence"])
)

# ============================================================
# 10. Positive / Negative Count Chart
# ============================================================

count_plot = count_table[
    ["Positive", "Negative"]
]

ax = count_plot.plot(
    kind="bar",
    figsize=(10, 5)
)

ax.set_title(
    "AI Tech Positive / Negative Count"
)
ax.set_xlabel("")
ax.set_ylabel("Number of Stocks")
ax.tick_params(
    axis="x",
    rotation=0
)
ax.grid(
    axis="y",
    alpha=0.3
)

plt.tight_layout()
plt.show()

# ============================================================
# 11. Moving Average Breadth
# ============================================================

plt.figure(figsize=(15, 6))

plt.plot(
    breadth.index,
    breadth["Above_MA20"],
    label="Above MA20"
)

plt.plot(
    breadth.index,
    breadth["Above_MA60"],
    label="Above MA60"
)

plt.plot(
    breadth.index,
    breadth["Above_MA200"],
    label="Above MA200"
)

plt.axhline(
    70,
    linestyle="--",
    alpha=0.5
)

plt.axhline(
    50,
    linestyle="--",
    alpha=0.5
)

plt.axhline(
    30,
    linestyle="--",
    alpha=0.5
)

plt.title(
    "AI Tech Moving Average Breadth"
)
plt.ylabel("Stocks (%)")
plt.ylim(0, 100)
plt.legend()
plt.grid(alpha=0.3)

plt.tight_layout()
plt.show()

# ============================================================
# 12. Breadth Score
# ============================================================

plt.figure(figsize=(15, 6))

plt.plot(
    breadth.index,
    breadth["Breadth_Score"],
    alpha=0.30,
    label="Daily Breadth Score"
)

plt.plot(
    breadth.index,
    breadth["Breadth_Score_MA5"],
    linewidth=2,
    label="Breadth Score MA5"
)

plt.axhline(
    70,
    linestyle="--",
    alpha=0.5
)

plt.axhline(
    60,
    linestyle="--",
    alpha=0.5
)

plt.axhline(
    50,
    linestyle="--",
    alpha=0.5
)

plt.axhline(
    35,
    linestyle="--",
    alpha=0.5
)

plt.title("AI Tech Breadth Score")
plt.ylabel("Score")
plt.ylim(0, 100)
plt.legend()
plt.grid(alpha=0.3)

plt.tight_layout()
plt.show()

# ============================================================
# 13. Breadth Slope
# ============================================================

plt.figure(figsize=(15, 5))

plt.plot(
    breadth.index,
    breadth["Slope_5D"],
    label="5D Breadth Slope"
)

plt.plot(
    breadth.index,
    breadth["Slope_10D"],
    label="10D Breadth Slope"
)

plt.axhline(
    0,
    linewidth=1
)

plt.axhline(
    -10,
    linestyle="--",
    alpha=0.5
)

plt.axhline(
    10,
    linestyle="--",
    alpha=0.5
)

plt.title("AI Tech Breadth Slope")
plt.ylabel("Score Change")
plt.legend()
plt.grid(alpha=0.3)

plt.tight_layout()
plt.show()

# ============================================================
# 14. AI Tech Index vs Breadth Score
# ============================================================

fig, ax1 = plt.subplots(figsize=(15, 6))

# 왼쪽 축: 동일가중 지수
line1 = ax1.plot(
    breadth.index,
    breadth["AI_Tech_Index"],
    color="black",
    linewidth=1.8,
    label="AI Tech Equal-weight Index"
)

ax1.set_ylabel(
    "AI Tech Index",
    color="black"
)

ax1.tick_params(
    axis="y",
    labelcolor="black"
)

ax1.grid(alpha=0.3)

# 오른쪽 축: Breadth Score
ax2 = ax1.twinx()

line2 = ax2.plot(
    breadth.index,
    breadth["Breadth_Score_MA5"],
    color="orange",
    linewidth=2.0,
    label="Breadth Score MA5"
)

ax2.set_ylabel(
    "Breadth Score",
    color="orange"
)

ax2.tick_params(
    axis="y",
    labelcolor="orange"
)

ax2.set_ylim(0, 100)

# 강한 다이버전스 구간 표시
strong_divergence_dates = breadth.index[
    breadth["Strong_Bearish_Divergence"].fillna(False)
]

for date in strong_divergence_dates:
    ax1.axvline(
        date,
        color="red",
        alpha=0.10
    )

# 범례 합치기
lines = line1 + line2
labels = [
    line.get_label()
    for line in lines
]

ax1.legend(
    lines,
    labels,
    loc="upper left"
)

plt.title(
    "AI Tech Equal-weight Index vs Breadth"
)

plt.tight_layout()
plt.show()

# ============================================================
# 15. Recent 30 Trading Days
# ============================================================

recent_columns = [
    "Above_MA20",
    "Above_MA60",
    "Above_MA200",
    "Positive_60D",
    "Breadth_Score_MA5",
    "Breadth_Diff",
    "Slope_5D",
    "Slope_10D",
    "Breadth_From_20D_High",
    "Bearish_Divergence",
    "Strong_Bearish_Divergence",
    "Risk_Level"
]

recent_table = (
    breadth[recent_columns]
    .tail(30)
)

display(
    recent_table.style.format({
        "Above_MA20": "{:.1f}",
        "Above_MA60": "{:.1f}",
        "Above_MA200": "{:.1f}",
        "Positive_60D": "{:.1f}",
        "Breadth_Score_MA5": "{:.1f}",
        "Breadth_Diff": "{:+.1f}",
        "Slope_5D": "{:+.1f}",
        "Slope_10D": "{:+.1f}",
        "Breadth_From_20D_High": "{:+.1f}"
    })
)