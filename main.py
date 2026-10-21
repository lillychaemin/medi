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

# GitHub에 업로드한 CSV 파일의 Raw URL로 바꾸세요.
# CSV가 저장소 최상위(루트)에 있으므로 /data/를 넣지 않습니다.
DATA_URL = "https://raw.githubusercontent.com/lillychaemin/medi/main/hospital_202606.csv"
# 2026-07 기준 최신 시군구 경계(256개, 전남광주 통합 반영)
GEOJSON_URL = (
    "https://raw.githubusercontent.com/DevMinGeonPark/mapcn-kr/main/data/sgg.json"
)

# 단계구분도에 사용할 색상: 연한 색 → 진한 색
COLORS = [
    [239, 246, 255, 210],
    [191, 219, 254, 215],
    [96, 165, 250, 220],
    [37, 99, 235, 225],
    [30, 64, 175, 230],
]


@st.cache_data(show_spinner="GitHub에서 의료기관 CSV를 불러오는 중...")
def load_hospitals(data_url: str) -> pd.DataFrame:
    """GitHub Raw URL에서 2026년 6월 의료기관 CSV를 읽습니다."""
    df = pd.read_csv(data_url, encoding="utf-8-sig", low_memory=False)

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
        raise ValueError(f"CSV에 필요한 열이 없습니다: {', '.join(missing)}")

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


def normalize_sido_name(value) -> str:
    """CSV와 GeoJSON의 시도 명칭을 공통 키로 정규화합니다."""
    name = re.sub(r"\s+", "", str(value or ""))
    rules = [
        ("서울", ("서울",)),
        ("부산", ("부산",)),
        ("대구", ("대구",)),
        ("인천", ("인천",)),
        ("광주", ("광주",)),
        ("대전", ("대전",)),
        ("울산", ("울산",)),
        ("세종", ("세종",)),
        ("경기", ("경기",)),
        ("강원", ("강원",)),
        ("충북", ("충북", "충청북")),
        ("충남", ("충남", "충청남")),
        ("전북", ("전북", "전라북")),
        ("전남", ("전남", "전라남")),
        ("경북", ("경북", "경상북")),
        ("경남", ("경남", "경상남")),
        ("제주", ("제주",)),
    ]
    for key, prefixes in rules:
        if any(name.startswith(prefix) for prefix in prefixes):
            return key
    return name


def normalize_sgg_name(value) -> str:
    """시군구 명칭의 공백과 '고양시 덕양구' 같은 표기 차이를 정리합니다."""
    name = re.sub(r"\s+", "", str(value or ""))
    # 예: 고양시덕양구 -> 고양덕양구, 전주시덕진구 -> 전주덕진구
    name = re.sub(r"시(?=[가-힣]+[구군]$)", "", name)
    return name


def sgg_aliases(value) -> list[str]:
    """시군구명 표기 차이를 흡수하되, 시도 키와 함께 비교할 별칭을 만듭니다."""
    name = normalize_sgg_name(value)
    aliases = [name]

    # CSV에서 시 이름이 시군구명에 중복된 표기: 대구대구서구/대구서구,
    # 인천인천동구, 부산부산서구 등. 시도도 함께 비교하므로 다른 시도의
    # 같은 이름과 잘못 연결되지 않습니다.
    for city in ("부천", "화성", "대구", "인천", "부산", "광주", "대전", "울산"):
        if name.startswith(city) and len(name) > len(city):
            aliases.append(name[len(city):])

    # 구 이름 앞에 도시명이 붙은 경우(예: 부천소사구, 화성동탄구)도
    # 짧은 구 이름으로 비교합니다. 다만 실제 경계 feature가 있어야 연결됩니다.
    if name.endswith("구"):
        for i in range(1, len(name) - 1):
            suffix = name[i:]
            if suffix.endswith("구") and len(suffix) >= 2:
                aliases.append(suffix)

    # 세종은 시군구 레벨 데이터에서 세종시/세종특별자치시로 다르게 표기될 수 있습니다.
    if name in {"세종", "세종시", "세종특별자치시"}:
        aliases.extend(["세종", "세종시", "세종특별자치시"])

    return list(dict.fromkeys(a for a in aliases if a))


def _feature_sido_and_name(props: dict) -> tuple[str, str]:
    """GeoJSON의 다양한 속성명에서 시도명과 시군구명을 추출합니다."""
    full = str(props.get("FULL_NM") or props.get("full_nm") or "").strip()
    sido = (
        props.get("sidonm") or props.get("SIDO_NM") or props.get("CTP_KOR_NM")
        or props.get("ctp_kor_nm") or props.get("sido_nm") or ""
    )
    sgg = (
        props.get("sggnm") or props.get("SIG_KOR_NM") or props.get("sig_kor_nm")
        or props.get("SIG_NM") or props.get("sgg_nm") or props.get("name") or ""
    )
    if full:
        parts = full.split()
        if not sido and parts:
            sido = parts[0]
        if not sgg and parts:
            sgg = parts[-1]
    return str(sido).strip(), str(sgg).strip()


def assign_geo_ids(hospitals: pd.DataFrame, geojson: dict) -> tuple[pd.DataFrame, list[str], int]:
    """기관 좌표를 시군구 폴리곤에 공간 연결합니다. 명칭 차이와 경계 개편에 강합니다."""
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree
    from numbers import Integral

    features = geojson.get("features", [])
    polygons, feature_ids, geom_identity = [], [], {}
    alias_lookup = {}
    for idx, feature in enumerate(features):
        props = feature.setdefault("properties", {})
        sido_raw, sgg_raw = _feature_sido_and_name(props)
        full = str(props.get("FULL_NM") or props.get("full_nm") or "").strip()
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
        # 통합 시도명과 구 데이터의 광주·전남을 함께 검색할 수 있게 별칭 처리
        if "전남광주" in re.sub(r"\s+", "", sido_raw):
            for name in [sgg_raw, full.split()[-1] if full.split() else ""]:
                for alias in sgg_aliases(name):
                    alias_lookup.setdefault(("광주", alias), set()).add(feature_id)
                    alias_lookup.setdefault(("전남", alias), set()).add(feature_id)

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
                if isinstance(candidate, Integral):  # Shapely 2.x returns indices
                    poly_idx = int(candidate)
                else:  # Shapely 1.x returns geometry objects
                    matches = geom_identity.get(id(candidate), [])
                    if not matches:
                        # Fallback for geometry objects whose Python identity was not retained
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

    # 좌표가 없거나 경계 밖인 기관은 시도·시군구 이름이 유일하게 일치할 때만 보완합니다.
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


def build_map_geojson(geojson: dict, counts: pd.DataFrame) -> tuple[dict, dict]:
    """GeoJSON feature index 기준 집계값을 붙이고 단계별 색상을 지정합니다."""
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
        # feature 순서에 대응하는 내부 ID를 생성해 공간 연결 결과와 결합합니다.
        count = int(mapped_counts.get(geo_id, 0))
        level = int(class_map.get(geo_id, 0))
        props["의료기관수"] = count
        props["단계"] = level
        props["fill_color"] = COLORS[level - 1] if 1 <= level <= 5 else [235, 235, 235, 120]
        sido_raw, sgg_raw = _feature_sido_and_name(props)
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
# 데이터 읽기
# ---------------------------------------------------------------------
try:
    hospitals = load_hospitals(DATA_URL)
except Exception as e:
    st.error(
        "GitHub Raw URL에서 CSV를 읽지 못했습니다. DATA_URL이 올바른지, "
        f"저장소와 파일이 공개되어 있는지 확인해 주세요.\n\n오류: {e}"
    )
    st.stop()

try:
    geojson = load_geojson()
    hospitals, unmatched_institutions, coordinate_matches = assign_geo_ids(hospitals, geojson)
except Exception as e:
    st.error(f"행정경계와 의료기관 좌표를 연결하지 못했습니다. GeoJSON 속성 및 좌표계를 확인해 주세요.\n\n오류: {e}")
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
    filtered.dropna(subset=["geo_id"])
    .groupby("geo_id", as_index=False)
    .size()
    .rename(columns={"size": "의료기관수"})
)

# 전체 의료기관 수
total_count = len(filtered)
sgg_count = int(filtered["geo_id"].dropna().nunique())

col1, col2, col3 = st.columns(3)
col1.metric("의료기관 수", format_number(total_count) + "개")
col2.metric("표시 시군구", format_number(sgg_count) + "곳")
col3.metric("원자료 기관 수", format_number(len(hospitals)) + "개")

# ---------------------------------------------------------------------
# 지도
# ---------------------------------------------------------------------
try:
    map_geojson, info = build_map_geojson(geojson, counts)
except Exception as e:
    st.error(f"지도 경계에 집계값을 연결하지 못했습니다.\n\n오류: {e}")
    st.stop()

if unmatched_institutions:
    with st.expander(f"좌표 또는 이름으로 경계를 찾지 못한 기관의 지역 {len(unmatched_institutions)}곳 확인"):
        st.caption(
            f"좌표를 통해 경계에 연결한 기관 수: {coordinate_matches:,}개. "
            "아래 지역은 좌표가 없거나 경계와 일치하지 않아 이름으로도 유일하게 연결되지 않았습니다. "
            "특히 행정구역이 분리·개편된 지역은 기관 주소를 확인해야 정확히 배정할 수 있습니다."
        )
        st.write(" · ".join(unmatched_institutions[:80]))

        # 누락된 행의 기관명·주소를 보여 주어 수동 확인 또는 주소 기반 보완이 가능하도록 함
        missing_detail_cols = [
            c for c in [
                "요양기관명", "종별코드명", "시도코드명", "시군구코드명",
                "주소", "소재지주소", "요양기관주소", "주소(도로명)",
                "좌표(X)", "좌표(Y)",
            ] if c in hospitals.columns
        ]
        missing_details = hospitals[hospitals["geo_id"].isna()]
        if missing_detail_cols and not missing_details.empty:
            st.markdown("**경계에 연결되지 않은 기관 상세 정보**")
            st.dataframe(
                missing_details[missing_detail_cols],
                width="stretch",
                hide_index=True,
            )

if filtered["geo_id"].isna().any():
    missing_n = int(filtered["geo_id"].isna().sum())
    st.warning(f"현재 필터에서 경계에 연결되지 않은 기관 {missing_n:,}개는 지도 집계에서 제외됩니다. 원자료 표에는 포함된 기관 수와 지도 집계 수가 다를 수 있습니다.")

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
    geo_rows = []
    for idx, feature in enumerate(map_geojson.get("features", [])):
        props = feature.get("properties", {})
        geo_rows.append({
            "시군구": props.get("FULL_NM", f"시군구 {idx}"),
            "의료기관 수": int(props.get("의료기관수", 0)),
        })
    table = pd.DataFrame(geo_rows).sort_values("의료기관 수", ascending=False)
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={
            "의료기관 수": st.column_config.NumberColumn("의료기관 수", format="%d개")
        },
    )

# ---------------------------------------------------------------------
# 데이터 출처
# ---------------------------------------------------------------------
st.caption(
    "의료기관 원자료: 건강보험심사평가원 병원정보서비스(2026년 6월). "
    "행정구역 경계: mapcn-kr 시군구 GeoJSON "
    "(통계청 SGIS·행정안전부 자료, 2026년 7월 기준; CC BY 4.0)."
)
