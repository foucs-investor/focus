import json
import os
import random
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from bs4 import BeautifulSoup

MENU_NAME = "아마존 트레킹"

DATA_DIR = "data"
WATCHLIST_FILE = os.path.join(DATA_DIR, "amazon_watchlist.csv")
HISTORY_FILE = os.path.join(DATA_DIR, "amazon_tracking_history.csv")
BROWSER_CACHE_DIR = "/home/appuser/.cache/ms-playwright"


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


def _ensure_chromium_installed() -> str | None:
    """Playwright Chromium 바이너리가 없으면 설치하고, 설치 실패 시 오류 메시지 반환"""
    env = os.environ.copy()
    if os.name != "nt":
        os.makedirs(BROWSER_CACHE_DIR, exist_ok=True)
        env["PLAYWRIGHT_BROWSERS_PATH"] = BROWSER_CACHE_DIR

    # 캐시 디렉터리에 chromium 또는 headless_shell 폴더가 있는지 확인
    has_browser = False
    if os.name == "nt":
        win_cache = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "ms-playwright"
        )
        if os.path.exists(win_cache):
            has_browser = any(
                name.startswith(("chromium-", "chromium_headless_shell-"))
                for name in os.listdir(win_cache)
            )
    else:
        if os.path.exists(BROWSER_CACHE_DIR):
            has_browser = any(
                name.startswith(("chromium-", "chromium_headless_shell-"))
                for name in os.listdir(BROWSER_CACHE_DIR)
            )

    if has_browser:
        return None

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        if proc.returncode != 0:
            err_tail = (proc.stderr or proc.stdout or "").strip()[-300:]
            return f"Chromium 설치 실패(코드 {proc.returncode}): {err_tail}"
        return None
    except Exception as e:
        return f"Chromium 설치 중 예외 발생: {e}"


def _parse_json_ld(soup: BeautifulSoup) -> dict:
    """페이지 내 JSON-LD 구조화 데이터에서 가격/평점/리뷰수 추출"""
    result = {"price": None, "rating": None, "review_count": None}
    for script in soup.select("script[type='application/ld+json']"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            offers = item.get("offers")
            if isinstance(offers, list) and offers:
                offers = offers[0]
            if isinstance(offers, dict) and result["price"] is None:
                p_val = offers.get("price")
                if p_val is not None:
                    try:
                        result["price"] = float(str(p_val).replace(",", ""))
                    except ValueError:
                        pass

            agg = item.get("aggregateRating")
            if isinstance(agg, dict):
                if result["rating"] is None and agg.get("ratingValue") is not None:
                    try:
                        result["rating"] = float(str(agg["ratingValue"]))
                    except ValueError:
                        pass
                if result["review_count"] is None and agg.get("reviewCount") is not None:
                    digits = re.sub(r"[^\d]", "", str(agg["reviewCount"]))
                    if digits:
                        result["review_count"] = int(digits)
    return result


def _playwright_worker(asin: str) -> dict:
    """메모리 절감 옵션으로 Chromium을 띄워 아마존 페이지 파싱"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "error": "playwright 미설치: requirements.txt에 playwright 추가 후 재배포 필요"
        }

    install_err = _ensure_chromium_installed()
    if install_err:
        return {"error": install_err}

    if os.name != "nt":
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = BROWSER_CACHE_DIR

    url = f"https://www.amazon.com/dp/{asin}?language=en_US&currency=USD"

    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--single-process",
                    "--no-zygote",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": 1280, "height": 720},
            )
            page = context.new_page()
            page.set_default_timeout(25000)

            def _block_heavy(route):
                if route.request.resource_type in {"image", "media", "font"}:
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", _block_heavy)

            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2000)

            html = page.content()
            title = page.title()
            browser.close()
            browser = None

        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text(" ", strip=True)
        snippet = re.sub(r"\s+", " ", page_text)[:140]

        if (
            "Enter the characters you see below" in page_text
            or "Type the characters you see in this image" in page_text
            or "Sorry! Something went wrong" in page_text
        ):
            return {
                "error": f"아마존 차단/오류 페이지 감지 [제목: {title} | 본문: {snippet}]"
            }

        ld_data = _parse_json_ld(soup)

        price = ld_data["price"]
        if price is None:
            price_selectors = [
                "#corePrice_feature_div span.a-price span.a-offscreen",
                "#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen",
                "span.apexPriceToPay span.a-offscreen",
                "#priceblock_ourprice",
                "#priceblock_dealprice",
                "span.a-price span.a-offscreen",
            ]
            for sel in price_selectors:
                for el in soup.select(sel):
                    txt = el.get_text().strip()
                    if "$" in txt:
                        num_match = re.search(r"\$\s*([\d,]+\.?\d*)", txt)
                        if num_match:
                            price = float(num_match.group(1).replace(",", ""))
                            break
                if price is not None:
                    break

        review_count = ld_data["review_count"]
        if review_count is None:
            rev_selectors = [
                "#acrCustomerReviewText",
                "#reviewsMedley span[data-hook='total-review-count']",
                "span[data-hook='total-review-count']",
            ]
            for sel in rev_selectors:
                el = soup.select_one(sel)
                if el:
                    m = re.search(
                        r"([\d,]+)\s*(?:global\s*)?ratings?", el.get_text(), re.I
                    )
                    digits = (
                        m.group(1).replace(",", "")
                        if m
                        else re.sub(r"[^\d]", "", el.get_text())
                    )
                    if digits:
                        review_count = int(digits)
                        break

        if review_count is None:
            m_text = re.search(r"([\d,]+)\s+global ratings", page_text, re.I)
            if m_text:
                review_count = int(m_text.group(1).replace(",", ""))

        rating = ld_data["rating"]
        if rating is None:
            rat_el = soup.select_one("#acrPopover span.a-icon-alt") or soup.select_one(
                "span[data-hook='rating-out-of-text']"
            )
            if rat_el:
                rat_match = re.search(r"([\d.]+)\s*out of\s*5", rat_el.get_text(), re.I)
                if rat_match:
                    rating = float(rat_match.group(1))

        bsr_main, bsr_sub = None, None
        detail_section = (
            soup.select_one("#detailBulletsWrapper_feature_div")
            or soup.select_one("#productDetails_detailBullets_sections1")
            or soup.select_one("#prodDetails")
        )
        target_text = (
            detail_section.get_text(" ", strip=True) if detail_section else page_text
        )
        bsr_matches = re.findall(r"#([\d,]+)\s+in\s+[A-Za-z0-9 &,'()/-]+", target_text)
        if len(bsr_matches) >= 1:
            bsr_main = int(bsr_matches[0].replace(",", ""))
        if len(bsr_matches) >= 2:
            bsr_sub = int(bsr_matches[1].replace(",", ""))

        stock_status = "In Stock"
        avail_el = soup.select_one("#availability")
        if avail_el:
            avail_txt = avail_el.get_text(strip=True).lower()
            if "currently unavailable" in avail_txt or "out of stock" in avail_txt:
                stock_status = "Out of Stock"
            elif "left in stock" in avail_txt:
                stock_status = "Low Stock"

        if price is None and review_count is None and bsr_main is None:
            return {"error": f"요소 미검출 [제목: {title} | 본문: {snippet}]"}

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
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


def fetch_amazon_product(asin: str) -> dict:
    """Streamlit 이벤트 루프 충돌 방지를 위해 별도 스레드에서 실행"""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_playwright_worker, asin)
        return future.result()


def render():
    init_storage()
    st.header("📦 아마존 트레킹 (Amazon Product Tracker)")
    st.caption(
        "기업별 미국 아마존 주력 SKU의 판매 순위(BSR), 누적 리뷰 증가 추이, 가격 및 품절 여부를 누적 추적합니다."
    )

    df_watch = pd.read_csv(WATCHLIST_FILE, dtype={"asin": str})
    df_hist = pd.read_csv(HISTORY_FILE, dtype={"asin": str})

    with st.expander("➕ 트래킹 제품 추가 / 관리", expanded=df_watch.empty):
        with st.form("add_product_form", clear_on_submit=True):
            col1, col2, col3, col4 = st.columns([1.2, 2, 1.8, 1.5])
            with col1:
                company = st.text_input("기업명", placeholder="예: 아로마티카")
            with col2:
                product_name = st.text_input(
                    "제품명", placeholder="예: 로즈마리 스칼프 스케일링 샴푸"
                )
            with col3:
                asin_input = st.text_input(
                    "ASIN 또는 아마존 URL", placeholder="예: B01NBJ9LTS"
                )
            with col4:
                memo = st.text_input("비고 (매출비중 등)", placeholder="예: 매출비중 11.0%")

            submitted = st.form_submit_button("관심 제품 등록")
            if submitted:
                clean_asin = extract_asin(asin_input)
                if not company or not product_name or not clean_asin:
                    st.error(
                        "기업명, 제품명, 그리고 올바른 10자리 ASIN(또는 아마존 상품 URL)을 입력해주세요."
                    )
                elif clean_asin in df_watch["asin"].values:
                    st.warning(f"이미 등록된 ASIN입니다: {clean_asin}")
                else:
                    new_row = pd.DataFrame(
                        [
                            [
                                company.strip(),
                                product_name.strip(),
                                clean_asin,
                                memo.strip(),
                            ]
                        ],
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
                options=["선택 안함"]
                + [
                    f"{r.company} - {r.product_name} ({r.asin})"
                    for _, r in df_watch.iterrows()
                ],
            )
            if del_asin != "선택 안함" and st.button("선택 제품 삭제"):
                target_asin = del_asin.split("(")[-1].replace(")", "")
                df_watch = df_watch[df_watch["asin"] != target_asin]
                df_watch.to_csv(WATCHLIST_FILE, index=False, encoding="utf-8-sig")
                st.rerun()

    if df_watch.empty:
        st.info(
            "상단의 '트래킹 제품 추가 / 관리'를 열어 모니터링할 기업과 제품의 ASIN을 등록해주세요."
        )
        return

    st.divider()
    col_f1, col_f2 = st.columns([2, 1])
    companies = ["전체 기업"] + sorted(df_watch["company"].unique().tolist())
    with col_f1:
        selected_company = st.selectbox("조회 및 수집할 기업 선택", companies)
    with col_f2:
        st.write("")
        run_scrape = st.button(
            "🔄 현재 시점 아마존 데이터 수집", type="primary", use_container_width=True
        )

    target_watch = (
        df_watch
        if selected_company == "전체 기업"
        else df_watch[df_watch["company"] == selected_company]
    )

    if run_scrape:
        today_str = datetime.now().strftime("%Y-%m-%d")
        progress = st.progress(0)
        status_box = st.empty()
        new_records = []

        for idx, row in enumerate(target_watch.itertuples()):
            status_box.text(
                f"브라우저 수집 중 ({idx+1}/{len(target_watch)}): [{row.company}] {row.product_name}..."
            )
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
            time.sleep(random.uniform(1.5, 3.0))

        if new_records:
            df_new = pd.DataFrame(new_records)
            df_hist = df_hist[
                ~((df_hist["date"] == today_str) & (df_hist["asin"].isin(df_new["asin"])))
            ]
            df_hist = pd.concat([df_hist, df_new], ignore_index=True)
            df_hist.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")
            status_box.success(
                f"{today_str} 기준 {len(new_records)}개 제품 데이터 업데이트 완료!"
            )
            st.rerun()

    with st.expander(
        "✍️ 데이터 수동 입력 / 수정 (차단 발생 시 또는 과거 데이터 보정용)"
    ):
        with st.form("manual_entry_form"):
            m_col1, m_col2, m_col3 = st.columns([2, 1, 1])
            with m_col1:
                m_prod = st.selectbox(
                    "대상 제품",
                    [
                        f"[{r.company}] {r.product_name} ({r.asin})"
                        for _, r in target_watch.iterrows()
                    ],
                )
            with m_col2:
                m_date = st.date_input("기준일자", datetime.now())
            with m_col3:
                m_stock = st.selectbox(
                    "재고상태", ["In Stock", "Low Stock", "Out of Stock"]
                )

            m_col4, m_col5, m_col6, m_col7 = st.columns(4)
            with m_col4:
                m_price = st.number_input("가격 (USD)", min_value=0.0, step=0.01, value=20.0)
            with m_col5:
                m_review = st.number_input("누적 리뷰 수", min_value=0, step=1, value=0)
            with m_col6:
                m_bsr_main = st.number_input(
                    "대분류 순위 (BSR)", min_value=0, step=1, value=0
                )
            with m_col7:
                m_bsr_sub = st.number_input(
                    "소분류 순위 (BSR)", min_value=0, step=1, value=0
                )

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
                df_hist = df_hist[
                    ~((df_hist["date"] == d_str) & (df_hist["asin"] == sel_asin_m))
                ]
                df_hist = pd.concat([df_hist, manual_row], ignore_index=True)
                df_hist.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")
                st.success(f"{d_str} 데이터가 저장되었습니다.")
                st.rerun()

    filtered_hist = (
        df_hist
        if selected_company == "전체 기업"
        else df_hist[df_hist["company"] == selected_company]
    )

    if filtered_hist.empty:
        st.info(
            "아직 수집된 이력이 없습니다. '현재 시점 아마존 데이터 수집' 버튼을 눌러 첫 데이터를 기록하세요."
        )
        return

    for num_col in ["price_usd", "review_count", "rating", "bsr_main", "bsr_sub"]:
        filtered_hist[num_col] = pd.to_numeric(filtered_hist[num_col], errors="coerce")

    filtered_hist = filtered_hist.sort_values(["asin", "date"])
    filtered_hist["new_reviews"] = (
        filtered_hist.groupby("asin")["review_count"].diff().fillna(0)
    )

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

    st.subheader("📈 제품별 판매 모멘텀 추이 (BSR 순위 & 누적 리뷰)")
    product_options = [
        f"[{r.company}] {r.product_name} ({r.asin})" for _, r in target_watch.iterrows()
    ]
    selected_prod = st.selectbox("그래프 조회 제품", product_options)
    sel_asin = selected_prod.split("(")[-1].replace(")", "")

    prod_df = filtered_hist[filtered_hist["asin"] == sel_asin].sort_values("date")

    if len(prod_df) > 0:
        fig = make_subplots(specs=[[{"secondary_y": True}]])

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
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
            ),
            hovermode="x unified",
        )
        fig.update_xaxes(type="category")
        fig.update_yaxes(title_text="누적 리뷰 수 (개)", secondary_y=False)
        fig.update_yaxes(
            title_text="BSR 판매 순위 (상단일수록 고순위)",
            autorange="reversed",
            secondary_y=True,
        )

        st.plotly_chart(fig, use_container_width=True)

        csv_data = prod_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            label="📥 선택 제품 누적 데이터 CSV 다운로드",
            data=csv_data,
            file_name=f"amazon_tracking_{sel_asin}.csv",
            mime="text/csv",
        )
