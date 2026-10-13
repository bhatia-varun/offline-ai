import os
import sys
from pathlib import Path

import requests
import streamlit as st

# Streamlit may put only this script's directory on sys.path, not the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_audio import live_audio

API_URL = os.getenv("DEMO_API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Offline AI Stack", page_icon="AI", layout="wide")
st.title("The Offline AI Stack")
st.caption("One API contract in front. Cloud or local behind it.")

try:
    health = requests.get(f"{API_URL}/health", timeout=4).json()
    st.sidebar.subheader("Service health")
    st.sidebar.json(health)
except requests.RequestException:
    st.sidebar.error("FastAPI is unavailable")

tab_chat, tab_rag, tab_agent, tab_audio = st.tabs(["Chat", "Private RAG", "Tools / Agent", "Speech to text"])

with tab_chat:
    prompt = st.text_area("Prompt", "Explain Kubernetes in simple terms.", key="chat_prompt")
    if st.button("Send", type="primary", key="chat_send"):
        with st.spinner("Calling logical model 'general' through LiteLLM..."):
            response = requests.post(f"{API_URL}/chat", json={"prompt": prompt}, timeout=240)
        if response.ok:
            st.write(response.json()["answer"])
            st.caption(f"Logical model: {response.json()['logical_model']}")
        else:
            st.error(response.text)

with tab_rag:
    if st.button("Ingest local documents"):
        with st.spinner("Embedding documents locally..."):
            response = requests.post(f"{API_URL}/rag/ingest", timeout=240)
        st.success(response.json()) if response.ok else st.error(response.text)
    question = st.text_area("Question", "What is our policy for working from another location?", key="rag_question")
    if st.button("Ask documents", type="primary"):
        with st.spinner("Retrieving locally and generating through LiteLLM..."):
            response = requests.post(f"{API_URL}/rag/query", json={"question": question}, timeout=240)
        if response.ok:
            payload = response.json()
            st.write(payload["answer"])
            st.caption("Sources: " + ", ".join(payload["sources"]))
        else:
            st.error(response.text)

with tab_audio:
    st.caption("English transcription only. Live mode updates after short chunks, not word-by-word or language translation.")
    st.subheader("Live (experimental)")
    st.caption("Start microphone capture or explicitly share a browser tab with audio. Stop after at most 2 minutes. No audio is saved.")
    live_audio(key="live_stt")
    st.subheader("Record, then transcribe")
    st.caption("Record up to 15 seconds of English, stop, then transcribe locally with Whisper tiny.en.")
    recording = st.audio_input("Record English speech", sample_rate=16000, key="stt_recording")
    with st.expander("Or upload a prepared PCM WAV"):
        uploaded_clip = st.file_uploader("16 kHz mono, 16-bit PCM WAV", type=["wav"], key="stt_clip")
    clip = recording if recording is not None else uploaded_clip
    if recording is not None and uploaded_clip is not None:
        st.caption("Using the microphone recording; remove it to transcribe the uploaded file.")
    if st.button("Transcribe locally", disabled=clip is None, key="stt_send") and clip is not None:
        if clip.size > 1_000_000:
            st.error("Recording exceeds 1 MB. Try a clip under 15 seconds.")
        else:
            try:
                with st.spinner("Transcribing locally..."):
                    response = requests.post(
                        f"{API_URL}/audio/transcribe", data=clip.getvalue(),
                        headers={"Content-Type": "audio/wav"}, timeout=100,
                    )
                if response.ok:
                    st.write(response.json()["text"])
                    st.caption(f"Duration: {response.json()['duration_seconds']} s")
                else:
                    st.error(response.json().get("detail", "Unable to transcribe this recording"))
            except requests.RequestException:
                st.error("Speech transcription service unavailable or timed out")

with tab_agent:
    agent_prompt = st.text_area("Agent request", "What is the weather in Delhi, and what is 17 * 23?", key="agent_prompt")
    if st.button("Run agent", type="primary"):
        with st.spinner("The model selects tools; the application executes them..."):
            response = requests.post(f"{API_URL}/agent", json={"prompt": agent_prompt}, timeout=300)
        if response.ok:
            payload = response.json()
            st.write(payload["answer"])
            st.subheader("Tool execution trace")
            st.json(payload["steps"])
        else:
            st.error(response.text)
