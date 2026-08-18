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

> 목표가는 이제 텔레그램 명령으로도 바꿀 수 있어요. 봇에게 이렇게 메시지를 보내보세요.
> - `/target` → 현재 목표가 확인
> - `/target 550000` → 550000원으로 변경 (조건은 기존 유지)
> - `/target 550000 이하` → 550000원 이하로 내려가면 알림
> - `/target 700000 이상` → 700000원 이상으로 올라가면 알림
>
> `telegram_commands.yml` 워크플로우가 5분마다 새 메시지를 확인해서 `data/target.json`을 갱신합니다.

## 참고
- 알림 기준 가격은 "팔 때 가격"(3.75g 기준) 입니다. "살 때 가격" 기준으로 바꾸려면
  `scrape_gold_price.py`의 `check_target_and_alert` 함수에서 `budy_price`를 쓰도록 수정하면 됩니다.
