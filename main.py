import json
import re
from urllib.request import Request, urlopen

import pandas as pd
import pydeck as pdk
import streamlit as st


st.set_page_config(
    page_title="전국 의료기관 현황 지도",
    page_icon="🏥",
    layout="wide",
)

# GitHub에 업로드한 CSV 파일의 Raw URL로 바꾸세요.
# CSV가 저장소 최상위(루트)에 있으므로 /data/를 넣지 않습니다.
DATA_URL = "https://raw.githubusercontent.com/lillychaemin/medi/main/hospital_202606.csv"
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
    """도시 이름이 앞에 붙은 구 명칭도 연결할 수 있도록 별칭을 만듭니다."""
    name = normalize_sgg_name(value)
    aliases = [name]
    # 예: 대구동구 -> 동구, 고양덕양구 -> 덕양구
    # 시도까지 함께 비교하므로 동일한 구 이름의 다른 시도와 혼동하지 않습니다.
    if name.endswith("구"):
        for i in range(1, len(name) - 1):
            suffix = name[i:]
            if suffix.endswith("구") and len(suffix) >= 2:
                aliases.append(suffix)
    return list(dict.fromkeys(aliases))


def build_map_geojson(geojson: dict, counts: pd.DataFrame) -> tuple[dict, dict]:
    """서로 다른 코드 체계 대신 시도·시군구 명칭을 정규화해 집계값을 연결합니다."""
    result = json.loads(json.dumps(geojson))
    features = result.get("features", [])

    # (정규화된 시도, 시군구 별칭) -> GeoJSON SIG_CD 후보 목록
    alias_to_codes = {}
    feature_by_code = {}
    for feature in features:
        props = feature.setdefault("properties", {})
        code = str(props.get("SIG_CD", "")).strip()
        if not code:
            continue
        feature_by_code[code] = feature
        sido = normalize_sido_name(
            props.get("SIDO_NM") or props.get("CTP_KOR_NM") or
            str(props.get("FULL_NM", "")).split()[0]
        )
        names = [props.get("SIG_KOR_NM", "")]
        full_name = str(props.get("FULL_NM", "")).strip()
        if full_name:
            names.append(full_name.split()[-1])
            # FULL_NM의 마지막 두 행정단위(예: '고양시 덕양구')도 후보로 사용
            parts = full_name.split()
            if len(parts) >= 2:
                names.append("".join(parts[-2:]))
        for name in names:
            for alias in sgg_aliases(name):
                alias_to_codes.setdefault((sido, alias), set()).add(code)

    # 각 CSV 집계 행을 이름으로 GeoJSON 코드에 연결합니다.
    mapped_counts = {}
    unmatched = []
    for row in counts.itertuples(index=False):
        # counts 컬럼 순서: 시도코드, 시도코드명, 시군구코드, 시군구코드명, 의료기관수
        sido = normalize_sido_name(getattr(row, "시도코드명"))
        sgg_name = getattr(row, "시군구코드명")
        candidates = set()
        for alias in sgg_aliases(sgg_name):
            found = alias_to_codes.get((sido, alias), set())
            if len(found) == 1:
                candidates = found
                break
        if len(candidates) == 1:
            code = next(iter(candidates))
            mapped_counts[code] = mapped_counts.get(code, 0) + int(getattr(row, "의료기관수"))
        else:
            unmatched.append(f"{getattr(row, '시도코드명')} {sgg_name}")

    # 지도 색상 단계를 GeoJSON 지역 코드 기준으로 다시 계산합니다.
    mapped_series = pd.Series(mapped_counts, dtype="int64")
    if not mapped_series.empty:
        class_series = make_bins(mapped_series)
        class_map = class_series.to_dict()
    else:
        class_map = {}

    matched = 0
    for code, feature in feature_by_code.items():
        props = feature["properties"]
        count = int(mapped_counts.get(code, 0))
        level = int(class_map.get(code, 0))
        props["의료기관수"] = count
        props["단계"] = level
        props["fill_color"] = COLORS[level - 1] if 1 <= level <= 5 else [235, 235, 235, 120]
        if code in mapped_counts:
            matched += 1

    return result, {
        "matched": matched,
        "total_geo": len(features),
        "unmatched": unmatched,
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
        "CSV와 GeoJSON의 지역을 이름으로 연결하지 못했습니다. "
        "GeoJSON의 SIDO_NM/SIG_KOR_NM/FULL_NM 필드와 데이터의 시도·시군구 명칭을 확인해 주세요."
    )
elif info.get("unmatched"):
    with st.expander(f"경계 데이터와 이름이 달라 연결되지 않은 지역 {len(info['unmatched'])}곳 확인"):
        st.caption(
            "일부 지역은 행정구역 개편 또는 명칭 차이 때문에 현재 GeoJSON과 연결되지 않을 수 있습니다. "
            "아래 지역의 경계가 GeoJSON에 없는 경우 최신 시군구 경계 파일이 필요합니다."
        )
        st.write(" · ".join(info["unmatched"][:80]))

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
