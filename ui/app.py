import pandas as pd
import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000/ask"

st.set_page_config(page_title="SQL with Guardrails", layout="centered")
st.title("Text-to-SQL with Guardrails")

question = st.text_input("Ask a question about the customer/subscription database")
ask_clicked = st.button("Ask")

if ask_clicked and question.strip():
    with st.spinner("Thinking..."):
        try:
            resp = requests.post(API_URL, json={"question": question}, timeout=60)
            resp.raise_for_status()
            result = resp.json()
        except requests.RequestException as e:
            st.error(f"Could not reach the API: {e}")
            result = None

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
