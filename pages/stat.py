import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# ==============================================================================
# 1. 페이지 기본 설정 및 타이틀
# ==============================================================================
# 웹 브라우저 탭의 제목과 레이아웃을 넓게(wide) 설정합니다.
st.set_page_config(
    page_title="감염병 통계 대시보드",
    page_icon="🦠",
    layout="wide"
)

st.title("🦠 대한민국 감염병 발생 통계 대시보드")
st.markdown("제공된 월별 및 연도별 데이터를 바탕으로 감염병 발생 현황을 분석하고 시각화합니다.")
st.markdown("---")

# ==============================================================================
# 2. 데이터 불러오기 함수
# ==============================================================================
# @st.cache_data를 사용하여 데이터를 매번 다시 읽지 않고 메모리에 저장(캐싱)하여 속도를 높입니다.
@st.cache_data
def load_data():
    # CSV 파일을 읽어옵니다. (파일명이 변경된 경우 아래 이름을 수정해주세요)
    try:
        df_monthly = pd.read_csv('infectious_disease_monthly_clean_2.csv')
        df_annual = pd.read_csv('infectious_disease_annual_clean_2.csv')
    except FileNotFoundError:
        # 파일명이 혹시 _2가 없는 기본 이름일 경우를 대비한 예외 처리입니다.
        df_monthly = pd.read_csv('infectious_disease_monthly_clean.csv')
        df_annual = pd.read_csv('infectious_disease_annual_clean.csv')
    
    # 결측치(빈 값)를 0으로 채워줍니다.
    df_monthly['발생건수'] = df_monthly['발생건수'].fillna(0)
    df_annual['발생건수'] = df_annual['발생건수'].fillna(0)
    
    # 날짜 형태로 변환하여 시계열 그래프를 그릴 때 사용합니다. (예: 2020년 1월 -> 2020-01-01)
    df_monthly['연월'] = pd.to_datetime(
        df_monthly['연도'].astype(str) + '-' + df_monthly['월'].astype(str).str.zfill(2) + '-01'
    )
    
    return df_monthly, df_annual

# 데이터를 로드합니다.
df_monthly, df_annual = load_data()

# ==============================================================================
# 3. 사이드바 필터 (사용자가 선택하는 메뉴)
# ==============================================================================
st.sidebar.header("🔍 데이터 필터링")

# 1) 코로나19 포함 여부 선택
# 코로나19의 수치가 매우 커서 다른 질병 그래프가 묻히는 것을 방지하기 위한 토글 옵션입니다.
include_covid = st.sidebar.checkbox("코로나바이러스감염증-19 데이터 포함", value=True)

# 2) 감염병급 선택 (예: 제1급, 2급, 3급)
available_classes = sorted(df_monthly['감염병급'].dropna().unique().tolist())
selected_classes = st.sidebar.multiselect(
    "감염병급 선택",
    options=available_classes,
    default=available_classes
)

# 3) 연도 선택
available_years = sorted(df_monthly['연도'].unique().tolist(), reverse=True)
selected_years = st.sidebar.multiselect(
    "연도 선택",
    options=available_years,
    default=available_years
)

# 선택한 조건에 따라 데이터를 필터링합니다.
filtered_monthly = df_monthly.copy()
filtered_annual = df_annual.copy()

# 코로나19 제외 옵션 반영
if not include_covid:
    filtered_monthly = filtered_monthly[filtered_monthly['감염병명'] != '코로나바이러스감염증-19']
    filtered_annual = filtered_annual[filtered_annual['감염병명'] != '코로나바이러스감염증-19']

# 감염병급 및 연도 필터 적용
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
    
    # 주요 숫자를 계산합니다.
    total_cases = int(filtered_annual['발생건수'].sum())
    
    if not filtered_annual.empty and total_cases > 0:
        top_disease_series = filtered_annual.groupby('감염병명')['발생건수'].sum()
        top_disease_name = top_disease_series.idxmax()
        top_disease_count = int(top_disease_series.max())
    else:
        top_disease_name = "없음"
        top_disease_count = 0
        
    disease_type_count = filtered_annual[filtered_annual['발생건수'] > 0]['감염병명'].nunique()
    
    # 3개 컬럼으로 숫자를 강조하여 보여줍니다.
    col1, col2, col3 = st.columns(3)
    col1.metric("총 발생 건수", f"{total_cases:,} 건")
    col2.metric("최다 발생 감염병", top_disease_name, f"{top_disease_count:,} 건")
    col3.metric("발생 이력 감염병 수", f"{disease_type_count} 종")
    
    st.markdown("---")
    
    # 차트 2개를 양쪽에 배치합니다.
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
        
        # 바 차트 그리기
        fig_top10 = px.bar(
            top10_df,
            x='발생건수',
            y='감염병명',
            orientation='h',
            text_auto=',.0f',
            color='발생건수',
            color_continuous_scale='Blues',
            labels={'발생건수': '발생 건수', '감염병명': '감염병 이름'}
        )
        fig_top10.update_layout(yaxis={'categoryorder': 'total ascending'}, showlegend=False)
        st.plotly_chart(fig_top10, use_container_width=True)
        
    with col_right:
        st.markdown("##### 🏷️ 감염병급별 발생 비중")
        class_summary = filtered_annual.groupby('감염병급')['발생건수'].sum().reset_index()
        
        # 원형(파이) 차트 그리기
        fig_pie = px.pie(
            class_summary,
            names='감염병급',
            values='발생건수',
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        st.plotly_chart(fig_pie, use_container_width=True)

# ------------------------------------------------------------------------------
# [탭 2] 시계열 분석
# ------------------------------------------------------------------------------
with tab2:
    st.subheader("📈 시간 흐름에 따른 발생 추이")
    
    # 월별 합계 데이터 생성
    monthly_trend = filtered_monthly.groupby('연월')['발생건수'].sum().reset_index()
    
    # 선 그래프 그리기
    fig_line = px.line(
        monthly_trend,
        x='연월',
        y='발생건수',
        markers=True,
        title="전체 월별 감염병 발생 건수 추이",
        labels={'연월': '년-월', '발생건수': '발생 건수'}
    )
    fig_line.update_traces(line_color='#E74C3C', line_width=2)
    st.plotly_chart(fig_line, use_container_width=True)
    
    st.markdown("---")
    
    # 연도 및 월별 계절성 히트맵
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
        color_continuous_scale='YlOrRd',
        aspect="auto"
    )
    st.plotly_chart(fig_heatmap, use_container_width=True)

# ------------------------------------------------------------------------------
# [탭 3] 감염병 비교
# ------------------------------------------------------------------------------
with tab3:
    st.subheader("🔬 특정 감염병 선택 및 비교 분석")
    
    # 사용자가 선택할 수 있는 감염병 목록
    disease_options = sorted(filtered_monthly['감염병명'].unique().tolist())
    
    # 기본 선택값 설정 (최대 3개)
    default_selected = disease_options[:3] if len(disease_options) >= 3 else disease_options
    
    selected_diseases = st.multiselect(
        "비교할 감염병을 선택하세요 (여러 개 선택 가능):",
        options=disease_options,
        default=default_selected
    )
    
    if selected_diseases:
        # 선택한 질병 데이터만 추출
        compare_monthly = filtered_monthly[filtered_monthly['감염병명'].isin(selected_diseases)]
        compare_annual = filtered_annual[filtered_annual['감염병명'].isin(selected_diseases)]
        
        # 월별 추이 비교 그래프
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
        
        # 연도별 합계 비교 바 차트
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
        horizontal=True
    )
    
    if view_option == "월별 데이터":
        display_df = filtered_monthly.drop(columns=['연월'], errors='ignore')
    else:
        display_df = filtered_annual
        
    st.dataframe(display_df, use_container_width=True)
    
    # CSV 파일로 다운로드 기능
    csv_data = display_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 현재 조회 중인 데이터 CSV로 다운로드",
        data=csv_data,
        file_name=f"{view_option}_filtered.csv",
        mime="text/csv"
    )
