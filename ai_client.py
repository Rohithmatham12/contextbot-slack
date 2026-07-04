"""Groq LLM client — answers codebase questions with injected context."""
import os
from groq import Groq

_client: Groq | None = None


def _get() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def answer(question: str, code_context: str, thread_summary: str = "") -> str:
    """Answer a codebase question using ContextOS-packed context.

    thread_summary: Slack AI capability — pre-summarized thread context injected
    before reasoning so the LLM understands the team's discussion.
    """
    thread_block = (
        f"\n\nThread context from Slack (summarized):\n{thread_summary}\n"
        if thread_summary else ""
    )

    system = (
        "You are a senior engineer reviewing a codebase. "
        "Answer questions concisely using only the provided code context. "
        "Cite specific file names when relevant (e.g. `path/to/file.py`). "
        "If the answer is not in the context, say so — do not hallucinate."
    )
    user_msg = (
        f"Code context (selected by ContextOS MCP, secrets redacted):\n\n"
        f"{code_context[:28000]}"
        f"{thread_block}"
        f"\n\n---\nQuestion: {question}\n\n"
        "Answer concisely. Reference specific files and functions where relevant."
    )

    resp = _get().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=1200,
        temperature=0.2,
    )
    return resp.choices[0].message.content or "No answer generated."
