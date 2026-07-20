from __future__ import annotations

import html
import math
import re
import time
from datetime import datetime, time as dt_time, timedelta
from typing import Any, Iterable, Optional, Sequence
from urllib.parse import quote, unquote

import folium
import numpy as np
import pandas as pd
import requests
import streamlit as st
from folium.features import DivIcon
from streamlit_folium import st_folium


# -----------------------------------------------------------------------------
# 기본 설정과 상수
# -----------------------------------------------------------------------------
BASE_URL = "https://apis.data.go.kr/B551011/KorService2"
MOBILE_OS = "ETC"
MOBILE_APP = "TravelRouteApp"
CACHE_TTL_SECONDS = 60 * 60
LONG_CACHE_TTL_SECONDS = 60 * 60 * 24
REQUEST_TIMEOUT = (5, 20)
MAX_RETRIES = 2
MAX_AREA_PAGES = 5
ROWS_PER_PAGE = 100
DETAIL_ENRICHMENT_LIMIT = 18

TRIP_DAYS = {
    "당일치기": 1,
    "1박 2일": 2,
    "2박 3일": 3,
}

TRANSPORT_SPEED_KMH = {
    "도보": 4.0,
    "대중교통": 20.0,
    "자동차": 35.0,
}

DEFAULT_MAX_DISTANCE_KM = {
    "도보": 3,
    "대중교통": 10,
    "자동차": 25,
}

CONTENT_TYPE_NAMES = {
    "12": "관광지",
    "14": "문화시설",
    "15": "축제·행사",
    "25": "여행코스",
    "28": "레포츠",
    "32": "숙박",
    "38": "쇼핑",
    "39": "음식점",
}

DWELL_MINUTES_BY_TYPE = {
    "12": 90,
    "14": 90,
    "15": 120,
    "25": 90,
    "28": 120,
    "32": 60,
    "38": 60,
    "39": 60,
}

BASE_TAGS_BY_TYPE = {
    "12": {"자연", "사진 명소", "휴식"},
    "14": {"역사·문화", "전시·공연", "사진 명소"},
    "15": {"체험", "전시·공연", "사진 명소"},
    "25": {"자연", "역사·문화", "체험", "사진 명소"},
    "28": {"자연", "체험", "사진 명소"},
    "32": {"휴식"},
    "38": {"쇼핑", "음식"},
    "39": {"음식"},
}

PREFERENCE_KEYWORDS = {
    "자연": ("산", "숲", "공원", "해변", "바다", "계곡", "폭포", "수목원", "생태", "호수", "섬", "정원"),
    "역사·문화": ("궁", "성", "사찰", "절", "유적", "역사", "문화재", "한옥", "박물관", "기념관", "전통"),
    "체험": ("체험", "공방", "농장", "테마", "레저", "액티비티", "케이블카", "놀이"),
    "전시·공연": ("미술관", "박물관", "전시", "공연", "극장", "아트", "갤러리", "문화센터"),
    "사진 명소": ("전망", "야경", "포토", "벽화", "정원", "해변", "꽃", "수목원", "랜드마크"),
    "휴식": ("휴양", "온천", "스파", "정원", "공원", "산책", "숲", "힐링", "해변"),
    "쇼핑": ("시장", "쇼핑", "상가", "몰", "거리", "특산물", "아울렛"),
    "음식": ("음식", "맛집", "식당", "카페", "시장", "먹거리", "향토"),
}

COMPANION_PREFERENCE = {
    "혼자": {"역사·문화", "전시·공연", "사진 명소", "휴식"},
    "친구": {"체험", "사진 명소", "쇼핑", "음식"},
    "연인": {"사진 명소", "휴식", "전시·공연", "음식"},
    "가족": {"자연", "역사·문화", "체험", "휴식"},
    "어린이 동반": {"체험", "자연", "전시·공연"},
    "부모님 동반": {"역사·문화", "자연", "휴식", "음식"},
}

PROVINCE_ALIASES = {
    "서울": "서울특별시",
    "부산": "부산광역시",
    "대구": "대구광역시",
    "인천": "인천광역시",
    "광주": "광주광역시",
    "대전": "대전광역시",
    "울산": "울산광역시",
    "세종": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도",
    "충북": "충청북도",
    "충남": "충청남도",
    "전북": "전북특별자치도",
    "전남": "전라남도",
    "경북": "경상북도",
    "경남": "경상남도",
    "제주": "제주특별자치도",
}

DAY_COLORS = ["#2563eb", "#16a34a", "#ea580c"]


# -----------------------------------------------------------------------------
# 예외와 공통 유틸리티
# -----------------------------------------------------------------------------
class TourAPIError(RuntimeError):
    """관광공사 API 요청 중 사용자가 조치할 수 있는 오류를 나타낸다."""

    def __init__(self, user_message: str, technical_message: str = "") -> None:
        super().__init__(technical_message or user_message)
        self.user_message = user_message
        self.technical_message = technical_message


def get_service_key() -> Optional[str]:
    """Streamlit Secrets에서 API 키를 안전하게 읽는다."""
    try:
        raw_key = str(st.secrets["KTO_API_KEY"]).strip()
    except (KeyError, FileNotFoundError):
        return None

    if not raw_key:
        return None

    # 인코딩 키를 그대로 requests.params에 넣으면 %가 다시 인코딩될 수 있으므로
    # 한 번 디코딩한 뒤 requests가 올바르게 URL 인코딩하도록 맡긴다.
    return unquote(raw_key)


def normalize_text(value: Any) -> str:
    """검색과 중복 판정을 위해 문자열을 단순화한다."""
    text = str(value or "").strip().lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^0-9a-z가-힣]+", "", text)
    return text


def strip_html(value: Any) -> str:
    """API가 제공하는 HTML 문자열을 일반 텍스트로 변환한다."""
    text = str(value or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def extract_first_url(value: Any) -> str:
    """HTML 또는 일반 문자열에서 첫 번째 HTTP URL을 추출한다."""
    text = html.unescape(str(value or ""))
    match = re.search(r"https?://[^\s\"'<>]+", text)
    return match.group(0).rstrip(".,)") if match else ""


def safe_float(value: Any) -> Optional[float]:
    """좌표 문자열을 float로 변환하고 실패하면 None을 반환한다."""
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass
    return None


def first_nonempty(mapping: dict[str, Any], keys: Sequence[str]) -> str:
    """여러 후보 필드 중 비어 있지 않은 첫 값을 반환한다."""
    for key in keys:
        value = str(mapping.get(key, "") or "").strip()
        if value:
            return value
    return ""


def canonicalize_region_query(query: str) -> str:
    """서울, 경기 같은 짧은 시도 이름을 공식 명칭과 함께 검색되게 만든다."""
    compact = re.sub(r"\s+", " ", query.strip())
    tokens = compact.split()
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if token in PROVINCE_ALIASES:
            expanded.append(PROVINCE_ALIASES[token])
    return " ".join(dict.fromkeys(expanded))


def as_params_tuple(params: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """캐시 가능한 정렬 튜플로 요청 파라미터를 변환한다."""
    return tuple(
        sorted(
            (str(key), str(value))
            for key, value in params.items()
            if value is not None and str(value) != ""
        )
    )


def parse_provider_error_text(text: str) -> str:
    """JSON 대신 XML로 반환된 공공데이터포털 오류 메시지를 간단히 추출한다."""
    candidates = [
        r"<returnAuthMsg>(.*?)</returnAuthMsg>",
        r"<errMsg>(.*?)</errMsg>",
        r"<returnReasonCode>(.*?)</returnReasonCode>",
    ]
    messages = []
    for pattern in candidates:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            messages.append(strip_html(match.group(1)))
    return " / ".join(dict.fromkeys(messages))


def api_error_message(code: str, message: str) -> str:
    """공공데이터포털 응답코드를 사용자가 이해하기 쉬운 문장으로 바꾼다."""
    code_map = {
        "01": "API 서버에서 처리 오류가 발생했습니다.",
        "02": "필수 요청값이 누락되었거나 잘못되었습니다.",
        "10": "요청 파라미터가 올바르지 않습니다.",
        "20": "현재 서비스 접근이 제한되어 있습니다.",
        "22": "API 일일 호출 한도를 초과했습니다.",
        "30": "API 키가 등록되지 않았거나 사용할 수 없습니다.",
        "31": "API 키 사용 기간이 만료되었습니다.",
        "32": "등록되지 않은 IP에서 요청했습니다.",
        "99": "API 제공기관에서 알 수 없는 오류를 반환했습니다.",
    }
    base = code_map.get(code, "한국관광공사 API 요청을 처리하지 못했습니다.")
    clean_message = strip_html(message)
    return f"{base} ({clean_message})" if clean_message else base


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def request_tour_api(
    endpoint: str,
    _service_key: str,
    params_tuple: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    """TourAPI를 호출하고 공통 응답·오류 구조를 검증한다.

    `_service_key`처럼 밑줄로 시작하는 인수는 Streamlit 캐시 해시에서 제외된다.
    따라서 API 키가 캐시 키나 사용자 화면에 노출되지 않는다.
    """
    url = f"{BASE_URL}/{endpoint}"
    query: dict[str, Any] = {
        "serviceKey": _service_key,
        "MobileOS": MOBILE_OS,
        "MobileApp": MOBILE_APP,
        "_type": "json",
    }
    query.update(dict(params_tuple))

    last_error: Optional[Exception] = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.get(url, params=query, timeout=REQUEST_TIMEOUT)

            if response.status_code == 429:
                raise TourAPIError("API 호출 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.")

            if response.status_code >= 500:
                raise requests.HTTPError(f"서버 오류: HTTP {response.status_code}")

            if response.status_code >= 400:
                raise TourAPIError(
                    "API 요청이 거부되었습니다. 활용 신청 상태와 요청값을 확인해 주세요.",
                    f"HTTP {response.status_code}",
                )

            try:
                payload = response.json()
            except ValueError as exc:
                provider_message = parse_provider_error_text(response.text)
                if provider_message:
                    raise TourAPIError(
                        "API 인증 또는 요청 형식에 문제가 있습니다. API 키와 활용 신청 상태를 확인해 주세요.",
                        provider_message,
                    ) from exc
                raise TourAPIError(
                    "API가 JSON이 아닌 응답을 반환했습니다. 잠시 후 다시 시도해 주세요.",
                    "JSON 파싱 실패",
                ) from exc

            # 공공데이터포털 인증 오류가 별도 구조로 반환되는 경우
            service_error = payload.get("OpenAPI_ServiceResponse", {})
            if isinstance(service_error, dict) and service_error:
                header = service_error.get("cmmMsgHeader", {})
                err_msg = first_nonempty(
                    header if isinstance(header, dict) else {},
                    ["errMsg", "returnAuthMsg", "returnReasonCode"],
                )
                raise TourAPIError(
                    "API 키가 유효하지 않거나 활용 신청이 완료되지 않았습니다.",
                    err_msg,
                )

            # 일부 오류는 최상위 resultCode/resultMsg로 반환된다.
            top_code = str(payload.get("resultCode", "") or "")
            if top_code and top_code not in {"0000", "00", "03"}:
                top_message = str(payload.get("resultMsg", "") or "")
                raise TourAPIError(api_error_message(top_code, top_message), top_message)

            response_root = payload.get("response", {})
            if not isinstance(response_root, dict):
                raise TourAPIError(
                    "API 응답 형식을 확인할 수 없습니다.",
                    "response 객체가 없음",
                )

            header = response_root.get("header", {})
            if isinstance(header, dict):
                result_code = str(header.get("resultCode", "") or "")
                result_message = str(header.get("resultMsg", "") or "")
                # 03은 검색 결과 없음으로 처리한다.
                if result_code and result_code not in {"0000", "00", "03"}:
                    raise TourAPIError(
                        api_error_message(result_code, result_message),
                        result_message,
                    )

            return payload

        except TourAPIError:
            raise
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(0.7 * (2**attempt))
                continue
        except requests.RequestException as exc:
            last_error = exc
            break

    raise TourAPIError(
        "한국관광공사 API에 연결하지 못했습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.",
        str(last_error or "연결 실패"),
    )


def extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """response.body.items.item을 리스트와 단일 딕셔너리 모두 안전하게 처리한다."""
    response_root = payload.get("response", {})
    if not isinstance(response_root, dict):
        return []
    body = response_root.get("body", {})
    if not isinstance(body, dict):
        return []
    items = body.get("items", {})
    if not items or not isinstance(items, dict):
        return []
    item = items.get("item", [])
    if isinstance(item, list):
        return [row for row in item if isinstance(row, dict)]
    if isinstance(item, dict):
        return [item]
    return []


def extract_total_count(payload: dict[str, Any]) -> int:
    """API 응답의 전체 결과 수를 정수로 반환한다."""
    try:
        return int(payload["response"]["body"].get("totalCount", 0))
    except (KeyError, TypeError, ValueError):
        return 0


# -----------------------------------------------------------------------------
# TourAPI 세부 조회 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=LONG_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_all_legal_dong_rows(_service_key: str) -> list[dict[str, Any]]:
    """법정동 시도·시군구 전체 목록을 페이지 단위로 조회한다."""
    all_rows: list[dict[str, Any]] = []
    page = 1
    page_size = 1000

    while page <= 10:
        payload = request_tour_api(
            "ldongCode2",
            _service_key,
            as_params_tuple(
                {
                    "pageNo": page,
                    "numOfRows": page_size,
                    "lDongListYn": "Y",
                }
            ),
        )
        rows = extract_items(payload)
        all_rows.extend(rows)
        total_count = extract_total_count(payload)

        if not rows or len(all_rows) >= total_count or len(rows) < page_size:
            break
        page += 1

    return all_rows


def region_match_score(query: str, row: dict[str, Any]) -> float:
    """사용자 지역 문자열과 법정동 코드 행의 유사도를 간단한 규칙으로 계산한다."""
    province = str(row.get("lDongRegnNm", "") or row.get("region_name", "")).strip()
    district = str(row.get("lDongSignguNm", "") or row.get("district_name", "")).strip()
    label = f"{province} {district}".strip()
    normalized_label = normalize_text(label)

    original_tokens = [token for token in re.split(r"\s+", query.strip()) if token]
    expanded_query = canonicalize_region_query(query)
    expanded_tokens = [token for token in re.split(r"\s+", expanded_query) if token]

    score = 0.0
    for token in dict.fromkeys(original_tokens + expanded_tokens):
        normalized_token = normalize_text(token)
        if not normalized_token:
            continue
        if normalized_token in normalized_label:
            score += 2.0
        if normalize_text(district) == normalized_token:
            score += 4.0
        if normalize_text(province) == normalized_token:
            score += 3.0

    if normalize_text(query) == normalized_label:
        score += 10.0
    if district and normalize_text(query) == normalize_text(district):
        score += 8.0
    if not district and any(
        normalize_text(alias) in normalize_text(query)
        for alias in (province, *[key for key, value in PROVINCE_ALIASES.items() if value == province])
        if alias
    ):
        score += 5.0

    return score


def search_legal_dong_codes(region_query: str, service_key: str) -> list[dict[str, str]]:
    """자연어 지역명과 일치하는 법정동 시도·시군구 코드를 반환한다."""
    rows = fetch_all_legal_dong_rows(service_key)
    candidates: list[dict[str, Any]] = []

    for row in rows:
        region_code = first_nonempty(row, ["lDongRegnCd", "regionCode", "code"])
        province = first_nonempty(row, ["lDongRegnNm", "regionName", "name"])
        district_code = first_nonempty(row, ["lDongSignguCd", "districtCode"])
        district = first_nonempty(row, ["lDongSignguNm", "districtName"])

        # lDongListYn=Y 응답이 아닌 계층형 응답은 지역명이 불완전할 수 있으므로 제외한다.
        if not region_code or not province:
            continue

        score = region_match_score(
            region_query,
            {
                "lDongRegnNm": province,
                "lDongSignguNm": district,
            },
        )
        if score <= 0:
            continue

        candidates.append(
            {
                "region_code": region_code,
                "district_code": district_code,
                "province": province,
                "district": district,
                "label": f"{province} {district}".strip() if district else f"{province} 전체",
                "score": score,
            }
        )

    # 동일 코드 중복 제거 후 가장 일치하는 결과를 앞에 둔다.
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in candidates:
        key = (candidate["region_code"], candidate["district_code"])
        if key not in unique or candidate["score"] > unique[key]["score"]:
            unique[key] = candidate

    ordered = sorted(
        unique.values(),
        key=lambda item: (
            -float(item["score"]),
            0 if item["district"] else 1,
            item["label"],
        ),
    )
    return [
        {
            "region_code": str(item["region_code"]),
            "district_code": str(item["district_code"]),
            "province": str(item["province"]),
            "district": str(item["district"]),
            "label": str(item["label"]),
        }
        for item in ordered[:30]
    ]


@st.cache_data(ttl=LONG_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_classification_codes(_service_key: str) -> list[dict[str, Any]]:
    """신분류 대·중·소분류 코드 전체 목록을 조회한다."""
    rows: list[dict[str, Any]] = []
    page = 1
    page_size = 1000

    while page <= 10:
        payload = request_tour_api(
            "lclsSystmCode2",
            _service_key,
            as_params_tuple(
                {
                    "pageNo": page,
                    "numOfRows": page_size,
                    "lclsSystmListYn": "Y",
                }
            ),
        )
        current = extract_items(payload)
        rows.extend(current)
        total_count = extract_total_count(payload)
        if not current or len(rows) >= total_count or len(current) < page_size:
            break
        page += 1

    return rows


def build_classification_lookup(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str, str], str]:
    """신분류 코드 조합을 사람이 읽을 수 있는 이름으로 바꿀 조회표를 만든다."""
    lookup: dict[tuple[str, str, str], str] = {}
    for row in rows:
        code1 = first_nonempty(row, ["lclsSystm1Cd", "lclsSystm1"])
        code2 = first_nonempty(row, ["lclsSystm2Cd", "lclsSystm2"])
        code3 = first_nonempty(row, ["lclsSystm3Cd", "lclsSystm3"])
        names = [
            first_nonempty(row, ["lclsSystm1Nm"]),
            first_nonempty(row, ["lclsSystm2Nm"]),
            first_nonempty(row, ["lclsSystm3Nm"]),
        ]
        readable = " > ".join(name for name in names if name)
        if code1 and readable:
            lookup[(code1, code2, code3)] = readable
            if code3:
                lookup[(code1, code2, "")] = " > ".join(name for name in names[:2] if name)
            if code2:
                lookup[(code1, "", "")] = names[0]
    return lookup


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_area_attractions(
    region_code: str,
    district_code: str,
    _service_key: str,
    max_pages: int = MAX_AREA_PAGES,
) -> list[dict[str, Any]]:
    """법정동 코드를 사용하여 지역 기반 관광정보를 조회한다."""
    all_rows: list[dict[str, Any]] = []

    for page in range(1, max_pages + 1):
        params: dict[str, Any] = {
            "pageNo": page,
            "numOfRows": ROWS_PER_PAGE,
            "arrange": "A",
            "lDongRegnCd": region_code,
        }
        if district_code:
            params["lDongSignguCd"] = district_code

        payload = request_tour_api(
            "areaBasedList2",
            _service_key,
            as_params_tuple(params),
        )
        rows = extract_items(payload)
        all_rows.extend(rows)
        total_count = extract_total_count(payload)

        if not rows or len(all_rows) >= total_count or len(rows) < ROWS_PER_PAGE:
            break

    return all_rows


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_keyword_results(
    keyword: str,
    region_code: str,
    district_code: str,
    _service_key: str,
) -> list[dict[str, Any]]:
    """출발지 후보를 찾기 위해 지역 제한이 있는 키워드 검색을 수행한다."""
    params: dict[str, Any] = {
        "pageNo": 1,
        "numOfRows": 50,
        "arrange": "A",
        "keyword": keyword,
    }
    if region_code:
        params["lDongRegnCd"] = region_code
    if district_code:
        params["lDongSignguCd"] = district_code

    payload = request_tour_api(
        "searchKeyword2",
        _service_key,
        as_params_tuple(params),
    )
    return extract_items(payload)


@st.cache_data(ttl=LONG_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_detail_common(content_id: str, _service_key: str) -> dict[str, Any]:
    """선택된 관광지의 개요·홈페이지 등 공통 상세정보를 조회한다."""
    payload = request_tour_api(
        "detailCommon2",
        _service_key,
        as_params_tuple({"pageNo": 1, "numOfRows": 10, "contentId": content_id}),
    )
    items = extract_items(payload)
    return items[0] if items else {}


@st.cache_data(ttl=LONG_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_detail_intro(
    content_id: str,
    content_type_id: str,
    _service_key: str,
) -> dict[str, Any]:
    """선택된 관광지의 운영시간·휴무일 등 유형별 소개정보를 조회한다."""
    payload = request_tour_api(
        "detailIntro2",
        _service_key,
        as_params_tuple(
            {
                "pageNo": 1,
                "numOfRows": 10,
                "contentId": content_id,
                "contentTypeId": content_type_id,
            }
        ),
    )
    items = extract_items(payload)
    return items[0] if items else {}


@st.cache_data(ttl=LONG_CACHE_TTL_SECONDS, show_spinner=False)
def fetch_detail_images(content_id: str, _service_key: str) -> list[dict[str, Any]]:
    """선택된 관광지의 이미지 목록을 조회한다."""
    payload = request_tour_api(
        "detailImage2",
        _service_key,
        as_params_tuple({"pageNo": 1, "numOfRows": 20, "contentId": content_id}),
    )
    return extract_items(payload)


# -----------------------------------------------------------------------------
# 데이터 정제와 추천 점수
# -----------------------------------------------------------------------------
def classification_name_for_row(
    row: pd.Series,
    lookup: dict[tuple[str, str, str], str],
) -> str:
    """관광정보 행에 맞는 가장 구체적인 신분류 이름을 반환한다."""
    code1 = str(row.get("lclsSystm1", "") or "")
    code2 = str(row.get("lclsSystm2", "") or "")
    code3 = str(row.get("lclsSystm3", "") or "")
    return (
        lookup.get((code1, code2, code3))
        or lookup.get((code1, code2, ""))
        or lookup.get((code1, "", ""))
        or ""
    )


def clean_attraction_data(
    rows: Sequence[dict[str, Any]],
    classification_lookup: Optional[dict[tuple[str, str, str], str]] = None,
) -> pd.DataFrame:
    """TourAPI 목록 응답을 추천·지도 표시에 적합한 DataFrame으로 정제한다."""
    records: list[dict[str, Any]] = []
    classification_lookup = classification_lookup or {}

    for item in rows:
        title = str(item.get("title", "") or "").strip()
        content_id = str(item.get("contentid", "") or item.get("contentId", "")).strip()
        content_type_id = str(
            item.get("contenttypeid", "") or item.get("contentTypeId", "")
        ).strip()
        address = " ".join(
            part.strip()
            for part in [str(item.get("addr1", "") or ""), str(item.get("addr2", "") or "")]
            if part.strip()
        )
        latitude = safe_float(item.get("mapy"))
        longitude = safe_float(item.get("mapx"))

        if not title or not content_id or not address or latitude is None or longitude is None:
            continue
        if not (32.0 <= latitude <= 39.5 and 123.0 <= longitude <= 132.0):
            continue

        records.append(
            {
                "title": title,
                "content_id": content_id,
                "content_type_id": content_type_id,
                "type_name": CONTENT_TYPE_NAMES.get(content_type_id, "기타 관광정보"),
                "address": address,
                "phone": str(item.get("tel", "") or "").strip(),
                "latitude": latitude,
                "longitude": longitude,
                "image_url": str(
                    item.get("firstimage", "") or item.get("firstimage2", "") or ""
                ).strip(),
                "thumbnail_url": str(item.get("firstimage2", "") or "").strip(),
                "overview": strip_html(item.get("overview", "")),
                "homepage": extract_first_url(item.get("homepage", "")),
                "lDongRegnCd": str(item.get("lDongRegnCd", "") or ""),
                "lDongSignguCd": str(item.get("lDongSignguCd", "") or ""),
                "lclsSystm1": str(item.get("lclsSystm1", "") or ""),
                "lclsSystm2": str(item.get("lclsSystm2", "") or ""),
                "lclsSystm3": str(item.get("lclsSystm3", "") or ""),
                "modified_time": str(item.get("modifiedtime", "") or ""),
                "recommendation_score": 0.0,
                "classification_name": "",
                "operation_info": "",
                "rest_info": "",
            }
        )

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # 정보가 풍부한 행을 먼저 두고 content_id·거의 같은 좌표 중복을 제거한다.
    df["_quality"] = (
        df["image_url"].ne("").astype(int) * 3
        + df["phone"].ne("").astype(int)
        + df["address"].ne("").astype(int)
    )
    df = df.sort_values("_quality", ascending=False)
    df = df.drop_duplicates(subset=["content_id"], keep="first")
    df["_coord_key"] = (
        df["latitude"].round(5).astype(str) + "," + df["longitude"].round(5).astype(str)
    )
    df = df.drop_duplicates(subset=["_coord_key"], keep="first")

    if classification_lookup:
        df["classification_name"] = df.apply(
            classification_name_for_row,
            axis=1,
            lookup=classification_lookup,
        )

    return df.drop(columns=["_quality", "_coord_key"]).reset_index(drop=True)


def infer_tags(row: pd.Series) -> set[str]:
    """콘텐츠 유형·분류명·제목·개요에서 여행 취향 태그를 추론한다."""
    type_id = str(row.get("content_type_id", "") or "")
    tags = set(BASE_TAGS_BY_TYPE.get(type_id, set()))
    combined = " ".join(
        [
            str(row.get("title", "") or ""),
            str(row.get("classification_name", "") or ""),
            str(row.get("overview", "") or ""),
        ]
    )

    for preference, keywords in PREFERENCE_KEYWORDS.items():
        if any(keyword in combined for keyword in keywords):
            tags.add(preference)

    return tags


def calculate_haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """두 위경도 좌표 사이의 직선거리를 km 단위로 계산한다."""
    earth_radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return earth_radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_medoid_coordinate(df: pd.DataFrame) -> tuple[float, float]:
    """후보 관광지까지 거리 합이 가장 작은 실제 관광지 좌표를 반환한다."""
    if df.empty:
        raise ValueError("중심 좌표를 계산할 관광지가 없습니다.")

    points = df[["latitude", "longitude"]].to_numpy(dtype=float)
    if len(points) == 1:
        return float(points[0, 0]), float(points[0, 1])

    # 후보가 많아도 계산량을 제한하기 위해 최대 150개만 균등 추출한다.
    if len(points) > 150:
        indices = np.linspace(0, len(points) - 1, 150, dtype=int)
        sampled = points[indices]
    else:
        sampled = points

    sums: list[float] = []
    for lat, lon in sampled:
        total = sum(
            calculate_haversine_distance(lat, lon, other_lat, other_lon)
            for other_lat, other_lon in sampled
        )
        sums.append(total)

    best = sampled[int(np.argmin(sums))]
    return float(best[0]), float(best[1])


def calculate_recommendation_score(
    row: pd.Series,
    preferences: Sequence[str],
    companion: str,
    center: tuple[float, float],
    distance_reference_km: float,
) -> float:
    """사용자 취향·거리·정보 완성도에 따라 100점 만점 추천 점수를 계산한다."""
    tags = infer_tags(row)

    # 1) 취향 일치도: 40점
    if preferences:
        matched = len(tags.intersection(preferences))
        preference_score = 40.0 * min(1.0, matched / max(1, min(2, len(preferences))))
    else:
        preference_score = 24.0

    # 2) 출발점 또는 지역 중심과 거리: 20점
    distance = calculate_haversine_distance(
        center[0],
        center[1],
        float(row["latitude"]),
        float(row["longitude"]),
    )
    reference = max(3.0, distance_reference_km)
    distance_score = 20.0 * max(0.0, 1.0 - min(distance, reference) / reference)

    # 3) 이미지와 상세 설명: 15점
    media_score = 0.0
    if str(row.get("image_url", "") or ""):
        media_score += 7.5
    if str(row.get("overview", "") or ""):
        media_score += 7.5
    elif str(row.get("classification_name", "") or ""):
        media_score += 3.0

    # 4) 동행 유형: 15점
    preferred_tags = COMPANION_PREFERENCE.get(companion, set())
    companion_score = 15.0 * min(1.0, len(tags.intersection(preferred_tags)) / 2.0)
    if not preferred_tags:
        companion_score = 8.0

    # 5) 정보 완성도: 10점
    completeness_fields = [
        row.get("address", ""),
        row.get("phone", ""),
        row.get("classification_name", ""),
        row.get("homepage", ""),
        row.get("modified_time", ""),
    ]
    completeness_score = 10.0 * sum(bool(str(value or "").strip()) for value in completeness_fields) / len(
        completeness_fields
    )

    return round(
        min(
            100.0,
            preference_score
            + distance_score
            + media_score
            + companion_score
            + completeness_score,
        ),
        1,
    )


def apply_recommendation_scores(
    df: pd.DataFrame,
    preferences: Sequence[str],
    companion: str,
    center: tuple[float, float],
    distance_reference_km: float,
) -> pd.DataFrame:
    """모든 관광지 후보에 추천 점수를 계산한다."""
    scored = df.copy()
    scored["recommendation_score"] = scored.apply(
        calculate_recommendation_score,
        axis=1,
        preferences=preferences,
        companion=companion,
        center=center,
        distance_reference_km=distance_reference_km,
    )
    return scored.sort_values(
        ["recommendation_score", "image_url"],
        ascending=[False, False],
    ).reset_index(drop=True)


def choose_start_place(
    keyword_rows: Sequence[dict[str, Any]],
    keyword: str,
    classification_lookup: dict[tuple[str, str, str], str],
) -> Optional[dict[str, Any]]:
    """키워드 검색 결과 중 입력어와 가장 잘 맞는 출발지 후보를 고른다."""
    if not keyword_rows:
        return None
    df = clean_attraction_data(keyword_rows, classification_lookup)
    if df.empty:
        return None

    query_norm = normalize_text(keyword)
    df["_match"] = df.apply(
        lambda row: (
            10 if normalize_text(row["title"]) == query_norm else 0
        )
        + (5 if query_norm and query_norm in normalize_text(row["title"]) else 0)
        + (2 if query_norm and query_norm in normalize_text(row["address"]) else 0),
        axis=1,
    )
    best = df.sort_values(["_match", "image_url"], ascending=[False, False]).iloc[0]
    return {
        "title": str(best["title"]),
        "latitude": float(best["latitude"]),
        "longitude": float(best["longitude"]),
        "address": str(best["address"]),
        "content_id": str(best["content_id"]),
    }


# -----------------------------------------------------------------------------
# 관광지 선택과 경로 최적화
# -----------------------------------------------------------------------------
def route_total_distance(
    route: Sequence[dict[str, Any]],
    start_coordinate: tuple[float, float],
) -> float:
    """출발점에서 시작하는 열린 경로의 총 직선거리를 계산한다."""
    if not route:
        return 0.0

    total = calculate_haversine_distance(
        start_coordinate[0],
        start_coordinate[1],
        float(route[0]["latitude"]),
        float(route[0]["longitude"]),
    )
    for previous, current in zip(route, route[1:]):
        total += calculate_haversine_distance(
            float(previous["latitude"]),
            float(previous["longitude"]),
            float(current["latitude"]),
            float(current["longitude"]),
        )
    return total


def nearest_neighbor_route(
    candidates: pd.DataFrame,
    start_coordinate: tuple[float, float],
    target_count: int,
    max_leg_km: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    """추천 점수와 거리를 함께 고려한 최근접 이웃 경로를 만든다."""
    if candidates.empty or target_count <= 0:
        return [], []

    pool = candidates.head(max(target_count * 5, target_count)).to_dict("records")
    route: list[dict[str, Any]] = []
    warnings: list[str] = []
    current = start_coordinate

    while pool and len(route) < target_count:
        evaluated: list[tuple[float, float, dict[str, Any]]] = []
        for item in pool:
            distance = calculate_haversine_distance(
                current[0],
                current[1],
                float(item["latitude"]),
                float(item["longitude"]),
            )
            score_penalty = (100.0 - float(item.get("recommendation_score", 0))) / 100.0
            combined_cost = distance + score_penalty * max(1.0, max_leg_km * 0.45)
            evaluated.append((combined_cost, distance, item))

        within_limit = [entry for entry in evaluated if entry[1] <= max_leg_km * 1.25]
        if within_limit:
            chosen_cost, chosen_distance, chosen = min(within_limit, key=lambda entry: entry[0])
        else:
            chosen_cost, chosen_distance, chosen = min(evaluated, key=lambda entry: entry[1])
            warnings.append(
                f"‘{chosen['title']}’까지의 직선거리({chosen_distance:.1f}km)가 설정한 최대 이동거리보다 큽니다."
            )

        route.append(chosen)
        pool.remove(chosen)
        current = (float(chosen["latitude"]), float(chosen["longitude"]))

    return route, warnings


def apply_two_opt(
    route: Sequence[dict[str, Any]],
    start_coordinate: tuple[float, float],
    max_iterations: int = 60,
) -> list[dict[str, Any]]:
    """2-opt 알고리즘으로 열린 경로의 총 이동거리를 줄인다."""
    best = list(route)
    if len(best) < 4:
        return best

    best_distance = route_total_distance(best, start_coordinate)
    iteration = 0
    improved = True

    while improved and iteration < max_iterations:
        improved = False
        iteration += 1
        for i in range(0, len(best) - 2):
            for j in range(i + 2, len(best)):
                candidate = best[:i] + list(reversed(best[i:j])) + best[j:]
                candidate_distance = route_total_distance(candidate, start_coordinate)
                if candidate_distance + 1e-6 < best_distance:
                    best = candidate
                    best_distance = candidate_distance
                    improved = True
                    break
            if improved:
                break

    return best


def optimize_route(
    candidates: pd.DataFrame,
    start_coordinate: tuple[float, float],
    target_count: int,
    max_leg_km: float,
) -> tuple[pd.DataFrame, list[str]]:
    """추천 후보를 선택하고 최근접 이웃과 2-opt를 적용한다."""
    route, warnings = nearest_neighbor_route(
        candidates=candidates,
        start_coordinate=start_coordinate,
        target_count=target_count,
        max_leg_km=max_leg_km,
    )
    optimized = apply_two_opt(route, start_coordinate)
    return pd.DataFrame(optimized), warnings


def split_route_by_days(route_df: pd.DataFrame, days: int) -> list[pd.DataFrame]:
    """전체 관광지 경로를 날짜별로 가능한 한 균등하게 나눈다."""
    if route_df.empty:
        return [pd.DataFrame() for _ in range(days)]
    chunks = np.array_split(route_df.reset_index(drop=True), days)
    return [chunk.reset_index(drop=True) for chunk in chunks]


def choose_restaurant_for_day(
    restaurant_candidates: pd.DataFrame,
    day_route: pd.DataFrame,
    used_ids: set[str],
) -> Optional[pd.Series]:
    """해당 날짜 관광지 중심에 가장 가까운 미사용 음식점을 선택한다."""
    available = restaurant_candidates[
        ~restaurant_candidates["content_id"].astype(str).isin(used_ids)
    ].copy()
    if available.empty:
        return None

    if day_route.empty:
        center = find_medoid_coordinate(available)
    else:
        center = (
            float(day_route["latitude"].mean()),
            float(day_route["longitude"].mean()),
        )

    available["_day_distance"] = available.apply(
        lambda row: calculate_haversine_distance(
            center[0],
            center[1],
            float(row["latitude"]),
            float(row["longitude"]),
        ),
        axis=1,
    )
    available["_choice"] = (
        available["_day_distance"]
        + (100 - available["recommendation_score"]) / 100 * 2.0
    )
    return available.sort_values("_choice").iloc[0]


def insert_restaurant_near_lunch(
    route_df: pd.DataFrame,
    restaurant: Optional[pd.Series],
) -> pd.DataFrame:
    """음식점을 일정 중간 지점에 삽입해 점심 시간대에 도착하도록 유도한다."""
    if restaurant is None:
        return route_df.reset_index(drop=True)

    rows = route_df.to_dict("records")
    restaurant_record = restaurant.drop(labels=[key for key in restaurant.index if str(key).startswith("_")], errors="ignore").to_dict()
    insert_index = min(2, max(1, math.ceil(len(rows) / 2))) if rows else 0
    rows.insert(insert_index, restaurant_record)
    return pd.DataFrame(rows).reset_index(drop=True)


def select_attractions(
    scored_df: pd.DataFrame,
    days: int,
    visits_per_day: int,
    include_food: bool,
    start_coordinate: tuple[float, float],
    max_leg_km: float,
) -> tuple[list[pd.DataFrame], list[str], bool]:
    """기간과 음식점 포함 여부를 반영하여 날짜별 추천 경로를 만든다."""
    warnings: list[str] = []
    food_df = scored_df[scored_df["content_type_id"] == "39"].copy()
    main_df = scored_df[
        ~scored_df["content_type_id"].isin(["32", "39"])
    ].copy()

    food_slots = days if include_food else 0
    main_target = max(days, days * visits_per_day - food_slots)

    if len(main_df) < main_target:
        warnings.append(
            f"조건에 맞는 일반 관광지가 {len(main_df)}개뿐이라 요청한 {main_target}개를 모두 채우지 못했습니다."
        )
        main_target = len(main_df)

    global_route, route_warnings = optimize_route(
        candidates=main_df,
        start_coordinate=start_coordinate,
        target_count=main_target,
        max_leg_km=max_leg_km,
    )
    warnings.extend(route_warnings)
    day_routes = split_route_by_days(global_route, days)

    food_added = False
    used_restaurant_ids: set[str] = set()
    final_routes: list[pd.DataFrame] = []

    for day_route in day_routes:
        # 각 날짜는 동일한 출발 기준점에서 다시 2-opt를 적용한다.
        locally_optimized = pd.DataFrame(
            apply_two_opt(day_route.to_dict("records"), start_coordinate)
        )
        restaurant: Optional[pd.Series] = None
        if include_food:
            restaurant = choose_restaurant_for_day(food_df, locally_optimized, used_restaurant_ids)
            if restaurant is not None:
                used_restaurant_ids.add(str(restaurant["content_id"]))
                food_added = True
        final_routes.append(insert_restaurant_near_lunch(locally_optimized, restaurant))

    if include_food and not food_added:
        warnings.append("해당 지역에서 좌표가 있는 음식점 정보를 찾지 못해 음식점을 일정에 넣지 못했습니다.")

    return final_routes, list(dict.fromkeys(warnings)), food_added


# -----------------------------------------------------------------------------
# 상세정보 보강과 일정 계산
# -----------------------------------------------------------------------------
def merge_detail_into_record(
    record: dict[str, Any],
    common: dict[str, Any],
    intro: dict[str, Any],
    images: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """목록 정보에 공통·소개·이미지 상세정보를 병합한다."""
    merged = dict(record)

    overview = strip_html(common.get("overview", ""))
    homepage = extract_first_url(common.get("homepage", ""))
    phone = first_nonempty(common, ["tel", "telname"])
    image_url = first_nonempty(common, ["firstimage", "firstimage2"])

    if overview:
        merged["overview"] = overview
    if homepage:
        merged["homepage"] = homepage
    if phone and not merged.get("phone"):
        merged["phone"] = phone
    if image_url and not merged.get("image_url"):
        merged["image_url"] = image_url

    if not merged.get("image_url") and images:
        merged["image_url"] = first_nonempty(
            images[0], ["originimgurl", "smallimageurl"]
        )

    operation_fields = [
        "usetime",
        "usetimeculture",
        "usetimefestival",
        "usetimeleports",
        "opentime",
        "opentimefood",
        "checkintime",
    ]
    rest_fields = [
        "restdate",
        "restdateculture",
        "restdateleports",
        "restdatefood",
    ]
    merged["operation_info"] = strip_html(first_nonempty(intro, operation_fields))
    merged["rest_info"] = strip_html(first_nonempty(intro, rest_fields))
    return merged


def enrich_selected_attractions(
    day_routes: Sequence[pd.DataFrame],
    service_key: str,
) -> list[pd.DataFrame]:
    """최종 선택 관광지만 제한적으로 상세 조회하여 API 호출량을 줄인다."""
    enriched_routes: list[pd.DataFrame] = []
    enriched_count = 0

    for route_df in day_routes:
        enriched_records: list[dict[str, Any]] = []
        for record in route_df.to_dict("records"):
            if enriched_count >= DETAIL_ENRICHMENT_LIMIT:
                enriched_records.append(record)
                continue

            content_id = str(record.get("content_id", ""))
            content_type_id = str(record.get("content_type_id", ""))
            common: dict[str, Any] = {}
            intro: dict[str, Any] = {}
            images: list[dict[str, Any]] = []

            try:
                common = fetch_detail_common(content_id, service_key)
            except TourAPIError:
                common = {}

            if content_type_id:
                try:
                    intro = fetch_detail_intro(content_id, content_type_id, service_key)
                except TourAPIError:
                    intro = {}

            if not record.get("image_url"):
                try:
                    images = fetch_detail_images(content_id, service_key)
                except TourAPIError:
                    images = []

            enriched_records.append(
                merge_detail_into_record(record, common, intro, images)
            )
            enriched_count += 1

        enriched_routes.append(pd.DataFrame(enriched_records))

    return enriched_routes


def dwell_minutes(record: dict[str, Any]) -> int:
    """콘텐츠 유형에 따른 기본 체류 시간을 반환한다."""
    return DWELL_MINUTES_BY_TYPE.get(str(record.get("content_type_id", "")), 90)


def build_daily_schedule(
    day_routes: Sequence[pd.DataFrame],
    start_coordinate: tuple[float, float],
    start_time: dt_time,
    transport_mode: str,
) -> tuple[pd.DataFrame, list[pd.DataFrame], dict[str, float]]:
    """이동시간·체류시간을 계산하여 날짜별 예상 일정을 만든다."""
    speed = TRANSPORT_SPEED_KMH[transport_mode]
    all_rows: list[dict[str, Any]] = []
    scheduled_days: list[pd.DataFrame] = []
    total_distance = 0.0
    total_minutes = 0.0

    for day_index, route_df in enumerate(day_routes, start=1):
        current_coordinate = start_coordinate
        current_datetime = datetime.combine(datetime.today().date(), start_time)
        day_rows: list[dict[str, Any]] = []

        for order, record in enumerate(route_df.to_dict("records"), start=1):
            distance = calculate_haversine_distance(
                current_coordinate[0],
                current_coordinate[1],
                float(record["latitude"]),
                float(record["longitude"]),
            )
            travel_minutes = int(math.ceil(distance / speed * 60)) if distance > 0 else 0
            arrival = current_datetime + timedelta(minutes=travel_minutes)
            stay = dwell_minutes(record)
            departure = arrival + timedelta(minutes=stay)

            scheduled = dict(record)
            scheduled.update(
                {
                    "day": day_index,
                    "order": order,
                    "arrival_time": arrival.strftime("%H:%M"),
                    "stay_minutes": stay,
                    "distance_from_previous_km": round(distance, 2),
                    "travel_minutes": travel_minutes,
                    "next_distance_km": 0.0,
                }
            )
            day_rows.append(scheduled)

            total_distance += distance
            total_minutes += travel_minutes + stay
            current_coordinate = (
                float(record["latitude"]),
                float(record["longitude"]),
            )
            current_datetime = departure

        for index in range(len(day_rows) - 1):
            day_rows[index]["next_distance_km"] = round(
                calculate_haversine_distance(
                    float(day_rows[index]["latitude"]),
                    float(day_rows[index]["longitude"]),
                    float(day_rows[index + 1]["latitude"]),
                    float(day_rows[index + 1]["longitude"]),
                ),
                2,
            )

        day_df = pd.DataFrame(day_rows)
        scheduled_days.append(day_df)
        all_rows.extend(day_rows)

    schedule_df = pd.DataFrame(all_rows)
    summary = {
        "total_distance_km": round(total_distance, 1),
        "average_daily_distance_km": round(total_distance / max(1, len(day_routes)), 1),
        "total_minutes": round(total_minutes),
    }
    return schedule_df, scheduled_days, summary


def format_duration(total_minutes: float) -> str:
    """분 단위 시간을 읽기 쉬운 문자열로 바꾼다."""
    minutes = int(round(total_minutes))
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"약 {hours}시간 {remainder}분"
    if hours:
        return f"약 {hours}시간"
    return f"약 {remainder}분"


# -----------------------------------------------------------------------------
# 지도와 화면 렌더링
# -----------------------------------------------------------------------------
def create_route_map(
    scheduled_days: Sequence[pd.DataFrame],
    start_coordinate: tuple[float, float],
    start_label: str,
) -> folium.Map:
    """날짜별 번호 마커와 경로선을 포함한 Folium 지도를 만든다."""
    all_points = [start_coordinate]
    for day_df in scheduled_days:
        for _, row in day_df.iterrows():
            all_points.append((float(row["latitude"]), float(row["longitude"])))

    center_lat = float(np.mean([point[0] for point in all_points]))
    center_lon = float(np.mean([point[1] for point in all_points]))
    route_map = folium.Map(
        location=[center_lat, center_lon],
        tiles="OpenStreetMap",
        zoom_start=12,
        control_scale=True,
    )

    folium.Marker(
        location=list(start_coordinate),
        tooltip="출발 기준점",
        popup=folium.Popup(html.escape(start_label), max_width=280),
        icon=folium.Icon(color="darkpurple", icon="home", prefix="fa"),
    ).add_to(route_map)

    global_order = 1
    for day_index, day_df in enumerate(scheduled_days, start=1):
        if day_df.empty:
            continue
        color = DAY_COLORS[(day_index - 1) % len(DAY_COLORS)]
        coordinates = [start_coordinate]

        for _, row in day_df.iterrows():
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
            coordinates.append((latitude, longitude))
            popup_html = (
                f"<div style='font-family: sans-serif; min-width:220px'>"
                f"<b>{html.escape(str(row['title']))}</b><br>"
                f"{day_index}일 차 · {html.escape(str(row['arrival_time']))}<br>"
                f"{html.escape(str(row['address']))}"
                f"</div>"
            )
            marker_html = (
                f"<div style='background:{color};color:white;border:2px solid white;"
                f"border-radius:50%;width:30px;height:30px;line-height:26px;"
                f"text-align:center;font-weight:700;box-shadow:0 1px 5px rgba(0,0,0,.35)'>"
                f"{global_order}</div>"
            )
            folium.Marker(
                location=[latitude, longitude],
                tooltip=f"{global_order}. {row['title']}",
                popup=folium.Popup(popup_html, max_width=320),
                icon=DivIcon(html=marker_html, icon_size=(30, 30), icon_anchor=(15, 15)),
            ).add_to(route_map)
            global_order += 1

        folium.PolyLine(
            locations=coordinates,
            color=color,
            weight=5,
            opacity=0.8,
            tooltip=f"{day_index}일 차 예상 경로",
        ).add_to(route_map)

    route_map.fit_bounds([[point[0], point[1]] for point in all_points], padding=(30, 30))
    return route_map


def render_no_image() -> None:
    """대표 이미지가 없을 때 통일된 대체 UI를 표시한다."""
    st.markdown(
        """
        <div class="no-image-box">
            <div>🖼️</div>
            <span>등록된 대표 이미지가 없습니다.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_attraction_card(row: pd.Series) -> None:
    """관광지 한 곳을 이미지와 상세정보가 있는 카드로 표시한다."""
    with st.container(border=True):
        image_column, info_column = st.columns([1, 2.1], gap="large")

        with image_column:
            image_url = str(row.get("image_url", "") or "")
            if image_url:
                try:
                    st.image(image_url, use_container_width=True)
                except Exception:
                    render_no_image()
            else:
                render_no_image()

        with info_column:
            st.markdown(f"### {int(row['order'])}. {row['title']}")
            info_columns = st.columns(3)
            info_columns[0].metric("예상 도착", str(row["arrival_time"]))
            info_columns[1].metric("예상 체류", f"{int(row['stay_minutes'])}분")
            next_distance = float(row.get("next_distance_km", 0.0) or 0.0)
            info_columns[2].metric(
                "다음 장소까지",
                f"{next_distance:.1f}km" if next_distance else "마지막 장소",
            )

            st.markdown(f"**유형:** {row.get('type_name', '관광정보')}")
            if str(row.get("classification_name", "") or ""):
                st.caption(f"신분류: {row['classification_name']}")
            st.markdown(f"**주소:** {row['address']}")
            if str(row.get("phone", "") or ""):
                st.markdown(f"**전화:** {row['phone']}")

            operation_info = str(row.get("operation_info", "") or "")
            rest_info = str(row.get("rest_info", "") or "")
            if operation_info:
                st.markdown(f"**이용시간:** {operation_info}")
            else:
                st.caption("운영시간 정보가 명확하지 않습니다. 방문 전 운영시간을 확인하세요.")
            if rest_info:
                st.caption(f"휴무 안내: {rest_info}")

            overview = str(row.get("overview", "") or "")
            if overview:
                preview = overview if len(overview) <= 200 else overview[:200].rstrip() + "…"
                st.write(preview)
                if len(overview) > 200:
                    with st.expander("관광지 소개 전체 보기"):
                        st.write(overview)
            else:
                st.caption("등록된 상세 소개가 없습니다.")

            query = quote(f"{row['title']} {row['address']}")
            naver_url = f"https://map.naver.com/p/search/{query}"
            kakao_url = f"https://map.kakao.com/link/search/{query}"
            homepage = str(row.get("homepage", "") or "")

            links = [f"[네이버 지도]({naver_url})", f"[카카오맵]({kakao_url})"]
            if homepage:
                links.insert(0, f"[공식 홈페이지]({homepage})")
            st.markdown(" · ".join(links))


def convert_dataframe_to_csv(df: pd.DataFrame) -> bytes:
    """일정표를 Excel에서도 한글이 깨지지 않는 CSV 바이트로 변환한다."""
    export_columns = {
        "day": "날짜",
        "order": "순서",
        "arrival_time": "예상 시각",
        "title": "관광지명",
        "type_name": "관광지 유형",
        "address": "주소",
        "stay_minutes": "체류 시간(분)",
        "distance_from_previous_km": "이동 거리(km)",
        "recommendation_score": "추천 점수",
    }
    if df.empty:
        export_df = pd.DataFrame(columns=list(export_columns.values()))
    else:
        export_df = df[list(export_columns.keys())].rename(columns=export_columns)
        export_df["날짜"] = export_df["날짜"].map(lambda value: f"{int(value)}일 차")
    return export_df.to_csv(index=False).encode("utf-8-sig")


def apply_custom_css() -> None:
    """밝고 단정한 여행 서비스 스타일을 적용한다."""
    st.markdown(
        """
        <style>
        .block-container {max-width: 1320px; padding-top: 2rem; padding-bottom: 4rem;}
        [data-testid="stSidebar"] {background: #f8fafc;}
        .hero {
            padding: 1.8rem 2rem;
            border: 1px solid #e2e8f0;
            border-radius: 20px;
            background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%);
            margin-bottom: 1.5rem;
        }
        .hero h1 {margin: 0 0 .45rem 0; font-size: 2.25rem;}
        .hero p {margin: 0; color: #475569; font-size: 1.05rem;}
        .no-image-box {
            min-height: 210px;
            width: 100%;
            border-radius: 14px;
            border: 1px dashed #cbd5e1;
            background: #f8fafc;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: .5rem;
            color: #64748b;
            text-align: center;
        }
        .no-image-box div {font-size: 2rem;}
        .stMetric {background: #f8fafc; border-radius: 12px; padding: .6rem .8rem;}
        @media (max-width: 700px) {
            .hero {padding: 1.3rem;}
            .hero h1 {font-size: 1.75rem;}
            .block-container {padding-left: 1rem; padding-right: 1rem;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_results(result: dict[str, Any]) -> None:
    """세션에 저장된 추천 결과 전체를 화면에 출력한다."""
    schedule_df: pd.DataFrame = result["schedule_df"]
    scheduled_days: list[pd.DataFrame] = result["scheduled_days"]
    summary: dict[str, float] = result["summary"]

    st.divider()
    st.subheader(f"📍 {result['region_label']} 추천 여행 코스")

    metrics = st.columns(6)
    metrics[0].metric("선택 지역", result["region_label"])
    metrics[1].metric("여행 기간", result["trip_duration"])
    metrics[2].metric("추천 장소", f"{len(schedule_df)}곳")
    metrics[3].metric("전체 이동", f"{summary['total_distance_km']:.1f}km")
    metrics[4].metric("하루 평균", f"{summary['average_daily_distance_km']:.1f}km")
    metrics[5].metric("전체 예상 시간", format_duration(summary["total_minutes"]))

    st.info(
        "추천 점수는 사용자가 선택한 취향, 출발 기준점과의 거리, 이미지·설명 보유 여부, "
        "동행 유형, 정보 완성도를 조합한 자체 알고리즘 결과입니다. 실제 이용자 평점이나 방문자 수를 뜻하지 않습니다."
    )
    st.caption(
        "지도 경로와 거리는 위경도 사이의 직선거리를 기준으로 계산했습니다. "
        "대중교통·자동차 예상시간은 설정한 평균 속도를 사용하므로 실제 교통 상황과 다를 수 있습니다."
    )

    warnings = result.get("warnings", [])
    if warnings:
        with st.expander("경로 생성 시 확인할 점", expanded=False):
            for warning in warnings:
                st.warning(warning)

    route_map = create_route_map(
        scheduled_days,
        result["start_coordinate"],
        result["start_label"],
    )
    st_folium(
        route_map,
        use_container_width=True,
        height=600,
        returned_objects=[],
        key="travel_route_map",
    )

    st.subheader("🗓️ 날짜별 일정")
    tabs = st.tabs([f"{index}일 차" for index in range(1, len(scheduled_days) + 1)])
    for tab, day_df in zip(tabs, scheduled_days):
        with tab:
            if day_df.empty:
                st.info("이 날짜에 배정된 관광지가 없습니다.")
                continue
            for _, row in day_df.iterrows():
                render_attraction_card(row)

    st.subheader("📋 이동 경로 표")
    display_df = schedule_df[
        [
            "day",
            "order",
            "arrival_time",
            "title",
            "type_name",
            "address",
            "stay_minutes",
            "distance_from_previous_km",
            "recommendation_score",
        ]
    ].copy()
    display_df.columns = [
        "날짜",
        "순서",
        "예상 시각",
        "관광지명",
        "관광지 유형",
        "주소",
        "체류 시간(분)",
        "이동 거리(km)",
        "추천 점수",
    ]
    display_df["날짜"] = display_df["날짜"].map(lambda value: f"{int(value)}일 차")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.download_button(
        "CSV 일정표 다운로드",
        data=convert_dataframe_to_csv(schedule_df),
        file_name=f"{normalize_text(result['region_label']) or '여행'}_추천코스.csv",
        mime="text/csv",
        use_container_width=True,
    )


# -----------------------------------------------------------------------------
# 앱 실행 흐름
# -----------------------------------------------------------------------------
def reset_region_candidates_when_query_changes(region_query: str) -> None:
    """지역 입력이 바뀌면 이전 법정동 후보를 초기화한다."""
    previous_query = st.session_state.get("region_candidate_query", "")
    if previous_query != region_query:
        st.session_state.pop("region_candidates", None)
        st.session_state.pop("selected_region_label", None)
        st.session_state["region_candidate_query"] = region_query


def run_recommendation(
    service_key: str,
    region_query: str,
    selected_region: Optional[dict[str, str]],
    trip_duration: str,
    visits_per_day: int,
    start_time: dt_time,
    transport_mode: str,
    preferences: Sequence[str],
    companion: str,
    max_distance_km: float,
    start_place_keyword: str,
    include_food: bool,
) -> Optional[dict[str, Any]]:
    """입력값 검증부터 API 조회, 추천, 지도용 일정 생성까지 수행한다."""
    if not region_query.strip():
        st.error("여행 지역을 입력해 주세요.")
        return None

    # 첫 클릭에서는 법정동 후보를 검색한다. 여러 후보가 있으면 사용자가 선택하도록 멈춘다.
    if selected_region is None:
        with st.spinner("입력한 지역의 법정동 코드를 찾고 있습니다..."):
            candidates = search_legal_dong_codes(region_query, service_key)
        if not candidates:
            st.error(
                "입력한 지역의 법정동 코드를 찾지 못했습니다. ‘서울 종로구’, ‘강릉시’처럼 다시 입력해 주세요."
            )
            return None

        st.session_state["region_candidates"] = candidates
        st.session_state["region_candidate_query"] = region_query
        if len(candidates) > 1:
            st.info("일치하는 지역이 여러 개입니다. 사이드바에서 지역을 선택한 뒤 다시 ‘여행 코스 추천’을 눌러 주세요.")
            return None
        selected_region = candidates[0]

    region_code = selected_region["region_code"]
    district_code = selected_region["district_code"]
    region_label = selected_region["label"]

    progress = st.progress(0, text="지역 관광정보를 불러오는 중입니다.")

    try:
        area_rows = fetch_area_attractions(region_code, district_code, service_key)
        progress.progress(22, text="신분류 체계를 확인하는 중입니다.")

        try:
            classification_rows = fetch_classification_codes(service_key)
            classification_lookup = build_classification_lookup(classification_rows)
        except TourAPIError:
            classification_lookup = {}

        progress.progress(35, text="관광지 좌표와 중복 데이터를 정리하는 중입니다.")
        attractions = clean_attraction_data(area_rows, classification_lookup)
        if attractions.empty:
            st.error(
                "입력한 지역에서 조건에 맞는 관광정보를 찾지 못했습니다. "
                "시군구보다 넓은 지역명으로 다시 검색하거나 최대 이동 거리를 늘려보세요."
            )
            return None

        non_lodging = attractions[attractions["content_type_id"] != "32"].copy()
        if non_lodging.empty:
            st.error("경로에 사용할 수 있는 관광지 좌표를 찾지 못했습니다.")
            return None

        start_place: Optional[dict[str, Any]] = None
        warnings: list[str] = []
        if start_place_keyword.strip():
            progress.progress(44, text="입력한 출발 장소를 찾는 중입니다.")
            keyword_rows = fetch_keyword_results(
                start_place_keyword.strip(),
                region_code,
                district_code,
                service_key,
            )
            start_place = choose_start_place(
                keyword_rows,
                start_place_keyword,
                classification_lookup,
            )
            if start_place is None:
                warnings.append(
                    f"출발 장소 ‘{start_place_keyword}’를 관광정보에서 찾지 못해 지역 중심점을 사용했습니다."
                )

        if start_place:
            start_coordinate = (
                float(start_place["latitude"]),
                float(start_place["longitude"]),
            )
            start_label = f"출발지: {start_place['title']}"
        else:
            start_coordinate = find_medoid_coordinate(non_lodging)
            nearest_to_center = non_lodging.assign(
                _center_distance=non_lodging.apply(
                    lambda row: calculate_haversine_distance(
                        start_coordinate[0],
                        start_coordinate[1],
                        float(row["latitude"]),
                        float(row["longitude"]),
                    ),
                    axis=1,
                )
            ).sort_values("_center_distance").iloc[0]
            start_label = f"지역 중심 기준점: {nearest_to_center['title']} 인근"

        progress.progress(55, text="사용자 조건에 따라 추천 점수를 계산하는 중입니다.")
        scored = apply_recommendation_scores(
            non_lodging,
            preferences,
            companion,
            start_coordinate,
            max(max_distance_km * 2.5, 10.0),
        )

        days = TRIP_DAYS[trip_duration]
        progress.progress(68, text="이동 거리가 짧은 방문 순서를 만드는 중입니다.")
        day_routes, selection_warnings, _ = select_attractions(
            scored_df=scored,
            days=days,
            visits_per_day=visits_per_day,
            include_food=include_food,
            start_coordinate=start_coordinate,
            max_leg_km=max_distance_km,
        )
        warnings.extend(selection_warnings)

        if not any(not route.empty for route in day_routes):
            st.error(
                "조건에 맞는 여행 경로를 만들지 못했습니다. 최대 이동 거리를 늘리거나 여행 취향을 줄여보세요."
            )
            return None

        progress.progress(78, text="선택된 장소의 상세 설명과 이미지를 확인하는 중입니다.")
        enriched_routes = enrich_selected_attractions(day_routes, service_key)

        # 상세 설명이 추가된 뒤 최종 점수를 다시 계산한다.
        rescored_routes: list[pd.DataFrame] = []
        for route in enriched_routes:
            if route.empty:
                rescored_routes.append(route)
                continue
            rescored = route.copy()
            rescored["recommendation_score"] = rescored.apply(
                calculate_recommendation_score,
                axis=1,
                preferences=preferences,
                companion=companion,
                center=start_coordinate,
                distance_reference_km=max(max_distance_km * 2.5, 10.0),
            )
            rescored_routes.append(rescored)

        progress.progress(90, text="예상 방문 시각과 이동시간을 계산하는 중입니다.")
        schedule_df, scheduled_days, summary = build_daily_schedule(
            rescored_routes,
            start_coordinate,
            start_time,
            transport_mode,
        )
        progress.progress(100, text="여행 코스를 완성했습니다.")
        time.sleep(0.15)
        progress.empty()

        return {
            "region_label": region_label,
            "trip_duration": trip_duration,
            "schedule_df": schedule_df,
            "scheduled_days": scheduled_days,
            "summary": summary,
            "start_coordinate": start_coordinate,
            "start_label": start_label,
            "warnings": list(dict.fromkeys(warnings)),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

    except TourAPIError as exc:
        progress.empty()
        st.error(exc.user_message)
        if exc.technical_message:
            with st.expander("오류 진단 정보"):
                st.code(exc.technical_message)
        return None


def main() -> None:
    """Streamlit 앱의 진입점."""
    st.set_page_config(
        page_title="나만의 지역 여행 코스",
        page_icon="🧭",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_custom_css()

    st.markdown(
        """
        <section class="hero">
            <h1>🧭 나만의 지역 여행 코스</h1>
            <p>지역과 여행 조건을 입력하면 관광 명소를 연결한 맞춤형 여행 코스를 추천해 드립니다.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    service_key = get_service_key()
    if not service_key:
        st.error(
            "한국관광공사 API 키가 설정되지 않았습니다. Streamlit Secrets에 KTO_API_KEY를 등록해 주세요."
        )
        st.code('KTO_API_KEY = "공공데이터포털에서_발급받은_API_키"', language="toml")
        st.stop()

    with st.sidebar:
        st.header("여행 조건")
        region_query = st.text_input(
            "여행 지역 *",
            placeholder="예: 서울 종로구, 부산 해운대구, 강릉시",
        )
        reset_region_candidates_when_query_changes(region_query)

        selected_region: Optional[dict[str, str]] = None
        candidates = st.session_state.get("region_candidates", [])
        if candidates and st.session_state.get("region_candidate_query") == region_query:
            labels = [candidate["label"] for candidate in candidates]
            selected_label = st.selectbox(
                "정확한 지역 선택",
                labels,
                key="selected_region_label",
            )
            selected_region = next(
                candidate for candidate in candidates if candidate["label"] == selected_label
            )

        trip_duration = st.selectbox("여행 기간 *", list(TRIP_DAYS.keys()))
        visits_per_day = st.slider("하루 방문 장소 수 *", 3, 8, 5)
        travel_start_time = st.time_input("여행 시작 시각 *", value=dt_time(10, 0))
        transport_mode = st.selectbox("이동 수단 *", list(TRANSPORT_SPEED_KMH.keys()))

        if st.session_state.get("_last_transport_mode") != transport_mode:
            st.session_state["max_distance_km"] = DEFAULT_MAX_DISTANCE_KM[transport_mode]
            st.session_state["_last_transport_mode"] = transport_mode

        preferences = st.multiselect(
            "여행 취향",
            ["자연", "역사·문화", "체험", "전시·공연", "사진 명소", "휴식", "쇼핑", "음식"],
        )
        companion = st.selectbox(
            "동행 유형",
            ["혼자", "친구", "연인", "가족", "어린이 동반", "부모님 동반"],
        )
        max_distance_km = st.slider(
            "장소 사이 최대 이동 거리(km)",
            1,
            30,
            key="max_distance_km",
        )
        start_place_keyword = st.text_input(
            "출발 장소",
            placeholder="선택 입력: 관광지명 또는 역 이름",
        )
        include_food = st.checkbox("일정에 음식점 포함", value=True)

        recommend_clicked = st.button(
            "여행 코스 추천",
            type="primary",
            use_container_width=True,
        )

        st.caption(
            "API는 추천 버튼을 눌렀을 때만 호출됩니다. 입력값을 바꾸는 동안에는 이전 결과가 유지됩니다."
        )

    if recommend_clicked:
        with st.spinner("여행 조건을 확인하고 있습니다..."):
            result = run_recommendation(
                service_key=service_key,
                region_query=region_query,
                selected_region=selected_region,
                trip_duration=trip_duration,
                visits_per_day=visits_per_day,
                start_time=travel_start_time,
                transport_mode=transport_mode,
                preferences=preferences,
                companion=companion,
                max_distance_km=float(max_distance_km),
                start_place_keyword=start_place_keyword,
                include_food=include_food,
            )
        if result is not None:
            st.session_state["travel_result"] = result
            st.success("맞춤형 여행 코스를 만들었습니다.")

    if "travel_result" in st.session_state:
        render_results(st.session_state["travel_result"])
    else:
        st.info("지역과 여행 조건을 선택한 뒤 여행 코스 추천 버튼을 눌러 주세요.")
        st.markdown(
            """
            **앱이 만드는 과정**  
            1. 입력 지역의 법정동 코드를 찾습니다.  
            2. 관광지·문화시설·레포츠·음식점 정보를 불러옵니다.  
            3. 취향과 동행 유형에 맞는 추천 점수를 계산합니다.  
            4. 최근접 이웃 방식과 2-opt로 이동 순서를 정리합니다.
            """
        )


if __name__ == "__main__":
    main()
