from datetime import datetime, timedelta
import io
import json
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from openpyxl import load_workbook
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf

# ==============================================================================
# 1. 메뉴명 정의 (자동 로더 인식용)
# ==============================================================================
MENU_NAME = "자료찾기_FROM_NAVER"
KST = ZoneInfo("Asia/Seoul")

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
    url = (
        f"https://openapi.naver.com/v1/search/blog.json"
        f"?query={enc_text}&display={display}&start={start}&sort=date"
    )

    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", client_id.strip())
    request.add_header("X-Naver-Client-Secret", client_secret.strip())

    try:
        response = urllib.request.urlopen(request, timeout=15)
        if response.getcode() == 200:
            return json.loads(response.read().decode("utf-8")).get("items", [])
        return []
    except Exception:
        return []


# ==============================================================================
# 3. 기업명 기반 주가 데이터 조회 함수 (Yahoo Finance 자동 티커 검색)
# ==============================================================================
def resolve_korean_ticker(company_name: str) -> tuple[str | None, str | None]:
    """기업명으로 야후 파이낸스 검색 API를 조회하여 한국 증시(.KS / .KQ) 티커를 반환합니다."""
    query = company_name.strip()
    if not query:
        return None, None

    # 이미 6자리 숫자 티커 형태로 입력한 경우
    if re.fullmatch(r"\d{6}", query):
        for suffix in (".KS", ".KQ"):
            try:
                hist = yf.Ticker(query + suffix).history(period="5d")
                if not hist.empty:
                    return query + suffix, query
            except Exception:
                continue

    try:
        encoded = urllib.parse.quote(query)
        search_url = (
            f"https://query2.finance.yahoo.com/v1/finance/search"
            f"?q={encoded}&quotesCount=10&newsCount=0"
        )
        req = urllib.request.Request(
            search_url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            quotes = data.get("quotes", [])

            # .KS(코스피) 또는 .KQ(코스닥) 종목 우선 탐색
            for q in quotes:
                symbol = q.get("symbol", "")
                if symbol.endswith((".KS", ".KQ")):
                    resolved_name = (
                        q.get("shortname") or q.get("longname") or query
                    )
                    return symbol, resolved_name
    except Exception:
        pass

    return None, None


def fetch_stock_history(
    company_name: str, start_date: datetime, end_date: datetime
) -> tuple[pd.DataFrame, str | None, str | None]:
    """검색 기간에 해당하는 기업의 일별 주가(종가)를 가져옵니다."""
    ticker, resolved_name = resolve_korean_ticker(company_name)
    if not ticker:
        return pd.DataFrame(), None, None

    try:
        hist = yf.Ticker(ticker).history(
            start=start_date.strftime("%Y-%m-%d"),
            end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
        )
        if hist.empty:
            return pd.DataFrame(), ticker, resolved_name

        df_stock = hist[["Close"]].reset_index()
        df_stock["Date"] = pd.to_datetime(df_stock["Date"]).dt.strftime(
            "%Y-%m-%d"
        )
        df_stock = df_stock.groupby("Date", as_index=False)["Close"].last()
        return df_stock, ticker, resolved_name
    except Exception:
        return pd.DataFrame(), ticker, resolved_name


# ==============================================================================
# 4. 엑셀 파일 생성 (하이퍼링크 적용)
# ==============================================================================
def create_excel_with_hyperlinks(df, sheet_name="블로그글"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)

    output.seek(0)
    wb = load_workbook(output)
    ws = wb[sheet_name]

    header = {cell.value: cell.column for cell in ws[1] if cell.value}
    link_col_name = "블로그링크"

    if link_col_name in header:
        col_idx = header[link_col_name]
        for row_idx in range(2, ws.max_row + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            url = cell.value
            if url and str(url).startswith("http"):
                cell.hyperlink = url
                cell.style = "Hyperlink"

    excel_data = io.BytesIO()
    wb.save(excel_data)
    excel_data.seek(0)
    return excel_data


# ==============================================================================
# 5. 주가(기본축) & 블로그 글 건수(보조축) 이중축 차트 생성
# ==============================================================================
def build_price_and_blog_chart(
    result_df: pd.DataFrame,
    df_stock: pd.DataFrame,
    keyword: str,
    ticker: str | None,
    start_date: datetime,
    end_date: datetime,
) -> go.Figure:
    # 1. 검색 기간 전체 날짜 캘린더 생성
    all_dates = pd.date_range(
        start=start_date.strftime("%Y-%m-%d"),
        end=end_date.strftime("%Y-%m-%d"),
        freq="D",
    )
    base_df = pd.DataFrame({"Date": all_dates.strftime("%Y-%m-%d")})

    # 2. 일별 블로그 건수 집계
    blog_counts = (
        result_df.groupby("날짜")
        .size()
        .reset_index(name="블로그건수")
        .rename(columns={"날짜": "Date"})
    )
    merged = pd.merge(base_df, blog_counts, on="Date", how="left")
    merged["블로그건수"] = merged["블로그건수"].fillna(0).astype(int)

    # 3. 주가 데이터 병합 (휴장일은 직전 거래일 종가로 보간하여 선이 끊기지 않게 처리)
    has_stock = not df_stock.empty
    if has_stock:
        merged = pd.merge(merged, df_stock, on="Date", how="left")
        merged["Close"] = merged["Close"].ffill().bfill()

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 보조축(우측): 일별 블로그 글 건수 (막대 차트)
    fig.add_trace(
        go.Bar(
            x=merged["Date"],
            y=merged["블로그건수"],
            name="블로그 글 건수 (건)",
            marker_color="rgba(56, 189, 248, 0.45)",
            hovertemplate="날짜: %{x}<br>블로그 건수: %{y}건<extra></extra>",
        ),
        secondary_y=True,
    )

    # 기본축(좌측): 기업 주가 (라인 차트)
    if has_stock:
        label_name = (
            f"{keyword} 주가 ({ticker})" if ticker else f"{keyword} 주가"
        )
        fig.add_trace(
            go.Scatter(
                x=merged["Date"],
                y=merged["Close"],
                name=label_name,
                mode="lines",
                line=dict(color="#ef4444", width=2.5),
                hovertemplate="날짜: %{x}<br>종가: %{y:,.0f}원<extra></extra>",
            ),
            secondary_y=False,
        )

    title_suffix = (
        f"주가 ({ticker}) vs 블로그 언급량"
        if has_stock
        else "블로그 언급량 (주가 데이터 미매칭)"
    )

    fig.update_layout(
        title=dict(
            text=f"<b>📈 {keyword} — {title_suffix}</b>",
            font=dict(size=17),
        ),
        height=560,
        margin=dict(l=15, r=15, t=60, b=20),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
        ),
        bargap=0.15,
    )

    # 기본축(좌측 Y축) 설정
    fig.update_yaxes(
        title_text="주가 (원)" if has_stock else "주가 (데이터 없음)",
        tickformat=",",
        showgrid=True,
        secondary_y=False,
    )

    # 보조축(우측 Y축) 설정
    max_cnt = max(int(merged["블로그건수"].max()), 1)
    fig.update_yaxes(
        title_text="블로그 글 건수 (건)",
        range=[0, max_cnt * 1.25],
        dtick=max(1, max_cnt // 5),
        showgrid=False,
        secondary_y=True,
    )

    return fig


# ==============================================================================
# 6. Streamlit 화면 렌더링
# ==============================================================================
def render():
    st.title("🔍 네이버 블로그 키워드 단독 언급 검색기")
    st.markdown(
        "네이버 블로그에서 특정 키워드/기업명이 **제목에 단독으로 언급된 글**을 최근 작성일 순으로 검색하고, "
        "**주가 추이와 블로그 언급량**을 함께 비교합니다."
    )

    # API 키 및 기본 설정
    with st.expander("🔑 네이버 API 키 설정", expanded=False):
        col_api1, col_api2 = st.columns(2)
        with col_api1:
            client_id = st.text_input(
                "Client ID", value=DEFAULT_CLIENT_ID, type="password"
            )
        with col_api2:
            client_secret = st.text_input(
                "Client Secret", value=DEFAULT_CLIENT_SECRET, type="password"
            )

    # 검색 입력 및 옵션 설정
    st.subheader("📌 검색 옵션")

    sample_keywords = [
        "인바디",
        "아이센스",
        "넥스트바이오메디컬",
        "세나테크놀로지",
        "티앤엘",
        "크래프톤",
        "에프앤가이드",
        "씨어스",
        "NI스틸",
        "에스티팜",
        "HK이노엔",
        "글로벌텍스프리",
        "인텔리안테크",
        "디케이티",
        "파마리서치",
    ]
    st.markdown(
        "**💡 추천 예시 키워드:** "
        + ", ".join([f"`{k}`" for k in sample_keywords[:8]])
    )

    col_input1, col_input2, col_input3 = st.columns([2.5, 1, 1])

    with col_input1:
        keyword = st.text_input(
            "검색 키워드 (기업명) 입력",
            placeholder="예: 티앤엘, 크래프톤, 파마리서치",
        )

    with col_input2:
        months_filter = st.selectbox(
            "검색 기간",
            options=[3, 6, 12, 24],
            index=1,
            format_func=lambda x: f"최근 {x}개월",
        )

    with col_input3:
        max_fetch = st.selectbox(
            "최대 수집 건수",
            options=[300, 500, 1000],
            index=2,
            format_func=lambda x: f"최대 {x}건",
        )

    # 제외할 단어 입력 및 필터 옵션
    col_opt1, col_opt2 = st.columns([2.5, 1.5])
    with col_opt1:
        exclude_words_input = st.text_input(
            "🚫 제외할 단어 (쉼표로 구분하여 여러 개 입력 가능)",
            placeholder="예: 채용, 후기, 이벤트, 할인, 부고",
        )
    with col_opt2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        exclude_in_desc = st.checkbox(
            "본문 요약에도 제외 단어 적용",
            value=False,
            help="체크 시 제목뿐 아니라 네이버 검색 결과의 본문 요약(description)에 제외 단어가 포함된 글도 제외합니다.",
        )

    only_single_mention = st.checkbox(
        "제목에 타 기업/키워드 동시 언급된 글 제외 (단독 언급 필터링)",
        value=True,
    )

    if st.button("🚀 블로그 검색 시작", use_container_width=True, type="primary"):
        clean_kw = keyword.strip()
        if not clean_kw:
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
            status_text.text(
                f"네이버 블로그 데이터 수집 중... ({start}~{start + 99}건)"
            )
            items = search_naver_blog(
                clean_kw, client_id, client_secret, display=100, start=start
            )
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
        df["postDate"] = pd.to_datetime(
            df["postdate"], format="%Y%m%d", errors="coerce"
        )
        df = df.dropna(subset=["postDate"])

        if df.empty:
            st.warning("날짜 파싱이 가능한 글이 없습니다.")
            return

        # 기간 필터링 (KST 기준)
        now_kst = datetime.now(KST).replace(tzinfo=None)
        cutoff = now_kst - timedelta(days=months_filter * 30)
        df = df[df["postDate"] >= cutoff]

        if df.empty:
            st.warning(f"최근 {months_filter}개월 내 작성된 블로그 글이 없습니다.")
            return

        # 제목 및 본문 요약 정제 (HTML 태그 제거)
        df["clean_title"] = (
            df["title"].str.replace(r"<.*?>", "", regex=True).str.strip()
        )
        df["clean_desc"] = (
            df["description"]
            .fillna("")
            .str.replace(r"<.*?>", "", regex=True)
            .str.strip()
        )

        # 키워드 포함 조건
        df = df[
            df["clean_title"].str.contains(re.escape(clean_kw), case=False)
        ]

        # 제외 단어 필터링
        exclude_list = [
            w.strip() for w in exclude_words_input.split(",") if w.strip()
        ]
        if exclude_list:
            exclude_pattern = "|".join(re.escape(w) for w in exclude_list)
            df = df[
                ~df["clean_title"].str.contains(
                    exclude_pattern, case=False, na=False
                )
            ]
            if exclude_in_desc:
                df = df[
                    ~df["clean_desc"].str.contains(
                        exclude_pattern, case=False, na=False
                    )
                ]

        # 단독 언급 필터링
        if only_single_mention:
            multi_pattern = re.compile(
                r"[,&·\|]\s*[가-힣\w]+(?:주|코퍼레이션|홀딩스|인더스트리)?\s*[,&·\|]"
            )
            df = df[~df["clean_title"].str.contains(multi_pattern)]
            df = df[
                ~df["clean_title"].str.contains(
                    r",.*" + re.escape(clean_kw), case=False
                )
            ]
            df = df[
                ~df["clean_title"].str.contains(
                    re.escape(clean_kw) + r".*,", case=False
                )
            ]

        if df.empty:
            st.warning(
                "선택하신 필터링 조건(기간, 제외 단어, 단독 언급)을 만족하는 블로그 글이 없습니다."
            )
            return

        # 최신순 정렬
        df = df.sort_values("postDate", ascending=False)

        # 결과 정리
        result_df = df[["postDate", "clean_title", "link"]].copy()
        result_df["postDate"] = result_df["postDate"].dt.strftime("%Y-%m-%d")
        result_df.rename(
            columns={
                "postDate": "날짜",
                "clean_title": "제목",
                "link": "블로그링크",
            },
            inplace=True,
        )

        # 기업 주가 데이터 조회
        with st.spinner(f"'{clean_kw}' 주가 데이터를 조회하는 중입니다..."):
            df_stock, ticker, resolved_name = fetch_stock_history(
                clean_kw, cutoff, now_kst
            )

        filter_info = (
            f" (제외 단어: {', '.join(exclude_list)})" if exclude_list else ""
        )
        st.success(
            f"🎉 총 **{len(result_df)}건**의 블로그 글을 수집했습니다!{filter_info}"
        )

        # 엑셀 다운로드 버튼 준비
        excel_bytes = create_excel_with_hyperlinks(result_df)
        today_str = now_kst.strftime("%Y%m%d")
        safe_kw = re.sub(r'[\/\\:*?"<>|]', "_", clean_kw)
        download_filename = f"{safe_kw}_블로그글_{today_str}.xlsx"

        st.download_button(
            label="📥 클릭 가능한 엑셀 파일 다운로드 (.xlsx)",
            data=excel_bytes,
            file_name=download_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

        st.markdown("---")

        # 좌측: 수집 결과 목록 / 우측: 주가(기본축) + 글 건수(보조축) 차트
        left_col, right_col = st.columns([1.05, 1.15], gap="medium")

        with left_col:
            st.subheader("📋 수집 결과 목록")
            st.dataframe(
                result_df,
                height=560,
                column_config={
                    "날짜": st.column_config.TextColumn("날짜", width="small"),
                    "제목": st.column_config.TextColumn("제목", width="large"),
                    "블로그링크": st.column_config.LinkColumn(
                        "블로그링크", display_text="링크 이동"
                    ),
                },
                hide_index=True,
                use_container_width=True,
            )

        with right_col:
            st.subheader("📊 주가 및 블로그 언급 추이")
            if df_stock.empty:
                st.caption(
                    f"'{clean_kw}'에 해당하는 국내 상장 종목 주가를 찾지 못해 블로그 건수만 표시합니다."
                )
            else:
                st.caption(
                    f"기준 종목: {resolved_name} ({ticker}) | 기본축(좌): 주가(원) · 보조축(우): 블로그 글 건수(건)"
                )

            fig = build_price_and_blog_chart(
                result_df=result_df,
                df_stock=df_stock,
                keyword=clean_kw,
                ticker=ticker,
                start_date=cutoff,
                end_date=now_kst,
            )
            st.plotly_chart(fig, use_container_width=True)
