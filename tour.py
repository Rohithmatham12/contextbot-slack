"""Tour Mode — Slack-AI-summarized onboarding walkthrough of any repo."""
import os
from groq import Groq

_client: Groq | None = None


def _groq() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def generate_tour(repo_name: str, context: str, file_list: str) -> str:
    """Generate a plain-English onboarding walkthrough using repo context."""
    prompt = f"""You are a senior engineer giving a new teammate their first walkthrough of the '{repo_name}' codebase.

Here is the repo's code context (secrets already redacted):

{context[:20000]}

Top relevant files:
{file_list[:2000]}

Write a concise onboarding tour in this exact format:

**What this repo does** (2-3 sentences, no jargon)

**Main components** (bullet list — directory or module name + one-line description each)

**Where to start reading** (the 2-3 most important files for a new contributor, and why)

**Key things to know** (2-3 non-obvious facts about the architecture, conventions, or gotchas)

Keep it under 400 words. Write for a bootcamp grad or open-source contributor, not an expert."""

    resp = _groq().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.3,
    )
    return resp.choices[0].message.content or "Tour generation failed."
