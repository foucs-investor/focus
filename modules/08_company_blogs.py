from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

# 사이드바 라디오 버튼에 표시될 메뉴명
MENU_NAME = "기업별 관심 블로그"

# 데이터 저장 경로 (etf_dashboard/data/company_blogs.json)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_FILE = DATA_DIR / "company_blogs.json"


def _load_blogs() -> list[dict]:
    """저장된 기업별 블로그 목록을 불러옵니다."""
    if not DATA_FILE.exists():
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_blogs(blogs: list[dict]) -> None:
    """기업별 블로그 목록을 JSON 파일에 저장합니다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(blogs, f, ensure_ascii=False, indent=2)


def _normalize_url(raw_url: str) -> str:
    """URL 앞뒤 공백을 제거하고 프로토콜이 없으면 https://를 붙입니다."""
    url = raw_url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def render():
    st.markdown("## 📝 기업별 관심 블로그 관리 및 조회")
    st.caption(
        "기업명과 관련 블로그 URL을 등록하고, 특정 기업명을 검색해 저장된 링크를 언제든 바로 열어볼 수 있습니다."
    )

    blogs = _load_blogs()

    # 1. 신규 블로그 URL 등록 폼
    with st.expander("➕ 새 기업 블로그 URL 등록하기", expanded=True):
        with st.form("add_company_blog_form", clear_on_submit=True):
            col1, col2 = st.columns([1.2, 2.3])
            with col1:
                company_name = st.text_input(
                    "기업명 *",
                    placeholder="예: 삼성전자, SK하이닉스, 한화에어로스페이스",
                )
            with col2:
                blog_url = st.text_input(
                    "블로그 URL *",
                    placeholder="예: https://blog.naver.com/...",
                )

            col3, col4 = st.columns([1.5, 2.0])
            with col3:
                blog_title = st.text_input(
                    "글 제목 / 요약 (선택)",
                    placeholder="예: 3분기 실적 분석 및 HBM 전망",
                )
            with col4:
                memo = st.text_input(
                    "메모 / 태그 (선택)",
                    placeholder="예: 밸류에이션, 리서치 노트, 투자 포인트",
                )

            submitted = st.form_submit_button("저장하기", type="primary")
            if submitted:
                clean_company = company_name.strip()
                clean_url = _normalize_url(blog_url)

                if not clean_company:
                    st.error("기업명을 입력해 주세요.")
                elif not clean_url:
                    st.error("블로그 URL을 입력해 주세요.")
                else:
                    now_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime(
                        "%Y-%m-%d %H:%M"
                    )
                    new_entry = {
                        "id": f"{datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d%H%M%S%f')}",
                        "company": clean_company,
                        "url": clean_url,
                        "title": blog_title.strip() or clean_company,
                        "memo": memo.strip(),
                        "created_at": now_kst,
                    }
                    blogs.insert(0, new_entry)
                    _save_blogs(blogs)
                    st.success(f"**'{clean_company}'** 블로그 URL이 저장되었습니다.")
                    st.rerun()

    st.divider()

    # 2. 기업명 조회 및 필터링
    st.markdown("### 🔍 기업별 블로그 조회")

    if not blogs:
        st.info("아직 저장된 기업 블로그가 없습니다. 위 입력창에서 첫 번째 URL을 등록해 보세요.")
        return

    all_companies = sorted({item["company"] for item in blogs})

    search_col1, search_col2 = st.columns([2, 1.5])
    with search_col1:
        search_query = st.text_input(
            "기업명 / 키워드 검색",
            placeholder="조회할 기업명이나 메모를 입력하세요...",
        )
    with search_col2:
        selected_company = st.selectbox(
            "등록된 기업 빠른 선택",
            options=["전체 기업"] + all_companies,
        )

    filtered_blogs = blogs
    if selected_company != "전체 기업":
        filtered_blogs = [
            b for b in filtered_blogs if b["company"] == selected_company
        ]
    if search_query.strip():
        q = search_query.strip().lower()
        filtered_blogs = [
            b
            for b in filtered_blogs
            if q in b["company"].lower()
            or q in b["title"].lower()
            or q in b["memo"].lower()
            or q in b["url"].lower()
        ]

    st.markdown(f"**조회 결과: 총 {len(filtered_blogs)}건**")

    if not filtered_blogs:
        st.warning("검색 조건에 일치하는 블로그 기록이 없습니다.")
        return

    # 3. 카드/리스트 형태로 조회 및 바로 접속 제공
    for item in filtered_blogs:
        with st.container(border=True):
            c1, c2, c3 = st.columns([1.4, 3.6, 0.8])
            with c1:
                st.markdown(f"**🏢 {item['company']}**")
                st.caption(f"등록일: {item.get('created_at', '-')}")
            with c2:
                st.markdown(f"**{item['title']}**")
                st.link_button("🔗 블로그 열기", item["url"])
                st.caption(item["url"])
                if item.get("memo"):
                    st.caption(f"메모: {item['memo']}")
            with c3:
                if st.button("삭제", key=f"del_{item['id']}"):
                    updated = [b for b in blogs if b["id"] != item["id"]]
                    _save_blogs(updated)
                    st.rerun()

    # 4. 표 형태로 한눈에 보기 (선택 사항)
    with st.expander("📋 표로 한눈에 보기", expanded=False):
        df_view = pd.DataFrame(filtered_blogs)[
            ["company", "title", "url", "memo", "created_at"]
        ].rename(
            columns={
                "company": "기업명",
                "title": "제목",
                "url": "블로그 URL",
                "memo": "메모",
                "created_at": "등록일시",
            }
        )
        st.dataframe(df_view, use_container_width=True, hide_index=True)