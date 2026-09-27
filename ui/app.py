import os
import subprocess
import sys

import pandas as pd
import requests
import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

# Streamlit Cloud secrets (GROQ_API_KEY, LLM_MODEL, ...) -> env vars, which
# llm/llm_client.py reads. Must happen before pipeline is imported.
try:
    for key, value in st.secrets.items():
        if isinstance(value, str):
            os.environ[key] = value
except Exception:
    pass  # no secrets file when running locally

# If API_URL is set, go through the FastAPI server; otherwise run the
# pipeline in-process (single-service deploys like Streamlit Cloud).
API_URL = os.environ.get("API_URL")

# db/guardrails.db is gitignored, so build it on first run of a fresh deploy.
DB_PATH = os.path.join(ROOT, "db", "guardrails.db")
if not os.path.exists(DB_PATH):
    subprocess.run([sys.executable, os.path.join(ROOT, "db", "seed.py")], check=True)

st.set_page_config(page_title="SQL with Guardrails", layout="centered")
st.title("Text-to-SQL with Guardrails")

question = st.text_input("Ask a question about the customer/subscription database")
ask_clicked = st.button("Ask")

if ask_clicked and question.strip():
    with st.spinner("Thinking..."):
        result = None
        if API_URL:
            try:
                resp = requests.post(API_URL, json={"question": question}, timeout=60)
                resp.raise_for_status()
                result = resp.json()
            except requests.RequestException as e:
                st.error(f"Could not reach the API: {e}")
        else:
            try:
                from pipeline import answer_question
                result = answer_question(question)
            except OSError as e:
                st.error(f"LLM request failed (check GROQ_API_KEY, or that Ollama is running locally): {e}")

    if result is not None:
        if result["blocked"]:
            st.error(f"BLOCKED — {result['error']}")
        elif result["error"]:
            st.warning(f"Query failed — {result['error']}")
        else:
            answer = result["answer"]
            if isinstance(answer, list):
                st.caption(f"{len(answer)} row{'s' if len(answer) != 1 else ''}")
                st.dataframe(pd.DataFrame(answer))
            else:
                st.metric("Answer", answer)

            confidence = result["confidence"]
            st.progress(confidence, text=f"Confidence: {confidence:.2f}")

            if result["needs_review"]:
                st.warning("NEEDS REVIEW — low confidence, treat this answer as uncertain.")
            else:
                st.success("High confidence")

            with st.expander("Show generated SQL"):
                st.code(result["sql"], language="sql")
