import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# ==============================================================================
# 1. 페이지 기본 설정 및 병원풍 커스텀 디자인(CSS) 적용
# ==============================================================================
st.set_page_config(
    page_title="메디컬 감염병 통계 대시보드",
    page_icon="🏥",
    layout="wide"
)

# 병원 환경을 연상시키는 깔끔하고 세련된 스타일 (소프트 블루/그린 톤, 카드형 UI)
st.markdown("""
    <style>
    /* 전체 배경색 및 폰트 변경 */
    .stApp {
        background-color: #F8FAFC;
    }
    
    /* 사이드바 배경 스타일 */
    [data-testid="stSidebar"] {
        background-color: #F1F5F9;
        border-right: 1px solid #E2E8F0;
    }
    
    /* 메인 타이틀 스타일 */
    h1 {
        color: #0F172A;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    
    /* 탭 메뉴 스타일링 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #E2E8F0;
        border-radius: 6px 6px 0px 0px;
        color: #334155;
        font-weight: 600;
        padding: 10px 20px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0284C7 !important;
        color: white !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🏥 메디컬 감염병 통합 관리 대시보드")
st.markdown("데이터 기반의 체계적인 감염병 발생 현황 분석 및 시각화 시스템입니다.")
st.markdown("---")

# ==============================================================================
# 2. 데이터 불러오기 및 질병 정보 딕셔너리 정의
# ==============================================================================
@st.cache_data
def load_data():
    # CSV 파일을 읽어옵니다. (기존 파일명 호환성 유지)
    try:
        df_monthly = pd.read_csv('infectious_disease_monthly_clean_2.csv')
        df_annual = pd.read_csv('infectious_disease_annual_clean_2.csv')
    except FileNotFoundError:
        df_monthly = pd.read_csv('infectious_disease_monthly_clean.csv')
        df_annual = pd.read_csv('infectious_disease_annual_clean.csv')
    
    # 결측치(빈 값)를 0으로 채워줍니다.
    df_monthly['발생건수'] = df_monthly['발생건수'].fillna(0)
    df_annual['발생건수'] = df_annual['발생건수'].fillna(0)
    
    # 날짜 형태로 변환하여 시계열 그래프를 그릴 때 사용합니다.
    df_monthly['연월'] = pd.to_datetime(
        df_monthly['연도'].astype(str) + '-' + df_monthly['월'].astype(str).str.zfill(2) + '-01'
    )
    
    return df_monthly, df_annual

df_monthly, df_annual = load_data()

# 파이썬 딕셔너리를 활용한 주요 감염병 상세 정보 데이터베이스
DISEASE_INFO_DICT = {
    "백일해": {
        "정의": "보르데텔라균에 의해 발생하는 급성 호흡기 감염병입니다.",
        "전파경로": "환자의 기침이나 재채기 등을 통한 비말 감염",
        "주요증상": "발작성 기침(켁켁거림), 흡기 시 웁(whoop) 소리",
        "예방수칙": "적기 DTaP 백신 접종, 올바른 손씻기 및 마스크 착용"
    },
    "A형간염": {
        "정의": "A형간염 바이러스에 감염되어 발생하는 간의 염증성 질환입니다.",
        "전파경로": "오염된 물이나 음식물 섭취, 환자와의 밀접 접촉",
        "주요증상": "발열, 피로감, 식욕부진, 구토, 황달",
        "예방수칙": "A형간염 예방접종, 물 끓여 마시기, 음식 익혀 먹기"
    },
    "수두": {
        "정의": "수두-대상포진 바이러스에 의해 발생하는 급성 바이러스성 질환입니다.",
        "전파경로": "환자의 물집 분비물 접촉 또는 비말 감염, 공기 감염",
        "주요증상": "급성 발열, 전신에 가려움증을 동반한 수포성 발진",
        "예방수칙": "수두 예방접종 완료, 개인위생 철저 및 환자 격리"
    },
    "유행성이하선염": {
        "정의": "볼거리로 불리며, 이하선(귀밑샘)이 붓고 통증이 생기는 바이러스 질환입니다.",
        "전파경로": "환자의 침이나 비말 등 호흡기 분비물을 통한 전파",
        "주요증상": "발열, 두통, 근육통, 귀밑샘 부종 및 압통",
        "예방수칙": "MMR 백신 접종, 기침 예절 준수"
    },
    "C형간염": {
        "정의": "C형간염 바이러스에 노출되어 혈액을 통해 감염되는 만성 간 질환입니다.",
        "전파경로": "오염된 주사기 재사용, 피하 시술, 혈액을 통한 노출",
        "주요증상": "대부분 무증상이나 피로감, 황달, 복부 불쾌감 유발 가능",
        "예방수칙": "문신, 피어싱 등 비인증 시술 지양, 면도기/칫솔 공유 금지"
    }
}

# ==============================================================================
# 3. 사이드바 필터 (사용자가 선택하는 메뉴)
# ==============================================================================
st.sidebar.header("🔍 검색 및 필터 조건")

# 1) 코로나19 포함 여부 선택 (key를 부여하여 중복 ID 에러 방지)
include_covid = st.sidebar.checkbox(
    "코로나바이러스감염증-19 데이터 포함", 
    value=True, 
    key="include_covid_checkbox"
)

# 2) 감염병급 선택
available_classes = sorted(df_monthly['감염병급'].dropna().unique().tolist())
selected_classes = st.sidebar.multiselect(
    "감염병급 선택",
    options=available_classes,
    default=available_classes,
    key="selected_classes_multiselect"
)

# 3) 연도 선택
available_years = sorted(df_monthly['연도'].unique().tolist(), reverse=True)
selected_years = st.sidebar.multiselect(
    "연도 선택",
    options=available_years,
    default=available_years,
    key="selected_years_multiselect"
)

# 선택한 조건에 따라 데이터를 필터링합니다.
filtered_monthly = df_monthly.copy()
filtered_annual = df_annual.copy()

if not include_covid:
    filtered_monthly = filtered_monthly[filtered_monthly['감염병명'] != '코로나바이러스감염증-19']
    filtered_annual = filtered_annual[filtered_annual['감염병명'] != '코로나바이러스감염증-19']

filtered_monthly = filtered_monthly[
    (filtered_monthly['감염병급'].isin(selected_classes)) & 
    (filtered_monthly['연도'].isin(selected_years))
]

filtered_annual = filtered_annual[
    (filtered_annual['감염병급'].isin(selected_classes)) & 
    (filtered_annual['연도'].isin(selected_years))
]

# ==============================================================================
# 4. 메인 화면 - 탭(Tab) 구성
# ==============================================================================
tab1, tab2, tab3, tab4 = st.tabs(["📊 주요 요약", "📈 시계열 분석", "🔬 감염병 비교", "📄 데이터 보기"])

# ------------------------------------------------------------------------------
# [탭 1] 주요 요약
# ------------------------------------------------------------------------------
with tab1:
    st.subheader("📌 핵심 요약 지표")
    
    total_cases = int(filtered_annual['발생건수'].sum())
    
    if not filtered_annual.empty and total_cases > 0:
        top_disease_series = filtered_annual.groupby('감염병명')['발생건수'].sum()
        top_disease_name = top_disease_series.idxmax()
        top_disease_count = int(top_disease_series.max())
    else:
        top_disease_name = "없음"
        top_disease_count = 0
        
    disease_type_count = filtered_annual[filtered_annual['발생건수'] > 0]['감염병명'].nunique()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("총 발생 건수", f"{total_cases:,} 건")
    col2.metric("최다 발생 감염병", top_disease_name, f"{top_disease_count:,} 건")
    col3.metric("발생 이력 감염병 수", f"{disease_type_count} 종")
    
    st.markdown("---")
    
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.markdown("##### 🏆 최다 발생 감염병 Top 10")
        top10_df = (
            filtered_annual.groupby('감염병명')['발생건수']
            .sum()
            .reset_index()
            .sort_values(by='발생건수', ascending=False)
            .head(10)
        )
        
        fig_top10 = px.bar(
            top10_df,
            x='발생건수',
            y='감염병명',
            orientation='h',
            text_auto=',.0f',
            color='발생건수',
            color_continuous_scale='Teal',
            labels={'발생건수': '발생 건수', '감염병명': '감염병 이름'}
        )
        fig_top10.update_layout(yaxis={'categoryorder': 'total ascending'}, showlegend=False)
        st.plotly_chart(fig_top10, use_container_width=True)
        
    with col_right:
        st.markdown("##### 🏷️ 감염병급별 발생 비중")
        class_summary = filtered_annual.groupby('감염병급')['발생건수'].sum().reset_index()
        
        fig_pie = px.pie(
            class_summary,
            names='감염병급',
            values='발생건수',
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Safe
        )
        st.plotly_chart(fig_pie, use_container_width=True)

# ------------------------------------------------------------------------------
# [탭 2] 시계열 분석
# ------------------------------------------------------------------------------
with tab2:
    st.subheader("📈 시간 흐름에 따른 발생 추이")
    
    monthly_trend = filtered_monthly.groupby('연월')['발생건수'].sum().reset_index()
    
    fig_line = px.line(
        monthly_trend,
        x='연월',
        y='발생건수',
        markers=True,
        title="전체 월별 감염병 발생 건수 추이",
        labels={'연월': '년-월', '발생건수': '발생 건수'}
    )
    fig_line.update_traces(line_color='#0284C7', line_width=2.5)
    st.plotly_chart(fig_line, use_container_width=True)
    
    st.markdown("---")
    
    st.subheader("🗓️ 연도별 · 월별 발생 히트맵 (계절성 확인)")
    pivot_df = filtered_monthly.pivot_table(
        index='연도', 
        columns='월', 
        values='발생건수', 
        aggfunc='sum'
    ).fillna(0)
    
    fig_heatmap = px.imshow(
        pivot_df,
        labels=dict(x="월", y="연도", color="발생 건수"),
        x=pivot_df.columns,
        y=pivot_df.index,
        color_continuous_scale='Blues',
        aspect="auto"
    )
    st.plotly_chart(fig_heatmap, use_container_width=True)

# ------------------------------------------------------------------------------
# [탭 3] 감염병 비교
# ------------------------------------------------------------------------------
with tab3:
    st.subheader("🔬 특정 감염병 선택 및 비교 분석")
    
    disease_options = sorted(filtered_monthly['감염병명'].unique().tolist())
    default_selected = disease_options[:3] if len(disease_options) >= 3 else disease_options
    
    selected_diseases = st.multiselect(
        "비교할 감염병을 선택하세요 (여러 개 선택 가능):",
        options=disease_options,
        default=default_selected,
        key="compare_diseases_multiselect"
    )
    
    if selected_diseases:
        compare_monthly = filtered_monthly[filtered_monthly['감염병명'].isin(selected_diseases)]
        compare_annual = filtered_annual[filtered_annual['감염병명'].isin(selected_diseases)]
        
        fig_compare_line = px.line(
            compare_monthly,
            x='연월',
            y='발생건수',
            color='감염병명',
            markers=True,
            title="선택한 감염병의 월별 발생 추이 비교",
            labels={'연월': '년-월', '발생건수': '발생 건수', '감염병명': '감염병 이름'}
        )
        st.plotly_chart(fig_compare_line, use_container_width=True)
        
        fig_compare_bar = px.bar(
            compare_annual,
            x='연도',
            y='발생건수',
            color='감염병명',
            barmode='group',
            title="선택한 감염병의 연도별 총 발생 건수 비교",
            labels={'연도': '연도', '발생건수': '발생 건수', '감염병명': '감염병 이름'}
        )
        st.plotly_chart(fig_compare_bar, use_container_width=True)
        
        st.markdown("---")
        st.subheader("📋 선택한 감염병 상세 가이드")
        
        for disease in selected_diseases:
            if disease in DISEASE_INFO_DICT:
                info = DISEASE_INFO_DICT[disease]
                with st.expander(f"📌 {disease} 백과사전 정보 보기", expanded=True):
                    st.markdown(f"• **질병 정의:** {info['정의']}")
                    st.markdown(f"• **전파 경로:** {info['전파경로']}")
                    st.markdown(f"• **주요 증상:** {info['주요증상']}")
                    st.markdown(f"• **예방 수칙:** {info['예방수칙']}")
            else:
                with st.expander(f"📌 {disease} 정보 안내", expanded=False):
                    st.info(f"'{disease}'에 대한 상세 가이드 정보가 아직 등록되지 않았습니다.")
                    
    else:
        st.info("💡 분석하고 싶은 감염병을 하나 이상 선택해주세요.")

# ------------------------------------------------------------------------------
# [탭 4] 데이터 보기
# ------------------------------------------------------------------------------
with tab4:
    st.subheader("📄 필터링된 원본 데이터 확인")
    
    view_option = st.radio(
        "표시할 데이터 종류를 선택하세요:",
        ["월별 데이터", "연간 데이터"],
        horizontal=True,
        key="data_view_radio"
    )
    
    if view_option == "월별 데이터":
        display_df = filtered_monthly.drop(columns=['연월'], errors='ignore')
    else:
        display_df = filtered_annual
        
    st.dataframe(display_df, use_container_width=True)
    
    csv_data = display_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 현재 조회 중인 데이터 CSV로 다운로드",
        data=csv_data,
        file_name=f"{view_option}_filtered.csv",
        mime="text/csv",
        key="download_csv_btn"
    )
