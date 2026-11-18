import streamlit as st
import pandas as pd
from datetime import datetime
import FinanceDataReader as fdr

# OpenDartReader 패키지 로드 및 설치 여부 체크
try:
    import OpenDartReader
    DART_AVAILABLE = True
except ImportError:
    DART_AVAILABLE = False

MENU_NAME = "📈 전종목 PSR 분석"

def get_ttm_sales_dart(dart, corp_code, year):
    """
    DART API를 활용해 정기보고서(손익계산서/포괄손익계산서)에서 매출액 수집
    """
    try:
        # 단일회사 주요계정 재무제표 API 조회
        df_fin = dart.finstate(corp_code, year)
        
        if df_fin is not None and not df_fin.empty:
            # 매출액 또는 영업수익 항목 파싱
            sales_df = df_fin[df_fin['account_nm'].str.contains('매출액|영업수익', na=False)]
            
            if not sales_df.empty:
                # 당기 금액 추출 및 억원 단위 변환
                val_str = str(sales_df.iloc[0]['thstrm_amount']).replace(',', '')
                val = float(val_str)
                return round(val / 100_000_000, 1)
    except Exception:
        pass
        
    return None


@st.cache_data(ttl=3600)
def fetch_financial_data_dart(api_key, max_count=100):
    """
    KRX 시가총액 데이터와 DART 매출액을 병합하여 PSR 산출
    """
    try:
        dart = OpenDartReader(api_key)

        # 1. KRX 상장 종목 데이터 가져오기
        df_krx = fdr.StockListing('KRX')
        if df_krx.empty:
            return pd.DataFrame()

        rename_dict = {
            'Code': '티커',
            'Name': '종목명',
            'Market': '시장',
            'Close': '종가',
            'Marcap': '시가총액'
        }
        df_result = df_krx.rename(columns=rename_dict).copy()
        
        # 수치형 타입 정제
        df_result['시가총액'] = pd.to_numeric(df_result['시가총액'], errors='coerce')
        df_result['종가'] = pd.to_numeric(df_result['종가'], errors='coerce')
        df_result['시가총액(억원)'] = (df_result['시가총액'] / 100_000_000).round(1)

        # 분석 지정 범위 추출
        target_df = df_result.copy()
        if max_count > 0:
            target_df = target_df.head(max_count)

        # Progress bar 생성
        progress_text = "전자공시(DART) API로부터 정식 매출액 수집 중..."
        my_bar = st.progress(0, text=progress_text)
        
        sales_list = []
        total_len = len(target_df)
        current_year = datetime.now().year - 1  # 최근 결산연도 (직전 연도)

        for idx, row in enumerate(target_df.itertuples()):
            ticker = getattr(row, '티커')
            
            # DART API 매출액 수집
            sales = get_ttm_sales_dart(dart, ticker, current_year)
            sales_list.append(sales)

            if idx % 5 == 0 or idx == total_len - 1:
                my_bar.progress((idx + 1) / total_len, text=f"{progress_text} ({idx + 1}/{total_len})")

        my_bar.empty()

        target_df['매출액(억원)'] = sales_list
        target_df['매출액(억원)'] = pd.to_numeric(target_df['매출액(억원)'], errors='coerce')

        # PSR 계산 = 시가총액(억원) / 매출액(억원)
        target_df['PSR'] = (target_df['시가총액(억원)'] / target_df['매출액(억원)']).round(2)

        return target_df

    except Exception as e:
        st.error(f"DART 데이터 처리 중 오류 발생: {e}")
        return pd.DataFrame()


def render():
    st.title("📊 한국 상장기업 전종목 PSR 분석 (DART 연동)")
    st.caption("금융감독원 전자공시시스템(DART) 공식 재무제표 데이터를 조회하여 PSR을 산출합니다.")

    st.markdown("---")

    # 1. 패키지 설치 여부 검증
    if not DART_AVAILABLE:
        st.error("⚠️ `OpenDartReader` 패키지가 설치되어 있지 않습니다.")
        st.info("터미널(가상환경)에서 아래 명령어를 실행한 뒤 앱을 다시 시작해 주세요:\n```bash\npip install OpenDartReader finance-datareader\n```")
        return

    # 2. 사이드바 설정 영역
    st.sidebar.subheader("⚙️ DART API 및 분석 설정")
    
    dart_api_key = st.sidebar.text_input(
        "🔑 DART Open API Key", 
        type="password",
        help="https://opendart.fss.or.kr/ 에서 무료로 발급받은 API Key를 입력하세요."
    )

    analysis_scope = st.sidebar.radio(
        "분석 종목 범위 선택",
        ["시가총액 상위 50개 (빠름)", "시가총액 상위 100개", "시가총액 상위 300개", "전종목"],
        index=0
    )
    
    max_count_map = {
        "시가총액 상위 50개 (빠름)": 50,
        "시가총액 상위 100개": 100,
        "시가총액 상위 300개": 300,
        "전종목": 0
    }
    selected_count = max_count_map[analysis_scope]

    # 3. 메인 분석 연산 실행
    if st.button("🚀 DART 공식 재무제표 기반 PSR 계산 시작"):
        if not dart_api_key:
            st.error("사이드바에 DART Open API Key를 입력해 주세요.")
            return

        with st.spinner("DART 전자공시 시스템에서 재무제표를 수집 중입니다..."):
            df_cap = fetch_financial_data_dart(dart_api_key, max_count=selected_count)

        if not df_cap.empty:
            st.success(f"상장기업 {len(df_cap)}개 종목 분석 완료!")

            df_result = df_cap.copy()

            col1, col2 = st.columns(2)
            with col1:
                search_kw = st.text_input("🔍 종목명/티커 검색", "")
            with col2:
                max_psr = st.number_input("💡 최대 PSR 필터 (0 = 전체보기)", min_value=0.0, value=0.0, step=0.5)

            # 필터링
            if search_kw:
                df_result = df_result[
                    df_result["종목명"].astype(str).str.contains(search_kw, case=False, na=False) |
                    df_result["티커"].astype(str).str.contains(search_kw, case=False, na=False)
                ]
            
            if max_psr > 0:
                df_result = df_result[(df_result["PSR"].notnull()) & (df_result["PSR"] <= max_psr)]

            # PSR 오름차순(저평가) 정렬
            df_sorted = df_result.sort_values(by="PSR", ascending=True).copy()

            # 종가 표시용 포맷팅
            if "종가" in df_sorted.columns:
                df_sorted["종가(원)"] = df_sorted["종가"].apply(lambda x: f"{int(x):,}" if pd.notnull(x) and not pd.isna(x) else "0")

            st.subheader(f"📈 DART 기반 PSR 분석 결과 ({len(df_sorted)}개 종목)")
            
            show_cols = ['티커', '종목명', '시장', '종가(원)', '시가총액(억원)', '매출액(억원)', 'PSR']
            available_cols = [c for c in show_cols if c in df_sorted.columns]
            
            # 데이터프레임 출력
            st.dataframe(
                df_sorted[available_cols],
                use_container_width=True,
                height=500
            )

            # CSV 파일 다운로드
            today_str = datetime.today().strftime("%Y%m%d")
            csv_data = df_sorted[available_cols].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 분석 결과 CSV 다운로드",
                data=csv_data,
                file_name=f"dart_psr_analysis_{today_str}.csv",
                mime="text/csv"
            )
        else:
            st.warning("데이터를 가져오지 못했습니다. DART API Key 또는 네트워크 상태를 확인해 주세요.")