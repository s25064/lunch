import calendar
import datetime
import re
import pandas as pd
import requests
import streamlit as st

# ==========================================
# 1. 페이지 기본 설정 및 제목
# ==========================================
st.set_page_config(
    page_title="군 장병 영양 급식 달력",
    page_icon="🪖",
    layout="wide"
)

st.title("🪖 군 장병 맞춤 영양 식단표")
st.caption("NEIS 오픈 API 기반 식단 조회 및 군인 영양 표준 기준 영양소 분석 시스템")

# ==========================================
# 2. 알레르기 및 영양 기준 상수 설정
# ==========================================
# NEIS 알레르기 번호 매핑 (1~19)
ALLERGY_MAP = {
    "1": "난류", "2": "우유", "3": "메밀", "4": "땅콩", "5": "대두",
    "6": "밀", "7": "고등어", "8": "게", "9": "새우", "10": "돼지고기",
    "11": "복숭아", "12": "토마토", "13": "아황산류", "14": "호두", "15": "닭고기",
    "16": "쇠고기", "17": "오징어", "18": "조개류", "19": "잣"
}

# 20대 성인 남성 / 군인 기준 1일 영양 권장량 (1끼 기준 약 1/3 계산)
DAILY_RECS = {
    "열량": 3000,    # kcal (활동량이 많은 병사 기준)
    "탄수화물": 130,  # g
    "단백질": 65,     # g
    "지방": 50       # g
}

def convert_allergy_numbers(menu_str, convert_flag):
    """메뉴 문자열 내 알레르기 번호를 식재료명으로 변환하거나 제거하는 함수"""
    if not menu_str:
        return ""
    
    clean_menu = re.sub(r'<[^>]+>', ' ', str(menu_str))
    
    if not convert_flag:
        return clean_menu.strip()
    
    def replace_match(match):
        numbers = re.findall(r'\d+', match.group(0))
        names = [ALLERGY_MAP.get(num, num) for num in numbers]
        return f"({','.join(names)})" if names else ""

    converted = re.sub(r'\([\d\.]+\)', replace_match, clean_menu)
    return converted.strip()


def parse_nutrition_info(nut_str):
    """NEIS API의 영양정보 문자열(예: '열량(kcal): 850.5 / 단백질(g): 35.2')을 딕셔너리로 추출"""
    if not nut_str or pd.isna(nut_str):
        return {}
    
    # HTML 태그 제거
    clean_nut = re.sub(r'<[^>]+>', ' ', str(nut_str))
    
    nut_dict = {}
    # 패턴 추출 (항목명, 값)
    matches = re.findall(r'([가-힣a-zA-A]+)\([^)]*\)\s*:\s*([\d\.]+)', clean_nut)
    for name, val in matches:
        try:
            nut_dict[name] = float(val)
        except ValueError:
            continue
    return nut_dict


# ==========================================
# 3. 사이드바 - 부대/학교 정보 및 영양 설정
# ==========================================
st.sidebar.header("🪖 부대 및 식단 설정")

if "NEIS_KEY" not in st.secrets:
    st.error("🔑 **API 키가 설정되지 않았습니다!**")
    st.info(
        "`.streamlit/secrets.toml` 파일에 NEIS_KEY를 설정해 주세요:\n\n"
        '```toml\nNEIS_KEY = "발급받은_나이스_API_키"\n
except Exception as e:
    st.error(f"\u26a0\ufe0f 화면 구성 중 오류가 발생했습니다: {e}")
