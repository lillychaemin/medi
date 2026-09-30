import json
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
import pydeck as pdk
import streamlit as st


st.set_page_config(
    page_title="전국 의료기관 현황 지도",
    page_icon="🏥",
    layout="wide",
)

DATA_FILE = "1.병원정보서비스(2026.6.).xlsx"
GEOJSON_URL = (
    "https://raw.githubusercontent.com/KnellBalm/kr-admin-geojson/main/sig.geojson"
)

# 단계구분도에 사용할 색상: 연한 색 → 진한 색
COLORS = [
    [239, 246, 255, 210],
    [191, 219, 254, 215],
    [96, 165, 250, 220],
    [37, 99, 235, 225],
    [30, 64, 175, 230],
]


@st.cache_data
def load_hospitals(file_path: str) -> pd.DataFrame:
    """2026년 6월 병원정보서비스 엑셀을 읽습니다."""
    df = pd.read_excel(file_path, engine="openpyxl")

    required = [
        "요양기관명",
        "종별코드명",
        "시도코드",
        "시도코드명",
        "시군구코드",
        "시군구코드명",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"엑셀에 필요한 열이 없습니다: {', '.join(missing)}")

    # 코드가 숫자로 읽혀도 앞자리 0이 사라지지 않도록 문자열로 통일
    df["시도코드"] = (
        df["시도코드"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(2)
    )
    df["시군구코드"] = (
        df["시군구코드"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    )

    df["시도코드명"] = df["시도코드명"].fillna("미상").astype(str).str.strip()
    df["시군구코드명"] = df["시군구코드명"].fillna("미상").astype(str).str.strip()
    df["종별코드명"] = df["종별코드명"].fillna("미상").astype(str).str.strip()

    return df


@st.cache_data(ttl=86400)
def load_geojson() -> dict:
    """시군구 경계 GeoJSON을 GitHub에서 가져옵니다."""
    request = Request(
        GEOJSON_URL,
        headers={"User-Agent": "Streamlit-medical-map/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def make_bins(counts: pd.Series) -> pd.Series:
    """의료기관 수를 5단계로 나눕니다."""
    if counts.empty:
        return pd.Series(dtype="int64")

    # 분위수 기준으로 5단계. 값이 중복되어 구간이 줄어드는 경우에도 안전하게 처리.
    ranks = counts.rank(method="first")
    n = len(counts)

    if n == 1:
        return pd.Series([1], index=counts.index, dtype="int64")

    classes = ((ranks - 1) * 5 // n + 1).astype(int)
    return classes.clip(1, 5).astype(int)


def build_map_geojson(geojson: dict, counts: pd.DataFrame) -> tuple[dict, dict]:
    """GeoJSON과 집계 결과를 시군구 코드로 결합합니다."""
    count_map = dict(zip(counts["시군구코드"], counts["의료기관수"]))

    # 지도에 표시되는 통계의 최대/최소 및 단계 계산
    values = counts["의료기관수"].astype(int)
    if len(values) > 0:
        tmp = counts.copy()
        tmp["단계"] = make_bins(tmp["의료기관수"])
        class_map = dict(zip(tmp["시군구코드"], tmp["단계"]))
    else:
        class_map = {}

    result = json.loads(json.dumps(geojson))
    matched = 0

    for feature in result.get("features", []):
        props = feature.setdefault("properties", {})
        code = str(props.get("SIG_CD", "")).strip().zfill(5)

        count = int(count_map.get(code, 0))
        level = int(class_map.get(code, 0))

        props["의료기관수"] = count
        props["단계"] = level
        props["fill_color"] = COLORS[level - 1] if 1 <= level <= 5 else [235, 235, 235, 120]

        if code in count_map:
            matched += 1

    return result, {
        "matched": matched,
        "total_geo": len(result.get("features", [])),
    }


def format_number(value) -> str:
    return f"{int(value):,}"


# ---------------------------------------------------------------------
# 데이터 읽기
# ---------------------------------------------------------------------
if not Path(DATA_FILE).exists():
    st.error(
        f"**{DATA_FILE}** 파일을 찾을 수 없습니다. "
        "main.py와 같은 폴더에 엑셀 파일을 넣어 주세요."
    )
    st.stop()

try:
    hospitals = load_hospitals(DATA_FILE)
except Exception as e:
    st.error(f"엑셀 파일을 읽는 중 오류가 발생했습니다: {e}")
    st.stop()


# ---------------------------------------------------------------------
# 제목
# ---------------------------------------------------------------------
st.title("🏥 전국 의료기관 현황 지도")
st.caption("2026년 6월 병원정보서비스 기준 · 시군구별 의료기관 수 단계구분도")

# ---------------------------------------------------------------------
# 필터
# ---------------------------------------------------------------------
with st.sidebar:
    st.header("🔎 지도 필터")

    sido_options = ["전체"] + sorted(hospitals["시도코드명"].dropna().unique().tolist())
    selected_sido = st.selectbox("시도", sido_options)

    filtered = hospitals.copy()

    if selected_sido != "전체":
        filtered = filtered[filtered["시도코드명"] == selected_sido]

    type_options = ["전체"] + sorted(
        filtered["종별코드명"].dropna().unique().tolist()
    )
    selected_type = st.selectbox("의료기관 종류", type_options)

    if selected_type != "전체":
        filtered = filtered[filtered["종별코드명"] == selected_type]

    st.divider()
    st.markdown(
        """
        **지도 읽는 법**

        연한 색 → 의료기관 수가 적은 시군구  
        진한 색 → 의료기관 수가 많은 시군구

        *단계는 현재 필터 조건에 따라 상대적으로 구분됩니다.*
        """
    )

# ---------------------------------------------------------------------
# 시군구별 집계
# ---------------------------------------------------------------------
counts = (
    filtered.groupby(
        ["시도코드", "시도코드명", "시군구코드", "시군구코드명"],
        as_index=False,
    )
    .size()
    .rename(columns={"size": "의료기관수"})
)

# 전체 의료기관 수
total_count = len(filtered)
sgg_count = len(counts)

col1, col2, col3 = st.columns(3)
col1.metric("의료기관 수", format_number(total_count) + "개")
col2.metric("표시 시군구", format_number(sgg_count) + "곳")
col3.metric("원자료 기관 수", format_number(len(hospitals)) + "개")

# ---------------------------------------------------------------------
# 지도
# ---------------------------------------------------------------------
try:
    geojson = load_geojson()
    map_geojson, info = build_map_geojson(geojson, counts)
except Exception as e:
    st.error(
        "시군구 경계 GeoJSON을 불러오지 못했습니다. "
        f"인터넷 연결 또는 GeoJSON 주소를 확인해 주세요.\n\n{e}"
    )
    st.stop()

if info["matched"] == 0:
    st.warning(
        "엑셀의 시군구 코드와 GeoJSON의 시군구 코드가 일치하지 않아 "
        "지도에 집계값을 연결하지 못했습니다."
    )

layer = pdk.Layer(
    "GeoJsonLayer",
    data=map_geojson,
    id="medical-sgg",
    pickable=True,
    stroked=True,
    filled=True,
    extruded=False,
    get_fill_color="properties.fill_color",
    get_line_color=[90, 90, 90, 180],
    line_width_min_pixels=0.7,
    auto_highlight=True,
)

view_state = pdk.ViewState(
    latitude=36.35,
    longitude=127.85,
    zoom=6.3,
    min_zoom=5,
    max_zoom=10,
    pitch=0,
    bearing=0,
)

deck = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    tooltip={
        "html": """
        <div style="font-size:14px">
            <b>{FULL_NM}</b><br/>
            의료기관 수: <b>{의료기관수}개</b>
        </div>
        """,
        "style": {
            "backgroundColor": "white",
            "color": "#222",
        },
    },
    map_style=None,
)

st.pydeck_chart(deck, width="stretch", height=680)

# ---------------------------------------------------------------------
# 범례
# ---------------------------------------------------------------------
st.subheader("색상 범례")

if not counts.empty:
    sorted_counts = counts["의료기관수"].sort_values()
    q = sorted_counts.quantile([0.2, 0.4, 0.6, 0.8]).tolist()

    labels = [
        f"≤ {int(q[0]):,}",
        f"{int(q[0]) + 1:,} ~ {int(q[1]):,}",
        f"{int(q[1]) + 1:,} ~ {int(q[2]):,}",
        f"{int(q[2]) + 1:,} ~ {int(q[3]):,}",
        f"> {int(q[3]):,}",
    ]

    cols = st.columns(5)
    for i, col in enumerate(cols):
        rgb = COLORS[i][:3]
        col.markdown(
            f"""
            <div style="
                background: rgb({rgb[0]}, {rgb[1]}, {rgb[2]});
                padding: 8px 4px;
                border-radius: 4px;
                text-align: center;
                font-size: 13px;
                color: {'white' if i >= 3 else '#222'};
            ">{labels[i]}</div>
            """,
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------
# 시군구별 표
# ---------------------------------------------------------------------
with st.expander("📊 시군구별 의료기관 수 표 보기"):
    table = counts[
        ["시도코드명", "시군구코드명", "의료기관수"]
    ].sort_values("의료기관수", ascending=False)

    table = table.rename(
        columns={
            "시도코드명": "시도",
            "시군구코드명": "시군구",
            "의료기관수": "의료기관 수",
        }
    )

    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={
            "의료기관 수": st.column_config.NumberColumn(
                "의료기관 수", format="%d개"
            )
        },
    )

# ---------------------------------------------------------------------
# 데이터 출처
# ---------------------------------------------------------------------
st.caption(
    "의료기관 원자료: 건강보험심사평가원 병원정보서비스(2026년 6월). "
    "행정구역 경계: kr-admin-geojson 시군구 GeoJSON "
    "(국가공간정보포털/V-World 기반)."
)

