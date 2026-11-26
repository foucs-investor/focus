import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf


def to_weekly_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """일봉 OHLCV 데이터를 금요일 기준 주봉 데이터로 변환합니다."""
    if df.empty:
        return pd.DataFrame()

    data = df.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data.index = pd.to_datetime(data.index)
    weekly = data.resample("W-FRI").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    ).dropna(subset=["Close"])
    return weekly


def weighted_moving_average(series: pd.Series, window: int = 30) -> pd.Series:
    """Mansfield 차트 스타일의 선형 가중 이동평균(WMA)을 계산합니다."""
    weights = np.arange(1, window + 1, dtype=float)
    weights /= weights.sum()

    def _wma(x: np.ndarray) -> float:
        return float(np.dot(x, weights))

    return series.rolling(window=window, min_periods=window).apply(_wma, raw=True)


def analyze_weinstein_stages(
    ticker: str,
    benchmark_ticker: str = "^GSPC",
    period: str = "3y",
    ma_period: int = 30,
    slope_lookback: int = 4,
    range_lookback: int = 16,
    use_wma: bool = False,
) -> pd.DataFrame:
    """
    스탠 와인스타인 4단계 기준으로 주봉 데이터를 분석합니다.
    - Stage 2: MA 상승 + 주가 MA 상회 + 최근 저항선 돌파(또는 상승 추세 유지)
    - Stage 4: MA 하락 + 주가 MA 하회 + 최근 지지선 이탈(또는 하락 추세 유지)
    - Stage 1 / Stage 3: MA 평탄화(비상승·비하락) 구간에서 직전 추세(하락 후 -> Stage 1, 상승 후 -> Stage 3) 기반 분류
    """
    raw = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    weekly = to_weekly_ohlcv(raw)
    if weekly.empty or len(weekly) < ma_period + slope_lookback + 2:
        return pd.DataFrame()

    # 30주 이동평균 및 기울기(변화율)
    ma_col = "MA_30"
    weekly[ma_col] = (
        weighted_moving_average(weekly["Close"], ma_period)
        if use_wma
        else weekly["Close"].rolling(ma_period).mean()
    )
    weekly["MA_Slope_Pct"] = weekly[ma_col].pct_change(slope_lookback) * 100.0

    # 거래량 기준: 직전 4주 평균 대비 배수 (와인스타인 돌파 기준 2.0배 참고)
    weekly["Vol_4W_Avg"] = weekly["Volume"].shift(1).rolling(4).mean()
    weekly["Vol_Ratio"] = weekly["Volume"] / weekly["Vol_4W_Avg"].replace(0, np.nan)

    # 직전 박스권 상단(저항) / 하단(지지)
    prior_high = weekly["High"].shift(1).rolling(range_lookback).max()
    prior_low = weekly["Low"].shift(1).rolling(range_lookback).min()
    weekly["Resistance"] = prior_high
    weekly["Support"] = prior_low

    # 상대강도(RS): 종목 종가 / 벤치마크 종가
    bench_raw = yf.download(benchmark_ticker, period=period, auto_adjust=True, progress=False)
    bench_weekly = to_weekly_ohlcv(bench_raw)
    if not bench_weekly.empty:
        aligned_bench = bench_weekly["Close"].reindex(weekly.index).ffill()
        weekly["RS"] = weekly["Close"] / aligned_bench.replace(0, np.nan)
        weekly["RS_Slope_Pct"] = weekly["RS"].pct_change(slope_lookback) * 100.0
    else:
        weekly["RS"] = np.nan
        weekly["RS_Slope_Pct"] = np.nan

    # 기울기 임계값 (주봉 기준 약 +-1.5% 이내면 평탄화 구간으로 간주)
    flat_threshold = 1.5

    stages = []
    signals = []
    prev_stage = None

    for idx, row in weekly.iterrows():
        close = row["Close"]
        ma = row[ma_col]
        slope = row["MA_Slope_Pct"]
        res = row["Resistance"]
        sup = row["Support"]
        vol_ratio = row["Vol_Ratio"]

        if pd.isna(ma) or pd.isna(slope):
            stages.append("N/A")
            signals.append("")
            continue

        above_ma = close > ma
        below_ma = close < ma
        ma_rising = slope > flat_threshold
        ma_falling = slope < -flat_threshold
        ma_flat = not ma_rising and not ma_falling

        broke_out = pd.notna(res) and close > res and above_ma
        broke_down = pd.notna(sup) and close < sup and below_ma
        vol_confirmed = pd.notna(vol_ratio) and vol_ratio >= 2.0

        # 단계 판별 로직
        if ma_rising and above_ma:
            stage = "Stage 2"
            sig = "돌파 매수(거래량 2x+)" if (broke_out and vol_confirmed) else (
                "돌파(거래량 약함)" if broke_out else "상승 추세 유지"
            )
        elif ma_falling and below_ma:
            stage = "Stage 4"
            sig = "지지선 이탈(매도/회피)" if broke_down else "하락 추세 유지"
        elif ma_flat:
            # 직전 단계나 중기 위치를 바탕으로 Stage 1(바닥) vs Stage 3(천장) 구분
            if prev_stage in ("Stage 2", "Stage 3") or (
                pd.notna(row["MA_Slope_Pct"]) and weekly["MA_Slope_Pct"].loc[:idx].tail(12).max() > 4.0
            ):
                stage = "Stage 3"
                sig = "상승 둔화·천장 횡보"
            else:
                stage = "Stage 1"
                sig = "하락 둔화·바닥 다지기"
        else:
            # 전환 과도기: 이평선 상회 중이면 초기 Stage 2 후보, 하회 중이면 Stage 4 후보
            if above_ma and not ma_falling:
                stage = "Stage 2"
                sig = "상승 전환 초기"
            elif below_ma and not ma_rising:
                stage = "Stage 4"
                sig = "하락 전환 초기"
            else:
                stage = prev_stage if prev_stage else "Stage 1"
                sig = "추세 전환 관찰"

        stages.append(stage)
        signals.append(sig)
        prev_stage = stage

    weekly["Stage"] = stages
    weekly["Signal"] = signals
    return weekly


def build_weinstein_chart(df: pd.DataFrame, title: str = "Weinstein 4-Stage Chart") -> go.Figure:
    """어두운 테마 기반 스탠 와인스타인 주봉 차트를 생성합니다."""
    stage_colors = {
        "Stage 1": "#64748b",  # 슬레이트(횡보/바닥)
        "Stage 2": "#ef4444",  # 레드(상승)
        "Stage 3": "#f59e0b",  # 앰버(천장/주의)
        "Stage 4": "#22c55e",  # 그린(하락)
    }

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.58, 0.20, 0.22],
        subplot_titles=(title, "Relative Strength (vs Benchmark)", "Weekly Volume"),
    )

    # 1. 주봉 캔들 + 30주 MA + 저항/지지
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Price",
            increasing_line_color="#ef4444",
            decreasing_line_color="#22c55e",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["MA_30"],
            name="30-Week MA",
            line=dict(color="#38bdf8", width=2),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Resistance"],
            name="Resistance",
            line=dict(color="#f87171", width=1, dash="dot"),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Support"],
            name="Support",
            line=dict(color="#4ade80", width=1, dash="dot"),
        ),
        row=1,
        col=1,
    )

    # 최신 구간 Stage 배지 표기
    latest = df.iloc[-1]
    latest_stage = latest.get("Stage", "N/A")
    fig.add_annotation(
        x=df.index[-1],
        y=latest["High"],
        text=f"{latest_stage} | {latest.get('Signal', '')}",
        showarrow=True,
        arrowhead=2,
        ax=-60,
        ay=-35,
        bgcolor=stage_colors.get(latest_stage, "#334155"),
        font=dict(color="#ffffff", size=12),
        row=1,
        col=1,
    )

    # 2. 상대강도(RS)
    if "RS" in df.columns and df["RS"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["RS"],
                name="RS Line",
                line=dict(color="#c084fc", width=1.6),
            ),
            row=2,
            col=1,
        )

    # 3. 주간 거래량
    bar_colors = [
        "#ef4444" if c >= o else "#22c55e"
        for c, o in zip(df["Close"], df["Open"])
    ]
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            name="Volume",
            marker_color=bar_colors,
        ),
        row=3,
        col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        height=760,
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig
