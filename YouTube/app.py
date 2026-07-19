import io
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from wordcloud import WordCloud


# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(
    page_title="YouTube 댓글 분석기",
    page_icon="💬",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {padding-top: 1.6rem; padding-bottom: 2.5rem;}
        [data-testid="stMetricValue"] {font-size: 1.65rem;}
        .small-note {color: #6b7280; font-size: 0.88rem;}
        .video-card {
            padding: 1rem 1.1rem;
            border: 1px solid rgba(128,128,128,.25);
            border-radius: 14px;
            margin-bottom: 1rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# 텍스트 분석용 사전
# -----------------------------
POSITIVE_KO = {
    "좋아", "좋다", "최고", "재밌", "재미있", "감동", "멋지", "사랑", "감사",
    "대박", "웃기", "귀엽", "잘했", "행복", "추천", "완벽", "훌륭", "기대",
    "응원", "공감", "유익", "도움", "신기", "존경", "축하", "레전드",
}
NEGATIVE_KO = {
    "싫어", "싫다", "최악", "별로", "재미없", "실망", "화나", "짜증", "혐오",
    "문제", "거짓", "노잼", "불편", "답답", "망했", "아쉽", "비추천",
    "무섭", "슬프", "화남", "구리", "지루", "억지", "불쾌", "심각",
}
POSITIVE_EN = {
    "good", "great", "best", "awesome", "amazing", "love", "loved", "funny",
    "nice", "excellent", "perfect", "thanks", "thank", "helpful", "cool", "wow",
    "beautiful", "brilliant", "legend", "respect", "enjoy", "enjoyed", "happy",
}
NEGATIVE_EN = {
    "bad", "worst", "hate", "boring", "awful", "terrible", "dislike", "angry",
    "annoying", "sad", "fake", "problem", "disappointed", "disappointing", "poor",
    "ugly", "stupid", "trash", "scam", "wrong", "uncomfortable",
}

DEFAULT_STOPWORDS = {
    # 한국어 조사·상투어
    "그리고", "그러나", "그래서", "하지만", "또한", "저는", "나는", "제가", "우리",
    "이것", "그것", "저것", "정도", "때문", "대한", "있는", "없는", "합니다", "합니다만",
    "입니다", "같아요", "같습니다", "하면", "해서", "하는", "한번", "정말", "진짜",
    "너무", "그냥", "여기", "영상", "댓글", "유튜브", "사람", "지금", "오늘",
    # 영어 불용어
    "the", "and", "for", "that", "this", "with", "you", "your", "are", "was", "were",
    "have", "has", "had", "but", "not", "from", "they", "their", "what", "when", "where",
    "who", "why", "how", "can", "could", "would", "should", "will", "just", "really",
    "very", "video", "youtube", "comment", "comments", "like", "about", "into", "than",
}

WEEKDAY_ORDER = ["월", "화", "수", "목", "금", "토", "일"]
WEEKDAY_MAP = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}


# -----------------------------
# 유틸리티 함수
# -----------------------------
def get_secret_api_key() -> str:
    """로컬 또는 Streamlit Cloud secrets에 키가 있으면 가져온다."""
    try:
        return str(st.secrets.get("YOUTUBE_API_KEY", ""))
    except (FileNotFoundError, KeyError):
        return ""
    except Exception:
        return ""


def extract_video_id(value: str) -> str | None:
    """일반 영상, 단축 URL, Shorts, Live, Embed 링크 또는 11자리 ID를 처리한다."""
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value

    try:
        parsed = urlparse(value if "://" in value else f"https://{value}")
        host = parsed.netloc.lower().replace("www.", "")
        path_parts = [part for part in parsed.path.split("/") if part]

        if host in {"youtu.be"} and path_parts:
            candidate = path_parts[0]
        elif host.endswith("youtube.com"):
            if parsed.path == "/watch":
                candidate = parse_qs(parsed.query).get("v", [""])[0]
            elif path_parts and path_parts[0] in {"shorts", "embed", "live", "v"}:
                candidate = path_parts[1] if len(path_parts) >= 2 else ""
            else:
                candidate = ""
        else:
            candidate = ""

        if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
            return candidate
    except Exception:
        pass

    # 링크 문자열 중 v= 또는 youtu.be/ 패턴을 한 번 더 탐색
    match = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})", value)
    return match.group(1) if match else None


def youtube_client(api_key: str):
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def get_video_info(youtube, video_id: str) -> dict:
    response = youtube.videos().list(
        part="snippet,statistics",
        id=video_id,
    ).execute()

    if not response.get("items"):
        raise ValueError("영상을 찾을 수 없습니다. 비공개·삭제 영상이거나 링크가 잘못되었을 수 있습니다.")

    item = response["items"][0]
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})

    return {
        "video_id": video_id,
        "title": snippet.get("title", "제목 없음"),
        "channel": snippet.get("channelTitle", "채널 정보 없음"),
        "published_at": snippet.get("publishedAt"),
        "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
        "view_count": int(statistics.get("viewCount", 0)),
        "like_count": int(statistics.get("likeCount", 0)),
        "comment_count": int(statistics.get("commentCount", 0)),
    }


def comment_to_row(comment: dict, parent_id: str | None = None, is_reply: bool = False) -> dict:
    snippet = comment.get("snippet", {})
    return {
        "comment_id": comment.get("id", ""),
        "parent_id": parent_id,
        "is_reply": is_reply,
        "author": snippet.get("authorDisplayName", "익명"),
        "text": snippet.get("textDisplay", ""),
        "like_count": int(snippet.get("likeCount", 0)),
        "published_at": snippet.get("publishedAt"),
        "updated_at": snippet.get("updatedAt"),
    }


def fetch_replies(youtube, parent_id: str, remaining: int) -> list[dict]:
    rows: list[dict] = []
    page_token = None

    while len(rows) < remaining:
        request_kwargs = {
            "part": "snippet",
            "parentId": parent_id,
            "maxResults": min(100, remaining - len(rows)),
            "textFormat": "plainText",
        }
        if page_token:
            request_kwargs["pageToken"] = page_token

        response = youtube.comments().list(**request_kwargs).execute()
        for item in response.get("items", []):
            rows.append(comment_to_row(item, parent_id=parent_id, is_reply=True))
            if len(rows) >= remaining:
                break

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return rows


def fetch_comments(
    youtube,
    video_id: str,
    target_count: int,
    order: str,
    include_replies: bool,
    progress_callback=None,
) -> list[dict]:
    rows: list[dict] = []
    page_token = None

    while len(rows) < target_count:
        request_kwargs = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": min(100, target_count - len(rows)),
            "order": order,
            "textFormat": "plainText",
        }
        if page_token:
            request_kwargs["pageToken"] = page_token

        response = youtube.commentThreads().list(**request_kwargs).execute()
        items = response.get("items", [])

        for thread in items:
            top_comment = thread.get("snippet", {}).get("topLevelComment", {})
            top_id = top_comment.get("id", "")
            rows.append(comment_to_row(top_comment, parent_id=None, is_reply=False))

            if progress_callback:
                progress_callback(len(rows), target_count)

            if len(rows) >= target_count:
                break

            total_reply_count = int(thread.get("snippet", {}).get("totalReplyCount", 0))
            if include_replies and total_reply_count > 0 and top_id:
                remaining = target_count - len(rows)
                reply_rows = fetch_replies(youtube, top_id, remaining)
                rows.extend(reply_rows)
                if progress_callback:
                    progress_callback(len(rows), target_count)

            if len(rows) >= target_count:
                break

        page_token = response.get("nextPageToken")
        if not page_token or not items:
            break

    return rows[:target_count]


def parse_http_error(error: HttpError) -> str:
    text = str(error)
    if "commentsDisabled" in text:
        return "이 영상은 댓글이 비활성화되어 있습니다."
    if "quotaExceeded" in text or "dailyLimitExceeded" in text:
        return "YouTube Data API 할당량을 초과했습니다. Google Cloud Console에서 할당량을 확인해 주세요."
    if "keyInvalid" in text or "API key not valid" in text:
        return "API 키가 올바르지 않습니다. YouTube Data API v3가 활성화된 키인지 확인해 주세요."
    if "forbidden" in text:
        return "이 영상의 댓글에 접근할 수 없습니다. 비공개 영상이거나 API 제한이 설정되었을 수 있습니다."
    return f"YouTube API 요청 중 오류가 발생했습니다: {error}"


def analyze_sentiment(text: str) -> tuple[int, str]:
    """한국어·영어 키워드와 이모지를 이용한 가벼운 사전 기반 감성 추정."""
    lowered = text.lower()
    english_tokens = re.findall(r"[a-z']+", lowered)

    positive = sum(lowered.count(word) for word in POSITIVE_KO)
    negative = sum(lowered.count(word) for word in NEGATIVE_KO)
    positive += sum(token in POSITIVE_EN for token in english_tokens)
    negative += sum(token in NEGATIVE_EN for token in english_tokens)

    positive += sum(lowered.count(emoji) for emoji in ["👍", "❤️", "❤", "😍", "🥰", "😊", "😂", "🔥", "👏", "🎉"])
    negative += sum(lowered.count(emoji) for emoji in ["👎", "😡", "🤬", "😢", "😭", "💔", "🤮"])

    # 자주 등장하는 간단한 부정 표현 보정
    negative += len(re.findall(r"안\s*(?:좋|재밌|멋|추천|행복)", lowered))
    negative += len(re.findall(r"not\s+(?:good|great|funny|nice|helpful)", lowered))

    score = int(positive - negative)
    label = "긍정" if score > 0 else "부정" if score < 0 else "중립"
    return score, label


def prepare_dataframe(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["published_at"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
    df["updated_at"] = pd.to_datetime(df["updated_at"], utc=True, errors="coerce")
    df = df.dropna(subset=["published_at"]).copy()
    df["published_at_kst"] = df["published_at"].dt.tz_convert("Asia/Seoul")
    df["date_kst"] = df["published_at_kst"].dt.date
    df["hour"] = df["published_at_kst"].dt.hour
    df["weekday"] = df["published_at_kst"].dt.weekday.map(WEEKDAY_MAP)
    df["comment_type"] = np.where(df["is_reply"], "답글", "상위 댓글")

    sentiment = df["text"].fillna("").map(analyze_sentiment)
    df["sentiment_score"] = sentiment.map(lambda x: x[0])
    df["sentiment"] = sentiment.map(lambda x: x[1])

    max_like = int(df["like_count"].max()) if not df.empty else 0
    if max_like > 0:
        df["reaction_score"] = np.log1p(df["like_count"]) / np.log1p(max_like) * 100
    else:
        df["reaction_score"] = 0.0

    df["reaction_level"] = pd.cut(
        df["reaction_score"],
        bins=[-0.1, 33.33, 66.66, 100.01],
        labels=["낮음", "보통", "높음"],
    )
    return df.sort_values("published_at_kst").reset_index(drop=True)


def tokenize_comments(texts: pd.Series, custom_stopwords: set[str]) -> list[str]:
    stopwords = DEFAULT_STOPWORDS | {word.lower() for word in custom_stopwords}
    tokens: list[str] = []

    for text in texts.fillna(""):
        cleaned = re.sub(r"https?://\S+|www\.\S+", " ", str(text).lower())
        cleaned = re.sub(r"@[A-Za-z0-9_.-]+", " ", cleaned)
        found = re.findall(r"[가-힣]{2,}|[a-z]{2,}", cleaned)
        tokens.extend(token for token in found if token not in stopwords and not token.isdigit())

    return tokens


def find_font_path(uploaded_font_bytes: bytes | None, uploaded_font_name: str | None) -> tuple[str | None, str | None]:
    """업로드 글꼴을 우선 사용하고, 없으면 Streamlit Cloud의 Nanum 후보를 탐색한다."""
    if uploaded_font_bytes and uploaded_font_name:
        suffix = Path(uploaded_font_name).suffix or ".ttf"
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp.write(uploaded_font_bytes)
        temp.close()
        return temp.name, temp.name

    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path, None
    return None, None


def make_wordcloud(tokens: list[str], font_path: str | None) -> WordCloud:
    frequencies = Counter(tokens)
    return WordCloud(
        width=1500,
        height=760,
        background_color="white",
        font_path=font_path,
        max_words=180,
        collocations=False,
        prefer_horizontal=0.9,
        margin=4,
    ).generate_from_frequencies(frequencies)


def format_number(value: int | float) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


# -----------------------------
# 화면 상단
# -----------------------------
st.title("💬 YouTube 댓글 분석기")
st.caption("유튜브 영상의 댓글 작성 추이, 좋아요 기반 반응도, 간단한 감성 분포와 워드클라우드를 분석합니다.")

secret_key = get_secret_api_key()

with st.sidebar:
    st.header("분석 설정")
    with st.form("analysis_form"):
        api_key = st.text_input(
            "YouTube Data API 키",
            value=secret_key,
            type="password",
            help="직접 입력하거나 Streamlit Secrets의 YOUTUBE_API_KEY 값을 사용할 수 있습니다.",
        )
        video_url = st.text_input(
            "유튜브 영상 링크 또는 영상 ID",
            placeholder="https://www.youtube.com/watch?v=...",
        )
        target_count = st.number_input(
            "수집할 댓글 수",
            min_value=10,
            max_value=5000,
            value=500,
            step=100,
            help="YouTube API는 요청당 최대 100개를 반환하므로 여러 번 나누어 수집합니다.",
        )
        order_label = st.radio(
            "댓글 수집 순서",
            options=["최신순", "관련도순"],
            horizontal=True,
        )
        include_replies = st.checkbox(
            "답글도 포함",
            value=False,
            help="답글을 포함하면 댓글 스레드별 추가 API 요청이 발생할 수 있습니다.",
        )
        custom_stopword_text = st.text_area(
            "추가 제외 단어",
            placeholder="쉼표로 구분: 채널명, 출연자명, 반복 단어",
            height=80,
        )
        uploaded_font = st.file_uploader(
            "워드클라우드 글꼴(선택)",
            type=["ttf", "otf", "ttc"],
            help="한국어가 네모로 보일 때 한글을 지원하는 글꼴 파일을 올려 주세요.",
        )
        submitted = st.form_submit_button("댓글 분석 시작", type="primary", use_container_width=True)

    st.markdown(
        '<p class="small-note">API 키는 화면에 표시하거나 데이터 파일에 저장하지 않습니다. 공개 앱에서는 Streamlit Secrets 사용을 권장합니다.</p>',
        unsafe_allow_html=True,
    )


# -----------------------------
# 데이터 수집
# -----------------------------
if submitted:
    video_id = extract_video_id(video_url)

    if not api_key.strip():
        st.error("YouTube Data API 키를 입력해 주세요.")
        st.stop()
    if not video_id:
        st.error("올바른 유튜브 영상 링크 또는 11자리 영상 ID를 입력해 주세요.")
        st.stop()

    progress = st.progress(0, text="YouTube API에 연결하는 중입니다.")
    status = st.empty()

    def update_progress(current: int, total: int):
        ratio = min(current / max(total, 1), 1.0)
        progress.progress(ratio, text=f"댓글 수집 중: {current:,} / {total:,}개")

    try:
        youtube = youtube_client(api_key.strip())
        video_info = get_video_info(youtube, video_id)
        rows = fetch_comments(
            youtube=youtube,
            video_id=video_id,
            target_count=int(target_count),
            order="time" if order_label == "최신순" else "relevance",
            include_replies=include_replies,
            progress_callback=update_progress,
        )
        df = prepare_dataframe(rows)

        if df.empty:
            progress.empty()
            st.warning("수집할 수 있는 공개 댓글이 없습니다.")
            st.stop()

        custom_stopwords = {
            word.strip().lower()
            for word in re.split(r"[,\n]", custom_stopword_text)
            if word.strip()
        }

        st.session_state["youtube_analysis"] = {
            "video_info": video_info,
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "df": df,
            "custom_stopwords": custom_stopwords,
            "font_bytes": uploaded_font.getvalue() if uploaded_font else None,
            "font_name": uploaded_font.name if uploaded_font else None,
            "requested_count": int(target_count),
            "include_replies": include_replies,
            "order_label": order_label,
        }
        progress.progress(1.0, text=f"분석 완료: 댓글 {len(df):,}개")
        status.success("댓글 수집과 전처리가 완료되었습니다.")
    except HttpError as error:
        progress.empty()
        status.empty()
        st.error(parse_http_error(error))
        st.stop()
    except Exception as error:
        progress.empty()
        status.empty()
        st.error(f"분석 중 오류가 발생했습니다: {error}")
        st.stop()


# -----------------------------
# 결과 화면
# -----------------------------
analysis = st.session_state.get("youtube_analysis")
if not analysis:
    st.info("왼쪽 설정에서 API 키와 영상 링크를 입력한 뒤 **댓글 분석 시작**을 눌러 주세요.")
    st.markdown(
        """
        **제공 기능**  
        - 날짜·주·월 단위 댓글 작성 추이  
        - 하루 24시간대와 요일별 댓글 분포  
        - 댓글 좋아요 수와 상대적 반응도 점수  
        - 간단한 한국어·영어 감성 분류  
        - 워드클라우드와 상위 빈도 단어  
        - 원본 분석 데이터 CSV 다운로드
        """
    )
    st.stop()

video_info = analysis["video_info"]
df = analysis["df"].copy()
video_url = analysis["video_url"]

st.markdown('<div class="video-card">', unsafe_allow_html=True)
left, right = st.columns([1, 2.2], vertical_alignment="center")
with left:
    if video_info.get("thumbnail"):
        st.image(video_info["thumbnail"], use_container_width=True)
with right:
    st.subheader(video_info["title"])
    st.write(f"**채널:** {video_info['channel']}")
    if video_info.get("published_at"):
        published = pd.to_datetime(video_info["published_at"], utc=True).tz_convert("Asia/Seoul")
        st.write(f"**영상 게시일:** {published.strftime('%Y-%m-%d %H:%M')} (KST)")
    st.caption(
        f"수집 기준: {analysis['order_label']} · "
        f"{'상위 댓글과 답글' if analysis['include_replies'] else '상위 댓글만'} · "
        f"요청 {analysis['requested_count']:,}개 / 실제 {len(df):,}개"
    )
st.markdown("</div>", unsafe_allow_html=True)

positive_ratio = (df["sentiment"] == "긍정").mean() * 100
liked_ratio = (df["like_count"] > 0).mean() * 100

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("수집 댓글", f"{len(df):,}개")
m2.metric("영상 조회 수", format_number(video_info["view_count"]))
m3.metric("평균 댓글 좋아요", f"{df['like_count'].mean():.1f}")
m4.metric("좋아요 받은 댓글", f"{liked_ratio:.1f}%")
m5.metric("긍정 추정 댓글", f"{positive_ratio:.1f}%")

st.caption("감성 분류는 키워드·이모지 기반의 간단한 추정치이며 문맥, 반어법, 신조어를 완벽하게 해석하지 못합니다.")

overview_tab, time_tab, reaction_tab, cloud_tab, data_tab = st.tabs(
    ["📌 개요", "⏱ 시간 분석", "❤️ 반응도", "☁️ 워드클라우드", "📄 데이터"]
)

with overview_tab:
    col1, col2 = st.columns([1.25, 1])

    with col1:
        st.subheader("댓글 작성 누적 추이")
        cumulative = df.sort_values("published_at_kst")[["published_at_kst"]].copy()
        cumulative["누적 댓글 수"] = np.arange(1, len(cumulative) + 1)
        fig = px.line(
            cumulative,
            x="published_at_kst",
            y="누적 댓글 수",
            labels={"published_at_kst": "작성 시각(KST)"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("감성 분포")
        sentiment_order = ["긍정", "중립", "부정"]
        sentiment_counts = (
            df["sentiment"].value_counts().reindex(sentiment_order, fill_value=0).rename_axis("감성").reset_index(name="댓글 수")
        )
        fig = px.pie(
            sentiment_counts,
            names="감성",
            values="댓글 수",
            hole=0.48,
        )
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("좋아요가 많은 댓글")
    top_overview = df.nlargest(8, "like_count")[
        ["author", "text", "like_count", "sentiment", "published_at_kst", "comment_type"]
    ].copy()
    top_overview.columns = ["작성자", "댓글", "좋아요", "감성", "작성 시각(KST)", "유형"]
    st.dataframe(
        top_overview,
        use_container_width=True,
        hide_index=True,
        column_config={
            "댓글": st.column_config.TextColumn(width="large"),
            "작성 시각(KST)": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
        },
    )

with time_tab:
    st.subheader("시간 흐름에 따른 댓글 작성 추이")
    granularity = st.selectbox(
        "집계 단위",
        options=["시간", "일", "주", "월"],
        index=1,
        key="time_granularity",
    )
    freq_map = {"시간": "h", "일": "D", "주": "W-MON", "월": "MS"}

    timeline = (
        df.set_index("published_at_kst")
        .resample(freq_map[granularity])
        .size()
        .rename("댓글 수")
        .reset_index()
    )
    fig = px.line(
        timeline,
        x="published_at_kst",
        y="댓글 수",
        markers=True,
        labels={"published_at_kst": "작성 시각(KST)"},
    )
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("하루 시간대별 분포")
        hourly = df.groupby("hour").size().reindex(range(24), fill_value=0).rename("댓글 수").reset_index()
        fig = px.bar(hourly, x="hour", y="댓글 수", labels={"hour": "시간(KST)"})
        fig.update_xaxes(dtick=1)
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("요일별 분포")
        weekday = (
            df.groupby("weekday").size().reindex(WEEKDAY_ORDER, fill_value=0).rename("댓글 수").reset_index()
        )
        fig = px.bar(weekday, x="weekday", y="댓글 수", labels={"weekday": "요일"})
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    if len(df) >= 2:
        first_time = df["published_at_kst"].min()
        last_time = df["published_at_kst"].max()
        st.caption(
            f"분석된 댓글 작성 기간: {first_time.strftime('%Y-%m-%d %H:%M')} ~ "
            f"{last_time.strftime('%Y-%m-%d %H:%M')} (KST)"
        )

with reaction_tab:
    st.subheader("댓글 반응도 분석")
    st.caption("반응도 점수는 수집된 댓글 중 최대 좋아요 수를 100점으로 두고 로그 변환한 상대 점수입니다.")

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("최대 댓글 좋아요", f"{int(df['like_count'].max()):,}")
    r2.metric("좋아요 중앙값", f"{df['like_count'].median():.1f}")
    r3.metric("반응도 평균", f"{df['reaction_score'].mean():.1f}점")
    r4.metric("반응도 높은 댓글", f"{(df['reaction_level'] == '높음').mean() * 100:.1f}%")

    c1, c2 = st.columns(2)
    with c1:
        reaction_counts = (
            df["reaction_level"].astype(str).value_counts().reindex(["낮음", "보통", "높음"], fill_value=0)
            .rename_axis("반응 수준").reset_index(name="댓글 수")
        )
        fig = px.bar(reaction_counts, x="반응 수준", y="댓글 수", title="반응도 수준별 댓글 수")
        fig.update_layout(margin=dict(l=10, r=10, t=45, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        sentiment_like = (
            df.groupby("sentiment", as_index=False)["like_count"].mean()
            .rename(columns={"sentiment": "감성", "like_count": "평균 좋아요"})
        )
        fig = px.bar(sentiment_like, x="감성", y="평균 좋아요", title="감성별 평균 좋아요")
        fig.update_layout(margin=dict(l=10, r=10, t=45, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("반응도가 높은 댓글")
    top_reactions = df.nlargest(15, ["reaction_score", "like_count"])[
        ["author", "text", "like_count", "reaction_score", "sentiment", "published_at_kst", "comment_type"]
    ].copy()
    top_reactions["reaction_score"] = top_reactions["reaction_score"].round(1)
    top_reactions.columns = ["작성자", "댓글", "좋아요", "반응도", "감성", "작성 시각(KST)", "유형"]
    st.dataframe(
        top_reactions,
        use_container_width=True,
        hide_index=True,
        column_config={
            "댓글": st.column_config.TextColumn(width="large"),
            "반응도": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f점"),
            "작성 시각(KST)": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
        },
    )

with cloud_tab:
    st.subheader("댓글 워드클라우드")
    tokens = tokenize_comments(df["text"], analysis["custom_stopwords"])

    if not tokens:
        st.warning("워드클라우드를 만들 수 있는 단어가 없습니다. 제외 단어 설정을 줄여 보세요.")
    else:
        font_path, temp_font_path = find_font_path(analysis["font_bytes"], analysis["font_name"])
        contains_korean = any(re.search(r"[가-힣]", token) for token in tokens)

        if contains_korean and not font_path:
            st.warning("한글 글꼴을 찾지 못했습니다. 왼쪽에서 TTF·OTF 한글 글꼴을 업로드해 주세요.")
        else:
            try:
                cloud = make_wordcloud(tokens, font_path)
                fig, ax = plt.subplots(figsize=(15, 7.6))
                ax.imshow(cloud, interpolation="bilinear")
                ax.axis("off")
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)
            except Exception as error:
                st.error(f"워드클라우드 생성 중 오류가 발생했습니다: {error}")
            finally:
                if temp_font_path and os.path.exists(temp_font_path):
                    try:
                        os.unlink(temp_font_path)
                    except OSError:
                        pass

        st.subheader("상위 빈도 단어")
        top_words = pd.DataFrame(Counter(tokens).most_common(30), columns=["단어", "빈도"])
        fig = px.bar(top_words.sort_values("빈도"), x="빈도", y="단어", orientation="h")
        fig.update_layout(height=720, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

with data_tab:
    st.subheader("댓글 데이터 탐색")
    f1, f2, f3 = st.columns([1.4, 1, 1])
    with f1:
        keyword = st.text_input("댓글 검색", placeholder="키워드를 입력하세요", key="data_keyword")
    with f2:
        min_likes = st.number_input(
            "최소 좋아요",
            min_value=0,
            max_value=max(int(df["like_count"].max()), 0),
            value=0,
            step=1,
            key="min_likes",
        )
    with f3:
        sentiments = st.multiselect(
            "감성",
            options=["긍정", "중립", "부정"],
            default=["긍정", "중립", "부정"],
            key="sentiment_filter",
        )

    filtered = df[df["like_count"] >= min_likes].copy()
    if keyword.strip():
        filtered = filtered[filtered["text"].str.contains(keyword.strip(), case=False, na=False, regex=False)]
    if sentiments:
        filtered = filtered[filtered["sentiment"].isin(sentiments)]
    else:
        filtered = filtered.iloc[0:0]

    display_df = filtered[
        ["published_at_kst", "author", "text", "like_count", "reaction_score", "sentiment", "comment_type"]
    ].copy()
    display_df["reaction_score"] = display_df["reaction_score"].round(1)
    display_df.columns = ["작성 시각(KST)", "작성자", "댓글", "좋아요", "반응도", "감성", "유형"]

    st.write(f"필터 결과: **{len(display_df):,}개**")
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "작성 시각(KST)": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
            "댓글": st.column_config.TextColumn(width="large"),
            "반응도": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f점"),
        },
    )

    export_df = df.copy()
    export_df["published_at_kst"] = export_df["published_at_kst"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    export_df["published_at"] = export_df["published_at"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    export_df["updated_at"] = export_df["updated_at"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    csv_bytes = export_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "전체 분석 데이터 CSV 다운로드",
        data=csv_bytes,
        file_name=f"youtube_comments_{video_info['video_id']}.csv",
        mime="text/csv",
        use_container_width=True,
    )
