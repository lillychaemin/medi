import streamlit as st
from anthropic import Anthropic

# 페이지 기본 설정
st.set_page_config(page_title="의사 선생님과의 대화", page_icon="🩺", layout="centered")

# 병원이 연상되는 차분한 블루·화이트 디자인 (기존 기능에는 영향 없음)
st.markdown(
    """
    <style>
    /* 전체 페이지 배경 */
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(ellipse at 8% 8%, rgba(111, 190, 255, 0.22), transparent 36%),
            radial-gradient(ellipse at 92% 18%, rgba(99, 220, 207, 0.15), transparent 32%),
            linear-gradient(145deg, #f5fbff 0%, #edf6ff 48%, #f8fcff 100%);
    }

    [data-testid="stHeader"] {
        background: rgba(245, 251, 255, 0.72);
    }

    .block-container {
        max-width: 900px;
        padding-top: 2.4rem;
        padding-bottom: 3rem;
    }

    /* 상단 제목 영역 */
    h1 {
        color: #124a83 !important;
        letter-spacing: -0.04em;
        font-weight: 800 !important;
    }

    [data-testid="stCaptionContainer"] {
        color: #52718f;
        font-size: 1rem;
    }

    /* 은은한 병원 안내 배너 */
    .clinic-banner {
        display: flex;
        align-items: center;
        gap: 14px;
        margin: 1rem 0 1.5rem 0;
        padding: 18px 20px;
        border: 1px solid rgba(116, 174, 224, 0.35);
        border-radius: 20px;
        background: rgba(255, 255, 255, 0.78);
        box-shadow: 0 8px 26px rgba(38, 104, 158, 0.08);
        color: #315b7f;
    }
    .clinic-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        flex: 0 0 48px;
        width: 48px;
        height: 48px;
        border-radius: 15px;
        background: linear-gradient(145deg, #2f91f4, #1766c2);
        color: white;
        font-size: 1.65rem;
        box-shadow: 0 5px 13px rgba(36, 119, 211, 0.22);
    }
    .clinic-banner strong {
        display: block;
        color: #164c80;
        font-size: 1rem;
        margin-bottom: 3px;
    }
    .clinic-banner span {
        font-size: 0.9rem;
        line-height: 1.5;
    }

    /* 채팅 메시지 카드 */
    [data-testid="stChatMessage"] {
        border: 1px solid rgba(138, 183, 222, 0.24);
        border-radius: 18px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.75rem;
        background: rgba(255, 255, 255, 0.82);
        box-shadow: 0 5px 18px rgba(43, 93, 139, 0.045);
    }

    /* 입력창 */
    [data-testid="stChatInput"] {
        border: 1px solid #c5def4;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 6px 22px rgba(39, 105, 163, 0.10);
    }
    [data-testid="stChatInput"] textarea {
        color: #173d61;
    }

    /* 일반 버튼과 경고창 */
    .stButton > button {
        border-radius: 12px;
    }
    [data-testid="stAlert"] {
        border-radius: 14px;
    }

    /* 좁은 화면에서도 여백 유지 */
    @media (max-width: 640px) {
        .block-container {
            padding-top: 1.4rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        .clinic-banner {
            padding: 14px;
        }
    }
    </style>
    <div class="clinic-banner">
        <div class="clinic-icon">✚</div>
        <div>
            <strong>편안한 건강 상담 공간</strong>
            <span>궁금한 점을 차근차근 적어 주세요. 이해하기 쉬운 설명을 도와드릴게요.</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.title("🩺 친절한 의사 선생님과의 상담")
st.caption("궁금한 건강 질문이나 증상을 편하게 물어보세요.")

# 1. API 키 확인 및 Anthropic 클라이언트 설정
if "CLAUDE_API_KEY" not in st.secrets:
    st.error("API 키 설정이 필요합니다. .streamlit/secrets.toml 파일에 CLAUDE_API_KEY를 등록해주세요.")
    st.stop()

client = Anthropic(api_key=st.secrets["CLAUDE_API_KEY"])

# 2. 의사 선생님 페르소나 설정
SYSTEM_PROMPT = "너는 환자에게 설명하는 친절한 의사 선생님이야. 어려운 말은 쉬운 말로 바꿔 주고, 반드시 순수 한국어로만 답해"

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
            # 기존 Anthropic 스트리밍 API 호출 유지
            with client.messages.stream(
                model="claude-sonnet-5",  # 기존 모델명 유지
                max_tokens=1000,
                system=SYSTEM_PROMPT,
                messages=st.session_state.messages,
            ) as stream:
                full_response = st.write_stream(stream.text_stream)

            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except Exception:
            st.warning("의사 선생님과 연결 중에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.")

# 건강 상담 관련 안내
st.markdown(
    """
    <div style="margin-top: 1.4rem; padding: 12px 15px; border-radius: 14px;
                background: rgba(224, 241, 255, 0.72); color: #55738e;
                font-size: 0.82rem; line-height: 1.6;">
        💙 이 서비스의 답변은 일반적인 건강 정보이며 전문적인 진단이나 진료를 대신하지 않습니다.
        심한 증상이나 응급 상황에서는 의료기관 또는 응급서비스에 도움을 요청하세요.
    </div>
    """,
    unsafe_allow_html=True,
)
