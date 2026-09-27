"""Single entry point for every LLM call in the project.

Uses Groq's hosted API when GROQ_API_KEY is set (deployed app), otherwise a
local Ollama server. Both are asked for JSON output; callers get the raw text.
"""
import json
import os
import urllib.request

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")


# Read at call time, not import time: Streamlit hot-reloads code without
# restarting the process, so a secret added later must still be picked up.
def _groq_key():
    return os.environ.get("GROQ_API_KEY")


def default_model():
    return os.environ.get("LLM_MODEL") or (
        "llama-3.3-70b-versatile" if _groq_key() else "qwen2.5-coder:3b"
    )


MODEL = default_model()


def _post_json(url, payload, headers):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        # Groq sits behind Cloudflare, which rejects urllib's default User-Agent.
        headers={"Content-Type": "application/json", "User-Agent": "sql-with-guardrails", **headers},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def call_llm(system, user, model=None):
    model = model or default_model()
    groq_key = _groq_key()
    if groq_key:
        body = _post_json(
            GROQ_URL,
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
            {"Authorization": f"Bearer {groq_key}"},
        )
        return body["choices"][0]["message"]["content"]

    body = _post_json(
        OLLAMA_URL,
        {"model": model, "prompt": user, "system": system, "format": "json", "stream": False},
        {},
    )
    return body.get("response", "")
