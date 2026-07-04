import json
from llama_cpp import Llama

# --- Local GGUF model (default) ----------------------------------------------

llm = Llama.from_pretrained(
    repo_id="Qwen/Qwen2.5-3B-Instruct-GGUF",
    filename="qwen2.5-3b-instruct-q4_k_m.gguf",
    n_ctx=2048,
    verbose=False,
)

def call_model(system: str, history: list[dict]) -> dict:
    response = llm.create_chat_completion(
        messages=[{"role": "system", "content": system}] + history,
        max_tokens=512,
        temperature=0.7,
    )
    raw = response["choices"][0]["message"]["content"].strip()
    return _parse_response(raw)


# --- Remote API (OpenAI) — uncomment to use instead -------------------------

# import os
# from openai import OpenAI
#
# client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
#
# def call_model(system: str, history: list[dict]) -> dict:
#     response = client.chat.completions.create(
#         model="gpt-4o-mini",
#         messages=[{"role": "system", "content": system}] + history,
#     )
#     raw = response.choices[0].message.content.strip()
#     return _parse_response(raw)

# -----------------------------------------------------------------------------


def _parse_response(raw: str) -> dict:
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        parsed = json.loads(raw)
        if isinstance(parsed.get("msg"), str) and not parsed.get("element"):
            inner = parsed["msg"].strip()
            if inner.startswith("{"):
                try:
                    inner_parsed = json.loads(inner)
                    if isinstance(inner_parsed, dict) and inner_parsed.get("element"):
                        return inner_parsed
                except json.JSONDecodeError:
                    pass
        return parsed
    except (json.JSONDecodeError, IndexError):
        return {"msg": raw}
