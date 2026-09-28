import streamlit as st
from openai import OpenAI

# 페이지 기본 설정
st.set_page_config(page_title="의사 선생님과의 대화", page_icon="🩺")

st.title("🩺 친절한 의사 선생님과의 상담")
st.caption("궁금한 건강 질문이나 증상을 편하게 물어보세요.")

# 1. API 키 확인 및 OpenAI 클라이언트 설정
if "CLAUDE_API_KEY" not in st.secrets:
    st.error("API 키 설정이 필요합니다. .streamlit/secrets.toml 파일에 CLAUDE_API_KEY를 등록해주세요.")
    st.stop()

# Anthropic API 호환성을 위한 client 설정
client = OpenAI(
    api_key=st.secrets["CLAUDE_API_KEY"],
    base_url="https://api.anthropic.com/v1/"
)

# 2. 의사 선생님 페르소나 설정
SYSTEM_PROMPT = {
    "role": "system",
    "content": "너는 환자에게 설명하는 친절한 의 선생님이야. 어려운 말은 쉬운 말로 바꿔 주고, 반드시 순수 한국어로만 답해"
}

# 3. 대화 내역 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 4. 이전 대화 기록 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# 5. 사용자 입력 및 처리
if prompt := st.chat_input("의사 선생님께 물어볼 내용을 입력하세요..."):
    # 사용자 메시지 표시
    with st.chat_message("user"):
        st.write(prompt)
    
    st.session_state.messages.append({"role": "user", "content": prompt})

    # AI 응답 생성
    with st.chat_message("assistant"):
        try:
            api_messages = [SYSTEM_PROMPT] + st.session_state.messages

            response = client.chat.completions.create(
                model="claude-3-5-sonnet-20241022",
                messages=api_messages,
                stream=True
            )

            full_response = st.write_stream(response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except Exception as e:
            # 디버깅용: 디버그 모드 시 실제 오류 메시지를 함께 확인
            st.error(f"디버그 오류 정보: {e}")
            st.warning("의사 선생님과 연결 중에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.")
