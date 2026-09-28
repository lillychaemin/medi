import streamlit as st
from anthropic import Anthropic

# 페이지 기본 설정
st.set_page_config(page_title="의사 선생님과의 대화", page_icon="🩺")

st.title("🩺 친절한 의사 선생님과의 상담")
st.caption("궁금한 건강 질문이나 증상을 편하게 물어보세요.")

# 1. API 키 확인 및 Anthropic 클라이언트 설정
if "CLAUDE_API_KEY" not in st.secrets:
    st.error("API 키 설정이 필요합니다. .streamlit/secrets.toml 파일에 CLAUDE_API_KEY를 등록해주세요.")
    st.stop()

client = Anthropic(api_key=st.secrets["CLAUDE_API_KEY"])

# 2. 의사 선생님 페르소나 설정 (Anthropic SDK에서는 system 매개변수로 따로 전달합니다)
SYSTEM_PROMPT = "너는 환자에게 설명하는 친절한 의 선생님이야. 어려운 말은 쉬운 말로 바꿔 주고, 반드시 순수 한국어로만 답해"

# 3. 대화 내역 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 4. 이전 대화 기록 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# 5. 사용자 입력 및 처리
if prompt := st.chat_input("의사 선생님께 물어볼 내용을 입력하세요..."):
    with st.chat_message("user"):
        st.write(prompt)
    
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        try:
            # Anthropic 스트리밍 API 호출
            with client.messages.stream(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                system=SYSTEM_PROMPT,
                messages=st.session_state.messages
            ) as stream:
                full_response = st.write_stream(stream.text_stream)
            
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except Exception:
            st.warning("의사 선생님과 연결 중에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.")
