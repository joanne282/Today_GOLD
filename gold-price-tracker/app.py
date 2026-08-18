"""
Streamlit 그래프 확인용 웹앱
============================

[이 파일이 하는 일]
  GitHub Actions가 계속 쌓아둔 data/gold_price.csv 파일을 읽어서
  숫자 표(테이블)와 꺾은선 그래프로 예쁘게 보여주는 웹페이지.

  Streamlit은 "HTML/CSS를 몰라도 파이썬 코드만으로 웹페이지를 만들 수 있게 해주는" 도구.
  st.제목(...) 처럼 쓰면 그게 그대로 화면 요소가 됨.

  실행 방법:
    로컬에서 테스트: 터미널에서 `streamlit run app.py`
    배포: Streamlit Community Cloud에 이 리포지토리를 연결하면 자동으로 이 파일을 실행해줌
"""

import pandas as pd  # 표(테이블) 형태 데이터를 다루는 라이브러리. CSV 읽기/가공에 필수
import streamlit as st

# set_page_config: 브라우저 탭 제목, 아이콘, 레이아웃 폭 등을 설정. 반드시 다른 st. 호출보다 먼저 와야 함.
st.set_page_config(page_title="금 시세 트래커", page_icon="🪙", layout="centered")

CSV_PATH = "data/gold_price.csv"

st.title("🪙 한국금거래소 금 시세")

try:
    # pandas의 read_csv: CSV 파일을 통째로 읽어서 DataFrame(표) 객체로 만들어줌
    df = pd.read_csv(CSV_PATH, encoding="utf-8")
except FileNotFoundError:
    # 아직 GitHub Actions가 한 번도 안 돌았으면 이 파일이 없을 수 있음 -> 친절한 안내 메시지
    st.warning("아직 수집된 데이터가 없어요. GitHub Actions가 한 번 이상 실행된 후에 데이터가 쌓입니다.")
    st.stop()  # 여기서 스크립트 실행을 멈춤 (아래 코드는 실행 안 됨)

# CSV의 "수집시각" 열은 원래 그냥 문자열(텍스트)로 읽힘. 그래프에서 시간축으로 쓰려면
# pandas가 이해하는 "날짜/시간" 타입으로 변환해줘야 함.
df["수집시각(KST)"] = pd.to_datetime(df["수집시각(KST)"])

# 시간순으로 정렬 (CSV에 이미 순서대로 쌓이긴 하지만, 혹시 몰라 한번 더 보장)
df = df.sort_values("수집시각(KST)")

# .iloc[-1] : 표의 마지막 줄(=가장 최근 데이터)을 가져옴
latest = df.iloc[-1]

# st.columns(2): 화면을 가로로 2칸 나눠서 배치. col1, col2 각각에 원하는 요소를 넣을 수 있음.
col1, col2 = st.columns(2)
# st.metric: 큰 숫자 하나를 강조해서 보여주는 카드형 위젯 (제목 + 값)
# f"{...:,.0f}" 서식은 천단위 콤마를 찍어줌 (예: 550000 -> "550,000")
col1.metric("현재 살때가 (3.75g)", f"{latest['살때가']:,.0f} 원")
col2.metric("현재 팔때가 (3.75g)", f"{latest['팔때가']:,.0f} 원")

st.caption(f"마지막 업데이트: {latest['수집시각(KST)']}")

# st.line_chart: 표의 특정 열들을 자동으로 꺾은선 그래프로 그려주는 함수.
# set_index로 "수집시각"을 x축(가로축)으로 지정하고, 나머지 두 열을 y축 값으로 사용.
st.line_chart(
    df.set_index("수집시각(KST)")[["살때가", "팔때가"]],
)

# st.expander: 클릭하면 펼쳐지는 접이식 영역. 평소엔 숨겨뒀다가 필요할 때만 전체 데이터를 봄.
with st.expander("전체 데이터 보기"):
    st.dataframe(df.sort_values("수집시각(KST)", ascending=False), use_container_width=True)
