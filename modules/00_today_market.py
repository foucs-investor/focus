# modules/00_today_market.py
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf
from utils import clean_theme_name, download_etf_data, etf_tickers

# 사이드바 라디오 버튼에 표시될 메뉴명
MENU_NAME = "오늘 시장"


def group_theme_category(ticker: str, full_name: str, theme_name: str) -> str:
    """티커, 전체 종목명, 세부 테마명을 기반으로 상위 대분류 테마로 묶어주는 함수"""
    lower_name = (full_name or "").lower()
    lower_theme = (theme_name or "").lower()
        
    # 시장 지표 자체는 별도의 대분류 명칭 부여
    if ticker in ["^KS11", "^KQ11"]:
        return "시장 지표 (KOSPI/KOSDAQ)"
        
    # 화장품/음식료 및 K뷰티 통합 그룹화
    if any(keyword in lower_name or keyword in lower_theme for keyword in ["화장품", "k뷰티", "k-뷰티", "뷰티", "푸드"]):
        return "화장품/음식료"
        
    # 1. 엔터/컨텐츠/인터넷 그룹 (ACE KPOP포커스 포함)
    elif ticker == "475050.KS" or any(keyword in lower_name or keyword in lower_theme for keyword in ["k-pop", "kpop", "포커스", "엔터", "미디어", "게임", "컨텐츠", "웹툰", "플랫폼", "인터넷", "포털"]):
        return "엔터/컨텐츠/인터넷"
       
    # 3. 반도체 그룹
    elif any(keyword in lower_name or keyword in lower_theme for keyword in ["반도체", "소부장", "후공정", "장비", "메모리"]):
        return "반도체"
        
    # 4. 금융 그룹
    elif any(keyword in lower_name or keyword in lower_theme for keyword in ["증권", "은행", "금융", "보험", "지주사"]):
        return "금융"
        
    # 5. 바이오/헬스케어 그룹
    elif any(keyword in lower_name or keyword in lower_theme for keyword in ["바이오", "헬스케어", "제약", "의료기기", "의료"]):
        return "바이오/헬스케어"
        
    # 6. AI/인공지능/소프트웨어 그룹
    elif any(keyword in lower_name or keyword in lower_theme for keyword in ["인공지능", "소프트웨어", "클라우드", "software", "보안", "it"]):
        return "IT·소프트웨어"
        
    # 7. 조선/방산/우주 그룹
    elif any(keyword in lower_name or keyword in lower_theme for keyword in ["조선", "방산", "우주", "항공"]):
        return "조선/방산"
        
    # 8. 친환경에너지
    elif any(keyword in lower_name or keyword in lower_theme for keyword in ["친환경"]):
        return "친환경에너지"      
          
    # 9. 소비재
    elif any(keyword in lower_name or keyword in lower_theme for keyword in ["생활소비","경기소비"]):
        return "소비재"       
        
    # 10. AIDC
    elif any(keyword in lower_name or keyword in lower_theme for keyword in ["건설","설비","원자력"]):
        return "AIDC"      
        
    # 11. 로봇/자동차/2차전지
    elif any(keyword in lower_name or keyword in lower_theme for keyword in ["로봇", "자동차", "2차전지", "배터리", "전기차", "lfp", "양극재"]):
        return "로봇/자동차/2차전지"                    
    
    return theme_name


def render():
    with st.spinner("최신 시장 및 ETF 시세 데이터를 가져오는 중입니다..."):
        # 1. 기존 ETF 데이터 다운로드
        df_raw, name_mapping = download_etf_data(etf_tickers, period="1mo")
        etf_data = df_raw.ffill().bfill()
        etf_data.index = pd.to_datetime(etf_data.index)

        # 2. 코스피(^KS11), 코스닥(^KQ11) 지수 데이터 정밀 다운로드
        index_tickers = {"^KS11": "코스피 (KOSPI)", "^KQ11": "코스닥 (KOSDAQ)"}

        idx_returns = {}
        idx_latest_vals = {}

        for ticker, name in index_tickers.items():
            t_obj = yf.Ticker(ticker)
            try:
                fi = t_obj.fast_info
                curr_val = fi.last_price
                prev_close = fi.previous_close
                if curr_val and prev_close:
                    ret = (curr_val - prev_close) / prev_close * 100
                    idx_latest_vals[ticker] = curr_val
                    idx_returns[ticker] = ret
                    continue
            except Exception:
                pass

            hist = t_obj.history(period="5d")
            if len(hist) >= 2:
                curr_val = hist["Close"].iloc[-1]
                prev_close = hist["Close"].iloc[-2]
                ret = (curr_val - prev_close) / prev_close * 100
                idx_latest_vals[ticker] = curr_val
                idx_returns[ticker] = ret
            else:
                idx_latest_vals[ticker] = 0.0
                idx_returns[ticker] = 0.0

    # 당일 등락률 계산 (ETF)
    etf_pct = etf_data.pct_change()
    latest_returns = (
        etf_pct.iloc[-1] * 100
        if not etf_pct.empty
        else pd.Series(dtype=float)
    )

    base_date_str = "2026-11-16"
    current_time_str = datetime.now().strftime("%H:%M")
    full_timestamp = f"{base_date_str} {current_time_str}"

    kospi_ret = idx_returns.get("^KS11", 0)
    kospi_val = idx_latest_vals.get("^KS11", 0)
    kosdaq_ret = idx_returns.get("^KQ11", 0)
    kosdaq_val = idx_latest_vals.get("^KQ11", 0)

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

    # 1. 시장 지표 데이터 (좌측 상단 고정)
    for idx_t, idx_name in index_tickers.items():
        ret = idx_returns.get(idx_t, 0)
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

    # 2. ETF 테마 데이터 처리 및 지수 대비 상대 강도 계산
    for ticker, ret in latest_returns.items():
        if pd.isna(ret):
            continue
        full_name = name_mapping.get(ticker, ticker)
        raw_theme = clean_theme_name(full_name)
        
        theme_name = group_theme_category(ticker, full_name, raw_theme)

        # 기준 지수 대비 차이(초과 수익/부진) 계산
        diff = ret - base_index_ret
        if diff >= 0:
            display_str = f"▲ +{diff:.2f}% ({ret:+.2f}%)"
            diff_html = f"<span style='font-size:11px;'>지수대비 {diff:+.2f}%</span>"
        else:
            display_str = f"▼ {diff:.2f}% ({ret:+.2f}%)"
            # 지수 대비 마이너스인 경우 검은색(#000000)으로 표기하고 체크 기호(✔) 추가[cite: 1]
            diff_html = f"<span style='font-size:11px; color:#000000; font-weight:bold;'>✔ 지수대비 {diff:+.2f}%</span>"

        status = "상승" if ret >= 0 else "하락"

        abs_ret = abs(ret)
        if ticker == "475050.KS":
            size_val = max(abs_ret + 3.0, 5.0)
        else:
            size_val = abs_ret + 1.5

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

    # 상승/하락 종목 수 및 비율 계산
    total_count = len(df_tree)
    if total_count > 0:
        rise_count = len(df_tree[df_tree["Status"] == "상승"])
        fall_count = len(df_tree[df_tree["Status"] == "하락"])
        rise_pct = (rise_count / total_count) * 100
        fall_pct = (fall_count / total_count) * 100
    else:
        rise_count, fall_count, rise_pct, fall_pct = 0, 0, 0.0, 0.0

    # 상단 요약 바 (고정형) - 상승/하락 통계 추가
    st.markdown(
        f"""
        <div style="position: sticky; top: 0; z-index: 999; background-color: #0f172a; padding: 16px 24px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #334155; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <div style="display: flex; gap: 30px;">
                    <div><span style="color: #94a3b8; font-size: 17px;">📈 코스피 (KOSPI)</span><br><span style="color: {kospi_color}; font-size: 22px;"><b>{kospi_val:,.2f} ({kospi_ret:+.2f}%)</b></span></div>
                    <div style="border-left: 1px solid #334155; padding-left: 30px;"><span style="color: #94a3b8; font-size: 17px;">📉 코스닥 (KOSDAQ)</span><br><span style="color: {kosdaq_color}; font-size: 22px;"><b>{kosdaq_val:,.2f} ({kosdaq_ret:+.2f}%)</b></span></div>
                </div>
                <div style="text-align: right; color: #94a3b8; font-size: 16px;">
                    기준 비교 지수: <b style="color: #38bdf8;">{base_index_name} ({base_index_ret:+.2f}%)</b><br>
                    기준 시점: <b style="color: #f8fafc;">{full_timestamp}</b>
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

    # Plotly 트리맵 생성 (상승/하락 상태별 고정 단색 지정)
    fig = px.treemap(
        df_tree,
        path=["Theme", "FullName"],
        values="Size",
        color="Status",
        color_discrete_map={
            "상승": "#ef4444",  # 선명한 빨간색 고정
            "하락": "#10b981",  # 선명한 초록색 고정
        },
        custom_data=["Ticker", "Return", "SubTheme", "Diff", "DiffHtml"],
    )

    # 트리맵 블록 내부 텍스트 렌더링 설정
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
            text=f"<b>오늘 시장 분석 - 테마별 당일 등락률 트리맵 ({base_date_str} 기준)</b>",
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