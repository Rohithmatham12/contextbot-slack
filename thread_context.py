"""Pull Slack thread history and summarize with Groq before reasoning."""
import logging
import os

from groq import Groq

log = logging.getLogger("contextbot.thread")
_client: Groq | None = None


def _groq() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def get_thread_summary(client, channel: str, thread_ts: str) -> str:
    """Fetch thread replies and return a Groq-generated summary."""
    try:
        resp = client.conversations_replies(channel=channel, ts=thread_ts, limit=20)
        messages = resp.get("messages", [])
        if len(messages) <= 1:
            return ""

        # Skip the first message (the question itself) and format the rest
        thread_text = "\n".join(
            f"{m.get('username', 'user')}: {m.get('text', '')}"
            for m in messages[1:]
            if m.get("text")
        )
        if not thread_text.strip():
            return ""

        resp = _groq().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": (
                    f"Summarize this Slack thread in 2-3 sentences. "
                    f"Focus on technical decisions and context.\n\n{thread_text[:3000]}"
                )
            }],
            max_tokens=200,
            temperature=0.1,
        )
        return resp.choices[0].message.content or ""

    except Exception as exc:
        log.debug("Thread summary failed: %s", exc)
        return ""
