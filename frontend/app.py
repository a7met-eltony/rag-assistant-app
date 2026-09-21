"""Helios Document Assistant: Streamlit chat interface for the RAG backend.

Run from the frontend/ folder:   python run.py        (or:  streamlit run app.py)
The backend address is read from API_BASE_URL (frontend/.env); nothing is hard-coded here.
"""
from typing import Dict, List

import streamlit as st

import api_client
from api_client import Answer, BackendError

MAX_QUESTION_CHARS = 1000          # same limit as the backend

# (button label, question). The last one is NOT in the documents: it shows the refusal behaviour.
EXAMPLES = [
    ("Annual leave", "How many days of annual leave do full-time employees get per year?"),
    ("Hotel limit", "What is the maximum nightly hotel cost in Tier-1 cities such as New York, London and Singapore?"),
    ("Robot error E-73", "What does error code E-73 mean on the HX-200?"),
    ("SEV1 response time", "How quickly must the on-call engineer respond to a SEV1 incident?"),
    ("Not in the documents", "What is the annual salary of the CEO of Helios Robotics?"),
]

st.set_page_config(page_title="Helios Document Assistant", page_icon="\U0001F4C4", layout="centered")


# ----------------------------------------------------------------------------- helpers
def md(text: str) -> str:
    """Escape '$' so prices like $260 are not rendered as LaTeX math by Streamlit's markdown."""
    return text.replace("$", "\\$")


@st.cache_data(ttl=5, show_spinner=False)
def backend_status(refresh_token: int = 0) -> Dict:
    """Backend health, cached for 5 seconds so the page stays snappy. Never raises.

    `refresh_token` is part of the cache key: the "Refresh status" button bumps it to force a fresh check.
    """
    try:
        return {"ok": True, "health": api_client.get_health()}
    except BackendError as exc:
        return {"ok": False, "message": exc.user_message}


def render_answer(answer: Answer) -> None:
    """Show the answer text and, below it, the sources it cites."""
    if answer.refused:
        st.info("The documents do not contain this information, so no answer was generated.", icon="\u2139\ufe0f")
    st.markdown(md(answer.text))
    if answer.sources:
        st.markdown("**Sources**")
        for source in answer.sources:
            tag = f"**[{source.tag}]** " if source.tag else ""
            st.markdown(f"- {tag}`{source.label}`")


def render_message(message: Dict) -> None:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(md(message["content"]))
        elif message.get("kind") == "error":
            st.error(message["content"], icon="\u26A0\uFE0F")
        else:
            render_answer(Answer(message["content"], message["sources"]))


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Helios Document Assistant")
        try:
            st.caption(f"Backend: {api_client.get_base_url()}")
        except BackendError as exc:
            st.error(exc.user_message)

        # --- backend status ---
        status = backend_status(st.session_state.refresh_token)
        if not status["ok"]:
            st.error(status["message"], icon="\U0001F534")
        else:
            health = status["health"]
            if health.status == "ok":
                st.success("Backend ready", icon="\U0001F7E2")
                st.caption(f"{health.num_chunks} passages indexed \u00b7 model: {health.ollama_model}")
            else:
                st.warning(f"Backend is running but not ready. {health.detail or ''}", icon="\U0001F7E0")
        if st.button("Refresh status", use_container_width=True):
            st.session_state.refresh_token += 1
            st.rerun()

        # --- example questions ---
        st.divider()
        st.subheader("Try an example")
        for index, (label, question) in enumerate(EXAMPLES):
            if st.button(label, key=f"example_{index}", use_container_width=True, help=question):
                st.session_state.pending_question = question

        st.divider()
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


# ----------------------------------------------------------------------------- page
st.session_state.setdefault("messages", [])
st.session_state.setdefault("refresh_token", 0)
messages: List[Dict] = st.session_state.messages

render_sidebar()

st.title("\U0001F4C4 Helios Document Assistant")
st.caption(
    "Ask a question about the company documents. Answers are generated only from the retrieved passages "
    "and cite their sources."
)

if not messages:
    st.info("Type a question below, or pick an example from the sidebar.", icon="\U0001F4AC")

for message in messages:
    render_message(message)

# The question comes from the chat box or from an example button in the sidebar.
question = st.chat_input("Ask a question about the documents...", max_chars=MAX_QUESTION_CHARS)
question = question or st.session_state.pop("pending_question", None)

if question:
    user_message = {"role": "user", "content": question}
    render_message(user_message)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching the documents and writing the answer..."):
                answer = api_client.ask(question)
        except BackendError as exc:
            assistant_message = {"role": "assistant", "kind": "error", "content": exc.user_message}
        else:
            assistant_message = {
                "role": "assistant", "kind": "answer", "content": answer.text, "sources": answer.sources,
            }
    # Re-render the assistant bubble from the stored message so live output and history look identical.
    messages.extend([user_message, assistant_message])
    st.rerun()
