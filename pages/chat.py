import streamlit as st
from openai import OpenAI

# 페이지 기본 설정 (타이틀 및 아이콘)
st.set_page_config(page_title="의사 선생님과의 대화", page_icon="🩺")

st.title("🩺 친절한 의사 선생님과의 상담")
st.caption("궁금한 건강 질문이나 증상을 편하게 물어보세요.")

# 1. API 키 확인 및 OpenAI 클라이언트 설정
# Streamlit secrets에서 CLAUDE_API_KEY를 불러옵니다.
if "CLAUDE_API_KEY" not in st.secrets:
    st.error("API 키 설정이 필요합니다. .streamlit/secrets.toml 파일에 CLAUDE_API_KEY를 등록해주세요.")
    st.stop()

# Claude API를 openai 라이브러리 인터페이스로 연결합니다.
client = OpenAI(
    api_key=st.secrets["CLAUDE_API_KEY"],
    base_url="https://api.anthropic.com/v1/"
)

# 2. 의사 선생님의 페르소나(시스템 프롬프트) 설정
# 이 내용은 화면에 표시되지 않고 AI의 역할 정의용으로만 사용됩니다.
SYSTEM_PROMPT = {
    "role": "system",
    "content": "너는 환자에게 설명하는 친절한 의 선생님이야. 어려운 말은 쉬운 말로 바꿔 주고, 반드시 순수 한국어로만 답해"
}

# 3. 대화 내역(세션 상태) 초기화
# 이전 대화를 기억할 수 있도록 Streamlit의 session_state를 사용합니다.
if "messages" not in st.session_state:
    st.session_state.messages = []

# 4. 이전 대화 기록을 화면에 말풍선으로 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# 5. 사용자 메시지 입력 및 처리
if prompt := st.chat_input("의사 선생님께 물어볼 내용을 입력하세요..."):
    # 사용자가 입력한 메시지를 화면에 말풍선으로 표시
    with st.chat_message("user"):
        st.write(prompt)
    
    # 대화 기록에 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": prompt})

    # AI 응답 생성 및 표시
    with st.chat_message("assistant"):
        try:
            # 시스템 프롬프트를 포함하여 전체 대화 내역을 API 전달용 목록으로 구성
            api_messages = [SYSTEM_PROMPT] + st.session_state.messages

            # Claude API 호출 (실시간 스트리밍 답변 요청)
            response = client.chat.completions.create(
                model="claude-3-5-sonnet-20241022",
                messages=api_messages,
                stream=True
            )

            # 답변이 실시간으로 흘러나오도록 출력
            full_response = st.write_stream(response)
            
            # 생성된 AI 답변을 대화 기록에 저장
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except Exception:
            # API 요청 실패 등 오류 발생 시 빨간 오류 창 대신 사용자 친화적 한국어 안내 문구 출력
            st.warning("의사 선생님과 연결 중에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.")
