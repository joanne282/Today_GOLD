"""
텔레그램 봇에 온 메시지를 확인해서 /target 명령을 처리하는 스크립트
=========================================================

[이 스크립트가 하는 일 - 큰 그림]
  텔레그램 봇은 기본적으로 "가만히 있다가 메시지가 오면 반응하는" 형태로 만들려면
  서버가 24시간 켜져 있어야 합니다 (Webhook 방식). 하지만 우리는 서버를 따로 안 두고
  GitHub Actions로만 운영하고 있으니, 대신 "폴링(Polling)" 방식을 씁니다:
  주기적으로(5분마다) "혹시 새 메시지 왔어?"라고 텔레그램에 물어보는 방식이에요.

  1. 텔레그램 서버에 "마지막으로 확인한 뒤로 새 메시지 있어?"라고 물어봄 (getUpdates)
  2. 새 메시지 중에 /target 으로 시작하는 게 있으면 명령으로 해석
  3. data/target.json 파일을 새 목표가로 갱신
  4. "설정했어요" 하고 답장을 보냄

지원 명령:
  /target                  -> 현재 설정된 목표가를 알려줌
  /target 550000           -> 목표가를 550000원으로 변경 (조건은 기존 값 유지, 기본 BELOW)
  /target 550000 이하      -> 550000원 "이하로 내려가면" 알림
  /target 700000 이상      -> 700000원 "이상으로 올라가면" 알림

환경 변수:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID   (이 chat_id로 온 메시지만 명령으로 인정 - 다른 사람이 내 봇에 말 걸어도 무시)
"""

import os
import re
import json

import requests

TARGET_PATH = os.path.join(os.path.dirname(__file__), "data", "target.json")
# 텔레그램의 getUpdates API는 "offset"이라는 숫자를 기준으로 "이 번호 이후의 메시지만 줘"
# 라고 요청할 수 있음. 매번 offset을 저장해뒀다가 다음 실행 때 이어서 물어봐야
# 같은 메시지를 여러 번 처리하는 걸 막을 수 있음. (이 파일이 그 "책갈피" 역할)
OFFSET_PATH = os.path.join(os.path.dirname(__file__), "data", "telegram_offset.txt")


def get_bot_token():
    return os.environ["TELEGRAM_BOT_TOKEN"]


def get_allowed_chat_id():
    """내 chat_id만 문자열로 반환. 이후 다른 chat_id에서 온 메시지는 전부 무시하는 데 사용.
    (내 봇의 사용자명을 누군가 알아내서 말을 걸어도, 그 사람 명령은 처리되지 않도록 하는 보안장치)"""
    return str(os.environ["TELEGRAM_CHAT_ID"])


def load_offset():
    """이전에 저장해둔 offset(책갈피)을 읽어옴. 처음 실행이면 파일이 없으니 None 반환."""
    if os.path.exists(OFFSET_PATH):
        with open(OFFSET_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return int(content) if content else None
    return None


def save_offset(offset):
    os.makedirs(os.path.dirname(OFFSET_PATH), exist_ok=True)
    with open(OFFSET_PATH, "w", encoding="utf-8") as f:
        f.write(str(offset))


def load_target_config():
    """현재 목표가 설정을 읽어옴. 파일이 없으면 빈 상태로 시작."""
    if os.path.exists(TARGET_PATH):
        with open(TARGET_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"target_price": None, "condition": "BELOW"}


def save_target_config(cfg):
    os.makedirs(os.path.dirname(TARGET_PATH), exist_ok=True)
    # indent=2: 사람이 읽기 좋게 들여쓰기해서 저장 (JSON 자체 동작에는 영향 없음)
    # ensure_ascii=False: 한글이 유니코드 escape(\uXXXX)로 안 바뀌고 그대로 저장되게 함
    with open(TARGET_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def send_message(text):
    """scrape_gold_price.py의 send_telegram_message와 동일한 역할.
    (파일이 분리되어 있어 중복 작성됨 - 나중에 공용 유틸 파일로 합쳐도 됨)"""
    token = get_bot_token()
    chat_id = get_allowed_chat_id()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
    resp.raise_for_status()


def get_updates(offset):
    """텔레그램 서버에 '새 메시지 있어?' 라고 물어보는 함수 (폴링의 핵심).

    getUpdates API: 이 봇으로 온 모든 메시지 목록을 시간순으로 반환해줌.
    offset을 넘기면 "이 번호 이상인 메시지만" 걸러서 받을 수 있음.
    """
    token = get_bot_token()
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"timeout": 0}  # long-polling 대기시간. 우리는 짧게 한 번만 확인하므로 0.
    if offset is not None:
        params["offset"] = offset
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("result", [])


# 정규표현식(regex): 문자열이 특정 패턴과 일치하는지 검사하는 방법.
# 이 패턴은 다음과 같은 형태를 모두 허용:
#   "/target"
#   "/target 550000"
#   "/target 550,000 이하"
#   "/target 700000 above"  (영어도 허용)
#
# 패턴 하나하나 뜯어보면:
#   ^/target          : 문자열이 "/target"으로 시작
#   (?:@\w+)?          : 뒤에 "@봇이름"이 붙어도 허용 (그룹채팅에서 여러 봇 구분할 때 붙는 형식)
#   (?:\s+([\d,]+))?   : 공백 + 숫자(콤마 포함) - 이게 "가격" 부분. 그룹 1번으로 캡처.
#   (?:\s+(이하|이상|below|above))? : 공백 + 조건 단어 - 그룹 2번으로 캡처.
#   \s*$               : 뒤에 공백만 있고 끝
TARGET_CMD_RE = re.compile(
    r"^/target(?:@\w+)?(?:\s+([\d,]+))?(?:\s+(이하|이상|below|above))?\s*$",
    re.IGNORECASE,
)


def handle_target_command(match, cfg):
    """/target 명령 하나를 실제로 처리하는 함수.

    match: 정규표현식이 찾아낸 결과 객체. match.group(1)이 가격, group(2)가 조건.
    cfg: 현재 목표가 설정 (dict) - 이 함수 안에서 값을 바꾸고 반환함.
    """
    price_str, cond_str = match.group(1), match.group(2)

    if not price_str:
        # "/target"만 보낸 경우 -> 현재 설정을 조회만 하고 답장
        price = cfg.get("target_price")
        condition = cfg.get("condition", "BELOW")
        if price is None:
            send_message("현재 설정된 목표가가 없어요. 예: /target 550000 이하")
        else:
            label = "이하로 내려가면" if condition == "BELOW" else "이상으로 올라가면"
            send_message(f"현재 목표가: {price:,.0f}원 ({label} 알림)")
        return cfg

    # 콤마 제거 후 숫자로 변환 (예: "550,000" -> 550000.0)
    new_price = float(price_str.replace(",", ""))

    if cond_str:
        new_condition = "BELOW" if cond_str.lower() in ("이하", "below") else "ABOVE"
    else:
        # 조건을 안 적었으면 기존 조건을 그대로 유지 (가격만 바꾸고 싶을 때 편하도록)
        new_condition = cfg.get("condition", "BELOW")

    cfg["target_price"] = new_price
    cfg["condition"] = new_condition
    save_target_config(cfg)

    label = "이하로 내려가면" if new_condition == "BELOW" else "이상으로 올라가면"
    send_message(f"목표가를 {new_price:,.0f}원으로 설정했어요. ({label} 알림)")
    return cfg


def main():
    allowed_chat_id = get_allowed_chat_id()
    offset = load_offset()
    updates = get_updates(offset)

    if not updates:
        print("새 메시지 없음.")
        return

    cfg = load_target_config()
    # 이번에 받은 메시지들 중 가장 큰 update_id를 추적해뒀다가,
    # 다음 실행 때는 "이 번호 다음부터"만 받아오도록 offset을 갱신할 것
    max_update_id = offset - 1 if offset else 0

    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])

        # message: 새 메시지, edited_message: 기존 메시지를 수정한 경우.
        # 둘 다 명령으로 인정해줌 (오타 수정했을 때도 반영되도록)
        message = update.get("message") or update.get("edited_message")
        if not message:
            continue

        chat_id = str(message.get("chat", {}).get("id"))
        text = (message.get("text") or "").strip()

        if chat_id != allowed_chat_id:
            # 내가 아닌 다른 사람이 이 봇에게 말을 건 경우 -> 무시 (보안)
            print(f"허용되지 않은 chat_id({chat_id})의 메시지는 무시합니다.")
            continue

        match = TARGET_CMD_RE.match(text)
        if match:
            cfg = handle_target_command(match, cfg)
        elif text:
            # /target 형식이 아닌 다른 메시지는 그냥 로그만 남기고 넘어감
            # (원한다면 여기에 다른 명령어를 추가로 만들 수 있음 - 예: /price 로 현재가 물어보기 등)
            print(f"처리하지 않는 메시지: {text}")

    # 마지막으로 처리한 update_id + 1 을 다음 offset으로 저장
    # (텔레그램 API 규칙: offset은 "이 번호까지는 처리 완료했다"는 확인 응답 역할도 겸함)
    save_offset(max_update_id + 1)


if __name__ == "__main__":
    main()
