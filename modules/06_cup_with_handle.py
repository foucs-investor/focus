import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import FinanceDataReader as fdr
from pykrx import stock
import io
import os

# PDF 생성 관련 ReportLab 라이브러리
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Image, PageBreak, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

MENU_NAME = "cup_with_handle"

# 한글 폰트 설정 (Windows 기준 Malgun Gothic, Mac 기준 AppleGothic / 없을 시 기본 폰트)
try:
    if os.name == 'nt':
        plt.rc('font', family='Malgun Gothic')
    else:
        plt.rc('font', family='AppleGothic')
    plt.rcParams['axes.unicode_minus'] = False
except Exception:
    pass


def determine_stock_cycle_stage(stock_data):
    """주가 사이클 단계 판단 함수"""
    current_price = stock_data['Close'].iloc[-1]
    current_ma200 = stock_data['MA200'].iloc[-1]

    # MA200의 기울기 계산 (최근 10일 간의 일일 평균 변화량)
    if len(stock_data) >= 10:
        ma200_slope = (stock_data['MA200'].iloc[-1] - stock_data['MA200'].iloc[-10]) / 10
    else:
        ma200_slope = 0

    # 최근 30일 가격 범위 (변동성 확인)
    if len(stock_data) >= 30:
        recent_price_range = stock_data['Close'].iloc[-30:].max() - stock_data['Close'].iloc[-30:].min()
        recent_price_avg = stock_data['Close'].iloc[-30:].mean()
    else:
        recent_price_range = 0
        recent_price_avg = current_price

    consolidation_threshold = 0.1 * recent_price_avg

    # 주가 사이클 단계 판단
    if current_price < current_ma200:
        if ma200_slope < 0:
            stage = 4  # Stage 4: Declining
        else:
            stage = 1  # Stage 1: Basing
    else:
        if ma200_slope > 0:
            stage = 2  # Stage 2: Advancing
        else:
            if recent_price_range < consolidation_threshold:
                stage = 3  # Stage 3: Distribution
            else:
                stage = 2  # Stage 2: Advancing

    return stage


def detect_cup_with_handle(stock_data):
    """
    윌리엄 오닐의 컵 위드 핸들(Cup with Handle) 패턴 감지 함수
    부합할 경우 컵과 핸들의 주요 위치 메타데이터(dict) 반환, 아닐 경우 None 반환
    """
    if len(stock_data) < 200:
        return None

    df = stock_data.iloc[-200:].copy()
    
    # 1. 기본 추세 확인: 200일 이동평균선 위에 위치
    current_price = df['Close'].iloc[-1]
    ma200 = df['Close'].rolling(window=200, min_periods=50).mean().iloc[-1]
    if pd.isna(ma200) or current_price < ma200:
        return None

    # 2. 컵의 왼쪽 고점(Left Rim)과 바닥(Bottom) 탐색
    n = len(df)
    first_half = df.iloc[:int(n * 0.6)]
    if first_half.empty:
        return None
        
    left_rim_idx = first_half['Close'].idxmax()
    left_rim_price = first_half.loc[left_rim_idx, 'Close']
    
    after_left_rim = df.loc[left_rim_idx:]
    if len(after_left_rim) < 30:
        return None
        
    cup_bottom_idx = after_left_rim['Close'].idxmin()
    cup_bottom_price = after_left_rim.loc[cup_bottom_idx, 'Close']
    
    # 컵 깊이 확인 (10% ~ 45% 조정)
    cup_depth = (left_rim_price - cup_bottom_price) / left_rim_price
    if not (0.10 <= cup_depth <= 0.45):
        return None
        
    # 3. 우측 고점(Right Rim) 확인
    after_bottom = df.loc[cup_bottom_idx:]
    if len(after_bottom) < 15:
        return None
        
    right_rim_idx = after_bottom['Close'].idxmax()
    right_rim_price = after_bottom.loc[right_rim_idx, 'Close']
    if not (0.85 * left_rim_price <= right_rim_price <= 1.08 * left_rim_price):
        return None
        
    # 4. 핸들(Handle) 확인 (최근 25거래일 내 얕은 조정)
    recent_df = df.iloc[-25:]
    if recent_df.empty:
        return None
        
    handle_start_idx = recent_df.index[0]
    handle_high = recent_df['Close'].max()
    handle_low = recent_df['Close'].min()
    handle_drop = (handle_high - handle_low) / handle_high
    
    # 핸들 깊이 (2% ~ 16%)
    if not (0.02 <= handle_drop <= 0.16):
        return None
        
    if current_price < handle_low * 0.95:
        return None

    cwh_info = {
        'left_rim_idx': left_rim_idx,
        'left_rim_price': left_rim_price,
        'cup_bottom_idx': cup_bottom_idx,
        'cup_bottom_price': cup_bottom_price,
        'right_rim_idx': right_rim_idx,
        'right_rim_price': right_rim_price,
        'handle_start_idx': handle_start_idx,
        'handle_high_price': handle_high,
        'pivot_price': right_rim_price
    }

    return cwh_info


def generate_single_stock_chart(ticker, name, stock_data, index_data, index_name, cycle_stage, cwh_info=None):
    """단일 종목의 주가/거래량 및 RS 차트를 생성하며 CWH 패턴 구간을 표기"""
    highest_price = stock_data['Close'].rolling(window=252, min_periods=1).max().iloc[-1]
    lowest_price = stock_data['Close'].rolling(window=252, min_periods=1).min().iloc[-1]

    fig = plt.figure(figsize=(12, 4.2), dpi=150)
    ax1 = plt.subplot2grid((1, 2), (0, 0))
    ax2 = plt.subplot2grid((1, 2), (0, 1))

    # [1] 좌측: 주가 및 200일 이동평균선
    ax1.fill_between(stock_data.index, stock_data['Close'], color='lightgray', alpha=0.3, label='종가')
    ax1.plot(stock_data.index, stock_data['Close'], color='black', linewidth=0.8)
    ax1.plot(stock_data.index, stock_data['MA200'], color='red', linewidth=1, label='200일 MA')

    # 컵 & 핸들 패턴 표기 (강조)
    if cwh_info is not None:
        left_idx = cwh_info['left_rim_idx']
        right_idx = cwh_info['right_rim_idx']
        handle_start = cwh_info['handle_start_idx']
        end_idx = stock_data.index[-1]
        
        # 1. Cup 영역 음영 강조 (하늘색)
        ax1.axvspan(left_idx, right_idx, color='skyblue', alpha=0.25, label='Cup Section')
        
        # 2. Handle 영역 음영 강조 (주황색)
        ax1.axvspan(handle_start, end_idx, color='orange', alpha=0.25, label='Handle Section')
        
        # 3. Pivot 돌파 기준선 (우측 고점)
        ax1.axhline(cwh_info['pivot_price'], color='purple', linestyle='--', linewidth=1, label=f"Pivot: {int(cwh_info['pivot_price']):,}")
        
        # 4. 주요 포인트 마커 표기
        ax1.scatter([left_idx, cwh_info['cup_bottom_idx'], right_idx], 
                    [cwh_info['left_rim_price'], cwh_info['cup_bottom_price'], cwh_info['right_rim_price']], 
                    color='blue', s=25, zorder=5)

    if not np.isnan(highest_price):
        ax1.scatter(stock_data.index[-1], highest_price, color='red', s=15)
        ax1.text(stock_data.index[-1], highest_price, f'{int(highest_price):,}', fontsize=6, ha='right', color='red')
    if not np.isnan(lowest_price):
        ax1.scatter(stock_data.index[-1], lowest_price, color='blue', s=15)
        ax1.text(stock_data.index[-1], lowest_price, f'{int(lowest_price):,}', fontsize=6, ha='right', color='blue')

    # 거래량 차트 오버레이
    ax1_vol = ax1.twinx()
    ax1_vol.bar(stock_data.index, stock_data['Volume'], color='blue', alpha=0.2, width=1)
    ax1_vol.set_yticks([])

    ax1.legend(fontsize=6, loc='upper left')
    ax1.set_ylabel('가격(원)', fontsize=8)
    ax1.set_title(f"{name} ({ticker}) - CWH 패턴 (Stage {cycle_stage})", fontsize=10, fontweight='bold')
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m'))
    ax1.tick_params(axis='both', labelsize=7)

    # [2] 우측: TraderLion's Relative Strength Line
    if index_data is not None and not index_data.empty:
        aligned_df = pd.DataFrame({'Close': stock_data['Close'], 'Index': index_data}).dropna()
        if not aligned_df.empty:
            rs_line = (aligned_df['Close'] / aligned_df['Index'])
            rs_line = (rs_line / rs_line.iloc[0]) * 100
            rs_line_ma = rs_line.rolling(window=20, min_periods=1).mean()

            colors = ['blue' if rs_line.iloc[i] > rs_line.iloc[i-1] else 'pink' for i in range(1, len(rs_line))]
            colors.insert(0, 'blue')

            for i in range(1, len(rs_line)):
                ax2.plot(rs_line.index[i-1:i+1], rs_line.iloc[i-1:i+1], color=colors[i-1], linewidth=0.8)

            ax2.plot(rs_line.index, rs_line_ma, color='black', linewidth=1, label='RS 20일 MA')

            # Crossover
            crossover = (rs_line > rs_line_ma) & (rs_line.shift(1) <= rs_line_ma.shift(1))
            crossover_points = rs_line[crossover]
            if not crossover_points.empty:
                ax2.scatter(crossover_points.index, [ax2.get_ylim()[0]] * len(crossover_points),
                            marker='^', color='black', s=15, label='RS MA Crossover', zorder=5)

            # RSNHBP
            stock_highs = aligned_df['Close'].rolling(window=252, min_periods=1).max()
            rs_highs = rs_line.rolling(window=252, min_periods=1).max()
            rs_new_high = (rs_line == rs_highs) & (rs_line.shift(1) < rs_highs.shift(1))
            price_new_high = (aligned_df['Close'] == stock_highs) & (aligned_df['Close'].shift(1) < stock_highs.shift(1))
            rsnhbp = rs_new_high & ~price_new_high
            rsnhbp_points = rs_line[rsnhbp]
            if not rsnhbp_points.empty:
                ax2.scatter(rsnhbp_points.index, rsnhbp_points, color='pink', marker='o', s=15, label='RSNHBP', zorder=5)

            ax2.set_ylabel('상대강도(RS)', fontsize=8)
            ax2.set_title(f"TraderLion's RS Line vs {index_name}", fontsize=10, fontweight='bold')
            ax2.grid(True, linestyle='--', alpha=0.5)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m'))
            ax2.tick_params(axis='both', labelsize=7)
            ax2.legend(fontsize=6, loc='upper left')

    plt.tight_layout()

    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', bbox_inches='tight')
    plt.close(fig)
    img_buf.seek(0)
    return img_buf


def render():
    st.title("📈 컵 위드 핸들(Cup with Handle) 패턴 종목 분석 및 PDF 생성")
    st.caption("엑셀 파일을 업로드하면 컵(Cup)과 핸들(Handle) 구간이 시각적으로 표기된 PDF 보고서를 생성합니다.")

    st.markdown("---")

    # 1. 엑셀 파일 업로드
    st.subheader("1. 분석할 종목 엑셀 파일 업로드")
    st.info("💡 **엑셀 양식 안내**: A열=종목코드(6자리), B열=기업명 (2행부터 데이터가 읽혀집니다.)")

    uploaded_file = st.file_uploader("엑셀 파일 선택 (.xlsx, .xls)", type=["xlsx", "xls"])

    if uploaded_file is not None:
        try:
            df_input = pd.read_excel(uploaded_file, header=None)
            df_data = df_input.iloc[1:, :2].copy()
            df_data.columns = ['Code', 'Name']
            df_data.dropna(inplace=True)

            df_data['Code'] = df_data['Code'].astype(str).str.zfill(6)

            st.success(f"총 **{len(df_data)}개 종목**을 성공적으로 로드했습니다.")
            st.dataframe(df_data.head(10), use_container_width=True)

        except Exception as e:
            st.error(f"엑셀 파일을 읽는 중 오류가 발생했습니다: {e}")
            return

        # 2. 분석 실행 버튼
        st.markdown("---")
        st.subheader("2. 컵 위드 핸들 패턴 분석 및 PDF 생성")

        if st.button("🚀 CWH 패턴 분석 및 PDF 보고서 생성 시작"):
            today_str = datetime.today().strftime('%Y-%m-%d')
            start_date = (datetime.today() - timedelta(days=3 * 365)).strftime('%Y-%m-%d')

            try:
                kospi_tickers = stock.get_market_ticker_list(market="KOSPI", date=today_str.replace('-', ''))
                kosdaq_tickers = stock.get_market_ticker_list(market="KOSDAQ", date=today_str.replace('-', ''))
            except Exception:
                kospi_tickers, kosdaq_tickers = [], []

            kospi_data = fdr.DataReader('^KS11', start_date, today_str)['Close']
            kosdaq_data = fdr.DataReader('^KQ11', start_date, today_str)['Close']

            analyzed_results = []
            progress_bar = st.progress(0, text="종목별 컵 위드 핸들 패턴 분석 중입니다...")
            total_items = len(df_data)

            for idx, row in enumerate(df_data.itertuples()):
                ticker = row.Code
                name = row.Name

                try:
                    stock_data = fdr.DataReader(ticker, start_date, today_str)
                    if stock_data.empty or len(stock_data) < 200:
                        continue

                    stock_data['MA200'] = stock_data['Close'].rolling(window=200).mean()

                    # 윌리엄 오닐 컵 위드 핸들 패턴 확인
                    cwh_info = detect_cup_with_handle(stock_data)
                    if cwh_info is None:
                        progress_bar.progress((idx + 1) / total_items, text=f"분석 진행 중... ({idx + 1}/{total_items})")
                        continue

                    cycle_stage = determine_stock_cycle_stage(stock_data)

                    if ticker in kosdaq_tickers:
                        idx_data = kosdaq_data
                        idx_name = '코스닥'
                    else:
                        idx_data = kospi_data
                        idx_name = '코스피'

                    # CWH 표기가 포함된 차트 생성
                    img_buf = generate_single_stock_chart(ticker, name, stock_data, idx_data, idx_name, cycle_stage, cwh_info)

                    analyzed_results.append({
                        'ticker': ticker,
                        'name': name,
                        'stage': cycle_stage,
                        'img_buf': img_buf
                    })

                except Exception as e:
                    print(f"Error processing {ticker}: {e}")

                progress_bar.progress((idx + 1) / total_items, text=f"분석 진행 중... ({idx + 1}/{total_items})")

            progress_bar.empty()

            if not analyzed_results:
                st.warning("조건에 부합하는 컵 위드 핸들 패턴 종목이 없습니다.")
                return

            analyzed_results.sort(key=lambda x: x['stage'])

            st.success(f"조건 부합 **총 {len(analyzed_results)}개 종목** 발견! PDF 생성을 시작합니다.")

            pdf_buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                pdf_buffer,
                pagesize=A4,
                rightMargin=15,
                leftMargin=15,
                topMargin=20,
                bottomMargin=20
            )

            story = []
            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                'ReportTitle',
                parent=styles['Heading1'],
                fontSize=14,
                leading=18,
                alignment=1,
                spaceAfter=10
            )

            chunk_size = 4
            for i in range(0, len(analyzed_results), chunk_size):
                chunk = analyzed_results[i:i + chunk_size]

                page_num = (i // chunk_size) + 1
                story.append(Paragraph(f"<b>Cup with Handle Pattern Report (Page {page_num})</b>", title_style))
                story.append(Spacer(1, 5))

                for item in chunk:
                    img = Image(item['img_buf'], width=540, height=170)
                    story.append(img)
                    story.append(Spacer(1, 4))

                if i + chunk_size < len(analyzed_results):
                    story.append(PageBreak())

            doc.build(story)
            pdf_buffer.seek(0)

            today_filename_str = datetime.today().strftime('%Y%m%d')
            pdf_file_name = f"cup_with_handle_{today_filename_str}.pdf"

            st.download_button(
                label="📥 CWH 분석 보고서 PDF 다운로드",
                data=pdf_buffer,
                file_name=pdf_file_name,
                mime="application/pdf"
            )


if __name__ == "__main__":
    render()