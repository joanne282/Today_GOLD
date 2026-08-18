"""
한국금거래소 금 시세 수집 + 목표가 알림 스크립트
=================================================

[이 스크립트가 하는 일 - 큰 그림]
  1. 한국금거래소의 (비공식) 내부 API를 호출해서 오늘 시세를 받아온다
  2. 받아온 시세를 data/gold_price.csv 에 한 줄 추가한다 (누적 기록 -> 나중에 그래프로 씀)
  3. 미리 정해둔 목표가와 비교해서, 조건에 맞으면 텔레그램으로 메시지를 보낸다

[다른 사이트에 적용하고 싶다면 이 순서로 보면 됩니다]
  - fetch_latest_price()      : "어디서, 어떻게 데이터를 가져오는가" - 사이트마다 이 함수만 새로 짜면 됨
  - append_to_csv()           : "가져온 데이터를 어떻게 저장하는가" - 거의 그대로 재사용 가능
  - send_telegram_message()   : "어떻게 알림을 보내는가" - 그대로 재사용 가능
  - check_target_and_alert()  : "언제 알림을 보낼지 판단하는 로직" - 조건만 바꾸면 재사용 가능
  - main()                    : 위 함수들을 순서대로 실행하는 흐름 (지휘자 역할)

환경 변수 (GitHub Actions Secrets 로 설정):
  TELEGRAM_BOT_TOKEN   : BotFather 에서 받은 토큰
  TELEGRAM_CHAT_ID     : 알림 받을 chat_id
  TARGET_PRICE         : 목표가 초기값 (data/target.json이 있으면 그게 우선됨)
  TARGET_CONDITION     : "BELOW" 또는 "ABOVE" 초기값
"""

import os
import csv
import json
import sys
from datetime import datetime, timezone, timedelta

import requests  # pip install requests 로 설치되는, HTTP 요청을 보내는 표준 라이브러리

# ── 설정값들을 파일 맨 위에 상수로 모아두면, 나중에 바꿀 때 코드 전체를 뒤질 필요 없이
#    여기 몇 줄만 보면 됩니다. (다른 사이트에 적용할 때도 이 URL만 바꾸면 되도록 설계)
API_URL = "https://apiserver.koreagoldx.co.kr/api/price/lineUp/list"

# os.path.dirname(__file__) = 이 스크립트 파일이 있는 폴더 경로
# 어디서 실행하든(로컬이든 GitHub Actions든) 항상 이 스크립트 옆의 data 폴더를 가리키게 하기 위함
CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "gold_price.csv")
TARGET_PATH = os.path.join(os.path.dirname(__file__), "data", "target.json")

# 한국 표준시(KST, UTC+9) 를 명시적으로 정의.
# GitHub Actions 서버는 기본적으로 UTC(세계표준시)로 동작하므로, 그냥 datetime.now()를 쓰면
# 한국 시간보다 9시간 느린 시각이 찍힙니다. 그래서 항상 timezone을 명시해줘야 합니다.
KST = timezone(timedelta(hours=9))


def load_target_config():
    """목표가 설정을 읽어오는 함수.

    data/target.json 파일이 있으면 그 값을 최우선으로 쓰고 (텔레그램 /target 명령으로 갱신됨),
    파일이 없으면 GitHub Secrets의 TARGET_PRICE 환경변수를 대신 씁니다.
    즉 "파일 > 환경변수" 우선순위로 설계되어 있습니다.

    Returns:
        (목표가: float 또는 None, 조건: "BELOW"/"ABOVE" 또는 None)
    """
    if os.path.exists(TARGET_PATH):
        with open(TARGET_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        price = cfg.get("target_price")
        condition = cfg.get("condition", "BELOW")
        if price is not None:
            return float(price), str(condition).upper()

    # target.json이 없거나 값이 비어있으면 환경변수를 대체 수단으로 사용
    env_price = os.environ.get("TARGET_PRICE")
    if env_price:
        return float(env_price), os.environ.get("TARGET_CONDITION", "BELOW").upper()

    return None, None


def fetch_latest_price():
    """한국금거래소 API를 호출해서 가장 최근 시세를 가져오는 함수.

    ★★★ 다른 사이트에 적용할 때 이 함수를 통째로 새로 짜면 됩니다 ★★★

    [사이트마다 API를 찾는 방법 - 일반적인 절차]
      1. 크롬/엣지 브라우저에서 시세 페이지를 열고 F12(개발자도구) → Network 탭을 켠다
      2. 페이지를 새로고침한다
      3. Network 탭에 뜨는 요청들 중, 응답이 JSON 형태인 것을 찾는다
         (Type 열이 "xhr" 또는 "fetch"인 것들 위주로 확인)
      4. 그 요청을 클릭하면 오른쪽에 Request URL, Method(GET/POST), Headers, 요청 Body가 보임
      5. 그 정보를 그대로 아래 requests.post(...) / requests.get(...) 코드에 옮기면 됨
      6. 응답(Response) 탭에서 실제 JSON 구조를 보고, 원하는 값이 어떤 key에 들어있는지 확인

    [이 함수의 동작 방식]
      - API_URL로 POST 요청을 보내면서, body에 {"srchDt": "1M", "type": "Au"}를 함께 보냄
        (srchDt: 조회 기간, type: "Au"=금(Gold), 다른 사이트라면 이 파라미터 이름/값이 다를 것)
      - 응답으로 날짜별 시세 리스트가 오는데, 그중 가장 최근 날짜 데이터를 골라서 반환

    ⚠️ 이 API는 한국금거래소가 공식적으로 공개한 게 아니라 내부적으로 쓰는 것을
       커뮤니티에서 역으로 찾아낸 것입니다. 그래서:
       - 사이트가 개편되면 이 URL/구조가 바뀌어 동작하지 않을 수 있습니다
       - 응답의 실제 필드명(buyPrice 등)이 아래 코드와 다를 수 있어서, 처음 실행 시
         에러가 나면 print(data)로 실제 응답을 한번 찍어보고 필드명을 맞춰줘야 합니다
    """
    # HTTP 요청 헤더: 브라우저인 척(User-Agent) 위장해야 막히지 않는 사이트가 많음.
    # Referer는 "이 요청을 어느 페이지에서 보냈는지"를 알려주는 값으로,
    # 일부 사이트는 이게 없으면 요청을 차단하기도 함.
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Referer": "https://www.koreagoldx.co.kr/",
    }
    # 요청 본문(body). 이 API는 "최근 1개월치 데이터를 줘" 라고 요청하는 것.
    # 만약 이 값이 안 통하면 "ALL"(전체 기간)로 바꿔서 재시도해볼 수 있음.
    body = {"srchDt": "1M", "type": "Au"}

    # requests.post(): POST 방식으로 HTTP 요청을 보내는 함수.
    #   url, json=본문, headers=헤더, timeout=최대 대기시간(초) 를 인자로 넘김
    #   timeout을 꼭 걸어두는 게 좋음 - 안 그러면 서버 응답이 없을 때 무한정 멈춰있을 수 있음
    resp = requests.post(API_URL, json=body, headers=headers, timeout=15)

    # raise_for_status(): 응답 코드가 200번대(성공)가 아니면 에러를 발생시켜줌
    # (예: 403 Forbidden, 500 서버에러 등) - 이게 없으면 실패해도 조용히 넘어가서 디버깅이 어려움
    resp.raise_for_status()

    # 응답 본문을 JSON(파이썬 dict/list)으로 변환
    data = resp.json()

    # 응답이 리스트로 바로 오는 경우와, {"data": [...]} 처럼 감싸서 오는 경우 둘 다 대응.
    # 실제로 받아본 뒤 이 구조가 다르면 여기를 수정해야 함.
    rows = data if isinstance(data, list) else data.get("data") or data.get("list") or []
    if not rows:
        # 데이터가 하나도 없으면, 여기서 바로 에러를 던져서 main()에서 잡아 로그를 남기게 함
        raise ValueError(f"API 응답에서 시세 데이터를 찾을 수 없습니다: {data}")

    def _get_date(r):
        """한 줄의 데이터(dict)에서 날짜 값을 꺼내는 헬퍼 함수.
        실제 API 응답의 key 이름을 모르니, 흔히 쓰이는 후보들을 순서대로 시도해봄."""
        for k in ("date", "srchDt", "regDt", "baseDt"):
            if k in r:
                return r[k]
        return ""

    # 날짜순으로 정렬해서, 맨 마지막(가장 최근) 데이터를 사용
    rows_sorted = sorted(rows, key=_get_date)
    latest = rows_sorted[-1]

    def _get(r, keys):
        """여러 후보 key 이름 중 실제로 존재하는 값을 찾아 반환하는 헬퍼 함수.
        이런 식으로 짜두면, 나중에 실제 필드명을 확인했을 때 여기 리스트에 하나만 추가하면 됨."""
        for k in keys:
            if k in r and r[k] not in (None, ""):
                return r[k]
        return None

    buy_price = _get(latest, ["buyPrice", "sellPrc", "buyPrc", "askPrice"])
    sell_price = _get(latest, ["sellPrice", "buyPrc2", "sellPrc2", "bidPrice"])
    date_val = _get_date(latest)

    # 호출한 쪽(main)에서 원본 데이터(raw)도 확인할 수 있게 함께 반환
    # -> 에러 디버깅할 때 print(raw) 해보면 실제 구조를 바로 확인 가능
    return date_val, buy_price, sell_price, latest


def append_to_csv(date_val, buy_price, sell_price):
    """가져온 시세 한 줄을 CSV 파일 맨 끝에 추가하는 함수.

    CSV(Comma-Separated Values)는 엑셀로도 열리는 아주 단순한 표 형식의 텍스트 파일.
    여기서는 "수집시각, 기준일자, 살때가, 팔때가" 4개 열을 가진 표를 계속 쌓아나감.
    """
    # 파일이 아직 없으면 "새로 만드는 것"이므로, 맨 처음에 헤더(컬럼 이름) 줄을 써줘야 함
    is_new_file = not os.path.exists(CSV_PATH)

    # exist_ok=True: 폴더가 이미 있어도 에러 내지 않고 넘어감
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)

    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    # ── 중복 저장 방지 로직 ──
    # 만약 API가 "오늘 하루치"만 주는 게 아니라 어제 데이터를 또 줄 수도 있으니,
    # 마지막 줄의 날짜와 이번에 받은 날짜가 같으면 다시 기록하지 않도록 방어.
    if not is_new_file:
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            last_line = None
            # CSV를 한 줄씩 읽으면서 계속 덮어쓰다 보면, 반복문이 끝났을 때
            # last_line에는 자연스럽게 "마지막 줄"이 남게 됨 (파일이 커지면 비효율적이지만
            # 이 정도 크기의 파일에서는 문제없음)
            for last_line in csv.reader(f):
                pass
        if last_line and len(last_line) >= 2 and last_line[1] == str(date_val):
            print("이미 기록된 날짜입니다. CSV에 추가하지 않습니다.")
            return

    # "a" 모드 = append(추가) 모드. 파일 내용을 지우지 않고 맨 뒤에 이어서 씀.
    # newline="" 은 윈도우에서 줄바꿈이 이상하게 두 번 들어가는 걸 방지하는 관례적인 설정.
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(["수집시각(KST)", "기준일자", "살때가", "팔때가"])
        writer.writerow([now_kst, date_val, buy_price, sell_price])


def send_telegram_message(text):
    """텔레그램 봇 API를 이용해 나에게 메시지를 보내는 함수.

    텔레그램 봇 API는 아주 단순해서, 그냥 아래 URL 형식으로 POST 요청 한 번만 보내면 끝.
      https://api.telegram.org/bot<봇토큰>/sendMessage

    다른 알림 수단(이메일, 카카오톡, 디스코드 등)으로 바꾸고 싶다면
    이 함수 하나만 그 서비스의 API 방식으로 바꿔치기하면 됩니다.
    """
    # os.environ["..."] 은 해당 환경변수가 없으면 바로 에러가 남 (KeyError)
    # -> 텔레그램 설정이 안 되어 있는데 실수로 이 함수가 호출되면 바로 알아챌 수 있게 하기 위함
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
    resp.raise_for_status()


def check_target_and_alert(buy_price, sell_price):
    """현재 시세와 목표가를 비교해서, 조건에 맞으면 알림을 보내는 함수 (판단 로직)."""
    target_price, condition = load_target_config()
    if target_price is None:
        # 목표가가 아직 설정 안 되어 있으면 그냥 조용히 넘어감 (에러 아님)
        print("목표가가 설정되지 않아 알림 체크를 건너뜁니다. (data/target.json 또는 TARGET_PRICE)")
        return

    # 알림 기준은 "살 때 가격"(내가 금을 살 때 지불하는 가격) 기준으로 판단.
    # 만약 "팔 때 가격" 기준으로 바꾸고 싶으면 아래 줄을 sell_price로 바꾸면 됨.
    current = float(sell_price)

    # 조건이 BELOW면 "목표가 이하로 떨어졌는지", ABOVE면 "목표가 이상으로 올랐는지" 확인
    hit = (condition == "BELOW" and current <= target_price) or (
        condition == "ABOVE" and current >= target_price
    )

    if hit:
        direction = "이하로 내려갔어요" if condition == "BELOW" else "이상으로 올라갔어요"
        # f-string 안의 :,.0f 는 "천단위 콤마를 찍고 소수점 없이" 숫자를 표시하는 서식.
        # 예: 550000.0 -> "550,000"
        msg = (
            f"🔔 금 시세 알림\n"
            f"현재가(살때, 3.75g): {current:,.0f}원\n"
            f"목표가 {target_price:,.0f}원 {direction}."
        )
        send_telegram_message(msg)
        print("알림 전송 완료.")
    else:
        print(f"목표가 미도달. 현재가 {current:,.0f}원 / 목표가 {target_price:,.0f}원 ({condition})")


def main():
    """스크립트가 실제로 실행될 때 처음부터 끝까지 흐르는 순서를 정의하는 함수.
    (GitHub Actions가 이 스크립트를 실행하면 결국 이 main() 함수가 호출됨)
    """
    try:
        date_val, buy_price, sell_price, raw = fetch_latest_price()
    except Exception as e:
        # 어떤 이유로든(네트워크 오류, API 구조 변경 등) 시세 조회에 실패하면
        # 여기서 잡아서 에러 메시지를 출력하고, 비정상 종료 코드(1)로 끝냄.
        # -> GitHub Actions 화면에서 이 워크플로우가 "실패"로 빨갛게 표시되어 바로 알아챌 수 있음
        print(f"시세 조회 실패: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"기준일자: {date_val}, 살때가: {buy_price}, 팔때가: {sell_price}")
    append_to_csv(date_val, buy_price, sell_price)

    # buy_price를 못 가져왔으면(None) 알림 체크 자체가 의미 없으니 건너뜀
    if buy_price is not None:
        try:
            check_target_and_alert(buy_price, sell_price)
        except KeyError as e:
            # 텔레그램 토큰/chat_id가 설정 안 되어 있으면 여기서 걸림.
            # (CSV 저장까지는 이미 끝났으니, 알림만 못 보내는 상황)
            print(f"텔레그램 환경변수가 없어 알림을 건너뜁니다: {e}")


# 이 스크립트를 "python scrape_gold_price.py" 처럼 직접 실행했을 때만 main()이 호출됨.
# (다른 파일에서 import해서 함수만 가져다 쓸 때는 자동으로 실행되지 않게 하는 파이썬의 관례)
if __name__ == "__main__":
    main()
