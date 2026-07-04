"""Slack Block Kit formatters for ContextBot responses."""

FOOTER_TEXT = "⚡ ContextOS MCP · Secrets auto-redacted · github.com/Rohithmatam12/ContextOS"


def _header(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text[:2900]}}


def _divider() -> dict:
    return {"type": "divider"}


def _footer() -> dict:
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": FOOTER_TEXT}],
    }


def ask_result(question: str, answer: str, context: str) -> list[dict]:
    file_count = context.count("\n### ")
    return [
        _header("🤖 ContextBot"),
        _section(f"*Question:* _{question}_"),
        _divider(),
        _section(answer),
        _divider(),
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"📂 {file_count} files analyzed · 🔒 secrets redacted · {FOOTER_TEXT}",
                }
            ],
        },
    ]


def files_result(task: str, result: str) -> list[dict]:
    return [
        _header("📁 Relevant Files"),
        _section(f"*Task:* _{task}_"),
        _divider(),
        _section(f"```{result[:2700]}```"),
        _footer(),
    ]


def scan_result(result: str) -> list[dict]:
    return [
        _header("✅ Repository Indexed"),
        _section(f"```{result[:2700]}```"),
        _footer(),
    ]


def churn_result(result: str) -> list[dict]:
    return [
        _header("🔥 Hottest Files (30 days)"),
        _section(f"```{result[:2700]}```"),
        _footer(),
    ]


def help_blocks() -> list[dict]:
    return [
        _header("ContextOS — Codebase Intelligence"),
        _section(
            "Ask anything about the connected repo. Commands:\n\n"
            "• `/ctx ask <question>` — AI answer backed by real code context\n"
            "• `/ctx files <task>` — ranked list of relevant files\n"
            "• `/ctx scan` — index or refresh the repo\n"
            "• `/ctx churn` — most actively changed files (30d)\n\n"
            "Or just `@contextbot <question>` in any channel."
        ),
        _footer(),
    ]


def error_block(msg: str) -> list[dict]:
    return [_section(f"❌ *Error:* {msg}")]
