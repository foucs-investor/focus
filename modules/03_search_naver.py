import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import urllib.request
import urllib.parse
import json
import re
import io
from openpyxl import load_workbook

# ==============================================================================
# 1. 메뉴명 정의 (자동 로더 인식용)
# ==============================================================================
MENU_NAME = '자료찾기_FROM_NAVER'

# 기본 API 키 설정 (필요시 UI에서 직접 수정 가능)
DEFAULT_CLIENT_ID = "b0IWGOne3WaxxRJD4tV_"
DEFAULT_CLIENT_SECRET = "YOyQkfImmL"

# ==============================================================================
# 2. 네이버 블로그 검색 함수
# ==============================================================================
def search_naver_blog(query, client_id, client_secret, display=100, start=1):
    if not client_id.strip() or not client_secret.strip():
        return []

    enc_text = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/blog.json?query={enc_text}&display={display}&start={start}&sort=date"

    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", client_id.strip())
    request.add_header("X-Naver-Client-Secret", client_secret.strip())

    try:
        response = urllib.request.urlopen(request, timeout=15)
        if response.getcode() == 200:
            return json.loads(response.read().decode('utf-8')).get('items', [])
        else:
            return []
    except Exception:
        return []

# ==============================================================================
# 3. 엑셀 파일 생성 (하이퍼링크 적용)
# ==============================================================================
def create_excel_with_hyperlinks(df, sheet_name='블로그글'):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    
    output.seek(0)
    wb = load_workbook(output)
    ws = wb[sheet_name]

    header = {cell.value: cell.column for cell in ws[1] if cell.value}
    link_col_name = '블로그링크'

    if link_col_name in header:
        col_idx = header[link_col_name]
        for row_idx in range(2, ws.max_row + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            url = cell.value
            if url and str(url).startswith('http'):
                cell.hyperlink = url
                cell.style = 'Hyperlink'

    excel_data = io.BytesIO()
    wb.save(excel_data)
    excel_data.seek(0)
    return excel_data

# ==============================================================================
# 4. Streamlit 화면 랜더링
# ==============================================================================
def render():
    st.title("🔍 네이버 블로그 키워드 단독 언급 검색기")
    st.markdown("네이버 블로그에서 특정 키워드/기업명이 **제목에 단독으로 언급된 글**을 최근 작성일 순으로 검색하고 엑셀로 다운로드합니다.")

    # API 키 및 기본 설정 (접을 수 있는 Expander)
    with st.expander("🔑 네이버 API 키 설정", expanded=False):
        col_api1, col_api2 = st.columns(2)
        with col_api1:
            client_id = st.text_input("Client ID", value=DEFAULT_CLIENT_ID, type="password")
        with col_api2:
            client_secret = st.text_input("Client Secret", value=DEFAULT_CLIENT_SECRET, type="password")

    # 검색 입력 및 옵션 설정
    st.subheader("📌 검색 옵션")
    
    # 추천 예시 키워드 태그
    sample_keywords = ["인바디", "아이센스", "넥스트바이오메디컬", "세나테크놀로지", "티앤엘", "크래프톤", "에프앤가이드", "씨어스", "NI스틸", "에스티팜", "HK이노엔", "글로벌텍스프리", "인텔리안테크", "디케이티", "파마리서치"]
    
    st.markdown("**💡 추천 예시 키워드:** " + ", ".join([f"`{k}`" for k in sample_keywords[:8]]))

    col_input1, col_input2, col_input3 = st.columns([2.5, 1, 1])
    
    with col_input1:
        keyword = st.text_input("검색 키워드 입력", placeholder="예: 티앤엘, 크래프톤, AI 반도체")
    
    with col_input2:
        months_filter = st.selectbox("검색 기간", options=[3, 6, 12, 24], index=1, format_func=lambda x: f"최근 {x}개월")
    
    with col_input3:
        max_fetch = st.selectbox("최대 수집 건수", options=[300, 500, 1000], index=2, format_func=lambda x: f"최대 {x}건")

    only_single_mention = st.checkbox("제목에 타 기업/키워드 동시 언급된 글 제외 (단독 언급 필터링)", value=True)

    if st.button("🚀 블로그 검색 시작", use_container_width=True, type="primary"):
        if not keyword.strip():
            st.warning("⚠️ 검색할 키워드를 입력해 주세요.")
            return
        
        if not client_id or not client_secret:
            st.error("⚠️ 네이버 API Client ID와 Client Secret을 입력해 주세요.")
            return

        status_text = st.empty()
        progress_bar = st.progress(0)

        blog_items = []
        max_start = min(max_fetch, 1000)

        for idx, start in enumerate(range(1, max_start + 1, 100)):
            status_text.text(f"네이버 블로그 데이터 수집 중... ({start}~{start + 99}건)")
            items = search_naver_blog(keyword.strip(), client_id, client_secret, display=100, start=start)
            if not items:
                break
            blog_items.extend(items)
            progress_bar.progress((idx + 1) / (max_start // 100))

        status_text.empty()
        progress_bar.empty()

        if not blog_items:
            st.warning("검색된 블로그 글이 없습니다.")
            return

        df = pd.DataFrame(blog_items)

        # postdate 파싱
        df['postDate'] = pd.to_datetime(df['postdate'], format='%Y%m%d', errors='coerce')
        df = df.dropna(subset=['postDate'])

        if df.empty:
            st.warning("날짜 파싱이 가능한 글이 없습니다.")
            return

        # 기간 필터링
        cutoff = datetime.now() - timedelta(days=months_filter * 30)
        df = df[df['postDate'] >= cutoff]

        if df.empty:
            st.warning(f"최근 {months_filter}개월 내 작성된 블로그 글이 없습니다.")
            return

        # 제목 정제 (HTML 태그 제거)
        df['clean_title'] = df['title'].str.replace(r'<.*?>', '', regex=True).str.strip()

        # 키워드 포함 조건
        df = df[df['clean_title'].str.contains(re.escape(keyword.strip()), case=False)]

        # 단독 언급 필터링
        if only_single_mention:
            multi_pattern = re.compile(r'[,&·\|]\s*[가-힣\w]+(?:주|코퍼레이션|홀딩스|인더스트리)?\s*[,&·\|]')
            df = df[~df['clean_title'].str.contains(multi_pattern)]
            df = df[~df['clean_title'].str.contains(r',.*' + re.escape(keyword.strip()), case=False)]
            df = df[~df['clean_title'].str.contains(re.escape(keyword.strip()) + r'.*,', case=False)]

        if df.empty:
            st.warning(f"필터링 조건(단독 언급 및 기간 {months_filter}개월)을 만족하는 블로그 글이 없습니다.")
            return

        # 최신순 정렬
        df = df.sort_values('postDate', ascending=False)

        # 결과 정리
        result_df = df[['postDate', 'clean_title', 'link']].copy()
        result_df['postDate'] = result_df['postDate'].dt.strftime('%Y-%m-%d')
        result_df.rename(columns={
            'postDate': '날짜',
            'clean_title': '제목',
            'link': '블로그링크'
        }, inplace=True)

        st.success(f"🎉 총 {len(result_df)}건의 블로그 글을 수집했습니다!")

        # 엑셀 다운로드 버튼 준비
        excel_bytes = create_excel_with_hyperlinks(result_df)
        today_str = datetime.now().strftime('%Y%m%d')
        safe_kw = re.sub(r'[\/\\:*?"<>|]', '_', keyword.strip())
        download_filename = f"{safe_kw}_블로그글_{today_str}.xlsx"

        st.download_button(
            label="📥 클릭 가능한 엑셀 파일 다운로드 (.xlsx)",
            data=excel_bytes,
            file_name=download_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

        st.markdown("---")
        st.subheader("📋 수집 결과 목록")

        # 클릭 가능한 하이퍼링크가 적용된 Streamlit 테이블 표시
        st.dataframe(
            result_df,
            column_config={
                "날짜": st.column_config.TextColumn("날짜", width="small"),
                "제목": st.column_config.TextColumn("제목", width="large"),
                "블로그링크": st.column_config.LinkColumn("블로그링크", display_text="링크 이동")
            },
            hide_index=True,
            use_container_width=True
        )