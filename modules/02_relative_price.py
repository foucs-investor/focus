import streamlit as st
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from utils import HAS_MATPLOTLIB, download_stock_relative_data

# 사이드바 라디오 버튼에 표시될 메뉴명
MENU_NAME = "주가 상대 비교"

def render():
    current_year = datetime.now().year
    st.title(f"📈 테마/그룹별 주가 상대 비교 (YTD: {current_year}년 1월 1일 기준)")
    st.markdown(f"**{current_year}년 1월 첫 거래일** 주가를 **기준값 100**으로 정규화하여 그룹 내 종목들의 상대 수익률 흐름을 비교합니다.")

    if not HAS_MATPLOTLIB:
        st.error("⚠️ `matplotlib` 패키지가 설치되어 있지 않습니다. 터미널에서 `pip install matplotlib` 명령어를 실행해 주세요.")
        return

    plt.rcParams['axes.unicode_minus'] = False
    try:
        plt.rcParams['font.family'] = 'Malgun Gothic'
    except Exception:
        try:
            plt.rcParams['font.family'] = 'Apple SD Gothic Neo'
        except Exception:
            plt.rcParams['font.family'] = 'DejaVu Sans'

    default_font_size = plt.rcParams['font.size']
    legend_font_size = default_font_size * 0.85
    date_font_size = default_font_size * 0.8

    groups = {
        '증권': {
            '039490.KS': '키움증권',
            '016360.KS': '삼성증권',
            '005940.KS': 'NH투자증권',
            '006800.KS': '미래에셋증권',
            '071050.KS': '한국금융지주'
        },
        '원자력': {
            '000720.KS': '현대건설',
            '052690.KS': '한전기술',
            '034020.KS': '두산에너빌리티',
            '083650.KQ': '비츠로테크',
            '051600.KS': '한전KPS'
        }
    }

    end_date = datetime.now()
    start_date = datetime(current_year, 1, 1)

    with st.spinner("그룹별 종목 데이터를 다운로드 중입니다..."):
        for group_name, ticker_dict in groups.items():
            st.subheader(f"🔍 Group: {group_name}")
            
            data = {}
            company_names = ticker_dict

            for ticker in ticker_dict.keys():
                close_data = download_stock_relative_data(ticker, start_date, end_date)
                if close_data is not None:
                    data[ticker] = close_data

            if data:
                valid_data = {t: v for t, v in data.items() if isinstance(v, pd.Series) and len(v) > 0}
                if not valid_data:
                    st.warning(f"[{group_name}] 그룹의 유효한 주가 데이터가 없습니다.")
                    continue

                df = pd.DataFrame(valid_data).ffill().bfill()
                
                log_df = df.apply(lambda x: x / x.iloc[0] * 100)

                ytd_returns = (log_df.iloc[-1] - log_df.iloc[0]) / log_df.iloc[0]
                sorted_ytd_returns = ytd_returns.sort_values(ascending=True)

                fig, ax = plt.subplots(figsize=(10, 4.8))
                fig.patch.set_facecolor('#1e1e1e')
                ax.set_facecolor('#1e1e1e')

                ax.spines['bottom'].set_color('#cccccc')
                ax.spines['top'].set_color('#cccccc')
                ax.spines['left'].set_color('#cccccc')
                ax.spines['right'].set_color('#cccccc')
                ax.xaxis.label.set_color('white')
                ax.yaxis.label.set_color('white')
                ax.tick_params(axis='x', colors='white', labelsize=date_font_size)
                ax.tick_params(axis='y', colors='white')

                for ticker in sorted_ytd_returns.index:
                    c_name = company_names.get(ticker, ticker)
                    ret_pct = sorted_ytd_returns[ticker]
                    ax.plot(log_df.index, log_df[ticker], label=f'{c_name} ({ticker.split(".")[0]}: {ret_pct:+.2%})', linewidth=1.8)

                ax.set_title(f'Stock Price Index Chart (YTD {current_year}) - {group_name}', color='white', fontsize=12, pad=12)
                ax.set_ylabel('Index (Base 100)', color='white')

                date_range = pd.date_range(start=start_date, end=end_date, freq='ME')
                if len(date_range) == 0:
                    date_range = pd.date_range(start=start_date, end=end_date, freq='15D')
                if end_date not in date_range:
                    date_range = list(date_range) + [end_date]
                
                ax.set_xticks(date_range)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

                fig.autofmt_xdate()

                ax.legend(
                    loc='upper center',
                    bbox_to_anchor=(0.5, -0.22),
                    title='종목명 (코드: YTD 수익률)',
                    fontsize=legend_font_size,
                    ncol=2,
                    facecolor='#2d2d2d',
                    edgecolor='#555555',
                    labelcolor='white',
                    title_fontproperties={'weight': 'bold'}
                )
                
                legend = ax.get_legend()
                if legend:
                    plt.setp(legend.get_title(), color='white')

                ax.grid(True, color='#444444', linestyle='--', alpha=0.6)
                plt.tight_layout()

                st.pyplot(fig)
                plt.close(fig)
            else:
                st.warning(f"[{group_name}] 그룹에 대한 데이터를 수집하지 못했습니다.")