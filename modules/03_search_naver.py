from datetime import datetime, timedelta
import html
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


def _clean_html_text(text: str) -> str:
    """HTML 태그를 제거하고 HTML 엔티티(&amp;, &quot; 등)를 원래 문자로 변환합니다."""
    if not text:
        return ""
    no_tags = re.sub(r"<.*?>", "", str(text))
    return html.unescape(no_tags).strip()


# ==============================================================================
# 3. 기업명 기반 주가 데이터 조회 함수 (네이버 종목코드 검색 + yfinance)
# ==============================================================================
def _try_yfinance_history(
    ticker: str, start_date: datetime, end_date: datetime
) -> pd.DataFrame:
    """주어진 티커로 yfinance 일별 종가 데이터를 조회합니다."""
    try:
        hist = yf.Ticker(ticker).history(
            start=start_date.strftime("%Y-%m-%d"),
            end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            auto_adjust=True,
        )
        if hist is None or hist.empty or "Close" not in hist.columns:
            return pd.DataFrame()

        df_stock = hist[["Close"]].dropna().reset_index()
        date_col = df_stock.columns[0]
        df_stock["Date"] = pd.to_datetime(df_stock[date_col]).dt.strftime(
            "%Y-%m-%d"
        )
        df_stock = df_stock.groupby("Date", as_index=False)["Close"].last()
        return df_stock[["Date", "Close"]]
    except Exception:
        return pd.DataFrame()


def resolve_korean_ticker(
    company_name: str, manual_ticker: str = ""
) -> tuple[list[str], str]:
    """기업명 또는 수동 입력 티커로부터 시도할 야후 파이낸스 티커 후보 목록과 종목명을 반환합니다."""
    manual = manual_ticker.strip().upper()
    if manual:
        if manual.endswith((".KS", ".KQ")):
            return [manual], manual
        if re.fullmatch(r"\d{6}", manual):
            return [f"{manual}.KS", f"{manual}.KQ"], manual
        return [manual], manual

    query = company_name.strip()
    if not query:
        return [], ""

    if re.fullmatch(r"\d{6}", query):
        return [f"{query}.KS", f"{query}.KQ"], query

    upper_q = query.upper()
    if upper_q.endswith((".KS", ".KQ")):
        return [upper_q], upper_q

    candidates: list[str] = []
    resolved_name = query
    try:
        ac_url = (
            "https://ac.stock.naver.com/ac"
            f"?q={urllib.parse.quote(query)}&target=stock"
        )
        req = urllib.request.Request(
            ac_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.naver.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            items = payload.get("items", [])
            for item in items:
                code = str(item.get("code", "")).strip()
                market = str(item.get("market", "")).upper()
                name = str(item.get("name", "")).strip()
                if re.fullmatch(r"\d{6}", code):
                    if name and resolved_name == query:
                        resolved_name = name
                    suffix = ".KQ" if "KOSDAQ" in market else ".KS"
                    alt_suffix = ".KS" if suffix == ".KQ" else ".KQ"
                    for t in (f"{code}{suffix}", f"{code}{alt_suffix}"):
                        if t not in candidates:
                            candidates.append(t)
                    if candidates:
                        break
    except Exception:
        pass

    if not candidates:
        try:
            yf_url = (
                "https://query2.finance.yahoo.com/v1/finance/search"
                f"?q={urllib.parse.quote(query)}&quotesCount=5&newsCount=0"
            )
            req = urllib.request.Request(
                yf_url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for q_item in data.get("quotes", []):
                    sym = str(q_item.get("symbol", "")).strip()
                    if sym.endswith((".KS", ".KQ")) and sym not in candidates:
                        candidates.append(sym)
                        resolved_name = (
                            q_item.get("shortname")
                            or q_item.get("longname")
                            or query
                        )
                        break
        except Exception:
            pass

    return candidates, resolved_name


def fetch_stock_history(
    company_name: str,
    start_date: datetime,
    end_date: datetime,
    manual_ticker: str = "",
) -> tuple[pd.DataFrame, str | None, str]:
    """검색 기간에 해당하는 기업의 일별 주가(종가)를 가져옵니다."""
    candidates, resolved_name = resolve_korean_ticker(
        company_name, manual_ticker=manual_ticker
    )
    for ticker in candidates:
        df_stock = _try_yfinance_history(ticker, start_date, end_date)
        if not df_stock.empty:
            return df_stock, ticker, resolved_name

    fallback_ticker = candidates[0] if candidates else None
    return pd.DataFrame(), fallback_ticker, resolved_name


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
# 5. 주가(기본축) & 블로그 글 건수(보조축) 이중축 선 차트 생성
# ==============================================================================
def build_price_and_blog_chart(
    result_df: pd.DataFrame,
    df_stock: pd.DataFrame,
    keyword: str,
    ticker: str | None,
    start_date: datetime,
    end_date: datetime,
) -> go.Figure:
    all_dates = pd.date_range(
        start=start_date.strftime("%Y-%m-%d"),
        end=end_date.strftime("%Y-%m-%d"),
        freq="D",
    )
    base_df = pd.DataFrame({"Date": all_dates.strftime("%Y-%m-%d")})

    blog_counts = (
        result_df.groupby("날짜")
        .size()
        .reset_index(name="블로그건수")
        .rename(columns={"날짜": "Date"})
    )
    merged = pd.merge(base_df, blog_counts, on="Date", how="left")
    merged["블로그건수"] = merged["블로그건수"].fillna(0).astype(int)

    has_stock = not df_stock.empty
    if has_stock:
        merged = pd.merge(merged, df_stock, on="Date", how="left")
        merged["Close"] = merged["Close"].ffill().bfill()

    merged["DateNum"] = merged["Date"].str.replace("-", "", regex=False)

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if has_stock:
        label_name = (
            f"{keyword} 주가 ({ticker})" if ticker else f"{keyword} 주가"
        )
        fig.add_trace(
            go.Scatter(
                x=merged["DateNum"],
                y=merged["Close"],
                name=label_name,
                mode="lines",
                line=dict(color="#ef4444", width=2.5),
                hovertemplate="날짜: %{x}<br>종가: %{y:,.0f}원<extra></extra>",
            ),
            secondary_y=False,
        )

    fig.add_trace(
        go.Scatter(
            x=merged["DateNum"],
            y=merged["블로그건수"],
            name="블로그 글 건수 (건)",
            mode="lines+markers",
            line=dict(color="#38bdf8", width=2),
            marker=dict(size=5, color="#38bdf8"),
            hovertemplate="날짜: %{x}<br>블로그 건수: %{y}건<extra></extra>",
        ),
        secondary_y=True,
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
    )

    fig.update_xaxes(
        type="category",
        title_text="날짜 (YYYYMMDD)",
        tickmode="auto",
        nticks=8,
    )

    fig.update_yaxes(
        title_text="주가 (원)" if has_stock else "주가 (데이터 없음)",
        tickformat=",",
        showgrid=True,
        secondary_y=False,
    )

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
        "네이버 블로그에서 검색된 글 목록을 최근 작성일 순으로 확인하고, "
        "**주가 추이와 블로그 언급량**을 함께 비교합니다."
    )

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

    col_opt1, col_opt2 = st.columns([2.5, 1.5])
    with col_opt1:
        exclude_words_input = st.text_input(
            "🚫 제외할 단어 (쉼표로 구분하여 여러 개 입력 가능)",
            placeholder="예: 채용, 후기, 이벤트, 할인, 부고",
        )
    with col_opt2:
        manual_ticker = st.text_input(
            "📈 종목코드 직접 지정 (선택)",
            placeholder="예: 259960 또는 259960.KS",
            help="기업명 자동 검색이 안 될 때 6자리 종목코드나 .KS/.KQ 티커를 직접 입력하세요.",
        )

    col_chk1, col_chk2 = st.columns([1.4, 2.6])
    with col_chk1:
        exclude_in_desc = st.checkbox(
            "본문 요약에도 제외 단어 적용",
            value=False,
            help="체크 시 제목뿐 아니라 네이버 검색 결과의 본문 요약(description)에 제외 단어가 포함된 글도 제외합니다.",
        )
    with col_chk2:
        # 검색 결과 누락 방지를 위해 기본값은 False로 설정
        only_single_mention = st.checkbox(
            "복수 종목 나열 제목 일부 제외 (선택)",
            value=False,
            help="체크 시 슬래시(/)나 파이프(|) 등으로 여러 종목이 나열된 일부 제목을 제외합니다.",
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
        total_pages = max(1, (max_start + 99) // 100)

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
            progress_bar.progress((idx + 1) / total_pages)

        status_text.empty()
        progress_bar.empty()

        if not blog_items:
            st.warning("검색된 블로그 글이 없습니다.")
            return

        df = pd.DataFrame(blog_items)

        # 중복 링크 제거
        if "link" in df.columns:
            df = df.drop_duplicates(subset=["link"], keep="first")

        # postdate 파싱
        df["postDate"] = pd.to_datetime(
            df["postdate"], format="%Y%m%d", errors="coerce"
        )
        df = df.dropna(subset=["postDate"])

        if df.empty:
            st.warning("날짜 파싱이 가능한 글이 없습니다.")
            return

        # 정확한 개월 수 기준 기간 필터링 (KST 기준)
        now_kst = datetime.now(KST).replace(tzinfo=None)
        cutoff = pd.Timestamp(now_kst) - pd.DateOffset(months=months_filter)
        df = df[df["postDate"] >= cutoff]

        if df.empty:
            st.warning(f"최근 {months_filter}개월 내 작성된 블로그 글이 없습니다.")
            return

        # 제목 및 본문 요약 정제 (HTML 태그 및 엔티티 디코딩)
        df["clean_title"] = df["title"].apply(_clean_html_text)
        df["clean_desc"] = df.get("description", pd.Series("", index=df.index)).apply(
            _clean_html_text
        )

        # 제외 단어 필터링
        exclude_list = [
            w.strip() for w in exclude_words_input.split(",") if w.strip()
        ]
        if exclude_list:
            exclude_pattern = "|".join(re.escape(w) for w in exclude_list)
            df = df[
                ~df["clean_title"].str.contains(
                    exclude_pattern, case=False, na=False, regex=True
                )
            ]
            if exclude_in_desc:
                df = df[
                    ~df["clean_desc"].str.contains(
                        exclude_pattern, case=False, na=False, regex=True
                    )
                ]

        # 선택적 복수 나열 패턴 필터링 (과도한 탈락 방지)
        if only_single_mention:
            multi_list_pattern = re.compile(r"\s*[|]\s*")
            df = df[
                ~df["clean_title"].str.contains(multi_list_pattern, na=False)
            ]

        if df.empty:
            st.warning(
                "선택하신 필터링 조건(기간, 제외 단어)을 만족하는 블로그 글이 없습니다."
            )
            return

        # 최신순 정렬
        df = df.sort_values("postDate", ascending=False)

        # 결과 정리 (수집된 검색결과 전체 반영)
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
                clean_kw, cutoff.to_pydatetime(), now_kst, manual_ticker=manual_ticker
            )

        filter_info = (
            f" (제외 단어: {', '.join(exclude_list)})" if exclude_list else ""
        )
        st.success(
            f"🎉 총 **{len(result_df)}건**의 블로그 글을 수집했습니다!{filter_info}"
        )

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

        left_col, right_col = st.columns([1.05, 1.15], gap="medium")

        with left_col:
            st.subheader(f"📋 수집 결과 목록 ({len(result_df)}건)")
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
                st.warning(
                    f"'{clean_kw}'의 주가 시세를 가져오지 못해 블로그 건수만 표시합니다. "
                    "상단 '종목코드 직접 지정'에 6자리 종목코드(예: 259960)를 입력해 다시 검색해 보세요."
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
                start_date=cutoff.to_pydatetime(),
                end_date=now_kst,
            )
            st.plotly_chart(fig, use_container_width=True)
