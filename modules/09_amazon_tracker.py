import os
import re
import time
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from bs4 import BeautifulSoup
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

MENU_NAME = "아마존 트레킹"

DATA_DIR = "data"
WATCHLIST_FILE = os.path.join(DATA_DIR, "amazon_watchlist.csv")
HISTORY_FILE = os.path.join(DATA_DIR, "amazon_tracking_history.csv")


def init_storage():
    """데이터 폴더 및 초기 CSV 파일 생성"""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(WATCHLIST_FILE):
        df_watch = pd.DataFrame(columns=["company", "product_name", "asin", "memo"])
        df_watch.to_csv(WATCHLIST_FILE, index=False, encoding="utf-8-sig")

    if not os.path.exists(HISTORY_FILE):
        df_hist = pd.DataFrame(
            columns=[
                "date",
                "company",
                "product_name",
                "asin",
                "price_usd",
                "review_count",
                "rating",
                "bsr_main",
                "bsr_sub",
                "stock_status",
            ]
        )
        df_hist.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")


def extract_asin(input_str: str) -> str:
    """전체 URL 또는 10자리 ASIN 코드 추출"""
    input_str = input_str.strip()
    match = re.search(r"(?:dp|gp/product)/([A-Z0-9]{10})", input_str)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Z0-9]{10}", input_str):
        return input_str
    return ""


def _playwright_worker(asin: str) -> dict:
    """실제 크롬 브라우저(Playwright)로 미국 배송지 기준 아마존 페이지 파싱"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"error": "playwright 미설치: 터미널에서 'pip install playwright && playwright install chromium' 실행 필요"}

    url = f"https://www.amazon.com/dp/{asin}?language=en_US&currency=USD"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": 1366, "height": 900},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)  # 동적 가격/리뷰 로딩 대기

            html = page.content()
            browser.close()

        if "Enter the characters you see below" in html or "Type the characters you see in this image" in html:
            return {"error": "아마존 CAPTCHA 차단 발생 (잠시 후 재시도 필요)"}

        soup = BeautifulSoup(html, "html.parser")

        # 1. 판매 가격 (USD) - 다중 셀렉터 대응
        price = None
        price_selectors = [
            "#corePrice_feature_div span.a-price span.a-offscreen",
            "#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen",
            "span.apexPriceToPay span.a-offscreen",
            "span.a-price span.a-offscreen",
        ]
        for sel in price_selectors:
            el = soup.select_one(sel)
            if el and "$" in el.get_text():
                txt = re.sub(r"[^\d.]", "", el.get_text())
                if txt:
                    price = float(txt)
                    break

        # 2. 누적 리뷰 수
        review_count = None
        rev_el = soup.select_one("#acrCustomerReviewText")
        if rev_el:
            rev_txt = re.sub(r"[^\d]", "", rev_el.get_text())
            review_count = int(rev_txt) if rev_txt else None

        # 3. 평점
        rating = None
        rat_el = soup.select_one("#acrPopover span.a-icon-alt") or soup.select_one("span[data-hook='rating-out-of-text']")
        if rat_el:
            rat_match = re.search(r"([\d.]+)", rat_el.get_text())
            rating = float(rat_match.group(1)) if rat_match else None

        # 4. 베스트셀러 순위 (BSR - 대분류 / 소분류)
        bsr_main, bsr_sub = None, None
        # Product Details 영역 우선 검색 후 전체 텍스트 백업 검색
        detail_section = soup.select_one("#detailBulletsWrapper_feature_div") or soup.select_one("#productDetails_detailBullets_sections1")
        target_text = detail_section.get_text(" ", strip=True) if detail_section else soup.get_text(" ", strip=True)
        bsr_matches = re.findall(r"#([\d,]+)\s+in\s+[A-Za-z0-9 &,'-]+", target_text)
        if len(bsr_matches) >= 1:
            bsr_main = int(bsr_matches[0].replace(",", ""))
        if len(bsr_matches) >= 2:
            bsr_sub = int(bsr_matches[1].replace(",", ""))

        # 5. 재고 상태
        stock_status = "In Stock"
        avail_el = soup.select_one("#availability")
        if avail_el:
            avail_txt = avail_el.get_text(strip=True).lower()
            if "currently unavailable" in avail_txt or "out of stock" in avail_txt:
                stock_status = "Out of Stock"
            elif "left in stock" in avail_txt:
                stock_status = "Low Stock"

        # 모든 핵심 지표가 None이면 차단/미로딩으로 간주
        if price is None and review_count is None and bsr_main is None:
            return {"error": "페이지 로딩은 되었으나 가격/리뷰/순위 요소를 찾지 못함 (아마존 구조 변경 또는 지역 제한)"}

        return {
            "price_usd": price,
            "review_count": review_count,
            "rating": rating,
            "bsr_main": bsr_main,
            "bsr_sub": bsr_sub,
            "stock_status": stock_status,
            "error": None,
        }

    except Exception as e:
        return {"error": str(e)}


def fetch_amazon_product(asin: str) -> dict:
    """Windows Streamlit 이벤트 루프 충돌 방지를 위해 별도 스레드에서 실행"""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_playwright_worker, asin)
        return future.result()


def render():
    init_storage()
    st.header("📦 아마존 트레킹 (Amazon Product Tracker)")
    st.caption("기업별 미국 아마존 주력 SKU의 판매 순위(BSR), 누적 리뷰 증가 추이, 가격 및 품절 여부를 누적 추적합니다.")

    df_watch = pd.read_csv(WATCHLIST_FILE, dtype={"asin": str})
    df_hist = pd.read_csv(HISTORY_FILE, dtype={"asin": str})

    # ---------------------------------------------------------
    # 1. 신규 트래킹 제품 등록
    # ---------------------------------------------------------
    with st.expander("➕ 트래킹 제품 추가 / 관리", expanded=df_watch.empty):
        with st.form("add_product_form", clear_on_submit=True):
            col1, col2, col3, col4 = st.columns([1.2, 2, 1.8, 1.5])
            with col1:
                company = st.text_input("기업명", placeholder="예: 아로마티카")
            with col2:
                product_name = st.text_input("제품명", placeholder="예: 로즈마리 스칼프 스케일링 샴푸")
            with col3:
                asin_input = st.text_input("ASIN 또는 아마존 URL", placeholder="예: B01NBJ9LTS")
            with col4:
                memo = st.text_input("비고 (매출비중 등)", placeholder="예: 매출비중 11.0%")

            submitted = st.form_submit_button("관심 제품 등록")
            if submitted:
                clean_asin = extract_asin(asin_input)
                if not company or not product_name or not clean_asin:
                    st.error("기업명, 제품명, 그리고 올바른 10자리 ASIN(또는 아마존 상품 URL)을 입력해주세요.")
                elif clean_asin in df_watch["asin"].values:
                    st.warning(f"이미 등록된 ASIN입니다: {clean_asin}")
                else:
                    new_row = pd.DataFrame(
                        [[company.strip(), product_name.strip(), clean_asin, memo.strip()]],
                        columns=["company", "product_name", "asin", "memo"],
                    )
                    df_watch = pd.concat([df_watch, new_row], ignore_index=True)
                    df_watch.to_csv(WATCHLIST_FILE, index=False, encoding="utf-8-sig")
                    st.success(f"[{company}] {product_name} ({clean_asin}) 등록 완료")
                    st.rerun()

        if not df_watch.empty:
            st.markdown("**등록된 트래킹 리스트**")
            st.dataframe(df_watch, use_container_width=True, hide_index=True)
            del_asin = st.selectbox(
                "삭제할 제품 선택",
                options=["선택 안함"] + [f"{r.company} - {r.product_name} ({r.asin})" for _, r in df_watch.iterrows()],
            )
            if del_asin != "선택 안함" and st.button("선택 제품 삭제"):
                target_asin = del_asin.split("(")[-1].replace(")", "")
                df_watch = df_watch[df_watch["asin"] != target_asin]
                df_watch.to_csv(WATCHLIST_FILE, index=False, encoding="utf-8-sig")
                st.rerun()

    if df_watch.empty:
        st.info("상단의 '트래킹 제품 추가 / 관리'를 열어 모니터링할 기업과 제품의 ASIN을 등록해주세요.")
        return

    # ---------------------------------------------------------
    # 2. 데이터 수집 실행 및 수동 보정 입력
    # ---------------------------------------------------------
    st.divider()
    col_f1, col_f2 = st.columns([2, 1])
    companies = ["전체 기업"] + sorted(df_watch["company"].unique().tolist())
    with col_f1:
        selected_company = st.selectbox("조회 및 수집할 기업 선택", companies)
    with col_f2:
        st.write("")
        run_scrape = st.button("🔄 현재 시점 아마존 데이터 수집", type="primary", use_container_width=True)

    target_watch = (
        df_watch if selected_company == "전체 기업" else df_watch[df_watch["company"] == selected_company]
    )

    if run_scrape:
        today_str = datetime.now().strftime("%Y-%m-%d")
        progress = st.progress(0)
        status_box = st.empty()
        new_records = []

        for idx, row in enumerate(target_watch.itertuples()):
            status_box.text(f"브라우저 수집 중 ({idx+1}/{len(target_watch)}): [{row.company}] {row.product_name}...")
            res = fetch_amazon_product(row.asin)

            if res.get("error"):
                st.error(f"[{row.product_name} ({row.asin})] 수집 실패: {res['error']}")
            else:
                new_records.append(
                    {
                        "date": today_str,
                        "company": row.company,
                        "product_name": row.product_name,
                        "asin": row.asin,
                        "price_usd": res["price_usd"],
                        "review_count": res["review_count"],
                        "rating": res["rating"],
                        "bsr_main": res["bsr_main"],
                        "bsr_sub": res["bsr_sub"],
                        "stock_status": res["stock_status"],
                    }
                )
            progress.progress((idx + 1) / len(target_watch))
            time.sleep(random.uniform(1.0, 2.0))

        if new_records:
            df_new = pd.DataFrame(new_records)
            df_hist = df_hist[
                ~((df_hist["date"] == today_str) & (df_hist["asin"].isin(df_new["asin"])))
            ]
            df_hist = pd.concat([df_hist, df_new], ignore_index=True)
            df_hist.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")
            status_box.success(f"{today_str} 기준 {len(new_records)}개 제품 데이터 업데이트 완료!")
            st.rerun()

    # 수동 입력 / 수정 Expander (차단 시 백업 및 과거 데이터 입력용)
    with st.expander("✍️ 데이터 수동 입력 / 수정 (차단 발생 시 또는 과거 데이터 보정용)"):
        with st.form("manual_entry_form"):
            m_col1, m_col2, m_col3 = st.columns([2, 1, 1])
            with m_col1:
                m_prod = st.selectbox(
                    "대상 제품",
                    [f"[{r.company}] {r.product_name} ({r.asin})" for _, r in target_watch.iterrows()],
                )
            with m_col2:
                m_date = st.date_input("기준일자", datetime.now())
            with m_col3:
                m_stock = st.selectbox("재고상태", ["In Stock", "Low Stock", "Out of Stock"])

            m_col4, m_col5, m_col6, m_col7 = st.columns(4)
            with m_col4:
                m_price = st.number_input("가격 (USD)", min_value=0.0, step=0.01, value=20.0)
            with m_col5:
                m_review = st.number_input("누적 리뷰 수", min_value=0, step=1, value=0)
            with m_col6:
                m_bsr_main = st.number_input("대분류 순위 (BSR)", min_value=0, step=1, value=0)
            with m_col7:
                m_bsr_sub = st.number_input("소분류 순위 (BSR)", min_value=0, step=1, value=0)

            if st.form_submit_button("수동 데이터 저장"):
                sel_asin_m = m_prod.split("(")[-1].replace(")", "")
                matched = df_watch[df_watch["asin"] == sel_asin_m].iloc[0]
                d_str = m_date.strftime("%Y-%m-%d")
                manual_row = pd.DataFrame(
                    [
                        {
                            "date": d_str,
                            "company": matched["company"],
                            "product_name": matched["product_name"],
                            "asin": sel_asin_m,
                            "price_usd": m_price if m_price > 0 else None,
                            "review_count": m_review if m_review > 0 else None,
                            "rating": None,
                            "bsr_main": m_bsr_main if m_bsr_main > 0 else None,
                            "bsr_sub": m_bsr_sub if m_bsr_sub > 0 else None,
                            "stock_status": m_stock,
                        }
                    ]
                )
                df_hist = df_hist[~((df_hist["date"] == d_str) & (df_hist["asin"] == sel_asin_m))]
                df_hist = pd.concat([df_hist, manual_row], ignore_index=True)
                df_hist.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")
                st.success(f"{d_str} 데이터가 저장되었습니다.")
                st.rerun()

    # ---------------------------------------------------------
    # 3. 트래킹 현황 요약 및 시계열 차트
    # ---------------------------------------------------------
    filtered_hist = (
        df_hist if selected_company == "전체 기업" else df_hist[df_hist["company"] == selected_company]
    )

    if filtered_hist.empty:
        st.info("아직 수집된 이력이 없습니다. '현재 시점 아마존 데이터 수집' 버튼을 눌러 첫 데이터를 기록하세요.")
        return

    # 숫자형 강제 변환 (None/NaN 안전 처리)
    for num_col in ["price_usd", "review_count", "rating", "bsr_main", "bsr_sub"]:
        filtered_hist[num_col] = pd.to_numeric(filtered_hist[num_col], errors="coerce")

    filtered_hist = filtered_hist.sort_values(["asin", "date"])
    filtered_hist["new_reviews"] = filtered_hist.groupby("asin")["review_count"].diff().fillna(0)

    # 최신 스냅샷 테이블
    latest_df = filtered_hist.groupby("asin").tail(1).copy()
    st.subheader("📊 최신 트래킹 현황")
    display_cols = [
        "date",
        "company",
        "product_name",
        "asin",
        "price_usd",
        "review_count",
        "new_reviews",
        "bsr_main",
        "bsr_sub",
        "stock_status",
    ]
    st.dataframe(latest_df[display_cols], use_container_width=True, hide_index=True)

    # 제품별 상세 시계열 그래프
    st.subheader("📈 제품별 판매 모멘텀 추이 (BSR 순위 & 누적 리뷰)")
    product_options = [
        f"[{r.company}] {r.product_name} ({r.asin})" for _, r in target_watch.iterrows()
    ]
    selected_prod = st.selectbox("그래프 조회 제품", product_options)
    sel_asin = selected_prod.split("(")[-1].replace(")", "")

    prod_df = filtered_hist[filtered_hist["asin"] == sel_asin].sort_values("date")

    if len(prod_df) > 0:
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # 좌축: 누적 리뷰 수
        fig.add_trace(
            go.Scatter(
                x=prod_df["date"],
                y=prod_df["review_count"],
                name="누적 리뷰 수 (좌)",
                mode="lines+markers",
                marker=dict(size=9),
                line=dict(color="#FF4B4B", width=2.5),
            ),
            secondary_y=False,
        )

        # 우축: 대분류 판매 순위 BSR
        fig.add_trace(
            go.Scatter(
                x=prod_df["date"],
                y=prod_df["bsr_main"],
                name="카테고리 판매순위 BSR (우, 역축)",
                mode="lines+markers",
                marker=dict(size=9),
                line=dict(color="#00CC96", width=2, dash="dot"),
            ),
            secondary_y=True,
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#1E1E1E",
            plot_bgcolor="#1E1E1E",
            height=420,
            margin=dict(l=20, r=20, t=40, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified",
        )
        # X축 날짜 포맷을 일 단위로 깔끔하게 고정 (1개 데이터일 때도 시:분:초 깨짐 방지)
        fig.update_xaxes(type="category")
        fig.update_yaxes(title_text="누적 리뷰 수 (개)", secondary_y=False)
        fig.update_yaxes(title_text="BSR 판매 순위 (상단일수록 고순위)", autorange="reversed", secondary_y=True)

        st.plotly_chart(fig, use_container_width=True)

        csv_data = prod_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="📥 선택 제품 누적 데이터 CSV 다운로드",
            data=csv_data,
            file_name=f"amazon_tracking_{sel_asin}.csv",
            mime="text/csv",
        )
