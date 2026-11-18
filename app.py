import streamlit as st
import os
import importlib.util

st.set_page_config(
    page_title="시장 분석 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .sidebar-header {
        font-size: 1.1rem;
        font-weight: bold;
        color: #333333;
        margin-top: 10px;
        margin-bottom: 10px;
    }
    .future-menu-box {
        border: 2px dashed #4B6B94;
        background-color: #EBF3FA;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        color: #1F4E78;
        font-weight: bold;
        margin-top: 30px;
    }
</style>
""", unsafe_allow_html=True)

def load_modules(modules_dir="modules"):
    """modules 폴더 내 모든 .py 파일을 자동 감지하여 메뉴 모듈로 로드합니다."""
    loaded_modules = {}
    if not os.path.exists(modules_dir):
        os.makedirs(modules_dir)
        return loaded_modules

    file_list = sorted([f for f in os.listdir(modules_dir) if f.endswith(".py") and not f.startswith("__")])

    for file_name in file_list:
        module_name = file_name[:-3]
        file_path = os.path.join(modules_dir, file_name)

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # MENU_NAME 변수와 render() 함수가 정의되어 있는 파일만 등록
        if hasattr(module, "MENU_NAME") and hasattr(module, "render"):
            loaded_modules[module.MENU_NAME] = module

    return loaded_modules

modules_dict = load_modules()

with st.sidebar:
    st.markdown('<div class="sidebar-header">📊 시장 지표</div>', unsafe_allow_html=True)

    if modules_dict:
        menu_options = list(modules_dict.keys())
        selected_menu_name = st.radio(
            label="시장 지표 메뉴 선택",
            options=menu_options,
            index=0,
            label_visibility="collapsed"
        )
    else:
        st.warning("modules 폴더에 등록할 프로그램 파일이 없습니다.")
        selected_menu_name = None

    st.markdown("""
    <div class="future-menu-box">
        💡 자동 모듈 로더 가동 중<br>
        <span style="font-size:0.85rem; font-weight:normal; color:#555555;">
            (modules 폴더에 .py 파일만 추가하면 앱 수정 없이 자동 반영됩니다)
        </span>
    </div>
    """, unsafe_allow_html=True)

if selected_menu_name and selected_menu_name in modules_dict:
    modules_dict[selected_menu_name].render()