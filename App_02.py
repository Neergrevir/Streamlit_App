import re
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pydeck as pdk
import plotly.express as px
import streamlit as st


st.set_page_config(
    page_title="서울시 공영주차장 정보 앱",
    page_icon="🅿️",
    layout="wide"
)


# =========================
# 기본 함수
# =========================

def read_uploaded_file(uploaded_file):
    """CSV, XLSX 파일 읽기"""
    file_name = uploaded_file.name.lower()

    if file_name.endswith(".csv"):
        encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
        last_error = None

        for enc in encodings:
            try:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, encoding=enc)
            except Exception as e:
                last_error = e

        raise last_error

    elif file_name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)

    else:
        raise ValueError("CSV 또는 Excel 파일만 업로드할 수 있습니다.")


def clean_columns(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def normalize_col_name(name):
    return str(name).lower().replace(" ", "").replace("_", "").replace("-", "")


def find_column(df, candidates):
    """후보 컬럼명 목록을 기준으로 실제 데이터 컬럼 자동 탐색"""
    normalized = {col: normalize_col_name(col) for col in df.columns}

    for candidate in candidates:
        target = normalize_col_name(candidate)

        for col, norm_col in normalized.items():
            if norm_col == target:
                return col

        for col, norm_col in normalized.items():
            if target in norm_col or norm_col in target:
                return col

    return None


def select_column(label, df, default_col=None):
    """자동 인식된 컬럼을 사용자가 수정할 수 있게 함"""
    options = ["선택 안 함"] + list(df.columns)

    if default_col in df.columns:
        index = options.index(default_col)
    else:
        index = 0

    selected = st.sidebar.selectbox(label, options, index=index)

    if selected == "선택 안 함":
        return None

    return selected


def extract_number(value):
    """문자열에서 숫자 추출"""
    if pd.isna(value):
        return np.nan

    text = str(value).replace(",", "")
    match = re.search(r"-?\d+(\.\d+)?", text)

    if match:
        return float(match.group())

    return np.nan


def parse_time_to_minutes(value):
    """
    09:00, 0900, 900, 9:00:00 같은 값을 분 단위로 변환
    """
    if pd.isna(value):
        return np.nan

    text = str(value).strip()

    if text == "":
        return np.nan

    text = text.replace("시", ":").replace("분", "")
    text = text.replace(".", ":")
    text = re.sub(r"\s+", "", text)

    # 09:00:00 같은 경우
    if ":" in text:
        parts = text.split(":")
        try:
            hour = int(float(parts[0]))
            minute = int(float(parts[1])) if len(parts) > 1 and parts[1] != "" else 0
        except:
            return np.nan
    else:
        text = re.sub(r"[^0-9]", "", text)

        if text == "":
            return np.nan

        try:
            if len(text) <= 2:
                hour = int(text)
                minute = 0
            elif len(text) == 3:
                hour = int(text[0])
                minute = int(text[1:])
            else:
                hour = int(text[:2])
                minute = int(text[2:4])
        except:
            return np.nan

    if hour == 24 and minute == 0:
        return 24 * 60

    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour * 60 + minute

    return np.nan


def minutes_to_time_text(minutes):
    if pd.isna(minutes):
        return "정보 없음"

    minutes = int(minutes)

    if minutes == 1440:
        return "24:00"

    hour = minutes // 60
    minute = minutes % 60

    return f"{hour:02d}:{minute:02d}"


def extract_district(address):
    """주소에서 서울시 자치구 추출"""
    if pd.isna(address):
        return "미상"

    text = str(address)

    match = re.search(r"([가-힣]+구)", text)

    if match:
        return match.group(1)

    return "미상"


def make_fee_type(fee_info, base_fee):
    """요금 정보를 무료/유료/미상으로 분류"""
    info = "" if pd.isna(fee_info) else str(fee_info)

    if "무료" in info:
        return "무료"

    if "유료" in info:
        return "유료"

    if pd.notna(base_fee):
        if base_fee == 0:
            return "무료"
        elif base_fee > 0:
            return "유료"

    return "미상"


def check_open_now(row, col_map):
    """현재 시각 기준 운영 여부 판단"""
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    weekday = now.weekday()
    current_minutes = now.hour * 60 + now.minute

    if weekday <= 4:
        start_col = col_map.get("weekday_start")
        end_col = col_map.get("weekday_end")
    elif weekday == 5:
        start_col = col_map.get("sat_start")
        end_col = col_map.get("sat_end")
    else:
        start_col = col_map.get("holiday_start")
        end_col = col_map.get("holiday_end")

    if not start_col or not end_col:
        return np.nan

    start = parse_time_to_minutes(row.get(start_col))
    end = parse_time_to_minutes(row.get(end_col))

    if pd.isna(start) or pd.isna(end):
        return np.nan

    # 00:00 ~ 00:00이면 24시간 운영으로 간주
    if start == 0 and end == 0:
        return True

    # 일반 운영
    if start <= end:
        return start <= current_minutes <= end

    # 자정 넘어가는 운영
    return current_minutes >= start or current_minutes <= end


def safe_unique_cols(cols):
    result = []
    for col in cols:
        if col and col not in result:
            result.append(col)
    return result


# =========================
# 화면 구성
# =========================

st.title("🅿️ 서울시 공영주차장 정보 시각화 앱")
st.write(
    "CSV 또는 Excel 파일을 업로드하면 공영주차장의 위치, 운영시간, 요금 정보를 지도와 그래프로 확인할 수 있습니다."
)

with st.expander("📌 사용 가능한 데이터 예시 컬럼"):
    st.write(
        """
        서울시 공영주차장 데이터에 다음과 비슷한 컬럼이 있으면 자동으로 인식합니다.

        - 주차장명
        - 주소
        - 위도
        - 경도
        - 주차장유형
        - 운영요일
        - 평일운영시작시각 / 평일운영종료시각
        - 토요일운영시작시각 / 토요일운영종료시각
        - 공휴일운영시작시각 / 공휴일운영종료시각
        - 요금정보
        - 주차기본시간
        - 주차기본요금
        - 추가단위시간
        - 추가단위요금
        - 1일주차권요금
        - 월정기권요금
        - 전화번호
        """
    )

uploaded_file = st.file_uploader(
    "서울시 공영주차장 데이터 파일을 업로드하세요",
    type=["csv", "xlsx", "xls"]
)


if uploaded_file is None:
    st.info("왼쪽 또는 위의 업로드 영역에 CSV 또는 Excel 파일을 업로드해주세요.")
    st.stop()


try:
    df = read_uploaded_file(uploaded_file)
    df = clean_columns(df)
except Exception as e:
    st.error(f"파일을 읽는 중 오류가 발생했습니다: {e}")
    st.stop()


if df.empty:
    st.warning("업로드한 파일에 데이터가 없습니다.")
    st.stop()


# =========================
# 컬럼 자동 인식
# =========================

auto_cols = {
    "name": find_column(df, ["주차장명", "주차장 이름", "주차장명칭", "공영주차장명", "시설명"]),
    "address": find_column(df, ["주소", "소재지도로명주소", "소재지지번주소", "도로명주소", "지번주소", "위치"]),
    "lat": find_column(df, ["위도", "latitude", "lat", "y좌표", "y", "위도(wgs84)"]),
    "lon": find_column(df, ["경도", "longitude", "lng", "lon", "x좌표", "x", "경도(wgs84)"]),
    "parking_type": find_column(df, ["주차장유형", "주차장구분", "주차장 종류", "유형", "구분"]),
    "operation_day": find_column(df, ["운영요일", "운영일", "운영 요일"]),
    "fee_info": find_column(df, ["요금정보", "요금 정보", "유무료구분", "유료무료", "요금구분"]),
    "base_time": find_column(df, ["주차기본시간", "기본시간", "기본 주차 시간"]),
    "base_fee": find_column(df, ["주차기본요금", "기본요금", "기본 주차 요금"]),
    "extra_time": find_column(df, ["추가단위시간", "추가시간", "추가 단위 시간"]),
    "extra_fee": find_column(df, ["추가단위요금", "추가요금", "추가 단위 요금"]),
    "day_fee": find_column(df, ["1일주차권요금", "일주차권요금", "일일요금", "1일 요금"]),
    "month_fee": find_column(df, ["월정기권요금", "월정기요금", "월정기권", "월 요금"]),
    "phone": find_column(df, ["전화번호", "연락처", "문의전화"]),
    "weekday_start": find_column(df, ["평일운영시작시각", "평일운영시작시간", "평일 시작", "평일시작"]),
    "weekday_end": find_column(df, ["평일운영종료시각", "평일운영종료시간", "평일 종료", "평일종료"]),
    "sat_start": find_column(df, ["토요일운영시작시각", "토요일운영시작시간", "토요일 시작", "토요일시작"]),
    "sat_end": find_column(df, ["토요일운영종료시각", "토요일운영종료시간", "토요일 종료", "토요일종료"]),
    "holiday_start": find_column(df, ["공휴일운영시작시각", "공휴일운영시작시간", "공휴일 시작", "공휴일시작"]),
    "holiday_end": find_column(df, ["공휴일운영종료시각", "공휴일운영종료시간", "공휴일 종료", "공휴일종료"]),
}


st.sidebar.header("⚙️ 컬럼 설정")

with st.sidebar.expander("자동 인식 컬럼 확인 / 수정", expanded=False):
    col_map = {
        "name": select_column("주차장명 컬럼", df, auto_cols["name"]),
        "address": select_column("주소 컬럼", df, auto_cols["address"]),
        "lat": select_column("위도 컬럼", df, auto_cols["lat"]),
        "lon": select_column("경도 컬럼", df, auto_cols["lon"]),
        "parking_type": select_column("주차장 유형 컬럼", df, auto_cols["parking_type"]),
        "operation_day": select_column("운영요일 컬럼", df, auto_cols["operation_day"]),
        "fee_info": select_column("요금정보 컬럼", df, auto_cols["fee_info"]),
        "base_time": select_column("기본시간 컬럼", df, auto_cols["base_time"]),
        "base_fee": select_column("기본요금 컬럼", df, auto_cols["base_fee"]),
        "extra_time": select_column("추가단위시간 컬럼", df, auto_cols["extra_time"]),
        "extra_fee": select_column("추가단위요금 컬럼", df, auto_cols["extra_fee"]),
        "day_fee": select_column("1일주차권요금 컬럼", df, auto_cols["day_fee"]),
        "month_fee": select_column("월정기권요금 컬럼", df, auto_cols["month_fee"]),
        "phone": select_column("전화번호 컬럼", df, auto_cols["phone"]),
        "weekday_start": select_column("평일 시작시각 컬럼", df, auto_cols["weekday_start"]),
        "weekday_end": select_column("평일 종료시각 컬럼", df, auto_cols["weekday_end"]),
        "sat_start": select_column("토요일 시작시각 컬럼", df, auto_cols["sat_start"]),
        "sat_end": select_column("토요일 종료시각 컬럼", df, auto_cols["sat_end"]),
        "holiday_start": select_column("공휴일 시작시각 컬럼", df, auto_cols["holiday_start"]),
        "holiday_end": select_column("공휴일 종료시각 컬럼", df, auto_cols["holiday_end"]),
    }


# =========================
# 분석용 데이터 생성
# =========================

data = df.copy()

if col_map["name"]:
    data["_name"] = data[col_map["name"]].astype(str)
else:
    data["_name"] = "주차장 " + (data.index + 1).astype(str)

if col_map["address"]:
    data["_address"] = data[col_map["address"]].astype(str)
else:
    data["_address"] = "주소 정보 없음"

data["_district"] = data["_address"].apply(extract_district)

if col_map["lat"]:
    data["_lat"] = data[col_map["lat"]].apply(extract_number)
else:
    data["_lat"] = np.nan

if col_map["lon"]:
    data["_lon"] = data[col_map["lon"]].apply(extract_number)
else:
    data["_lon"] = np.nan

if col_map["parking_type"]:
    data["_parking_type"] = data[col_map["parking_type"]].fillna("미상").astype(str)
else:
    data["_parking_type"] = "미상"

if col_map["fee_info"]:
    data["_fee_info"] = data[col_map["fee_info"]].fillna("정보 없음").astype(str)
else:
    data["_fee_info"] = "정보 없음"

if col_map["base_fee"]:
    data["_base_fee"] = data[col_map["base_fee"]].apply(extract_number)
else:
    data["_base_fee"] = np.nan

if col_map["base_time"]:
    data["_base_time"] = data[col_map["base_time"]].apply(extract_number)
else:
    data["_base_time"] = np.nan

if col_map["extra_fee"]:
    data["_extra_fee"] = data[col_map["extra_fee"]].apply(extract_number)
else:
    data["_extra_fee"] = np.nan

if col_map["day_fee"]:
    data["_day_fee"] = data[col_map["day_fee"]].apply(extract_number)
else:
    data["_day_fee"] = np.nan

if col_map["month_fee"]:
    data["_month_fee"] = data[col_map["month_fee"]].apply(extract_number)
else:
    data["_month_fee"] = np.nan

data["_fee_type"] = data.apply(
    lambda row: make_fee_type(row["_fee_info"], row["_base_fee"]),
    axis=1
)

data["_open_now"] = data.apply(
    lambda row: check_open_now(row, col_map),
    axis=1
)

data["_open_now_text"] = data["_open_now"].map(
    {
        True: "운영 중",
        False: "운영 종료"
    }
).fillna("판단 불가")


# =========================
# 사이드바 필터
# =========================

st.sidebar.header("🔎 필터")

keyword = st.sidebar.text_input("주차장명 또는 주소 검색")

district_options = sorted([x for x in data["_district"].dropna().unique() if x != "미상"])
selected_districts = st.sidebar.multiselect("자치구 선택", district_options)

type_options = sorted(data["_parking_type"].dropna().unique())
selected_types = st.sidebar.multiselect("주차장 유형 선택", type_options)

fee_type_options = sorted(data["_fee_type"].dropna().unique())
selected_fee_types = st.sidebar.multiselect("요금 유형 선택", fee_type_options)

open_only = st.sidebar.checkbox("현재 운영 중인 주차장만 보기")

fee_available = data["_base_fee"].notna().any()

if fee_available:
    min_fee = int(data["_base_fee"].dropna().min())
    max_fee = int(data["_base_fee"].dropna().max())

    selected_fee_range = st.sidebar.slider(
        "기본요금 범위",
        min_value=min_fee,
        max_value=max_fee,
        value=(min_fee, max_fee),
        step=100 if max_fee >= 1000 else 10
    )
else:
    selected_fee_range = None


filtered = data.copy()

if keyword:
    keyword_mask = (
        filtered["_name"].str.contains(keyword, case=False, na=False)
        | filtered["_address"].str.contains(keyword, case=False, na=False)
    )
    filtered = filtered[keyword_mask]

if selected_districts:
    filtered = filtered[filtered["_district"].isin(selected_districts)]

if selected_types:
    filtered = filtered[filtered["_parking_type"].isin(selected_types)]

if selected_fee_types:
    filtered = filtered[filtered["_fee_type"].isin(selected_fee_types)]

if open_only:
    filtered = filtered[filtered["_open_now"] == True]

if selected_fee_range:
    low, high = selected_fee_range
    filtered = filtered[
        filtered["_base_fee"].isna()
        | filtered["_base_fee"].between(low, high)
    ]


# =========================
# 요약 지표
# =========================

st.subheader("📊 요약 정보")

col1, col2, col3, col4 = st.columns(4)

col1.metric("전체 데이터", f"{len(data):,}개")
col2.metric("필터 적용 결과", f"{len(filtered):,}개")
col3.metric("지도 표시 가능", f"{filtered[['_lat', '_lon']].dropna().shape[0]:,}개")

if filtered["_base_fee"].notna().any():
    avg_fee = filtered["_base_fee"].mean()
    col4.metric("평균 기본요금", f"{avg_fee:,.0f}원")
else:
    col4.metric("평균 기본요금", "정보 없음")


# =========================
# 탭
# =========================

tab1, tab2, tab3, tab4 = st.tabs(
    ["🗺️ 지도", "📈 시각화", "📋 상세 목록", "🧾 원본 데이터"]
)


# =========================
# 지도 탭
# =========================

with tab1:
    st.subheader("주차장 위치 지도")

    map_data = filtered.dropna(subset=["_lat", "_lon"]).copy()

    # 서울 밖 이상치 제거
    map_data = map_data[
        map_data["_lat"].between(37.0, 38.0)
        & map_data["_lon"].between(126.0, 128.0)
    ]

    if map_data.empty:
        st.warning("지도에 표시할 수 있는 위도/경도 데이터가 없습니다.")
        st.write("데이터에 위도, 경도 컬럼이 있는지 확인해주세요.")
    else:
        map_data["lat"] = map_data["_lat"]
        map_data["lon"] = map_data["_lon"]
        map_data["name"] = map_data["_name"]
        map_data["address"] = map_data["_address"]
        map_data["district"] = map_data["_district"]
        map_data["fee_type"] = map_data["_fee_type"]
        map_data["base_fee_text"] = map_data["_base_fee"].apply(
            lambda x: "정보 없음" if pd.isna(x) else f"{int(x):,}원"
        )
        map_data["open_text"] = map_data["_open_now_text"]

        center_lat = map_data["lat"].mean()
        center_lon = map_data["lon"].mean()

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_data,
            get_position="[lon, lat]",
            get_radius=80,
            pickable=True,
            opacity=0.75,
            stroked=True,
            filled=True,
            line_width_min_pixels=1,
        )

        view_state = pdk.ViewState(
            latitude=center_lat,
            longitude=center_lon,
            zoom=11,
            pitch=0,
        )

        tooltip = {
            "html": """
            <b>{name}</b><br/>
            자치구: {district}<br/>
            주소: {address}<br/>
            요금 유형: {fee_type}<br/>
            기본요금: {base_fee_text}<br/>
            현재 상태: {open_text}
            """,
            "style": {
                "backgroundColor": "white",
                "color": "black"
            }
        }

        st.pydeck_chart(
            pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip=tooltip,
            )
        )

        st.caption("지도 위 점에 마우스를 올리면 주차장명, 주소, 요금 정보를 확인할 수 있습니다.")


# =========================
# 시각화 탭
# =========================

with tab2:
    st.subheader("공영주차장 데이터 시각화")

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        district_count = (
            filtered.groupby("_district")
            .size()
            .reset_index(name="주차장 수")
            .sort_values("주차장 수", ascending=False)
        )

        district_count = district_count[district_count["_district"] != "미상"]

        if district_count.empty:
            st.info("자치구별 시각화를 만들 주소 데이터가 부족합니다.")
        else:
            fig = px.bar(
                district_count,
                x="_district",
                y="주차장 수",
                title="자치구별 공영주차장 수",
                labels={"_district": "자치구"}
            )
            st.plotly_chart(fig, use_container_width=True)

    with chart_col2:
        fee_count = (
            filtered.groupby("_fee_type")
            .size()
            .reset_index(name="개수")
            .sort_values("개수", ascending=False)
        )

        if fee_count.empty:
            st.info("요금 유형 데이터가 부족합니다.")
        else:
            fig = px.pie(
                fee_count,
                names="_fee_type",
                values="개수",
                title="유료/무료 주차장 비율"
            )
            st.plotly_chart(fig, use_container_width=True)

    chart_col3, chart_col4 = st.columns(2)

    with chart_col3:
        type_count = (
            filtered.groupby("_parking_type")
            .size()
            .reset_index(name="개수")
            .sort_values("개수", ascending=False)
        )

        if type_count.empty:
            st.info("주차장 유형 데이터가 부족합니다.")
        else:
            fig = px.bar(
                type_count,
                x="_parking_type",
                y="개수",
                title="주차장 유형별 개수",
                labels={"_parking_type": "주차장 유형"}
            )
            st.plotly_chart(fig, use_container_width=True)

    with chart_col4:
        fee_data = filtered[filtered["_base_fee"].notna()].copy()

        if fee_data.empty:
            st.info("기본요금 분포를 그릴 수 있는 데이터가 없습니다.")
        else:
            fig = px.histogram(
                fee_data,
                x="_base_fee",
                nbins=20,
                title="기본요금 분포",
                labels={"_base_fee": "기본요금"}
            )
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader("운영 시작 시간 분포")

    if col_map["weekday_start"]:
        time_df = filtered.copy()
        time_df["_weekday_start_min"] = time_df[col_map["weekday_start"]].apply(parse_time_to_minutes)
        time_df = time_df[time_df["_weekday_start_min"].notna()]
        time_df["_start_hour"] = (time_df["_weekday_start_min"] // 60).astype(int)

        if time_df.empty:
            st.info("운영 시작 시간 데이터를 시각화할 수 없습니다.")
        else:
            hour_count = (
                time_df.groupby("_start_hour")
                .size()
                .reset_index(name="주차장 수")
                .sort_values("_start_hour")
            )

            hour_count["운영 시작 시간"] = hour_count["_start_hour"].apply(lambda x: f"{x:02d}:00")

            fig = px.bar(
                hour_count,
                x="운영 시작 시간",
                y="주차장 수",
                title="평일 운영 시작 시간 분포"
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("평일 운영 시작시각 컬럼이 없어 시간 분포를 만들 수 없습니다.")


# =========================
# 상세 목록 탭
# =========================

with tab3:
    st.subheader("상세 목록")

    show_df = filtered.copy()

    show_df["자치구"] = show_df["_district"]
    show_df["현재 운영 여부"] = show_df["_open_now_text"]
    show_df["요금 유형"] = show_df["_fee_type"]
    show_df["기본요금"] = show_df["_base_fee"].apply(
        lambda x: "정보 없음" if pd.isna(x) else f"{int(x):,}원"
    )

    display_cols = safe_unique_cols([
        col_map["name"],
        "자치구",
        col_map["address"],
        col_map["parking_type"],
        col_map["operation_day"],
        "현재 운영 여부",
        col_map["fee_info"],
        col_map["base_time"],
        "기본요금",
        col_map["extra_time"],
        col_map["extra_fee"],
        col_map["day_fee"],
        col_map["month_fee"],
        col_map["phone"],
    ])

    display_cols = [c for c in display_cols if c in show_df.columns]

    if not display_cols:
        st.dataframe(show_df, use_container_width=True)
    else:
        st.dataframe(show_df[display_cols], use_container_width=True)

    csv = show_df.to_csv(index=False, encoding="utf-8-sig")

    st.download_button(
        label="필터링된 데이터 CSV 다운로드",
        data=csv,
        file_name="filtered_parking_data.csv",
        mime="text/csv"
    )


# =========================
# 원본 데이터 탭
# =========================

with tab4:
    st.subheader("업로드한 원본 데이터")
    st.dataframe(df, use_container_width=True)

    st.write("컬럼 목록")
    st.write(list(df.columns))
