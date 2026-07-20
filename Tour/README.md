# 나만의 지역 여행 코스

한국관광공사의 **국문 관광정보 서비스_GW(KorService2)** OpenAPI를 이용해 지역별 맞춤 여행 경로를 추천하는 Streamlit 웹앱입니다.

## 주요 기능

- 자연어 지역명으로 법정동 시도·시군구 코드 검색
- 법정동 코드 기반 관광정보 수집
- 신분류 코드 기반 관광지 유형 보강
- 여행 취향·동행 유형·거리·정보 완성도를 반영한 추천 점수
- 최근접 이웃 및 2-opt 기반 방문 순서 최적화
- 여행 기간별 일정 분배와 음식점 삽입
- Folium 지도, 날짜별 관광지 카드, CSV 다운로드

## 1. 한국관광공사 API 활용 신청

1. 공공데이터포털에 로그인합니다.
2. `한국관광공사_국문 관광정보 서비스_GW`를 검색합니다.
3. 활용 신청을 누르고 개발계정을 발급받습니다.
4. 마이페이지에서 일반 인증키의 **Decoding 키**를 확인합니다.
5. 신청 직후에는 인증 정보가 반영되는 데 시간이 걸릴 수 있습니다.

앱은 인코딩 키를 입력한 경우에도 한 번 디코딩한 뒤 요청하도록 작성되어 있지만, 가능하면 공공데이터포털에서 제공하는 Decoding 키 사용을 권장합니다.

## 2. 로컬 API 키 설정

`.streamlit/secrets.toml.example` 파일을 복사하여 `.streamlit/secrets.toml`로 이름을 바꾸고 키를 입력합니다.

```toml
KTO_API_KEY = "발급받은_API_키"
```

실제 `secrets.toml`은 GitHub에 올리지 마세요. 필요하면 `.gitignore`에 다음을 추가합니다.

```gitignore
.streamlit/secrets.toml
__pycache__/
*.pyc
```

## 3. 로컬 실행

Python 3.10 이상을 권장합니다.

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

패키지 설치와 실행:

```bash
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 일반적으로 `http://localhost:8501`이 열립니다.

## 4. GitHub 업로드

다음 파일을 저장소에 올립니다.

```text
travel-route-app/
├── app.py
├── requirements.txt
├── README.md
└── .streamlit/
    ├── config.toml
    └── secrets.toml.example
```

실제 API 키가 들어 있는 `.streamlit/secrets.toml`은 업로드하지 않습니다.

## 5. Streamlit Community Cloud 배포

1. GitHub에 새 저장소를 만들고 프로젝트 파일을 푸시합니다.
2. Streamlit Community Cloud에 로그인합니다.
3. `Create app` 또는 `New app`을 선택합니다.
4. GitHub 저장소, 브랜치, 진입 파일 `app.py`를 선택합니다.
5. App settings의 Secrets에 다음을 입력합니다.

```toml
KTO_API_KEY = "발급받은_API_키"
```

6. Deploy를 누릅니다.

## 6. 앱 사용 방법

1. `서울 종로구`, `부산 해운대구`, `강릉시`, `제주시`처럼 지역을 입력합니다.
2. 처음 추천 버튼을 눌렀을 때 여러 법정동 후보가 나오면 정확한 지역을 선택합니다.
3. 여행 기간, 하루 방문 수, 이동 수단, 취향 등을 설정합니다.
4. 다시 `여행 코스 추천`을 누릅니다.
5. 지도, 날짜별 일정, 표를 확인하고 CSV를 다운로드합니다.

## 7. 자주 발생하는 오류

### API 키가 설정되지 않았습니다

- 로컬: `.streamlit/secrets.toml` 파일명과 `KTO_API_KEY` 철자를 확인합니다.
- Streamlit Cloud: App settings → Secrets에 키를 등록합니다.

### API 키가 유효하지 않습니다

- 공공데이터포털에서 활용 신청이 승인되었는지 확인합니다.
- 신청 직후라면 잠시 뒤 다시 시도합니다.
- 일반 인증키의 Decoding 키를 사용해 봅니다.
- 키 앞뒤에 따옴표 외의 공백이나 줄바꿈이 없는지 확인합니다.

### 검색 결과가 없습니다

- `종로구` 대신 `서울 종로구`처럼 입력해 봅니다.
- 시군구보다 넓은 시도 전체를 선택합니다.
- 관광공사 데이터에 주소 또는 좌표가 없는 장소는 경로 계산에서 제외됩니다.
- 최대 이동 거리를 늘려 봅니다.

### 호출 한도 초과

개발계정은 호출량 제한이 있습니다. 앱은 동일 요청을 캐시하고 최종 선택 관광지만 상세 조회하지만, 이용자가 많으면 운영계정 트래픽 증설 신청이 필요할 수 있습니다.

### 지도 경로가 실제 도로와 다릅니다

이 앱은 별도의 유료 길찾기 API를 사용하지 않고 하버사인 공식의 직선거리를 이용합니다. 지도 선과 예상 이동시간은 참고용이며 실제 도로·대중교통 경로와 다를 수 있습니다.

## 8. 데이터 이용 시 주의사항

- 추천 점수는 앱 내부 알고리즘이며 실제 평점이나 방문자 수가 아닙니다.
- 관광지 운영시간과 휴무일은 누락되거나 변경될 수 있으므로 방문 전 공식 홈페이지를 확인하세요.
- 관광공사 이미지의 저작권 구분과 이용 조건을 확인하고, 허용되지 않은 방식으로 재사용하지 마세요.
