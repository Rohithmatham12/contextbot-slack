"""Groq LLM client for answering questions with injected codebase context."""
import os
from groq import Groq

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def answer(question: str, context: str) -> str:
    """Answer a codebase question using ContextOS-packed context."""
    system = (
        "You are a senior engineer reviewing a codebase. "
        "Answer questions concisely using only the provided code context. "
        "Cite specific files when relevant. "
        "If the answer is not in the context, say so — do not hallucinate."
    )
    user_msg = f"""Code context (selected by ContextOS, secrets redacted):

{context}

---
Question: {question}

Answer concisely. Reference specific files/functions where relevant."""

    resp = _get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg[:30000]},  # Groq token safety
        ],
        max_tokens=1200,
        temperature=0.2,
    )
    return resp.choices[0].message.content or "No answer generated."
