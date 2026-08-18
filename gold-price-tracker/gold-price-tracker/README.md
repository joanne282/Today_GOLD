# 금 시세 트래커

한국금거래소 시세를 1시간마다 자동 수집하고, 목표가에 도달하면 텔레그램으로 알림을 보내고,
Streamlit 웹앱에서 그래프로 확인할 수 있는 프로젝트입니다.

## 구성
- `scrape_gold_price.py`: 시세 수집 + CSV 저장 + 텔레그램 알림
- `handle_telegram_commands.py`: 텔레그램 `/target` 명령으로 목표가 변경
- `.github/workflows/gold_price.yml`: 1시간마다 시세 자동 수집
- `.github/workflows/telegram_commands.yml`: 5분마다 텔레그램 명령 확인
- `app.py`: Streamlit 그래프 웹앱
- `data/gold_price.csv`: 누적 저장되는 시세 데이터 (자동 생성됨)
- `data/target.json`: 현재 목표가/조건 (텔레그램 명령으로 갱신됨)

## 설정 순서

### 1. GitHub에 리포지토리 만들기
1. github.com에서 새 리포지토리 생성 (Public이어도, Private이어도 상관없음)
2. 이 폴더의 파일들을 그대로 업로드 (또는 git push)

### 2. GitHub Secrets 등록
리포지토리 → Settings → Secrets and variables → Actions → New repository secret
아래 4개를 등록하세요.

| Secret 이름 | 값 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather에게 받은 토큰 |
| `TELEGRAM_CHAT_ID` | 알림 받을 chat_id |
| `TARGET_PRICE` | (선택) 목표가 초기값. `data/target.json`이 있으면 이 값보다 우선됩니다 |
| `TARGET_CONDITION` | (선택) `BELOW` 또는 `ABOVE` 초기값 |

> 목표가는 이제 텔레그램 명령으로도 바꿀 수 있어요. 봇에게 이렇게 메시지를 보내보세요.
> - `/target` → 현재 목표가 확인
> - `/target 550000` → 550000원으로 변경 (조건은 기존 유지)
> - `/target 550000 이하` → 550000원 이하로 내려가면 알림
> - `/target 700000 이상` → 700000원 이상으로 올라가면 알림
>
> `telegram_commands.yml` 워크플로우가 5분마다 새 메시지를 확인해서 `data/target.json`을 갱신합니다.

### 3. 동작 확인
- 리포지토리 → Actions 탭 → "Gold Price Tracker" → "Run workflow" 버튼으로 수동 실행해서
  정상적으로 도는지 먼저 확인하세요.
- `data/gold_price.csv` 파일이 커밋되면 정상 동작하는 것입니다.
- 실패하면 Actions 로그에서 에러 메시지를 확인하세요. 특히 API 응답 구조가 실제와 달라서
  `fetch_latest_price()` 함수의 필드명(`buyPrice`, `sellPrice` 등)을 조정해야 할 수도 있습니다.

### 4. Streamlit Cloud에 배포
1. https://streamlit.io/cloud 접속, GitHub 계정으로 로그인
2. "New app" → 방금 만든 리포지토리 선택 → Main file은 `app.py` 지정 → Deploy
3. 배포되면 생기는 URL을 폰 브라우저 즐겨찾기에 등록해두면 언제든 그래프 확인 가능

## 참고
- 한국금거래소는 공식 공개 API가 없어서, 커뮤니티에 알려진 내부 API
  (`apiserver.koreagoldx.co.kr`)를 사용합니다. 비공식 API이기 때문에 사이트가 개편되면
  응답 구조가 바뀌어 스크립트 수정이 필요할 수 있습니다.
- 알림 기준 가격은 "살 때 가격"(3.75g 기준) 입니다. "팔 때 가격" 기준으로 바꾸려면
  `scrape_gold_price.py`의 `check_target_and_alert` 함수에서 `sell_price`를 쓰도록 수정하면 됩니다.
