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
    page_title="군 장병 맞춤 영양 식단표",
    page_icon="🪖",
    layout="wide"
)

st.title("🪖 군 장병 맞춤 영양 식단표")
st.caption("NEIS API 및 가상 데이터를 활용한 월별 급식 및 영양 분석 시스템")

# ==========================================
# 2. 알레르기 및 영양소 처리 함수
# ==========================================
ALLERGY_MAP = {
    "1": "난류", "2": "우유", "3": "메밀", "4": "땅콩", "5": "대두",
    "6": "밀", "7": "고등어", "8": "게", "9": "새우", "10": "돼지고기",
    "11": "복숭아", "12": "토마토", "13": "아황산류", "14": "호두", "15": "닭고기",
    "16": "쇠고기", "17": "오징어", "18": "조개류", "19": "잣"
}

def clean_and_convert_menu(menu_str, convert_allergy=True):
    """메뉴 텍스트의 HTML 태그 및 알레르기 번호 변환/제거"""
    if not menu_str or pd.isna(menu_str):
        return ""
    
    # HTML 태그 제거
    text = re.sub(r'<[^>]+>', ' ', str(menu_str))
    
    if convert_allergy:
        def replace_fn(match):
            nums = re.findall(r'\d+', match.group(0))
            names = [ALLERGY_MAP.get(n, n) for n in nums]
            return f"({','.join(names)})" if names else ""
        text = re.sub(r'\([\d\.]+\)', replace_fn, text)
    else:
        # 알레르기 표시 번호 자체를 제거하고 메뉴명만 깔끔히 남김
        text = re.sub(r'\([\d\.]+\)', '', text)
        
    return text.strip()

def parse_nutrition(nut_str):
    """영양정보 문자열에서 열량 및 단백질 안전 추출"""
    if not nut_str or pd.isna(nut_str):
        return {"kcal": 0.0, "protein": 0.0}
    
    text = re.sub(r'<[^>]+>', ' ', str(nut_str))
    kcal, protein = 0.0, 0.0
    
    # 열량 추출
    m_kcal = re.search(r'열량\s*\([^)]*\)\s*:\s*([\d\.]+)', text)
    if m_kcal:
        try:
            kcal = float(m_kcal.group(1))
        except ValueError:
            pass
            
    # 단백질 추출
    m_prot = re.search(r'단백질\s*\([^)]*\)\s*:\s*([\d\.]+)', text)
    if m_prot:
        try:
            protein = float(m_prot.group(1))
        except ValueError:
            pass
            
    return {"kcal": kcal, "protein": protein}


# ==========================================
# 3. 사이드바 - 설정
# ==========================================
st.sidebar.header("🪖 부대 및 옵션 설정")

# Secrets 안전 확인 및 사용자 API 키 입력 옵션 제공
neis_key = st.secrets.get("NEIS_KEY", None)

if not neis_key:
    st.sidebar.warning("⚠️ 등록된 NEIS_KEY가 없습니다.")
    user_key_input = st.sidebar.text_input("NEIS API Key (선택)", type="password")
    if user_key_input:
        neis_key = user_key_input
    else:
        st.sidebar.info("💡 키가 없으면 [시뮬레이션 모드]로 실행됩니다.")

office_code = st.sidebar.text_input("관할 기관 코드", value="B10")
school_code = st.sidebar.text_input("부대/급식소 코드", value="7010536")

st.sidebar.markdown("---")
convert_allergy = st.sidebar.toggle("알레르기 식재료명 변환", value=True)
show_nutrition = st.sidebar.toggle("영양 분석 보기 (열량/단백질)", value=True)


# ==========================================
# 4. 데이터 로드 (API + 가상 데이터 Fallback)
# ==========================================
def generate_sample_data(year, month):
    """API 연동 불가 시 에러 방지용 샘플 데이터 생성"""
    _, last_day = calendar.monthrange(year, month)
    sample_rows = []
    
    sample_menus = [
        {"type": "조식", "menu": "쌀밥 해물두부찌개(5) 쇠고기불고기(16) 배추김치(9)", "nut": "열량 : 780.0 kcal / 단백질 : 28.5 g"},
        {"type": "중식", "menu": "현미밥 닭갈비(15) 콩나물국 계란말이(1) 깍두기", "nut": "열량 : 950.0 kcal / 단백질 : 32.0 g"},
        {"type": "석식", "menu": "잡곡밥 돼지김치찌개(10) 오징어볶음(17) 시금치나물", "nut": "열량 : 870.0 kcal / 단백질 : 26.0 g"}
    ]
    
    for day in range(1, last_day + 1):
        ymd = f"{year}{month:02d}{day:02d}"
        for item in sample_menus:
            sample_rows.append({
                "MLSV_YMD": ymd,
                "MMEAL_SC_NM": item["type"],
                "DDISH_NM": item["menu"],
                "NTR_INFO": item["nut"]
            })
    return pd.DataFrame(sample_rows)

@st.cache_data(ttl=1800)
def load_meal_data(api_key, ofcdc, sch, year, month):
    if not api_key:
        return generate_sample_data(year, month), "시뮬레이션 데이터로 표시 중입니다."

    _, last_day = calendar.monthrange(year, month)
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "KEY": api_key,
        "Type": "json",
        "pIndex": 1,
        "pSize": 100,
        "ATPT_OFCDC_SC_CODE": ofcdc,
        "SD_SCHUL_CODE": sch,
        "MLSV_FROM_YMD": f"{year}{month:02d}01",
        "MLSV_TO_YMD": f"{year}{month:02d}{last_day:02d}"
    }
    
    try:
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        data = res.json()
        
        if "mealServiceDietInfo" in data:
            rows = data["mealServiceDietInfo"][1]["row"]
            return pd.DataFrame(rows), None
        else:
            # API에서 데이터가 없을 시 가상 데이터로 에러 없이 전환
            return generate_sample_data(year, month), "API 응답이 없어 테스트 데이터를 표시합니다."
    except Exception:
        return generate_sample_data(year, month), "네트워크 연결 불안정으로 테스트 데이터를 표시합니다."


# ==========================================
# 5. 상단 조회 조건
# ==========================================
today = datetime.date.today()
c1, c2, c3 = st.columns([1, 1, 2])

with c1:
    selected_year = st.selectbox("연도", range(today.year - 1, today.year + 2), index=1)
with c2:
    selected_month = st.selectbox("월", range(1, 13), index=today.month - 1)
with c3:
    meal_filter = st.radio("식사 선택", ["전체", "조식", "중식", "석식"], horizontal=True)

st.markdown("---")


# ==========================================
# 6. 달력 출력
# ==========================================
df, status_msg = load_meal_data(neis_key, office_code, school_code, selected_year, selected_month)

if status_msg:
    st.info(f"ℹ️ {status_msg}")

st.subheader(f"📅 {selected_year}년 {selected_month}월 식단표")

# 요일 헤더 (월~금)
headers = st.columns(5)
for idx, day_name in enumerate(["월", "화", "수", "목", "금"]):
    headers[idx].markdown(f"### **{day_name}**")

cal = calendar.monthcalendar(selected_year, selected_month)

for week in cal:
    workdays = week[0:5] # 월~금만 선택
    if not any(d != 0 for d in workdays):
        continue
        
    cols = st.columns(5)
    for idx, day in enumerate(workdays):
        with cols[idx]:
            if day == 0:
                st.empty()
                continue
            
            date_str = f"{selected_year}{selected_month:02d}{day:02d}"
            is_today = (selected_year == today.year and selected_month == today.month and day == today.day)
            badge = " :orange[**[TODAY]**]" if is_today else ""
            
            with st.container(border=True):
                st.markdown(f"#### **{day}일**{badge}")
                
                day_data = df[df["MLSV_YMD"] == date_str] if not df.empty and "MLSV_YMD" in df.columns else pd.DataFrame()
                
                if day_data.empty:
                    st.caption("🔒 식단 정보 없음")
                else:
                    shown_count = 0
                    for _, row in day_data.iterrows():
                        meal_type = str(row.get("MMEAL_SC_NM", "급식"))
                        
                        # 필터 적용
                        if meal_filter != "전체" and meal_type != meal_filter:
                            continue
                            
                        shown_count += 1
                        
                        # 식사 구분에 따른 색상
                        color = "green" if "조식" in meal_type else ("blue" if "중식" in meal_type else "red")
                        st.markdown(f":{color}[**[{meal_type}]**]")
                        
                        # 메뉴 정제 출력
                        menu_text = clean_and_convert_menu(row.get("DDISH_NM", ""), convert_allergy)
                        for item in menu_text.split():
                            st.text(item)
                            
                        # 영양 성분 표시
                        if show_nutrition:
                            nut = parse_nutrition(row.get("NTR_INFO", ""))
                            if nut["kcal"] > 0 or nut["protein"] > 0:
                                st.caption(f"🔥 {nut['kcal']:.0f} kcal | 🥩 {nut['protein']:.1f}g")
                                # 1끼 기준 Target(1000kcal) 대비 달성도
                                ratio = min(nut["kcal"] / 1000.0, 1.0)
                                st.progress(ratio)
                                
                    if shown_count == 0:
                        st.caption("❌ 해당 식단 없음")
