"""Slack Block Kit formatters."""

FOOTER = "⚡ ContextOS MCP · Secrets auto-redacted · github.com/Rohithmatham12/ContextOS"


def _hdr(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}

def _md(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text[:2900]}}

def _div() -> dict:
    return {"type": "divider"}

def _ctx(text: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def ask_result(question: str, answer: str, file_count: int) -> list[dict]:
    return [
        _hdr("🤖 ContextBot"),
        _md(f"*Question:* _{question}_"),
        _div(),
        _md(answer),
        _div(),
        _ctx(f"📂 {file_count} files · 🔒 secrets redacted · {FOOTER}"),
    ]


def files_result(task: str, result: str) -> list[dict]:
    return [
        _hdr("📁 Relevant Files"),
        _md(f"*Task:* _{task}_"),
        _div(),
        _md(f"```{result[:2700]}```"),
        _ctx(f"🔒 secrets redacted · ranked by relevance + import centrality · {FOOTER}"),
    ]


def scan_result(name: str, result: str) -> list[dict]:
    return [
        _hdr(f"✅ Repo Indexed: {name}"),
        _md(f"```{result[:2700]}```"),
        _ctx(FOOTER),
    ]


def churn_result(result: str) -> list[dict]:
    return [
        _hdr("🔥 Hottest Files (30 days)"),
        _md(f"```{result[:2700]}```"),
        _ctx(FOOTER),
    ]


def connect_result(name: str, url: str, scan: str, redactions: int) -> list[dict]:
    return [
        _hdr(f"🔗 Connected: {name}"),
        _md(
            f"*URL:* `{url}`\n\n"
            f"```{scan[:1800]}```"
        ),
        _div(),
        _ctx(
            f"🔒 {redactions} secrets redacted at ingestion · "
            f"Use `/ctx use {name}` to switch repos · {FOOTER}"
        ),
    ]


def repos_list(repos: list[dict], active_url: str) -> list[dict]:
    if not repos:
        return [_md("No repos connected. Use `/ctx connect <github-url>` to add one.")]

    lines = []
    for r in repos:
        active = "✅ " if r["github_url"] == active_url else "   "
        lines.append(
            f"{active}*{r['name']}* — `{r['github_url']}`\n"
            f"     {r['file_count']} files · {r['redaction_count']} secrets redacted"
        )
    return [
        _hdr("📦 Connected Repos"),
        _md("\n\n".join(lines)),
        _ctx(f"Use `/ctx use <name>` to switch active repo · {FOOTER}"),
    ]


def audit_result(logs: list[dict], total: int) -> list[dict]:
    if not logs:
        return [_md(f"🔒 *{total} secrets redacted total.* No recent entries.")]

    lines = [f"🔒 *{total} secrets redacted across all repos*\n"]
    for entry in logs[:15]:
        lines.append(f"• `{entry['pattern']}` in `{entry['file_path']}` ({entry['repo_name']})")

    return [
        _hdr("🔒 Secret Redaction Audit"),
        _md("\n".join(lines)),
        _ctx(FOOTER),
    ]


def home_view(repos: list[dict], active: dict | None, total_redactions: int) -> dict:
    blocks: list[dict] = [
        _hdr("ContextBot — Codebase Intelligence"),
        _md(
            "Ask anything about any GitHub repo directly in Slack. "
            "Secrets are stripped at ingestion — nothing sensitive ever reaches an LLM."
        ),
        _div(),
    ]

    if active:
        blocks += [
            _md(
                f"*Active repo:* `{active['name']}`  "
                f"({active['file_count']} files · {active['redaction_count']} secrets redacted)"
            ),
        ]
    else:
        blocks += [_md("*No repo connected.* Use `/ctx connect <github-url>` to start.")]

    blocks += [
        _div(),
        _hdr("Commands"),
        _md(
            "• `/ctx connect <github-url>` — index any repo\n"
            "• `/ctx ask <question>` — AI answer from real code context\n"
            "• `/ctx files <task>` — relevant files ranked by importance\n"
            "• `/ctx use <repo-name>` — switch active repo\n"
            "• `/ctx repos` — list connected repos\n"
            "• `/ctx audit` — secret redaction log\n"
            "• `/ctx churn` — most changed files (30d)\n\n"
            "Or just DM me or @mention me in any channel."
        ),
        _div(),
        _ctx(f"🔒 {total_redactions} secrets redacted total · {FOOTER}"),
    ]

    return {"type": "home", "blocks": blocks}


def error_block(msg: str) -> list[dict]:
    return [_md(f"❌ *Error:* {msg[:500]}")]


def help_blocks() -> list[dict]:
    return [
        _hdr("ContextBot — Codebase Intelligence"),
        _md(
            "• `/ctx connect <github-url>` — index any repo, secrets stripped at ingestion\n"
            "• `/ctx ask <question>` — AI answer backed by real code + Slack history\n"
            "• `/ctx files <task>` — ranked relevant files\n"
            "• `/ctx use <repo-name>` — switch active repo\n"
            "• `/ctx repos` — list connected repos\n"
            "• `/ctx audit` — secret redaction audit log\n"
            "• `/ctx churn` — hottest files (30d)\n\n"
            "Or just @mention me or DM me with a question."
        ),
        _ctx(FOOTER),
    ]
