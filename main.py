import json
import re
from numbers import Integral
from urllib.request import Request, urlopen

import pandas as pd
import pydeck as pdk
import streamlit as st
from shapely.geometry import Point, shape
from shapely.strtree import STRtree


st.set_page_config(
    page_title="전국 의료기관 현황 지도",
    page_icon="🏥",
    layout="wide",
)

# ---------------------------------------------------------------------
# 디자인 CSS
# ---------------------------------------------------------------------
st.markdown(
    """
    <style>
    :root {
        --medical-navy: #123d78;
        --medical-blue: #2878e8;
        --medical-pale: #edf6ff;
        --medical-line: #d6e8fb;
    }

    .stApp {
        background:
            radial-gradient(ellipse at 8% 4%, rgba(255,255,255,.98) 0%, rgba(255,255,255,0) 34%),
            radial-gradient(ellipse at 92% 14%, rgba(181,220,255,.58) 0%, rgba(181,220,255,0) 32%),
            linear-gradient(135deg, #eaf5ff 0%, #f8fbff 46%, #e6f2ff 100%);
        color: #183b66;
    }

    [data-testid="stAppViewContainer"] {
        background-image:
            radial-gradient(circle at 94% 7%, rgba(255,255,255,.9) 0 5px, transparent 6px),
            radial-gradient(circle at 88% 12%, rgba(255,255,255,.65) 0 3px, transparent 4px),
            linear-gradient(90deg, transparent 0 97%, rgba(83,157,235,.045) 97% 98%, transparent 98%);
        background-attachment: fixed;
    }

    [data-testid="stHeader"] { background: rgba(255,255,255,.48); }
    .main .block-container {
        max-width: 1600px;
        padding-top: 1.6rem;
        padding-bottom: 2.8rem;
    }

    h1, h2, h3, [data-testid="stMetricLabel"] {
        color: var(--medical-navy) !important;
        letter-spacing: -.025em;
    }
    h1 { font-weight: 850 !important; }
    [data-testid="stCaptionContainer"] { color: #5c7899; }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(235,246,255,.98), rgba(248,252,255,.96));
        border-right: 1px solid #d6e8fa;
    }
    [data-testid="stSidebar"] > div { background: transparent; }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #254b78;
    }

    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div {
        border-color: #cfe2f7 !important;
        border-radius: 12px !important;
        background: rgba(255,255,255,.92) !important;
    }
    div[data-baseweb="select"] > div:focus-within,
    div[data-baseweb="input"] > div:focus-within {
        border-color: #65a5f4 !important;
        box-shadow: 0 0 0 3px rgba(40,120,232,.11) !important;
    }

    [data-testid="stMetric"] {
        background: linear-gradient(145deg, rgba(255,255,255,.98), rgba(239,247,255,.94));
        border: 1px solid var(--medical-line);
        border-radius: 18px;
        padding: 18px 20px;
        box-shadow: 0 7px 22px rgba(41,100,165,.075);
    }
    [data-testid="stMetricValue"] {
        color: #1765c4 !important;
        font-weight: 800;
    }
    [data-testid="stMetricLabel"] { font-weight: 650; }

    [data-testid="stExpander"] {
        background: rgba(255,255,255,.78);
        border: 1px solid var(--medical-line);
        border-radius: 15px;
        overflow: hidden;
    }
    [data-testid="stAlert"] { border-radius: 14px; }
    [data-testid="stDataFrame"] {
        border: 1px solid #dceafa;
        border-radius: 12px;
        overflow: hidden;
    }
    hr { border-color: #d7e8f8 !important; }

    [data-testid="stDeckGlJsonChart"] {
        border: 1px solid #d7e8fa;
        border-radius: 20px;
        overflow: hidden;
        box-shadow: 0 10px 30px rgba(35,91,150,.09);
        background: rgba(255,255,255,.75);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

DATA_URL = "https://raw.githubusercontent.com/lillychaemin/medi/main/hospital_202606.csv"
GEOJSON_URL = "https://raw.githubusercontent.com/DevMinGeonPark/mapcn-kr/main/data/sgg.json"

COLORS = [
    [239, 246, 255, 210],
    [191, 219, 254, 215],
    [96, 165, 250, 220],
    [37, 99, 235, 225],
    [30, 64, 175, 230],
]


@st.cache_data(show_spinner="GitHub에서 의료기관 CSV를 불러오는 중...")
def load_hospitals(data_url: str) -> pd.DataFrame:
    df = pd.read_csv(data_url, encoding="utf-8-sig", low_memory=False)
    required = ["요양기관명", "종별코드명", "시도코드", "시도코드명", "시군구코드", "시군구코드명"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV에 필요한 열이 없습니다: {', '.join(missing)}")

    df["시도코드"] = df["시도코드"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(2)
    df["시군구코드"] = df["시군구코드"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    df["시도코드명"] = df["시도코드명"].fillna("미상").astype(str).str.strip()
    df["시군구코드명"] = df["시군구코드명"].fillna("미상").astype(str).str.strip()
    df["종별코드명"] = df["종별코드명"].fillna("미상").astype(str).str.strip()
    return df


@st.cache_data(ttl=86400)
def load_geojson() -> dict:
    request = Request(GEOJSON_URL, headers={"User-Agent": "Streamlit-medical-map/1.0"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def make_bins(counts: pd.Series) -> pd.Series:
    if counts.empty:
        return pd.Series(dtype="int64")
    ranks = counts.rank(method="first")
    n = len(counts)
    if n == 1:
        return pd.Series([1], index=counts.index, dtype="int64")
    classes = ((ranks - 1) * 5 // n + 1).astype(int)
    return classes.clip(1, 5).astype(int)


def normalize_sido_name(value) -> str:
    name = re.sub(r"\s+", "", str(value or ""))
    rules = [
        ("서울", ("서울",)), ("부산", ("부산",)), ("대구", ("대구",)), ("인천", ("인천",)),
        ("광주", ("광주",)), ("대전", ("대전",)), ("울산", ("울산",)), ("세종", ("세종",)),
        ("경기", ("경기",)), ("강원", ("강원",)), ("충북", ("충북", "충청북")),
        ("충남", ("충남", "충청남")), ("전북", ("전북", "전라북")), ("전남", ("전남", "전라남")),
        ("경북", ("경북", "경상북")), ("경남", ("경남", "경상남")), ("제주", ("제주",)),
    ]
    for key, prefixes in rules:
        if any(name.startswith(prefix) for prefix in prefixes):
            return key
    return name


def normalize_sgg_name(value) -> str:
    name = re.sub(r"\s+", "", str(value or ""))
    name = re.sub(r"시(?=[가-힣]+[구군]$)", "", name)
    return name


def sgg_aliases(value) -> list[str]:
    name = normalize_sgg_name(value)
    aliases = [name]
    for city in ("부천", "화성", "대구", "인천", "부산", "광주", "대전", "울산"):
        if name.startswith(city) and len(name) > len(city):
            aliases.append(name[len(city):])
    if name.endswith("구"):
        for i in range(1, len(name) - 1):
            suffix = name[i:]
            if suffix.endswith("구") and len(suffix) >= 2:
                aliases.append(suffix)
    if name in {"세종", "세종시", "세종특별자치시"}:
        aliases.extend(["세종", "세종시", "세종특별자치시"])
    return list(dict.fromkeys(a for a in aliases if a))


def _feature_sido_and_name(props: dict) -> tuple[str, str]:
    full = str(props.get("FULL_NM") or props.get("full_nm") or "").strip()
    sido = props.get("sidonm") or props.get("SIDO_NM") or props.get("CTP_KOR_NM") or props.get("sido_nm") or ""
    sgg = props.get("sggnm") or props.get("SIG_KOR_NM") or props.get("SIG_NM") or props.get("name") or ""
    if full:
        parts = full.split()
        if not sido and parts:
            sido = parts[0]
        if not sgg and parts:
            sgg = parts[-1]
    return str(sido).strip(), str(sgg).strip()


def assign_geo_ids(hospitals: pd.DataFrame, geojson: dict) -> tuple[pd.DataFrame, list[str], int]:
    features = geojson.get("features", [])
    polygons, feature_ids, geom_identity = [], [], {}
    alias_lookup = {}
    for idx, feature in enumerate(features):
        props = feature.setdefault("properties", {})
        sido_raw, sgg_raw = _feature_sido_and_name(props)
        full = str(props.get("FULL_NM") or "").strip()
        if not full:
            full = f"{sido_raw} {sgg_raw}".strip()
        props["FULL_NM"] = full or sgg_raw or f"시군구 {idx}"
        feature_id = str(idx)
        try:
            polygon = shape(feature["geometry"])
        except Exception:
            continue
        if polygon.is_empty:
            continue
        polygons.append(polygon)
        feature_ids.append(feature_id)
        geom_identity.setdefault(id(polygon), []).append(len(polygons) - 1)
        sido_key = normalize_sido_name(sido_raw)
        for name in [sgg_raw, full.split()[-1] if full.split() else ""]:
            for alias in sgg_aliases(name):
                alias_lookup.setdefault((sido_key, alias), set()).add(feature_id)

    if not polygons:
        raise ValueError("GeoJSON에서 유효한 시군구 경계 폴리곤을 찾지 못했습니다.")
    tree = STRtree(polygons)
    x_col = next((c for c in ("좌표(X)", "경도", "longitude", "lon", "X") if c in hospitals.columns), None)
    y_col = next((c for c in ("좌표(Y)", "위도", "latitude", "lat", "Y") if c in hospitals.columns), None)
    result = hospitals.copy()
    result["geo_id"] = None
    coordinate_matches = 0

    if x_col and y_col:
        xs = pd.to_numeric(result[x_col], errors="coerce")
        ys = pd.to_numeric(result[y_col], errors="coerce")
        for row_idx, (x, y) in enumerate(zip(xs, ys)):
            if pd.isna(x) or pd.isna(y) or not (-180 <= x <= 180 and -90 <= y <= 90):
                continue
            point = Point(float(x), float(y))
            candidates = tree.query(point)
            hit = None
            for candidate in candidates:
                if isinstance(candidate, Integral):
                    poly_idx = int(candidate)
                else:
                    matches = geom_identity.get(id(candidate), [])
                    if not matches:
                        matches = [i for i, poly in enumerate(polygons) if poly.equals(candidate)]
                    if not matches:
                        continue
                    poly_idx = matches[0]
                if polygons[poly_idx].covers(point):
                    hit = feature_ids[poly_idx]
                    break
            if hit is not None:
                result.iat[row_idx, result.columns.get_loc("geo_id")] = hit
                coordinate_matches += 1

    for row_idx in result.index[result["geo_id"].isna()]:
        row = result.loc[row_idx]
        sido = normalize_sido_name(row.get("시도코드명", ""))
        sgg = row.get("시군구코드명", "")
        candidates = set()
        for alias in sgg_aliases(sgg):
            found = alias_lookup.get((sido, alias), set())
            if len(found) == 1:
                candidates = found
                break
        if len(candidates) == 1:
            result.at[row_idx, "geo_id"] = next(iter(candidates))

    missing_rows = result[result["geo_id"].isna()]
    unmatched = sorted(set(
        f"{row.get('시도코드명', '')} {row.get('시군구코드명', '')}"
        for _, row in missing_rows.iterrows()
    ))
    return result, unmatched, coordinate_matches


def build_map_geojson(geojson: dict, counts: pd.DataFrame, selected_sido: str, selected_sgg: str) -> tuple[dict, dict]:
    result = json.loads(json.dumps(geojson))
    features = result.get("features", [])
    mapped_counts = {}
    for row in counts.itertuples(index=False):
        geo_id = str(getattr(row, "geo_id"))
        mapped_counts[geo_id] = int(getattr(row, "의료기관수"))

    mapped_series = pd.Series(mapped_counts, dtype="int64")
    class_map = make_bins(mapped_series).to_dict() if not mapped_series.empty else {}

    for idx, feature in enumerate(features):
        props = feature.setdefault("properties", {})
        geo_id = str(idx)
        
        sido_raw, sgg_raw = _feature_sido_and_name(props)
        norm_sido = normalize_sido_name(sido_raw)
        
        # 필터 조건에 맞지 않는 지역은 아예 데이터를 지우거나 회색 처리
        is_visible = True
        if selected_sido != "전체" and norm_sido != normalize_sido_name(selected_sido):
            is_visible = False
        if selected_sgg != "전체" and normalize_sgg_name(sgg_raw) not in sgg_aliases(selected_sgg):
            is_visible = False

        if is_visible and geo_id in mapped_counts:
            count = int(mapped_counts[geo_id])
            level = int(class_map.get(geo_id, 1))
            props["의료기관수"] = count
            props["단계"] = level
            props["fill_color"] = COLORS[level - 1] if 1 <= level <= 5 else [30, 64, 175, 230]
        else:
            # 선택되지 않은 구역은 회색으로 처리
            props["의료기관수"] = 0
            props["단계"] = 0
            props["fill_color"] = [235, 235, 235, 120]

        full = str(props.get("FULL_NM") or "").strip()
        if not full:
            props["FULL_NM"] = f"{sido_raw} {sgg_raw}".strip() or f"시군구 {idx}"

    return result, {
        "matched": len(mapped_counts),
        "total_geo": len(features),
        "unmatched": [],
        "mapped_regions": len(mapped_counts),
    }


def format_number(value) -> str:
    return f"{int(value):,}"


# ---------------------------------------------------------------------
# 데이터 로드
# ---------------------------------------------------------------------
try:
    hospitals = load_hospitals(DATA_URL)
except Exception as e:
    st.error(f"CSV를 읽지 못했습니다: {e}")
    st.stop()

try:
    geojson = load_geojson()
    hospitals, unmatched_institutions, coordinate_matches = assign_geo_ids(hospitals, geojson)
except Exception as e:
    st.error(f"행정경계 연결 실패: {e}")
    st.stop()


# ---------------------------------------------------------------------
# 화면 구성 및 필터
# ---------------------------------------------------------------------
st.title("🏥 전국 의료기관 현황 지도")
st.caption("2026년 6월 병원정보서비스 기준 · 시군구별 의료기관 수 단계구분도")

with st.sidebar:
    st.header("🔎 지도 필터")

    sido_options = ["전체"] + sorted(hospitals["시도코드명"].dropna().unique().tolist())
    selected_sido = st.selectbox("시도", sido_options)

    filtered = hospitals.copy()
    if selected_sido != "전체":
        filtered = filtered[filtered["시도코드명"] == selected_sido]

    sgg_options = ["전체"] + sorted(filtered["시군구코드명"].dropna().unique().tolist())
    selected_sgg = st.selectbox("시군구", sgg_options)

    if selected_sgg != "전체":
        filtered = filtered[filtered["시군구코드명"] == selected_sgg]

    type_options = ["전체"] + sorted(filtered["종별코드명"].dropna().unique().tolist())
    selected_type = st.selectbox("의료기관 종류", type_options)

    if selected_type != "전체":
        filtered = filtered[filtered["종별코드명"] == selected_type]

    st.divider()
    st.markdown(
        """
        **지도 읽는 법**
        연한 색 → 의료기관 수가 적은 시군구  
        진한 색 → 의료기관 수가 많은 시군구
        """
    )

# 시군구별 집계
counts = (
    filtered.dropna(subset=["geo_id"])
    .groupby("geo_id", as_index=False)
    .size()
    .rename(columns={"size": "의료기관수"})
)

total_count = len(filtered)
sgg_count = int(filtered["geo_id"].dropna().nunique())

col1, col2, col3 = st.columns(3)
col1.metric("의료기관 수", format_number(total_count) + "개")
col2.metric("표시 시군구", format_number(sgg_count) + "곳")
col3.metric("원자료 기관 수", format_number(len(hospitals)) + "개")

# ---------------------------------------------------------------------
# 지도 생성
# ---------------------------------------------------------------------
try:
    map_geojson, info = build_map_geojson(geojson, counts, selected_sido, selected_sgg)
except Exception as e:
    st.error(f"지도 경계 연결 오류: {e}")
    st.stop()

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
# 선택 지역 병원 목록 (네이버 플레이스 스타일)
# ---------------------------------------------------------------------
st.subheader("📋 선택 지역 병원 목록")
st.caption("사이드바에서 선택한 지역과 조건에 해당하는 병원 상세 정보입니다.")

display_cols = [
    c for c in [
        "요양기관명", "종별코드명", "시도코드명", "시군구코드명", 
        "주소", "소재지주소", "요양기관주소", "전화번호", "개설일자"
    ] if c in filtered.columns
]

if not filtered.empty:
    st.dataframe(
        filtered[display_cols],
        width="stretch",
        hide_index=True,
        height=420,
        column_config={
            "요양기관명": st.column_config.TextColumn("병원 이름", width="medium"),
            "종별코드명": st.column_config.TextColumn("종류", width="small"),
        }
    )
else:
    st.info("선택한 조건에 해당하는 병원이 없습니다.")

# ---------------------------------------------------------------------
# 데이터 출처
# ---------------------------------------------------------------------
st.caption(
    "의료기관 원자료: 건강보험심사평가원 병원정보서비스(2026년 6월). "
    "행정구역 경계: MapCN-KR 시군구 GeoJSON."
)
