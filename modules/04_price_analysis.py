import io
import re
import urllib.parse
from datetime import datetime
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd
import requests
import streamlit as st
import FinanceDataReader as fdr
import yfinance as yf

# openpyxl 예외 처리 (미설치 시 엑셀 다운로드 fallback 대처)
try:
  from openpyxl import Workbook
  from openpyxl.styles import Font

  HAS_OPENPYXL = True
except ImportError:
  HAS_OPENPYXL = False

# ==============================================================================
# 1. 메뉴명 정의 (자동 로더 인식용)
# ==============================================================================
MENU_NAME = '가격분석'


# ==============================================================================
# 2. 한글 폰트 설정 (OS별 자동 대처)
# ==============================================================================
def set_korean_font():
  import platform

  system_name = platform.system()
  if system_name == 'Windows':
    plt.rc('font', family='Malgun Gothic')
  elif system_name == 'Darwin':  # macOS
    plt.rc('font', family='AppleGothic')
  else:  # Linux / Streamlit Cloud
    font_path = '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
    try:
      font_name = fm.FontProperties(fname=font_path).get_name()
      plt.rc('font', family=font_name)
    except Exception:
      pass
  plt.rc('axes', unicode_minus=False)


# ==============================================================================
# 3. 데이터 및 티커 탐색 유틸리티 함수
# ==============================================================================
def create_naver_news_url(keyword, date):
  date_str = date.strftime('%Y.%m.%d')
  encoded_kw = urllib.parse.quote(keyword)
  return f'https://search.naver.com/search.naver?where=news&query={encoded_kw}&sm=tab_opt&sort=0&photo=0&field=0&pd=3&ds={date_str}&de={date_str}'


@st.cache_data(ttl=3600)
def get_krx_listing():
  """KRX 전체 상장 종목 목록 가져오기"""
  try:
    return fdr.StockListing('KRX')
  except Exception:
    return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_ticker_by_name(company_input: str):
  """기업명 또는 종목코드를 받아 (ticker, formal_name, market) 튜플을 반환합니다."""
  clean_input = company_input.strip()
  if not clean_input:
    return None, None, 'KOSPI'

  # 1. 사용자가 6자리 숫자 종목코드를 직접 입력한 경우
  if clean_input.isdigit() and len(clean_input) == 6:
    ticker = clean_input
    name, market = get_company_info(ticker)
    return ticker, name, market

  headers = {
      'User-Agent': (
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
          'AppleWebKit/537.36 (KHTML, like Gecko) '
          'Chrome/120.0.0.0 Safari/537.36'
      )
  }

  # 2. KRX 상장법인 목록에서 조회
  try:
    df_krx = get_krx_listing()
    if not df_krx.empty and 'Code' in df_krx.columns:
      # 정확한 검색
      exact_match = df_krx[
          df_krx['Name'].astype(str).str.strip().str.upper()
          == clean_input.upper()
      ]
      if not exact_match.empty:
        row = exact_match.iloc[0]
        market = row['Market'] if 'Market' in row else 'KOSPI'
        return row['Code'], row['Name'], market

      # 부분 검색
      contains_match = df_krx[
          df_krx['Name']
          .astype(str)
          .str.replace(' ', '')
          .str.contains(clean_input.replace(' ', ''), case=False)
      ]
      if not contains_match.empty:
        row = contains_match.iloc[0]
        market = row['Market'] if 'Market' in row else 'KOSPI'
        return row['Code'], row['Name'], market
  except Exception:
    pass

  # 3. 네이버 검색을 통한 티커 추출 (Fallback)
  try:
    search_url = f'https://search.naver.com/search.naver?query={urllib.parse.quote(clean_input)}'
    res = requests.get(search_url, headers=headers, timeout=5)

    match = re.search(r'code=([0-9]{6})', res.text)
    if match:
      ticker = match.group(1)
      name, market = get_company_info(ticker)
      return ticker, name, market

    match2 = re.search(r'item/([0-9]{6})', res.text)
    if match2:
      ticker = match2.group(1)
      name, market = get_company_info(ticker)
      return ticker, name, market
  except Exception:
    pass

  return None, None, 'KOSPI'


def get_company_info(ticker):
  """티커 6자리로 회사명과 시장 구분 반환"""
  df = get_krx_listing()
  if not df.empty and 'Code' in df.columns:
    match = df[df['Code'] == ticker]
    if not match.empty:
      name = match['Name'].values[0]
      market = (
          match['Market'].values[0] if 'Market' in match.columns else 'KOSPI'
      )
      return name, market
  return f'종목_{ticker}', 'KOSPI'


def fetch_price_data(symbol: str, start_date: str, end_date: str):
  """FinanceDataReader 실패 시 yfinance로 자동 이중화 수집하는 안전 함수"""
  clean_code = ''.join(filter(str.isdigit, str(symbol)))

  # 지수 티커인 경우 처리 (KS11, KQ11)
  is_index = symbol in ['KS11', 'KQ11']

  # 1차 시도: FinanceDataReader
  try:
    df = fdr.DataReader(symbol if is_index else clean_code, start_date, end_date)
    if not df.empty and 'Close' in df.columns:
      df.index = pd.to_datetime(df.index)
      return df[['Close']].dropna()
  except Exception:
    pass

  # 2차 시도: yfinance 우회 수집
  yf_candidates = []
  if is_index:
    yf_candidates = ['^KS11'] if symbol == 'KS11' else ['^KQ11']
  else:
    yf_candidates = [f'{clean_code}.KS', f'{clean_code}.KQ']

  for yf_ticker in yf_candidates:
    try:
      df = yf.download(
          yf_ticker, start=start_date, end=end_date, progress=False
      )
      if df.empty:
        continue

      # yfinance MultiIndex 컬럼 정제
      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      if 'Close' in df.columns:
        df = df[['Close']].dropna()
        df.index = pd.to_datetime(df.index)
        if not df.empty:
          return df
    except Exception:
      continue

  return pd.DataFrame()


# ==============================================================================
# 4. 엑셀 보고서 생성 함수 (하이퍼링크 지원)
# ==============================================================================
def create_excel_report(table_data, ticker, company_name):
  output = io.BytesIO()
  if HAS_OPENPYXL:
    wb = Workbook()
    ws = wb.active
    ws.title = '급등락 뉴스'

    headers = ['날짜', '증감율', '네이버 뉴스']
    for col, header in enumerate(headers, 1):
      cell = ws.cell(row=1, column=col, value=header)
      cell.font = Font(bold=True)

    for r_idx, row_data in enumerate(table_data, 2):
      date_str, change, url = row_data
      change_text = (
          f'상승 {change:.2f}%' if change > 0 else f'하락 {abs(change):.2f}%'
      )

      ws.cell(row=r_idx, column=1, value=date_str)
      ws.cell(row=r_idx, column=2, value=change_text)

      link_cell = ws.cell(row=r_idx, column=3, value='네이버 뉴스 보기')
      link_cell.hyperlink = url
      link_cell.font = Font(color='0000FF', underline='single')

    ws.column_dimensions['A'].width = 15
    ws.column_dimensions['B'].width = 15
    ws.column_dimensions['C'].width = 25

    wb.save(output)
    output.seek(0)
  else:
    df_export = pd.DataFrame(table_data, columns=['날짜', '증감율', 'URL'])
    df_export['증감율'] = df_export['증감율'].apply(
        lambda x: f'상승 {x:.2f}%' if x > 0 else f'하락 {abs(x):.2f}%'
    )
    with pd.ExcelWriter(output) as writer:
      df_export.to_excel(writer, index=False, sheet_name='급등락 뉴스')
    output.seek(0)
  return output


# ==============================================================================
# 5. Streamlit 화면 메인 랜더링 함수
# ==============================================================================
def render():
  set_korean_font()

  st.title('📈 개별 종목 vs 시장지수 가격 분석 & 급등락 뉴스')
  st.markdown(
      '개별 종목과 지수(KOSPI/KOSDAQ)의 수익률을 비교하고, 설정한 기준 이상으로'
      ' **급등락한 날짜의 네이버 뉴스**를 빠르게 조회합니다.'
  )

  # 사이드바/상단 설정 영역
  st.subheader('📌 분석 조건 설정')

  col1, col2, col3 = st.columns([1.5, 1, 1])

  with col1:
    company_input = st.text_input(
        '기업명 또는 종목코드',
        value='삼성전자',
        placeholder='예: 삼성전자, 펌텍코리아, 005930',
    ).strip()

  current_year = datetime.now().year
  with col2:
    start_year = st.number_input(
        '시작 년도', min_value=2000, max_value=current_year, value=2020
    )

  with col3:
    end_year = st.number_input(
        '종료 년도',
        min_value=2000,
        max_value=current_year,
        value=current_year,
    )

  col4, col5 = st.columns([1.5, 1.5])
  with col4:
    threshold = st.number_input(
        '급등락 기준 변동률 (%)',
        min_value=0.5,
        max_value=30.0,
        value=5.0,
        step=0.5,
        help='예: 5.0 선택 시 하루 +5% 이상 상승 또는 -5% 이하 하락한 날을 탐색합니다.',
    )

  with col5:
    search_keyword = st.text_input(
        '네이버 뉴스 검색 키워드',
        value=company_input,
        help='기본값은 입력하신 기업명입니다.',
    )

  if st.button('🚀 가격 분석 실행', type='primary', use_container_width=True):
    if not company_input:
      st.error('⚠️ 기업명 또는 종목코드를 입력해주세요.')
      return

    if start_year > end_year:
      st.error('⚠️ 시작 년도가 종료 년도보다 클 수 없습니다.')
      return

    # 1. 기업명 -> 종목코드(티커) 변환
    with st.spinner(f"'{company_input}' 종목 정보를 조회 중..."):
      ticker, formal_name, market = get_ticker_by_name(company_input)

    if not ticker:
      st.error(
          f"❌ '{company_input}'에 대한 종목코드를 찾을 수 없습니다."
          ' 정확한 기업명이나 6자리 종목코드를 입력해주세요.'
      )
      return

    company_name = formal_name if formal_name else company_input
    start_date = f'{start_year}-01-01'
    end_date = f'{end_year}-12-31'

    index_ticker = 'KS11' if 'KOSDAQ' not in str(market).upper() else 'KQ11'
    index_name = 'KOSPI' if index_ticker == 'KS11' else 'KOSDAQ'

    st.success(
        f'선택 종목: **{company_name}** ({ticker}) | 시장: **{market}** | 비교'
        f' 지수: **{index_name}** | 변동률 기준: **±{threshold}%**'
    )

    # 2. 데이터 수집 (FinanceDataReader + yfinance 이중화)
    with st.spinner('주가 및 시장 지수 데이터를 가져오는 중...'):
      stock_data = fetch_price_data(ticker, start_date, end_date)
      index_data = fetch_price_data(index_ticker, start_date, end_date)

    if stock_data.empty:
      st.error(
          f'❌ [{company_name}({ticker})] 종목의 주가 데이터를 불러오지'
          ' 못했습니다. 종목코드를 다시 확인해 주세요.'
      )
      return

    if index_data.empty:
      st.warning(
          f'⚠️ {index_name} 지수 데이터를 불러오지 못해 종목 차트만'
          ' 표시합니다.'
      )

    # 3. 변동률 산출
    stock_data = stock_data.copy()
    stock_data['Return'] = stock_data['Close'].pct_change()

    up_days = stock_data[stock_data['Return'] >= threshold / 100].index
    down_days = stock_data[stock_data['Return'] <= -threshold / 100].index

    # 4. 차트 시각화
    st.markdown('---')
    st.subheader('📊 주가 & 지수 추이 및 급등락 포인트')

    fig, ax1 = plt.subplots(figsize=(10, 4.5))

    if not index_data.empty:
      ax1.plot(
          index_data.index,
          index_data['Close'],
          label=index_name,
          color='black',
          alpha=0.6,
      )
      ax1.set_xlabel('날짜')
      ax1.set_ylabel(f'{index_name} 종가', color='black')

    ax2 = ax1.twinx() if not index_data.empty else ax1
    ax2.plot(
        stock_data.index,
        stock_data['Close'],
        label=company_name,
        color='#1f77b4',
        linewidth=1.2,
    )
    ax2.set_ylabel(f'{company_name} 종가', color='#1f77b4')

    if len(up_days) > 0:
      ax2.scatter(
          up_days,
          stock_data.loc[up_days]['Close'],
          color='red',
          s=45,
          label=f'급등 (≥+{threshold}%)',
          zorder=5,
      )
    if len(down_days) > 0:
      ax2.scatter(
          down_days,
          stock_data.loc[down_days]['Close'],
          color='blue',
          s=45,
          label=f'급락 (≤-{threshold}%)',
          zorder=5,
      )

    plt.title(
        f'{company_name} ({ticker}) vs {index_name} ({start_year} ~'
        f' {end_year})',
        fontsize=12,
    )

    if not index_data.empty:
      lines1, labels1 = ax1.get_legend_handles_labels()
      lines2, labels2 = ax2.get_legend_handles_labels()
      ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    else:
      ax2.legend(loc='upper left')

    plt.tight_layout()
    st.pyplot(fig)

    # 5. 급등락 날짜 목록 및 네이버 뉴스 URL
    table_data = []
    kw_to_use = search_keyword if search_keyword else company_name

    for date in list(up_days) + list(down_days):
      try:
        daily_change = stock_data.loc[date]['Return'] * 100
        url = create_naver_news_url(kw_to_use, date)
        table_data.append([date.strftime('%Y-%m-%d'), daily_change, url])
      except Exception:
        continue

    st.markdown('---')
    st.subheader(
        f'🔔 급등락 날짜 및 네이버 뉴스 검색 ({len(table_data)}건)'
    )

    if not table_data:
      st.info(
          f'선택한 기간 동안 변동률 ±{threshold}% 이상의 급등락 발생일이'
          ' 없습니다.'
      )
      return

    df = pd.DataFrame(table_data, columns=['날짜', '변동률_raw', '네이버 뉴스'])
    df = df.sort_values(by='날짜', ascending=False)
    df['증감율'] = df['변동률_raw'].apply(
        lambda x: f'🔺 상승 {x:.2f}%' if x > 0 else f'🔹 하락 {abs(x):.2f}%'
    )

    # 엑셀 다운로드 버튼
    excel_bytes = create_excel_report(table_data, ticker, company_name)
    download_filename = f'stock_news_{ticker}_{start_year}_{end_year}.xlsx'

    st.download_button(
        label='📥 엑셀 파일 다운로드 (하이퍼링크 포함)',
        data=excel_bytes,
        file_name=download_filename,
        mime=(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ),
        type='primary',
    )

    st.write('')

    # Streamlit 대화형 테이블
    show_df = df[['날짜', '증감율', '네이버 뉴스']].copy()
    st.dataframe(
        show_df,
        column_config={
            '날짜': st.column_config.TextColumn('날짜', width='small'),
            '증감율': st.column_config.TextColumn('증감율', width='medium'),
            '네이버 뉴스': st.column_config.LinkColumn(
                '네이버 뉴스', display_text='해당일 뉴스 보기'
            ),
        },
        hide_index=True,
        use_container_width=True,
    )


if __name__ == '__main__':
  render()