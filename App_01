import random
from datetime import date
from urllib.parse import quote

import requests
import streamlit as st


# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(
    page_title="오늘 뭐 먹지?",
    page_icon="🍱",
    layout="wide"
)

st.title("🍱 오늘 뭐 먹지?")
st.caption("오늘 날씨, MBTI, 생일, 기분을 바탕으로 점심 메뉴를 추천해주는 웹앱입니다.")


# -----------------------------
# 데이터
# -----------------------------
MBTI_TYPES = [
    "ISTJ", "ISFJ", "INFJ", "INTJ",
    "ISTP", "ISFP", "INFP", "INTP",
    "ESTP", "ESFP", "ENFP", "ENTP",
    "ESTJ", "ESFJ", "ENFJ", "ENTJ"
]

MOOD_TAGS = {
    "행복해요 😊": ["함께먹기", "인기", "든든한"],
    "피곤해요 😴": ["따뜻한", "국물", "편안한"],
    "우울해요 😢": ["편안한", "따뜻한", "달달한"],
    "스트레스 받아요 😵": ["매운맛", "자극적", "든든한"],
    "집중이 필요해요 🧠": ["가벼운", "건강한", "깔끔한"],
    "든든하게 먹고 싶어요 💪": ["든든한", "밥", "고기"],
    "가볍게 먹고 싶어요 🥗": ["가벼운", "건강한", "산뜻한"]
}

MENUS = [
    {
        "name": "김치찌개",
        "category": "한식",
        "wiki_title": "김치찌개",
        "description": "비 오는 날이나 추운 날에 잘 어울리는 따뜻한 국물 메뉴",
        "tags": ["한식", "따뜻한", "국물", "매운맛", "비오는날", "추운날", "편안한", "밥"]
    },
    {
        "name": "비빔밥",
        "category": "한식",
        "wiki_title": "비빔밥",
        "description": "여러 재료가 균형 있게 들어간 건강한 한식 메뉴",
        "tags": ["한식", "건강한", "가벼운", "산뜻한", "맑은날", "균형", "밥"]
    },
    {
        "name": "불고기덮밥",
        "category": "한식",
        "wiki_title": "불고기",
        "description": "달짝지근한 고기와 밥이 어울리는 든든한 메뉴",
        "tags": ["한식", "든든한", "고기", "밥", "인기", "편안한"]
    },
    {
        "name": "냉면",
        "category": "한식",
        "wiki_title": "냉면",
        "description": "더운 날 시원하게 먹기 좋은 한식 메뉴",
        "tags": ["한식", "시원한", "가벼운", "더운날", "산뜻한"]
    },
    {
        "name": "제육볶음",
        "category": "한식",
        "wiki_title": "제육볶음",
        "description": "매콤하고 든든해서 스트레스 받을 때 좋은 메뉴",
        "tags": ["한식", "매운맛", "든든한", "고기", "밥", "자극적"]
    },

    {
        "name": "짜장면",
        "category": "중식",
        "wiki_title": "짜장면",
        "description": "익숙하고 편안한 맛의 대표적인 중식 메뉴",
        "tags": ["중식", "인기", "편안한", "든든한", "면"]
    },
    {
        "name": "짬뽕",
        "category": "중식",
        "wiki_title": "짬뽕",
        "description": "얼큰한 국물이 생각날 때 좋은 중식 메뉴",
        "tags": ["중식", "매운맛", "국물", "따뜻한", "비오는날", "추운날", "면"]
    },
    {
        "name": "마라탕",
        "category": "중식",
        "wiki_title": "마라탕",
        "description": "자극적이고 매운맛이 강한 스트레스 해소용 메뉴",
        "tags": ["중식", "매운맛", "자극적", "따뜻한", "국물", "도전적"]
    },
    {
        "name": "볶음밥",
        "category": "중식",
        "wiki_title": "볶음밥",
        "description": "부담 없이 먹기 좋은 무난하고 든든한 메뉴",
        "tags": ["중식", "밥", "든든한", "무난한", "깔끔한"]
    },
    {
        "name": "탕수육",
        "category": "중식",
        "wiki_title": "탕수육",
        "description": "여럿이 함께 먹기 좋은 인기 중식 메뉴",
        "tags": ["중식", "함께먹기", "인기", "고기", "든든한"]
    },

    {
        "name": "초밥",
        "category": "일식",
        "wiki_title": "초밥",
        "description": "깔끔하고 산뜻하게 먹기 좋은 일식 메뉴",
        "tags": ["일식", "깔끔한", "산뜻한", "가벼운", "맑은날"]
    },
    {
        "name": "라멘",
        "category": "일식",
        "wiki_title": "라멘",
        "description": "따뜻한 국물과 면이 어울리는 든든한 메뉴",
        "tags": ["일식", "따뜻한", "국물", "든든한", "비오는날", "추운날", "면"]
    },
    {
        "name": "우동",
        "category": "일식",
        "wiki_title": "우동",
        "description": "부드럽고 따뜻해서 피곤한 날 먹기 좋은 메뉴",
        "tags": ["일식", "따뜻한", "국물", "편안한", "면", "추운날"]
    },
    {
        "name": "돈가스",
        "category": "일식",
        "wiki_title": "돈가스",
        "description": "바삭하고 든든해서 기분 전환에 좋은 메뉴",
        "tags": ["일식", "든든한", "고기", "인기", "편안한"]
    },
    {
        "name": "규동",
        "category": "일식",
        "wiki_title": "규동",
        "description": "밥과 고기를 빠르고 든든하게 먹을 수 있는 메뉴",
        "tags": ["일식", "밥", "고기", "든든한", "깔끔한"]
    },

    {
        "name": "파스타",
        "category": "양식",
        "wiki_title": "파스타",
        "description": "기분 좋은 날 분위기 있게 먹기 좋은 양식 메뉴",
        "tags": ["양식", "인기", "산뜻한", "함께먹기", "면"]
    },
    {
        "name": "피자",
        "category": "양식",
        "wiki_title": "피자",
        "description": "친구들과 함께 먹기 좋은 대표적인 양식 메뉴",
        "tags": ["양식", "함께먹기", "인기", "든든한"]
    },
    {
        "name": "샐러드",
        "category": "양식",
        "wiki_title": "샐러드",
        "description": "가볍고 건강하게 먹고 싶을 때 좋은 메뉴",
        "tags": ["양식", "건강한", "가벼운", "산뜻한", "더운날", "깔끔한"]
    },
    {
        "name": "햄버거",
        "category": "양식",
        "wiki_title": "햄버거",
        "description": "간단하지만 든든하게 먹기 좋은 메뉴",
        "tags": ["양식", "든든한", "고기", "인기", "무난한"]
    },
    {
        "name": "스테이크",
        "category": "양식",
        "wiki_title": "스테이크",
        "description": "생일이나 특별한 날 기분 내기 좋은 메뉴",
        "tags": ["양식", "고기", "든든한", "특별한날", "인기"]
    }
]


# -----------------------------
# API 함수
# -----------------------------
@st.cache_data(ttl=60 * 60)
def get_coordinates(city_name):
    """도시 이름을 위도, 경도로 변환"""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": city_name,
        "count": 1,
        "language": "ko",
        "format": "json"
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    if "results" not in data:
        return None

    result = data["results"][0]
    return {
        "name": result.get("name", city_name),
        "country": result.get("country", ""),
        "latitude": result["latitude"],
        "longitude": result["longitude"],
        "timezone": result.get("timezone", "Asia/Seoul")
    }


@st.cache_data(ttl=30 * 60)
def get_weather(latitude, longitude):
    """Open-Meteo에서 오늘 날씨 정보 가져오기"""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": 1
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=60 * 60 * 24)
def get_wiki_image(title):
    """한국어 위키백과에서 음식 썸네일 이미지 가져오기"""
    url = "https://ko.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "prop": "pageimages",
        "titles": title,
        "pithumbsize": 900,
        "redirects": 1
    }
    headers = {
        "User-Agent": "StreamlitLunchRecommender/1.0"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            thumbnail = page.get("thumbnail")
            if thumbnail and "source" in thumbnail:
                return thumbnail["source"]

    except Exception:
        pass

    # 이미지가 없을 때 대체 이미지
    return f"https://placehold.co/900x600?text={quote(title)}"


# -----------------------------
# 추천 로직
# -----------------------------
def weather_code_to_korean(code):
    code = int(code)

    weather_map = {
        0: "맑음",
        1: "대체로 맑음",
        2: "부분적으로 흐림",
        3: "흐림",
        45: "안개",
        48: "서리 안개",
        51: "약한 이슬비",
        53: "이슬비",
        55: "강한 이슬비",
        61: "약한 비",
        63: "비",
        65: "강한 비",
        71: "약한 눈",
        73: "눈",
        75: "강한 눈",
        77: "싸락눈",
        80: "약한 소나기",
        81: "소나기",
        82: "강한 소나기",
        95: "천둥번개",
        96: "우박을 동반한 천둥번개",
        99: "강한 우박을 동반한 천둥번개"
    }

    return weather_map.get(code, "알 수 없음")


def weather_to_tags(weather_data):
    current = weather_data["current"]
    daily = weather_data["daily"]

    temp = current.get("temperature_2m")
    precipitation = current.get("precipitation", 0)
    weather_code = int(current.get("weather_code", 0))
    rain_probability = daily.get("precipitation_probability_max", [0])[0]

    tags = []

    if temp is not None:
        if temp >= 28:
            tags += ["더운날", "시원한", "가벼운", "산뜻한"]
        elif temp <= 7:
            tags += ["추운날", "따뜻한", "국물"]
        else:
            tags += ["무난한", "든든한"]

    rainy_codes = [51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99]
    snowy_codes = [71, 73, 75, 77]

    if weather_code in rainy_codes or precipitation > 0 or rain_probability >= 50:
        tags += ["비오는날", "따뜻한", "국물"]
    elif weather_code in snowy_codes:
        tags += ["눈오는날", "따뜻한", "국물", "추운날"]
    elif weather_code in [0, 1, 2]:
        tags += ["맑은날", "산뜻한", "가벼운"]

    return tags


def mbti_to_tags(mbti):
    tags = []

    if mbti[0] == "I":
        tags += ["편안한", "혼밥", "무난한"]
    else:
        tags += ["함께먹기", "인기", "든든한"]

    if mbti[1] == "N":
        tags += ["도전적", "자극적", "특별한날"]
    else:
        tags += ["무난한", "밥", "깔끔한"]

    if mbti[2] == "F":
        tags += ["편안한", "따뜻한"]
    else:
        tags += ["깔끔한", "든든한"]

    if mbti[3] == "J":
        tags += ["균형", "무난한", "밥"]
    else:
        tags += ["도전적", "인기", "자극적"]

    return tags


def birthday_to_tags(birthday):
    month = birthday.month

    if month in [3, 4, 5]:
        return ["산뜻한", "가벼운", "건강한"]
    elif month in [6, 7, 8]:
        return ["더운날", "시원한", "가벼운"]
    elif month in [9, 10, 11]:
        return ["든든한", "밥", "편안한"]
    else:
        return ["추운날", "따뜻한", "국물", "특별한날"]


def recommend_menus(weather_tags, mbti, birthday, mood, spicy_level, selected_categories):
    user_tags = []
    user_tags += weather_tags
    user_tags += mbti_to_tags(mbti)
    user_tags += birthday_to_tags(birthday)
    user_tags += MOOD_TAGS[mood]

    if spicy_level >= 4:
        user_tags += ["매운맛", "자극적"]
    elif spicy_level <= 1:
        user_tags += ["깔끔한", "무난한", "가벼운"]

    user_tag_set = set(user_tags)

    seed_text = f"{date.today()}-{mbti}-{birthday}-{mood}-{spicy_level}"

    scored = []

    for menu in MENUS:
        if menu["category"] not in selected_categories:
            continue

        menu_tag_set = set(menu["tags"])
        matched_tags = user_tag_set & menu_tag_set

        score = len(matched_tags) * 10

        # 매운맛 선호도 반영
        if spicy_level <= 1 and "매운맛" in menu_tag_set:
            score -= 8
        elif spicy_level >= 4 and "매운맛" in menu_tag_set:
            score += 8

        # 매일 같은 조건이어도 약간의 다양성을 주는 결정적 랜덤값
        score += random.Random(seed_text + menu["name"]).random()

        scored.append({
            "menu": menu,
            "score": score,
            "matched_tags": sorted(list(matched_tags))
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored, sorted(list(user_tag_set))


# -----------------------------
# 사이드바 입력
# -----------------------------
with st.sidebar:
    st.header("내 정보 입력")

    city = st.text_input("지역", value="서울")

    mbti = st.selectbox("MBTI", MBTI_TYPES, index=6)

    birthday = st.date_input(
        "생일",
        value=date(2008, 1, 1),
        help="추천에는 연도보다 월/일의 계절감을 중심으로 사용합니다."
    )

    mood = st.selectbox("오늘 기분", list(MOOD_TAGS.keys()))

    spicy_level = st.slider(
        "매운 음식 선호도",
        min_value=0,
        max_value=5,
        value=3,
        help="0은 전혀 안 매운 음식, 5는 아주 매운 음식을 선호한다는 뜻입니다."
    )

    categories = ["한식", "중식", "일식", "양식"]
    selected_categories = st.multiselect(
        "추천받고 싶은 음식 종류",
        categories,
        default=categories
    )


# -----------------------------
# 메인 화면
# -----------------------------
if not selected_categories:
    st.warning("최소 한 가지 음식 종류를 선택해주세요.")
    st.stop()

try:
    location = get_coordinates(city)

    if location is None:
        st.error("지역을 찾을 수 없습니다. 예: 서울, 부산, 인천, 대전처럼 입력해보세요.")
        st.stop()

    weather_data = get_weather(location["latitude"], location["longitude"])
    current = weather_data["current"]
    daily = weather_data["daily"]

    temperature = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    wind_speed = current.get("wind_speed_10m")
    weather_code = current.get("weather_code")
    rain_probability = daily.get("precipitation_probability_max", [0])[0]

    weather_text = weather_code_to_korean(weather_code)
    weather_tags = weather_to_tags(weather_data)

except Exception as e:
    st.error("날씨 정보를 불러오는 중 문제가 발생했습니다.")
    st.exception(e)
    st.stop()


st.subheader("🌤️ 오늘 날씨 정보")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("지역", f"{location['name']}")

with col2:
    st.metric("현재 기온", f"{temperature}℃")

with col3:
    st.metric("날씨", weather_text)

with col4:
    st.metric("강수 확률", f"{rain_probability}%")

st.caption(f"습도: {humidity}% · 풍속: {wind_speed} km/h")


recommendations, all_tags = recommend_menus(
    weather_tags=weather_tags,
    mbti=mbti,
    birthday=birthday,
    mood=mood,
    spicy_level=spicy_level,
    selected_categories=selected_categories
)

best = recommendations[0]
best_menu = best["menu"]

st.divider()

st.subheader("✨ 오늘의 추천 점심 메뉴")

left, right = st.columns([1.2, 1])

with left:
    st.image(
        get_wiki_image(best_menu["wiki_title"]),
        caption=f"{best_menu['category']} · {best_menu['name']}",
        use_container_width=True
    )

with right:
    st.markdown(f"## {best_menu['name']}")
    st.markdown(f"**분류:** {best_menu['category']}")
    st.write(best_menu["description"])

    st.markdown("### 추천 이유")
    if best["matched_tags"]:
        st.write(", ".join(best["matched_tags"]))
    else:
        st.write("입력한 조건과 가장 무난하게 어울리는 메뉴입니다.")

    st.markdown("### 반영된 조건")
    st.write(f"- MBTI: **{mbti}**")
    st.write(f"- 생일 계절감: **{birthday.month}월**")
    st.write(f"- 오늘 기분: **{mood}**")
    st.write(f"- 매운맛 선호도: **{spicy_level}/5**")


st.divider()

st.subheader("🏆 추천 순위 TOP 6")

top6 = recommendations[:6]
cols = st.columns(3)

for i, item in enumerate(top6):
    menu = item["menu"]

    with cols[i % 3]:
        st.image(
            get_wiki_image(menu["wiki_title"]),
            use_container_width=True
        )
        st.markdown(f"### {i + 1}. {menu['name']}")
        st.markdown(f"**{menu['category']}**")
        st.caption(menu["description"])

        if item["matched_tags"]:
            st.write("관련 키워드:", ", ".join(item["matched_tags"][:5]))


st.divider()

st.subheader("🍽️ 음식 종류별 추천 후보")

tabs = st.tabs(["한식", "중식", "일식", "양식"])

for tab, category in zip(tabs, ["한식", "중식", "일식", "양식"]):
    with tab:
        category_items = [
            item for item in recommendations
            if item["menu"]["category"] == category
        ]

        if not category_items:
            st.info(f"{category}은 현재 선택되지 않았습니다.")
            continue

        cols = st.columns(min(3, len(category_items)))

        for i, item in enumerate(category_items[:3]):
            menu = item["menu"]

            with cols[i]:
                st.image(
                    get_wiki_image(menu["wiki_title"]),
                    use_container_width=True
                )
                st.markdown(f"### {menu['name']}")
                st.caption(menu["description"])


with st.expander("🔍 추천에 사용된 태그 보기"):
    st.write(", ".join(all_tags))
